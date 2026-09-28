from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from . import models, database, auth
from .routers import admin, viewer, auth as auth_router, contact
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Aula PDF Reader")

# Session Middleware (Secret key should be env var in prod)
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "fallback-secret-for-dev-only"))

# Mount Static
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include Routers
app.include_router(auth_router.router)
app.include_router(admin.router)
app.include_router(viewer.router)
app.include_router(contact.router)

from sqlalchemy import text
from fastapi import Request
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

def run_db_migrations():
    # 1. Create tables if not exist
    try:
        models.Base.metadata.create_all(bind=database.engine)
    except Exception as e:
        print(f"Notice on create_all: {e}")

    # 2. Add missing columns directly with per-statement error handling
    db = database.SessionLocal()
    try:
        migration_statements = [
            "ALTER TABLE users ADD COLUMN full_name VARCHAR",
            "ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'parent'",
            "ALTER TABLE users ADD COLUMN has_active_license BOOLEAN DEFAULT FALSE",
            "ALTER TABLE licenses ADD COLUMN expires_at TIMESTAMP",
            "ALTER TABLE licenses ADD COLUMN allow_download BOOLEAN DEFAULT FALSE",
        ]
        for stmt in migration_statements:
            try:
                db.execute(text(stmt))
                db.commit()
            except Exception:
                db.rollback()

        # 3. Sync Admin User
        user = db.query(models.User).filter(models.User.username == "admin").first()
        admin_pass = os.getenv("ADMIN_PASSWORD")
        if not admin_pass:
            admin_pass = "admin123"
            
        if not user:
            print("Creating initial admin user...")
            hashed = auth.get_password_hash(admin_pass)
            new_user = models.User(username="admin", full_name="Administrador", hashed_password=hashed, is_admin=True, role="teacher")
            db.add(new_user)
            db.commit()
        elif admin_pass != "admin123":
            user.hashed_password = auth.get_password_hash(admin_pass)
            db.commit()
            
    except Exception as e:
        print(f"Error during startup migration/initialization: {e}")
        db.rollback()
    finally:
        db.close()

@app.on_event("startup")
def startup_db_setup():
    run_db_migrations()

from fastapi.responses import PlainTextResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    try:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": f"Error del sistema: {str(exc)}"
        }, status_code=500)
    except Exception:
        return PlainTextResponse(f"Error del servidor: {str(exc)}", status_code=500)

