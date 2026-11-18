import shutil
import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from .. import models, database, auth

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    responses={404: {"description": "Not found"}},
)

from ..templating import templates

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
    licenses = (
        db.query(models.License)
        .options(
            joinedload(models.License.user),
            joinedload(models.License.redemptions).joinedload(models.LicenseRedemption.user),
        )
        .order_by(models.License.created_at.desc())
        .all()
    )

    license_rows = []
    for lic in licenses:
        if getattr(lic, "is_reusable", False):
            uses = lic.use_count or 0
            lic_revoked = bool(getattr(lic, "is_revoked", False))
            license_rows.append({
                "row_type": "reusable_code",
                "id": lic.id,
                "code": lic.code,
                "is_reusable": True,
                "status": "REVOCADA" if lic_revoked else "DISPONIBLE",
                "allow_download": bool(lic.allow_download),
                "user_email": f"Reutilizable ({uses} usos)",
                "is_revoked": lic_revoked,
                "can_delete_permanently": uses == 0 and len(lic.redemptions) == 0,
                "toggle_download_url": f"/admin/toggle-license-download/{lic.id}",
                "action_url": f"/admin/delete-license/{lic.id}",
            })
            sorted_reds = sorted(lic.redemptions, key=lambda r: r.redeemed_at or lic.created_at, reverse=True)
            for red in sorted_reds:
                red_revoked = bool(getattr(red, "is_revoked", False))
                license_rows.append({
                    "row_type": "redemption",
                    "id": red.id,
                    "code": lic.code,
                    "is_reusable": True,
                    "status": "REVOCADA" if red_revoked else "USADA",
                    "allow_download": bool(red.allow_download),
                    "user_email": red.user.username if red.user else None,
                    "is_revoked": red_revoked,
                    "can_delete_permanently": False,
                    "toggle_download_url": f"/admin/toggle-redemption-download/{red.id}",
                    "action_url": f"/admin/delete-redemption/{red.id}",
                })
        else:
            lic_revoked = bool(getattr(lic, "is_revoked", False))
            status_label = "REVOCADA" if lic_revoked else ("USADA" if lic.is_used else "DISPONIBLE")
            license_rows.append({
                "row_type": "single",
                "id": lic.id,
                "code": lic.code,
                "is_reusable": False,
                "status": status_label,
                "allow_download": bool(lic.allow_download),
                "user_email": lic.user.username if lic.user else None,
                "is_revoked": lic_revoked,
                "can_delete_permanently": not lic.is_used,
                "toggle_download_url": f"/admin/toggle-license-download/{lic.id}",
                "action_url": f"/admin/delete-license/{lic.id}",
            })

    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "pdfs": pdfs,
        "licenses": licenses,
        "license_rows": license_rows,
        "subjects": SUBJECTS,
        "grades": GRADES
    })

import secrets

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

    # Save Metadata to DB
    new_pdf = models.PDF(
        title=title,
        filename=clean_filename,
        subject=subject,
        grade=grade
    )
    db.add(new_pdf)
    db.commit()

    return RedirectResponse(url="/admin", status_code=303)

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
            
        db.delete(pdf)
        db.commit()

    return RedirectResponse(url="/admin", status_code=303)

@router.post("/generate-license")
async def generate_license(
    request: Request,
    allow_download: bool = Form(False),
    is_reusable: bool = Form(False),
    db: Session = Depends(database.get_db)
):
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # Generate unique code
    new_code = auth.generate_user_license()
    while db.query(models.License).filter(models.License.code == new_code).first():
        new_code = auth.generate_user_license()
        
    # Save to DB
    license_record = models.License(
        code=new_code,
        allow_download=allow_download,
        is_reusable=is_reusable,
        use_count=0,
        is_revoked=False
    )
    db.add(license_record)
    db.commit()
    
    return RedirectResponse(url="/admin", status_code=303)

@router.post("/toggle-license-download/{license_id}")
async def toggle_license_download(license_id: int, request: Request, db: Session = Depends(database.get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    license_record = db.query(models.License).filter(models.License.id == license_id).first()
    if license_record:
        license_record.allow_download = not license_record.allow_download
        db.commit()
        
    return RedirectResponse(url="/admin", status_code=303)

@router.post("/toggle-redemption-download/{redemption_id}")
async def toggle_redemption_download(redemption_id: int, request: Request, db: Session = Depends(database.get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    redemption = db.query(models.LicenseRedemption).filter(models.LicenseRedemption.id == redemption_id).first()
    if redemption:
        redemption.allow_download = not bool(redemption.allow_download)
        db.commit()

    return RedirectResponse(url="/admin", status_code=303)

@router.post("/delete-license/{license_id}")
async def delete_license(license_id: int, request: Request, db: Session = Depends(database.get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    license_record = db.query(models.License).filter(models.License.id == license_id).first()
    if license_record:
        is_unused = (
            (not license_record.is_used and not getattr(license_record, "is_reusable", False))
            or (getattr(license_record, "is_reusable", False) and (license_record.use_count or 0) == 0 and len(license_record.redemptions) == 0)
        )
        if is_unused:
            db.delete(license_record)
            db.commit()
        else:
            license_record.is_revoked = not bool(getattr(license_record, "is_revoked", False))
            db.commit()
            if not getattr(license_record, "is_reusable", False) and license_record.user:
                auth.get_user_access_status(db, license_record.user)
        
    return RedirectResponse(url="/admin", status_code=303)

@router.post("/delete-redemption/{redemption_id}")
async def delete_redemption(redemption_id: int, request: Request, db: Session = Depends(database.get_db)):
    user = get_current_user(request, db)
    if not user or not user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    redemption = db.query(models.LicenseRedemption).filter(models.LicenseRedemption.id == redemption_id).first()
    if redemption:
        redemption.is_revoked = not bool(getattr(redemption, "is_revoked", False))
        db.commit()
        if redemption.user:
            auth.get_user_access_status(db, redemption.user)

    return RedirectResponse(url="/admin", status_code=303)
