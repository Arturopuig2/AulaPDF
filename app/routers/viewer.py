from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from ..templating import templates
from sqlalchemy.orm import Session
from .. import models, database, auth
from datetime import datetime, timedelta, timezone

def check_license_validity(expires_at):
    return auth.check_license_validity(expires_at)

router = APIRouter(
    tags=["viewer"],
    responses={404: {"description": "Not found"}},
)


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

    # Sync session safely with database
    try:
        user_licenses = db.query(models.License).filter(
            models.License.user_id == user.id,
            models.License.is_used == True
        ).order_by(models.License.created_at.desc()).all()

        has_active_license = user.is_admin or bool(user.has_active_license)
        can_download = user.is_admin
        exp_str = None

        for lic in user_licenses:
            if auth.check_license_validity(lic.expires_at):
                has_active_license = True
                if lic.allow_download:
                    can_download = True
                if lic.expires_at and not exp_str:
                    exp_str = lic.expires_at.strftime("%d/%m/%Y")

        if exp_str:
            request.session["license_expiration"] = exp_str

        if has_active_license and not user.has_active_license and not user.is_admin:
            user.has_active_license = True
            try:
                db.commit()
            except Exception:
                db.rollback()

        request.session["has_active_license"] = bool(has_active_license)
        request.session["can_download"] = bool(can_download)
    except Exception as e:
        print(f"Error checking user session in home: {e}")
        request.session["has_active_license"] = bool(getattr(user, 'has_active_license', False))
        request.session["can_download"] = bool(getattr(user, 'is_admin', False))

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
    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        request.session.clear()
        return RedirectResponse(url="/login", status_code=303)

    pdf = db.query(models.PDF).filter(models.PDF.id == pdf_id).first()
    if not pdf:
        raise HTTPException(status_code=404, detail="PDF not found")

    # Evaluate active licenses and download permission dynamically
    has_active_license = user.is_admin or bool(user.has_active_license)
    can_download = user.is_admin

    try:
        user_licenses = db.query(models.License).filter(
            models.License.user_id == user.id,
            models.License.is_used == True
        ).all()
        for lic in user_licenses:
            if auth.check_license_validity(lic.expires_at):
                has_active_license = True
                if lic.allow_download:
                    can_download = True

        if has_active_license and not user.has_active_license and not user.is_admin:
            user.has_active_license = True
            try:
                db.commit()
            except Exception:
                db.rollback()

        request.session["has_active_license"] = bool(has_active_license)
        request.session["can_download"] = bool(can_download)
    except Exception as e:
        print(f"Error checking user license in view_pdf_detail: {e}")

    return templates.TemplateResponse("viewer.html", {
        "request": request,
        "pdf": pdf,
        "has_active_license": has_active_license,
        "can_download": can_download
    })

import os

@router.api_route("/pdf/{pdf_id}/download", methods=["GET", "POST"])
async def download_pdf(
    pdf_id: int,
    request: Request,
    access_code: str = Form(None),
    db: Session = Depends(database.get_db)
):
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="No autorizado")
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="No autorizado")

    # Validate PDF existence
    pdf = db.query(models.PDF).filter(models.PDF.id == pdf_id).first()
    if not pdf:
        raise HTTPException(status_code=404, detail="PDF no encontrado")

    file_path = f"static/pdfs/{pdf.filename}"
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="El archivo PDF no se encuentra en el servidor.")

    # Si es admin o tiene permiso de descarga por licencia activa
    can_dl = user.is_admin or request.session.get("is_admin") or request.session.get("can_download")
    if not can_dl and user.has_active_license:
        active_lics = db.query(models.License).filter(
            models.License.user_id == user.id,
            models.License.is_used == True,
            models.License.allow_download == True
        ).all()
        for lic in active_lics:
            if check_license_validity(lic.expires_at):
                can_dl = True
                request.session["can_download"] = True
                break

    if can_dl:
        return FileResponse(file_path, media_type='application/pdf', filename=f"{pdf.title}.pdf")

    # Si no tiene permiso por licencia pero proporciona código de acceso específico
    if access_code:
        access_code = access_code.strip()
        code_record = db.query(models.AccessCode).filter(
            models.AccessCode.code == access_code,
            models.AccessCode.pdf_id == pdf_id
        ).first()

        if code_record:
            return FileResponse(file_path, media_type='application/pdf', filename=f"{pdf.title}.pdf")
        else:
            raise HTTPException(status_code=403, detail="Código inválido para este documento.")

    raise HTTPException(status_code=403, detail="Tu licencia actual no incluye permiso de descarga para este documento.")

@router.get("/pdf/{pdf_id}/inline")
async def view_pdf_inline(pdf_id: int, request: Request, db: Session = Depends(database.get_db)):
    user_id = request.session.get("user_id")
    if not user_id or not db.query(models.User).filter(models.User.id == user_id).first():
        raise HTTPException(status_code=401, detail="No autorizado")

    pdf = db.query(models.PDF).filter(models.PDF.id == pdf_id).first()
    if not pdf:
        raise HTTPException(status_code=404, detail="PDF not found")
        
    file_path = f"static/pdfs/{pdf.filename}"
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
    request.session["can_download"] = bool(user.is_admin or license_record.allow_download)
    
    msg = "Licencia activada correctamente con permisos de descarga." if license_record.allow_download else "Licencia activada correctamente."
    return {"message": f"{msg} Recargando..."}
