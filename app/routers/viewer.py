from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from .. import models, database

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
    pdf = db.query(models.PDF).filter(models.PDF.id == pdf_id).first()
    if not pdf:
        raise HTTPException(status_code=404, detail="PDF not found")
        
    return templates.TemplateResponse("viewer.html", {"request": request, "pdf": pdf})

@router.post("/pdf/{pdf_id}/download")
async def download_pdf(
    pdf_id: int,
    access_code: str = Form(...),
    db: Session = Depends(database.get_db)
):
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
async def view_pdf_inline(pdf_id: int, db: Session = Depends(database.get_db)):
    pdf = db.query(models.PDF).filter(models.PDF.id == pdf_id).first()
    if not pdf:
        raise HTTPException(status_code=404, detail="PDF not found")
        
    file_path = f"static/pdfs/{pdf.filename}"
    # Content-Disposition inline allows browser to show it
    return FileResponse(file_path, media_type='application/pdf', content_disposition_type="inline")
