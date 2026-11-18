from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, Response
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
        has_active_license, can_download, exp_str = auth.get_user_access_status(db, user)
        if exp_str:
            request.session["license_expiration"] = exp_str
        else:
            request.session.pop("license_expiration", None)

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
    has_active_license = user.is_admin
    can_download = user.is_admin

    try:
        has_active_license, can_download, exp_str = auth.get_user_access_status(db, user)
        if exp_str:
            request.session["license_expiration"] = exp_str
        else:
            request.session.pop("license_expiration", None)

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
import io
import urllib.parse
import unicodedata
from pypdf import PdfReader, PdfWriter

def clean_ascii_name(text: str) -> str:
    normalized = unicodedata.normalize('NFKD', text)
    ascii_bytes = normalized.encode('ascii', 'ignore')
    ascii_str = ascii_bytes.decode('ascii')
    clean = "".join(c for c in ascii_str if c.isalnum() or c in " _-").strip()
    return clean or "documento"

@router.api_route("/pdf/{pdf_id}/download", methods=["GET", "POST"])
async def download_pdf(
    pdf_id: int,
    request: Request,
    pages: str = None,
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

    if not pages:
        pages = request.query_params.get("pages")

    # Si es admin o tiene permiso de descarga por licencia activa (normal o reutilizable)
    has_active, can_dl, _ = auth.get_user_access_status(db, user)
    request.session["has_active_license"] = bool(has_active)
    request.session["can_download"] = bool(can_dl)

    # Si no tiene permiso por licencia pero proporciona código de acceso específico
    code_record = None
    if not can_dl and access_code:
        access_code = access_code.strip()
        code_record = db.query(models.AccessCode).filter(
            models.AccessCode.code == access_code,
            models.AccessCode.pdf_id == pdf_id
        ).first()

    if can_dl or code_record:
        # Si se solicita una página o pliego específico (ej: pages="2,3" o pages="1")
        if pages:
            try:
                page_nums = []
                for p_str in str(pages).split(","):
                    p_str = p_str.strip()
                    if p_str.isdigit():
                        p_val = int(p_str)
                        if p_val > 0:
                            page_nums.append(p_val)

                if page_nums:
                    reader = PdfReader(file_path)
                    writer = PdfWriter()
                    extracted_pages = []
                    for p_num in page_nums:
                        if 1 <= p_num <= len(reader.pages):
                            writer.add_page(reader.pages[p_num - 1])
                            extracted_pages.append(p_num)

                    if extracted_pages:
                        buffer = io.BytesIO()
                        writer.write(buffer)
                        buffer.seek(0)

                        ascii_title = clean_ascii_name(pdf.title)
                        encoded_title = urllib.parse.quote(pdf.title.replace("/", "_"))

                        if len(extracted_pages) == 1:
                            ascii_fn = f"{ascii_title}_pag_{extracted_pages[0]}.pdf"
                            encoded_fn = f"{encoded_title}_pag_{extracted_pages[0]}.pdf"
                        else:
                            ascii_fn = f"{ascii_title}_pags_{extracted_pages[0]}_{extracted_pages[-1]}.pdf"
                            encoded_fn = f"{encoded_title}_pags_{extracted_pages[0]}_{extracted_pages[-1]}.pdf"

                        return Response(
                            content=buffer.getvalue(),
                            media_type="application/pdf",
                            headers={
                                "Content-Disposition": f'attachment; filename="{ascii_fn}"; filename*=UTF-8\'\'{encoded_fn}'
                            }
                        )
            except Exception as e:
                print(f"Error extracting pages {pages} for PDF {pdf_id}: {e}")

        return FileResponse(file_path, media_type='application/pdf', filename=f"{pdf.title}.pdf")

    if access_code:
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

    if getattr(license_record, "is_revoked", False):
        raise HTTPException(status_code=403, detail="Esta licencia ha sido desactivada.")

    now = datetime.utcnow()
    expires_at = now + timedelta(days=365)

    if getattr(license_record, "is_reusable", False):
        existing = db.query(models.LicenseRedemption).filter(
            models.LicenseRedemption.license_id == license_record.id,
            models.LicenseRedemption.user_id == user.id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Ya has utilizado este código anteriormente en esta cuenta.")

        redemption = models.LicenseRedemption(
            license_id=license_record.id,
            user_id=user.id,
            redeemed_at=now,
            expires_at=expires_at,
            allow_download=bool(license_record.allow_download),
            is_revoked=False
        )
        db.add(redemption)
        license_record.use_count = (license_record.use_count or 0) + 1
        user.has_active_license = True
        db.commit()
    else:
        if license_record.is_used:
            raise HTTPException(status_code=400, detail="Esta licencia ya ha sido utilizada.")

        # Activate single-use license
        user.has_active_license = True
        license_record.is_used = True
        license_record.user_id = user.id
        license_record.expires_at = expires_at
        license_record.use_count = 1
        db.commit()

    has_active, can_dl, exp_str = auth.get_user_access_status(db, user)
    request.session["has_active_license"] = bool(has_active)
    if exp_str:
        request.session["license_expiration"] = exp_str
    request.session["can_download"] = bool(can_dl)

    msg = "Licencia activada correctamente con permisos de descarga." if can_dl else "Licencia activada correctamente."
    return {"message": f"{msg} Recargando..."}
