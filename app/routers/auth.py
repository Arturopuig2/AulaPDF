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
    username = username.strip()
    
    # 1. Rate Check
    allowed, wait_time = auth.check_rate_limit(db, ip)
    if not allowed:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": f"Demasiados intentos. Inténtalo de nuevo en {wait_time} minutos."
        })

    # 2. Verify User (support case-insensitive matching and trim)
    user = db.query(models.User).filter(
        (models.User.username == username) | 
        (models.User.username == username.lower())
    ).first()
    
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
    
    try:
        if user.has_active_license:
            active_lic = db.query(models.License).filter(
                models.License.user_id == user.id,
                models.License.is_used == True
            ).order_by(models.License.created_at.desc()).first()
            if active_lic and active_lic.expires_at:
                request.session["license_expiration"] = active_lic.expires_at.strftime("%d/%m/%Y")
            is_valid = active_lic and auth.check_license_validity(active_lic.expires_at)
            has_dl = bool(getattr(active_lic, 'allow_download', False))
            can_dl = user.is_admin or (is_valid and has_dl)
            request.session["can_download"] = bool(can_dl)
        else:
            request.session["can_download"] = bool(user.is_admin)
    except Exception as e:
        print(f"Error checking session download rights in login: {e}")
        request.session["can_download"] = bool(getattr(user, 'is_admin', False))
            
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
    full_name = full_name.strip()
    username = username.strip().lower()
    confirm_username = confirm_username.strip().lower()

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
    existing_user = db.query(models.User).filter(
        (models.User.username == username) | 
        (models.User.username == username.lower())
    ).first()
    if existing_user:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "El nombre de usuario o correo ya está en uso"
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
        
        # Auto-login upon registration for smooth access
        request.session["user_id"] = new_user.id
        request.session["is_admin"] = new_user.is_admin
        request.session["full_name"] = new_user.full_name
        request.session["has_active_license"] = False
        request.session["can_download"] = False
        
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        db.rollback()
        print(f"Error during user registration: {e}")
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": f"Error al crear el usuario. Inténtalo de nuevo."
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

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jose import jwt, JWTError
from datetime import timedelta

@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot_password.html", {"request": request})

@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request):
    return templates.TemplateResponse("reset_password.html", {"request": request})

@router.post("/forgot-password")
async def forgot_password(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(database.get_db)
):
    # In our DB, username is the email
    user = db.query(models.User).filter(models.User.username == email).first()
    if not user:
        return {"message": "Si el correo electrónico está registrado, recibirás un enlace para restablecer tu contraseña."}
        
    # Generate Token
    reset_token = auth.create_access_token(
        data={"sub": user.username, "type": "reset"},
        expires_delta=timedelta(minutes=15)
    )
    
    # Determine base url
    base_url = str(request.base_url).rstrip("/")
    if "127.0.0.1" not in base_url and "localhost" not in base_url:
        base_url = base_url.replace("http://", "https://")
    reset_link = f"{base_url}/reset-password?token={reset_token}"
    
    # Send email or fallback to simulation
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    
    if not all([smtp_host, smtp_user, smtp_pass]):
        print("==================================================")
        print(f"PASSWORD RESET LINK FOR {user.username}:")
        print(reset_link)
        print("==================================================")
        return {"message": "Si el correo electrónico está registrado, recibirás un enlace (modo simulación)."}
        
    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = user.username
        msg['Subject'] = 'Recuperar Contraseña - Aula PDF'
        
        body = f"Hola {user.full_name or 'Usuario'},\n\nAquí tienes tu enlace para restablecer tu contraseña en Aula PDF:\n\n{reset_link}\n\nEste enlace caducará en 15 minutos."
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
        
        return {"message": "Te hemos enviado un enlace para restablecer tu contraseña a tu correo electrónico."}
    except Exception as e:
        print(f"Error sending password reset email: {e}")
        return {"message": "Error al enviar el correo. Por favor, contacta con soporte."}

@router.post("/reset-password")
async def reset_password(
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(database.get_db)
):
    if new_password != confirm_password:
        raise HTTPException(status_code=400, detail="Las contraseñas no coinciden")
        
    try:
        # Decode Token
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        username: str = payload.get("sub")
        token_type: str = payload.get("type")
        
        if username is None or token_type != "reset":
            raise HTTPException(status_code=400, detail="Token inválido o expirado.")
            
        user = db.query(models.User).filter(models.User.username == username).first()
        if not user:
            raise HTTPException(status_code=400, detail="Usuario no encontrado.")
            
        # Update Password
        user.hashed_password = auth.get_password_hash(new_password)
        db.commit()
        
        return {"message": "Tu contraseña ha sido restablecida correctamente."}
    except JWTError:
        raise HTTPException(status_code=400, detail="El enlace de recuperación es inválido o ha expirado.")
