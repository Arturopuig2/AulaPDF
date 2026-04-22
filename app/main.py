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

@app.on_event("startup")
def create_initial_user():
    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == "admin").first()
        admin_pass = os.getenv("ADMIN_PASSWORD")
        
        if not user:
            # Create default admin if not exists
            if not admin_pass:
                admin_pass = "admin123"
            print("Creating default admin user...")
            hashed = auth.get_password_hash(admin_pass)
            new_user = models.User(username="admin", hashed_password=hashed, is_admin=True)
            db.add(new_user)
            db.commit()
            print(f"Default Admin created: user='admin'")
        elif admin_pass:
            # Update existing admin password to match environment variable
            print("Updating existing admin password from environment variable...")
            user.hashed_password = auth.get_password_hash(admin_pass)
            db.commit()
            print("Admin password updated successfully.")
    except Exception as e:
        print(f"Error initializing admin user: {e}")
        db.rollback()
    finally:
        db.close()
