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

from sqlalchemy import text, inspect

@app.on_event("startup")
def startup_db_setup():
    try:
        models.Base.metadata.create_all(bind=database.engine)
    except Exception as e:
        print(f"Notice on create_all: {e}")

    db = database.SessionLocal()
    try:
        inspector = inspect(database.engine)
        table_names = inspector.get_table_names()
        
        # 1. Automatic Migration for User Model
        if 'users' in table_names:
            columns = [c['name'] for c in inspector.get_columns('users')]
            if 'full_name' not in columns:
                try:
                    db.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR"))
                    db.commit()
                except Exception:
                    db.rollback()
            if 'role' not in columns:
                try:
                    db.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'parent'"))
                    db.commit()
                except Exception:
                    db.rollback()
            if 'has_active_license' not in columns:
                try:
                    db.execute(text("ALTER TABLE users ADD COLUMN has_active_license BOOLEAN DEFAULT FALSE"))
                    db.commit()
                except Exception:
                    db.rollback()
        
        # 1b. Automatic Migration for License Model
        if 'licenses' in table_names:
            columns_licenses = [c['name'] for c in inspector.get_columns('licenses')]
            if 'expires_at' not in columns_licenses:
                try:
                    db.execute(text("ALTER TABLE licenses ADD COLUMN expires_at TIMESTAMP"))
                    db.commit()
                except Exception:
                    db.rollback()
            if 'allow_download' not in columns_licenses:
                try:
                    db.execute(text("ALTER TABLE licenses ADD COLUMN allow_download BOOLEAN DEFAULT FALSE"))
                    db.commit()
                except Exception:
                    db.rollback()

        # 2. Sync Admin User
        user = db.query(models.User).filter(models.User.username == "admin").first()
        admin_pass = os.getenv("ADMIN_PASSWORD")
        
        if not user:
            if not admin_pass:
                admin_pass = "admin123"
            print("Creating initial admin user...")
            hashed = auth.get_password_hash(admin_pass)
            new_user = models.User(username="admin", full_name="Administrador", hashed_password=hashed, is_admin=True, role="teacher")
            db.add(new_user)
            db.commit()
        elif admin_pass:
            # Update password if env var changed
            user.hashed_password = auth.get_password_hash(admin_pass)
            db.commit()
            
    except Exception as e:
        print(f"Error during startup migration/initialization: {e}")
        db.rollback()
    finally:
        db.close()
