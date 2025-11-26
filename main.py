from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional
from uuid import uuid4
from pathlib import Path
import os
from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text
# Agregamos inspect y text para poder comprobar y alterar las columnas en tiempo de ejecución
from sqlalchemy import inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

app = FastAPI()

# =========================
#   RUTAS DE ARCHIVOS
# =========================

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
IMAGE_DIR = UPLOAD_DIR / "images"
VIDEO_DIR = UPLOAD_DIR / "videos"

IMAGE_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

# =========================
#   CONFIGURACIÓN POSTGRES
# =========================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://tecopos_user:postgres@localhost:5432/tecopos_helpcenter"
)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# =========================
#   ORM: Tabla "errors"
# =========================
class ErrorORM(Base):
    __tablename__ = "errors"

    id = Column(Integer, primary_key=True, index=True)

    # NUEVO CAMPO → Tipo de artículo
    type = Column(String(50), nullable=False, default="error")

    title = Column(String(255), nullable=False)
    short_description = Column(String(255), nullable=False)
    category = Column(String(100), nullable=False)
    is_common = Column(Boolean, default=False)
    client_message = Column(String(255), nullable=False)

    causes_text = Column(Text, default="")
    quick_steps_text = Column(Text, default="")
    internal_steps_text = Column(Text, default="")

    images_text = Column(Text, default="")
    video_url = Column(String(500), nullable=True)

    # Nuevos campos para soportar diferentes tipos de artículo
    # "primary_category" indica la categoría principal (errores, guías, buenas-prácticas, faq, novedades) que
    # determina en qué pestaña de la navegación se mostrará el elemento. Se inicializa por defecto en "errores".
    primary_category = Column(String(50), nullable=False, default="errores")
    # "description" es un cuerpo de texto largo utilizado por guías, comportamientos, novedades y cualquier
    # otro tipo que requiera un campo de descripción más extenso que el resumen corto.
    description = Column(Text, nullable=True)
    # "steps_text" almacena una lista de pasos (uno por línea) para las guías. Si el tipo no es guía, puede estar vacío.
    steps_text = Column(Text, nullable=True)
    # "answer_text" almacena la respuesta para las preguntas frecuentes (FAQ). Para otros tipos queda vacío.
    answer_text = Column(Text, nullable=True)
    # "tags_text" almacena etiquetas separadas por salto de línea o coma para las preguntas frecuentes. Opcional.
    tags_text = Column(Text, nullable=True)


# Crear tabla si no existe
Base.metadata.create_all(bind=engine)

# Aseguramos que todas las columnas nuevas existan. SQLAlchemy no crea columnas nuevas sobre tablas existentes
# al llamar a create_all, por lo que realizamos modificaciones conditionales si la tabla ya existía.
def ensure_extra_columns():
    """Verifica si faltan columnas en la tabla 'errors' y las añade en caso necesario."""
    inspector = inspect(engine)
    try:
        cols = [col['name'] for col in inspector.get_columns("errors")]
    except Exception:
        # Si por alguna razón no podemos inspeccionar, salimos silenciosamente
        return
    ddl_statements = []
    if 'primary_category' not in cols:
        ddl_statements.append("ALTER TABLE errors ADD COLUMN primary_category VARCHAR(50) DEFAULT 'errores';")
    if 'description' not in cols:
        ddl_statements.append("ALTER TABLE errors ADD COLUMN description TEXT;")
    if 'steps_text' not in cols:
        ddl_statements.append("ALTER TABLE errors ADD COLUMN steps_text TEXT;")
    if 'answer_text' not in cols:
        ddl_statements.append("ALTER TABLE errors ADD COLUMN answer_text TEXT;")
    if 'tags_text' not in cols:
        ddl_statements.append("ALTER TABLE errors ADD COLUMN tags_text TEXT;")
    if ddl_statements:
        with engine.connect() as conn:
            for stmt in ddl_statements:
                conn.execute(text(stmt))
                conn.commit()

# Ejecutamos la verificación de columnas adicionales
ensure_extra_columns()

# =========================
#  MODELOS Pydantic
# =========================

