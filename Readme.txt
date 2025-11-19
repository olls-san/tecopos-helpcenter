# Tecopos Help Center (MVP)

Mini centro de ayuda para Tecopos, pensado como un **FAQ de errores de front** (de cara al cliente) con:

- Página principal estilo Slack:
  - Buscador de errores
  - Categorías clicables
  - Errores destacados
  - Vista previa de chatbot
- Listado completo de errores con filtros
- Vista de detalle con:
  - Mensaje que ve el cliente
  - Causas posibles
  - Pasos rápidos para el cliente
  - Pasos internos para soporte
  - Capturas de pantalla
  - Video explicativo
- Panel de administración:
  - Crear errores
  - Subir imágenes y videos
  - Eliminar errores

Los errores se guardan en **PostgreSQL** usando **SQLAlchemy**, por lo que los datos permanecen aunque se reinicie el servidor.

---

## 1. Requisitos

- **Python 3.10+**
- **Docker** (Docker Desktop en Windows/Mac)
- **Git**
- **VS Code** (o cualquier editor)
- Cuenta en **GitHub** (para subir el repositorio)

---

## 2. Estructura del proyecto

Ejemplo de estructura mínima:

```text
tecopos-helpcenter/
├─ main.py
├─ requirements.txt
├─ templates/
│  ├─ base.html
│  ├─ index.html
│  ├─ errors.html
│  ├─ error_detail.html
│  └─ admin.html
├─ static/
│  └─ style.css
└─ uploads/
   ├─ images/
   └─ videos/
