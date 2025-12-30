from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from . import models, database, auth
from .routers import admin, viewer, auth as auth_router
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

@app.on_event("startup")
def create_initial_user():
    db = database.SessionLocal()
    user = db.query(models.User).filter(models.User.username == "admin").first()
    if not user:
        # Create default admin
        # In a real app, read from env or generate random and log it
        print("Creating default admin user...")
        admin_pass = os.getenv("ADMIN_PASSWORD", "admin123")
        hashed = auth.get_password_hash(admin_pass)
        new_user = models.User(username="admin", hashed_password=hashed, is_admin=True)
        db.add(new_user)
        db.commit()
        print(f"Default Admin created: user='admin'")
    db.close()