class ErrorBase(BaseModel):
    """
    Modelo Pydantic base para los artículos del centro de ayuda. Se utiliza la palabra
    "ErrorBase" por compatibilidad con la versión anterior, aunque realmente soporta
    múltiples tipos de artículos (error, guia, comportamiento, faq, novedad).
    
    Campos comunes:
      - type: tipo de documento (error, guia, comportamiento, faq, novedad)
      - title: título del artículo
      - primary_category: categoría principal que determina la pestaña de navegación
      - category: categoría visible (ej. módulo o etiqueta) que aparece en la tarjeta
      - is_common: indica si debe aparecer destacado en la página de inicio (solo para errores)
      - short_description: descripción breve o resumen. Obligatoria para errores pero opcional para otros tipos
      - description: descripción larga utilizada en guías, comportamientos y novedades
      - client_message: mensaje o respuesta visible para el cliente. Usado en errores y FAQs
      - causes: lista de causas (solo para errores)
      - quick_steps: lista de pasos rápidos (solo para errores)
      - internal_steps: lista de pasos o notas internas (solo para errores)
      - steps: lista de pasos detallados para guías
      - answer: respuesta para FAQs
      - tags: lista de etiquetas para FAQs
      - images: lista de URLs de imágenes
      - video_url: URL de un video relacionado
    """
    type: str = "error"   # Tipo de artículo
    title: str
    primary_category: str = "errores"
    category: str = ""
    is_common: bool = False
    short_description: Optional[str] = None
    description: Optional[str] = None
    client_message: Optional[str] = None
    causes: List[str] = []
    quick_steps: List[str] = []
    internal_steps: List[str] = []
    steps: List[str] = []
    answer: Optional[str] = None
    tags: List[str] = []
    images: List[str] = []
    video_url: Optional[str] = None


class Error(ErrorBase):
    """Modelo Pydantic que incluye el identificador del artículo."""
    id: int


# =========================
#  ORM ↔ Pydantic
# =========================

def orm_to_pydantic(e: ErrorORM) -> Error:
    """Convierte una fila ORM a un modelo Pydantic, adaptando campos opcionales según el tipo."""
    return Error(
        id=e.id,
        type=e.type,
        title=e.title,
        primary_category=e.primary_category or "errores",
        category=e.category or "",
        is_common=e.is_common,
        short_description=e.short_description,
        description=e.description,
        client_message=e.client_message,
        causes=[c for c in (e.causes_text or "").split("\n") if c],
        quick_steps=[q for q in (e.quick_steps_text or "").split("\n") if q],
        internal_steps=[i for i in (e.internal_steps_text or "").split("\n") if i],
        steps=[s for s in (e.steps_text or "").split("\n") if s],
        answer=e.answer_text,
        tags=[t for t in (e.tags_text or "").split("\n") if t],
        images=[img for img in (e.images_text or "").split("\n") if img],
        video_url=e.video_url,
    )


def pydantic_to_orm_data(data: ErrorBase) -> dict:
    """
    Convierte un modelo Pydantic en un diccionario listo para inicializar un objeto ORM.
    Los campos opcionales se convierten en cadenas unidas por saltos de línea para
    almacenarse en la base de datos.
    """
    return dict(
        type=data.type,
        title=data.title,
        primary_category=data.primary_category,
        category=data.category or "",
        short_description=data.short_description or "",
        description=data.description,
        is_common=data.is_common,
        client_message=data.client_message or "",
        causes_text="\n".join(data.causes),
        quick_steps_text="\n".join(data.quick_steps),
        internal_steps_text="\n".join(data.internal_steps),
        steps_text="\n".join(data.steps),
        answer_text=data.answer or None,
        tags_text="\n".join(data.tags),
        images_text="\n".join(data.images),
        video_url=data.video_url,
    )


# =========================
#  ACCESO A BD
# =========================

def get_all_errors() -> List[Error]:
    db = SessionLocal()
    try:
        rows = db.query(ErrorORM).order_by(ErrorORM.id.desc()).all()
        return [orm_to_pydantic(r) for r in rows]
    finally:
        db.close()


def get_error_by_id(error_id: int) -> Optional[Error]:
    db = SessionLocal()
    try:
        row = db.query(ErrorORM).filter(ErrorORM.id == error_id).first()
        if not row:
            return None
        return orm_to_pydantic(row)
    finally:
        db.close()


def create_error_db(data: ErrorBase) -> Error:
    db = SessionLocal()
    try:
        orm_data = pydantic_to_orm_data(data)
        obj = ErrorORM(**orm_data)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return orm_to_pydantic(obj)
    finally:
        db.close()


def delete_error_by_id(error_id: int) -> None:
    db = SessionLocal()
    try:
        row = db.query(ErrorORM).filter(ErrorORM.id == error_id).first()
        if row:
            db.delete(row)
            db.commit()
    finally:
        db.close()


# =========================
#   SEMILLA INICIAL
# =========================

