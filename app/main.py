from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from . import models, database, auth
from .routers import admin, viewer, auth as auth_router, contact
import os
from dotenv import load_dotenv

load_dotenv()

# Create Tables
models.Base.metadata.create_all(bind=database.engine)

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
    db = database.SessionLocal()
    try:
        # 1. Automatic Migration for User Model
        inspector = inspect(database.engine)
        columns = [c['name'] for c in inspector.get_columns('users')]
        
        if 'full_name' not in columns:
            print("Migrating DB: Adding full_name column to users table")
            db.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR"))
        if 'role' not in columns:
            print("Migrating DB: Adding role column to users table")
            db.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'parent'"))
        db.commit()

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
