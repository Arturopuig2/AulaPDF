from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .. import models, database
from datetime import datetime, timedelta

router = APIRouter(
    tags=["viewer"],
    responses={404: {"description": "Not found"}},
)

templates = Jinja2Templates(directory="templates")

# Same constants used for rendering filters
SUBJECTS = ["Matemáticas", "Matemàtiques", "Lengua", "Valencià", "Inglés", "Otras"]
GRADES = ["1º", "2º", "3º", "4º", "5º", "6º", "Sin curso"]

@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    subject: str = None,
    grade: str = None,
    db: Session = Depends(database.get_db)
):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        request.session.clear()
        return RedirectResponse(url="/login", status_code=303)

    # Sync session in case it is outdated
    request.session["has_active_license"] = user.has_active_license
    if user.has_active_license and "license_expiration" not in request.session:
        active_lic = db.query(models.License).filter(
            models.License.user_id == user.id,
            models.License.is_used == True
        ).order_by(models.License.created_at.desc()).first()
        if active_lic and active_lic.expires_at:
            request.session["license_expiration"] = active_lic.expires_at.strftime("%d/%m/%Y")

    query = db.query(models.PDF)
    
    if subject and subject != "":
        query = query.filter(models.PDF.subject == subject)
    if grade and grade != "":
        query = query.filter(models.PDF.grade == grade)
        
    pdfs = query.order_by(models.PDF.uploaded_at.desc()).all()
    
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "pdfs": pdfs,
        "selected_subject": subject,
        "selected_grade": grade,
        "subjects": SUBJECTS,
        "grades": GRADES
    })

@router.get("/pdf/{pdf_id}", response_class=HTMLResponse)
async def view_pdf_detail(request: Request, pdf_id: int, db: Session = Depends(database.get_db)):
    user_id = request.session.get("user_id")
    if not user_id or not db.query(models.User).filter(models.User.id == user_id).first():
        return RedirectResponse(url="/login", status_code=303)

    pdf = db.query(models.PDF).filter(models.PDF.id == pdf_id).first()
    if not pdf:
        raise HTTPException(status_code=404, detail="PDF not found")
        
    return templates.TemplateResponse("viewer.html", {"request": request, "pdf": pdf})

@router.post("/pdf/{pdf_id}/download")
async def download_pdf(
    pdf_id: int,
    request: Request,
    access_code: str = Form(...),
    db: Session = Depends(database.get_db)
):
    user_id = request.session.get("user_id")
    if not user_id or not db.query(models.User).filter(models.User.id == user_id).first():
        raise HTTPException(status_code=401, detail="No autorizado")
    access_code = access_code.strip()
    # Validate PDF existence
    pdf = db.query(models.PDF).filter(models.PDF.id == pdf_id).first()
    if not pdf:
        raise HTTPException(status_code=404, detail="PDF not found")

    # Validate Access Code
    # Code must belong to this specific PDF and not be expired/used?
    # Requirement says "unique code to download". Usually one-time use or just valid key?
    # Implied one-time or specific key. "Generación... para poder descargar".
    # If it's a "ticket", it should be one-time. Let's assume Valid Match.
    
    code_record = db.query(models.AccessCode).filter(
        models.AccessCode.code == access_code,
        models.AccessCode.pdf_id == pdf_id
    ).first()

    if not code_record:
         raise HTTPException(status_code=403, detail="Código inválido para este documento.")

    # Return the file
    file_path = f"static/pdfs/{pdf.filename}"
    return FileResponse(file_path, media_type='application/pdf', filename=f"{pdf.title}.pdf")

@router.get("/pdf/{pdf_id}/inline")
async def view_pdf_inline(pdf_id: int, request: Request, db: Session = Depends(database.get_db)):
    user_id = request.session.get("user_id")
    if not user_id or not db.query(models.User).filter(models.User.id == user_id).first():
        raise HTTPException(status_code=401, detail="No autorizado")

    pdf = db.query(models.PDF).filter(models.PDF.id == pdf_id).first()
    if not pdf:
        raise HTTPException(status_code=404, detail="PDF not found")
        
    file_path = f"static/pdfs/{pdf.filename}"
    # Content-Disposition inline allows browser to show it
    return FileResponse(file_path, media_type='application/pdf', content_disposition_type="inline")

@router.post("/activate-license")
async def activate_license(
    request: Request,
    license_code: str = Form(...),
    db: Session = Depends(database.get_db)
):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")
        
    license_code = license_code.strip().upper()
    if not license_code:
        raise HTTPException(status_code=400, detail="Código de licencia vacío")
        
    license_record = db.query(models.License).filter(models.License.code == license_code).first()
    if not license_record:
        raise HTTPException(status_code=404, detail="El código de licencia no es válido.")
        
    if license_record.is_used:
        raise HTTPException(status_code=400, detail="Esta licencia ya ha sido utilizada.")
        
    # Activate license
    user.has_active_license = True
    license_record.is_used = True
    license_record.user_id = user.id
    license_record.expires_at = datetime.utcnow() + timedelta(days=365)
    db.commit()
    
    request.session["has_active_license"] = True
    request.session["license_expiration"] = license_record.expires_at.strftime("%d/%m/%Y")
    
    return {"message": "Licencia activada correctamente. Recargando..."}