def seed_initial_data():
    db = SessionLocal()
    try:
        count = db.query(ErrorORM).count()
        if count > 0:
            return

        e1 = ErrorBase(
            type="error",
            title="No tiene permisos para realizar esta acción",
            primary_category="errores",
            category="roles-permisos",
            is_common=True,
            short_description="El usuario no tiene acceso al módulo seleccionado.",
            client_message="No tiene permisos para realizar esta acción",
            causes=[
                "El usuario no tiene un rol asignado.",
                "El rol no permite acceder a ese módulo.",
                "Está en el negocio incorrecto.",
            ],
            quick_steps=[
                "Cerrar sesión y volver a entrar.",
                "Verificar negocio seleccionado.",
                "Solicitar al administrador revisar el rol.",
            ],
            internal_steps=[
                "Revisar permisos del rol.",
                "Confirmar negocio asignado.",
            ],
            images=[],
            video_url=None,
        )
        create_error_db(e1)

        e2 = ErrorBase(
            type="error",
            title="Pantalla en blanco al iniciar sesión",
            primary_category="errores",
            category="errores-comunes",
            is_common=True,
            short_description="Suele ocurrir por caché acumulada o sesión expirada.",
            client_message="La pantalla queda en blanco después de iniciar sesión.",
            causes=[
                "Caché del navegador desactualizada.",
                "Sesión de usuario vencida.",
            ],
            quick_steps=[
                "Refrescar con Ctrl + F5.",
                "Cerrar sesión y volver a entrar.",
                "Probar en otro navegador.",
            ],
            internal_steps=[],
            images=[],
            video_url=None,
        )
        create_error_db(e2)

    finally:
        db.close()


seed_initial_data()


# =========================
#   STATIC & TEMPLATES
# =========================

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# =========================
#       RUTAS HTML
# =========================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, q: str = "", category: str = ""):
    """
    Página de inicio del centro de ayuda.

    - Muestra únicamente los artículos marcados como comunes (is_common) por defecto.
    - Permite filtrar por una categoría visible (`category`) y por búsqueda de texto.
    - La lista de categorías que se muestra corresponde a las `primary_category` disponibles en la base.
    """
    all_items = get_all_errors()
    # Usamos la categoría visible (campo `category`) para poblar la sección de categorías visibles
    categories = sorted(set(item.category for item in all_items))

    # Si se selecciona una categoría visible (etiqueta), filtramos por la propiedad `category`
    if category:
        filtered = [item for item in all_items if item.category == category]
    else:
        # Por defecto, mostramos los items frecuentes (is_common)
        filtered = [item for item in all_items if item.is_common]

    # Filtro por búsqueda de texto en título, descripción corta o mensaje al cliente
    if q:
        q_lower = q.lower()
        filtered = [
            item for item in filtered
            if q_lower in item.title.lower()
            or (item.short_description or "").lower().find(q_lower) != -1
            or (item.client_message or "").lower().find(q_lower) != -1
        ]

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "errors": filtered,
            "categories": categories,
            "q": q,
            "selected_category": category,
        },
    )


@app.get("/errors", response_class=HTMLResponse)
async def errors_list(request: Request, q: str = "", category: str = ""):
    all_errors = get_all_errors()
    categories = sorted(set(e.category for e in all_errors))

    filtered = all_errors
    if category:
        filtered = [e for e in filtered if e.category == category]

    if q:
        q_lower = q.lower()
        filtered = [
            e for e in filtered
            if q_lower in e.title.lower()
            or q_lower in e.short_description.lower()
            or q_lower in e.client_message.lower()
        ]

    return templates.TemplateResponse(
        "errors.html",
        {
            "request": request,
            "errors": filtered,
            "categories": categories,
            "q": q,
            "selected_category": category,
        },
    )


@app.get("/docs/{doc_type}", response_class=HTMLResponse)
async def docs_by_type(request: Request, doc_type: str):
    """
    Devuelve los artículos filtrados por tipo de documento y por su categoría principal.

    Se utiliza una correspondencia entre el parámetro de ruta (doc_type) y la
    `primary_category` almacenada en la base de datos. Esto permite que un
    artículo solo aparezca en la pestaña correspondiente cuando ambas
    condiciones se cumplen (por ejemplo, guías con categoría principal "guias").
    """
    all_items = get_all_errors()
    # Mapeo entre doc_type y primary_category
    type_to_category = {
        "error": "errores",
        "guia": "guias",
        "comportamiento": "buenas-practicas",
        "faq": "faq",
        "novedad": "novedades",
    }
    expected_cat = type_to_category.get(doc_type, doc_type)
    # Filtra artículos por tipo y categoría principal cuando aplique
    filtered = [item for item in all_items if item.type == doc_type and (item.primary_category == expected_cat)]

    return templates.TemplateResponse(
        "docs_type.html",
        {
            "request": request,
            "items": filtered,
            "doc_type": doc_type,
        },
    )


