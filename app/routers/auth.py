from fastapi import APIRouter, Depends, Request, Form, Response, BackgroundTasks
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
    return RedirectResponse(url="/admin", status_code=303)

@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)
