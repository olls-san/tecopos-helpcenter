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


# Crear tabla si no existe
Base.metadata.create_all(bind=engine)

# =========================
#  MODELOS Pydantic
# =========================

class ErrorBase(BaseModel):
    type: str = "error"   # NUEVO
    title: str
    short_description: str
    category: str
    is_common: bool
    client_message: str
    causes: List[str] = []
    quick_steps: List[str] = []
    internal_steps: List[str] = []
    images: List[str] = []
    video_url: Optional[str] = None


class Error(ErrorBase):
    id: int


# =========================
#  ORM ↔ Pydantic
# =========================

def orm_to_pydantic(e: ErrorORM) -> Error:
    return Error(
        id=e.id,
        type=e.type,
        title=e.title,
        short_description=e.short_description,
        category=e.category,
        is_common=e.is_common,
        client_message=e.client_message,
        causes=[c for c in (e.causes_text or "").split("\n") if c],
        quick_steps=[q for q in (e.quick_steps_text or "").split("\n") if q],
        internal_steps=[i for i in (e.internal_steps_text or "").split("\n") if i],
        images=[img for img in (e.images_text or "").split("\n") if img],
        video_url=e.video_url,
    )


def pydantic_to_orm_data(data: ErrorBase) -> dict:
    return dict(
        type=data.type,
        title=data.title,
        short_description=data.short_description,
        category=data.category,
        is_common=data.is_common,
        client_message=data.client_message,
        causes_text="\n".join(data.causes),
        quick_steps_text="\n".join(data.quick_steps),
        internal_steps_text="\n".join(data.internal_steps),
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
            short_description="El usuario no tiene acceso al módulo seleccionado.",
            category="roles-permisos",
            is_common=True,
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
            short_description="Suele ocurrir por caché acumulada o sesión expirada.",
            category="errores-comunes",
            is_common=True,
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
    all_errors = get_all_errors()
    categories = sorted(set(e.category for e in all_errors))

    if category:
        filtered = [e for e in all_errors if e.category == category]
    else:
        filtered = [e for e in all_errors if e.is_common]

    if q:
        q_lower = q.lower()
        filtered = [
            e for e in filtered
            if q_lower in e.title.lower()
            or q_lower in e.short_description.lower()
            or q_lower in e.client_message.lower()
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
    all_errors = get_all_errors()
    filtered = [a for a in all_errors if a.type == doc_type]

    return templates.TemplateResponse(
        "docs_type.html",
        {
            "request": request,
            "items": filtered,
            "doc_type": doc_type
        }
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
    type: str = Form("error"),
    title: str = Form(...),
    short_description: str = Form(...),
    category: str = Form(...),
    is_common: bool = Form(False),
    client_message: str = Form(...),
    causes: str = Form(""),
    quick_steps: str = Form(""),
    internal_steps: str = Form(""),
    image_files: List[UploadFile] = File([]),
    video_file: Optional[UploadFile] = File(None),
):
    image_urls: List[str] = []

    for img in image_files:
        if img and img.filename:
            ext = img.filename.split(".")[-1]
            filename = f"{uuid4().hex}.{ext}"
            dest = IMAGE_DIR / filename
            with dest.open("wb") as f:
                f.write(await img.read())
            image_urls.append(f"/uploads/images/{filename}")

    video_url: Optional[str] = None
    if video_file and video_file.filename:
        ext = video_file.filename.split(".")[-1]
        filename = f"{uuid4().hex}.{ext}"
        dest = VIDEO_DIR / filename
        with dest.open("wb") as f:
            f.write(await video_file.read())
        video_url = f"/uploads/videos/{filename}"

    data = ErrorBase(
        type=type,
        title=title,
        short_description=short_description,
        category=category,
        is_common=is_common,
        client_message=client_message,
        causes=[c.strip() for c in causes.split("\n") if c.strip()],
        quick_steps=[q.strip() for q in quick_steps.split("\n") if q.strip()],
        internal_steps=[i.strip() for i in internal_steps.split("\n") if i.strip()],
        images=image_urls,
        video_url=video_url,
    )

    create_error_db(data)

    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/delete/{error_id}", response_class=HTMLResponse)
async def admin_delete_error(error_id: int):
    delete_error_by_id(error_id)
    return RedirectResponse(url="/admin", status_code=303)

