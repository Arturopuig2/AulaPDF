import shutil
import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .. import models, database, auth

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    responses={404: {"description": "Not found"}},
)

templates = Jinja2Templates(directory="templates")

# Constants for Filters
SUBJECTS = ["Matemáticas", "Matemàtiques", "Lengua", "Valencià", "Inglés", "Otras"]
GRADES = ["1º", "2º", "3º", "4º", "5º", "6º", "Sin curso"]

def get_current_user(request: Request, db: Session = Depends(database.get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(models.User).filter(models.User.id == user_id).first()

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(database.get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Acceso restringido"})

    pdfs = db.query(models.PDF).order_by(models.PDF.uploaded_at.desc()).all()
    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "pdfs": pdfs,
        "subjects": SUBJECTS,
        "grades": GRADES
    })

@router.post("/upload")
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    subject: str = Form(...),
    grade: str = Form(...),
    db: Session = Depends(database.get_db)
):
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Generate Secure Filename
    clean_filename = f"{secrets.token_hex(4)}_{file.filename}"
    file_location = f"static/pdfs/{clean_filename}"
    
    # Save File
    os.makedirs(os.path.dirname(file_location), exist_ok=True)
    with open(file_location, "wb+") as file_object:
        shutil.copyfileobj(file.file, file_object)

    # Generate Access Code
    new_code_str = auth.generate_access_code()
    # Retry if collision (extremely rare with this space but safe to handle)
    while db.query(models.AccessCode).filter(models.AccessCode.code == new_code_str).first():
        new_code_str = auth.generate_access_code()

    # Save Metadata to DB
    new_pdf = models.PDF(
        title=title,
        filename=clean_filename,
        subject=subject,
        grade=grade
    )
    db.add(new_pdf)
    db.commit()
    db.refresh(new_pdf)

    # Associate Code
    access_code = models.AccessCode(code=new_code_str, pdf_id=new_pdf.id)
    db.add(access_code)
    db.commit()

    return await admin_dashboard(request, db)

@router.post("/delete/{pdf_id}")
async def delete_pdf(pdf_id: int, request: Request, db: Session = Depends(database.get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    pdf = db.query(models.PDF).filter(models.PDF.id == pdf_id).first()
    if pdf:
        # Remove file from disk
        file_path = f"static/pdfs/{pdf.filename}"
        if os.path.exists(file_path):
            os.remove(file_path)
            
        # Cascading delete handles access codes usually, but explicit here for safety
        db.query(models.AccessCode).filter(models.AccessCode.pdf_id == pdf_id).delete()
        db.delete(pdf)
        db.commit()

    return await admin_dashboard(request, db)

import secrets # Need to import locally or at top
