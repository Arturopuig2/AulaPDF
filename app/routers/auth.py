from fastapi import APIRouter, Depends, Request, Form, Response, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .. import models, database, auth

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="templates")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(database.get_db)
):
    ip = request.client.host
    
    # 1. Rate Check
    allowed, wait_time = auth.check_rate_limit(db, ip)
    if not allowed:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": f"Demasiados intentos. Inténtalo de nuevo en {wait_time} minutos."
        })

    # 2. Verify User
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not auth.verify_password(password, user.hashed_password):
        # Register failure
        auth.register_failed_attempt(db, ip)
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Credenciales incorrectas"
        })

    # 3. Success - Reset limits & Set Session
    auth.reset_rate_limit(db, ip)
    request.session["user_id"] = user.id
    request.session["is_admin"] = user.is_admin
    request.session["full_name"] = user.full_name
    request.session["has_active_license"] = user.has_active_license
    
    if user.has_active_license:
        active_lic = db.query(models.License).filter(
            models.License.user_id == user.id,
            models.License.is_used == True
        ).order_by(models.License.created_at.desc()).first()
        if active_lic and active_lic.expires_at:
            request.session["license_expiration"] = active_lic.expires_at.strftime("%d/%m/%Y")
            
    return RedirectResponse(url="/", status_code=303)

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@router.post("/register")
async def register(
    request: Request,
    full_name: str = Form(...),
    username: str = Form(...),
    confirm_username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(database.get_db)
):
    # 0. Check Emails match
    if username != confirm_username:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Los correos electrónicos no coinciden"
        })

    # 1. Check Passwords match
    if password != confirm_password:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Las contraseñas no coinciden"
        })

    # 2. Check if user already exists
    existing_user = db.query(models.User).filter(models.User.username == username).first()
    if existing_user:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "El nombre de usuario ya está en uso"
        })

    # 3. Create User
    hashed_password = auth.get_password_hash(password)
    new_user = models.User(
        username=username, 
        full_name=full_name,
        hashed_password=hashed_password,
        role="parent"
    )
    
    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        # Optional: Auto-login
        # request.session["user_id"] = new_user.id
        # return RedirectResponse(url="/", status_code=303)
        
        # Redirect to login with success message (implicitly via clean login page)
        return RedirectResponse(url="/login", status_code=303)
    except Exception as e:
        db.rollback()
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Error al crear el usuario. Inténtalo de nuevo."
        })

@router.post("/change-password")
async def change_password(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(database.get_db)
):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
        
    # Verify old password
    if not auth.verify_password(old_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta")
        
    # Verify new passwords match
    if new_password != confirm_password:
        raise HTTPException(status_code=400, detail="Las nuevas contraseñas no coinciden")
        
    # Update password
    user.hashed_password = auth.get_password_hash(new_password)
    db.commit()
    
    return {"message": "Contraseña actualizada correctamente."}