@app.get("/categories", response_class=HTMLResponse)
async def categories_page(request: Request):
    all_errors = get_all_errors()

    category_counts = {}
    for e in all_errors:
        category_counts[e.category] = category_counts.get(e.category, 0) + 1

    categories = sorted(
        [{"name": name, "count": count} for name, count in category_counts.items()],
        key=lambda x: x["name"]
    )

    return templates.TemplateResponse(
        "categories.html",
        {
            "request": request,
            "categories": categories,
        },
    )


@app.get("/errors/{error_id}", response_class=HTMLResponse)
async def error_detail(request: Request, error_id: int):
    err = get_error_by_id(error_id)
    if not err:
        return HTMLResponse("Error no encontrado", status_code=404)
    return templates.TemplateResponse(
        "error_detail.html",
        {"request": request, "error": err},
    )


# =========================
#        ADMIN
# =========================

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request):
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "errors": get_all_errors()},
    )


@app.post("/admin/create", response_class=HTMLResponse)
async def admin_create_error(
    request: Request,
    # Tipo de artículo (error, guia, comportamiento, faq, novedad)
    type: str = Form("error"),
    # Categoría principal: errores, guias, buenas-practicas, faq, novedades
    primary_category: str = Form("errores"),
    # Título del artículo
    title: str = Form(...),
    # Categoría visible o etiqueta del artículo (por ejemplo, módulo o área funcional)
    category: str = Form(""),
    # Indica si el artículo debe considerarse común o destacado (solo para errores)
    is_common: bool = Form(False),
    # Descripción corta u opcional según el tipo
    short_description: str = Form(""),
    # Descripción larga (para guías, comportamientos, novedades)
    description: str = Form(""),
    # Mensaje que ve el cliente (errores) o respuesta (FAQs)
    client_message: str = Form(""),
    # Lista de causas (solo errores)
    causes: str = Form(""),
    # Pasos rápidos para el usuario (solo errores)
    quick_steps: str = Form(""),
    # Pasos internos o notas (solo errores)
    internal_steps: str = Form(""),
    # Pasos detallados para guías (una por línea)
    steps: str = Form(""),
    # Respuesta para FAQs
    answer: str = Form(""),
    # Etiquetas para FAQs (una por línea)
    tags: str = Form(""),
    # Archivos de imagen
    image_files: List[UploadFile] = File([]),
    # Archivo de video
    video_file: Optional[UploadFile] = File(None),
):
    """
    Procesa el formulario de creación de artículos. Dependiendo del tipo seleccionado,
    se aprovecharán distintos campos. Los campos irrelevantes para un tipo se ignoran.
    """
    image_urls: List[str] = []

    # Procesamiento de imágenes
    for img in image_files:
        if img and img.filename:
            ext = img.filename.split(".")[-1]
            filename = f"{uuid4().hex}.{ext}"
            dest = IMAGE_DIR / filename
            with dest.open("wb") as f:
                f.write(await img.read())
            image_urls.append(f"/uploads/images/{filename}")

    # Procesamiento de video
    video_url: Optional[str] = None
    if video_file and video_file.filename:
        ext = video_file.filename.split(".")[-1]
        filename = f"{uuid4().hex}.{ext}"
        dest = VIDEO_DIR / filename
        with dest.open("wb") as f:
            f.write(await video_file.read())
        video_url = f"/uploads/videos/{filename}"

    # Convertimos cadenas separadas por líneas en listas
    causes_list = [c.strip() for c in causes.split("\n") if c.strip()]
    quick_steps_list = [q.strip() for q in quick_steps.split("\n") if q.strip()]
    internal_steps_list = [i.strip() for i in internal_steps.split("\n") if i.strip()]
    steps_list = [s.strip() for s in steps.split("\n") if s.strip()]
    tags_list = [t.strip() for t in tags.split("\n") if t.strip()]

    # Inicializamos el modelo Pydantic con los campos correspondientes
    data = ErrorBase(
        type=type,
        title=title,
        primary_category=primary_category,
        category=category,
        is_common=is_common,
        short_description=short_description or None,
        description=description or None,
        client_message=client_message or None,
        causes=causes_list,
        quick_steps=quick_steps_list,
        internal_steps=internal_steps_list,
        steps=steps_list,
        answer=answer or None,
        tags=tags_list,
        images=image_urls,
        video_url=video_url,
    )

    create_error_db(data)

    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/delete/{error_id}", response_class=HTMLResponse)
async def admin_delete_error(error_id: int):
    delete_error_by_id(error_id)
    return RedirectResponse(url="/admin", status_code=303)

