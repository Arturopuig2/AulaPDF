from fastapi import APIRouter, Form, HTTPException
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/contact", tags=["contact"])

@router.post("/send")
async def send_contact_form(
    name: str = Form(...),
    email: str = Form(...),
    message: str = Form(...)
):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    
    if not all([smtp_host, smtp_user, smtp_pass]):
        raise HTTPException(status_code=500, detail="Configuración de correo no encontrada.")

    # Create message
    msg = MIMEMultipart()
    msg['From'] = smtp_user
    msg['To'] = "info@editorialaula.es"
    msg['Subject'] = f"Nueva solicitud de información AulaPDF: {name}"

    body = f"""
    Has recibido una nueva solicitud de información desde AulaPDF:

    Nombre: {name}
    Correo: {email}
    
    Mensaje:
    {message}
    """
    msg.attach(MIMEText(body, 'plain'))

    try:
        # Use simple SMTP send for now (standard for many setups)
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
        return {"message": "Solicitud enviada correctamente. Gracias por contactarnos."}
    except Exception as e:
        print(f"Error sending email: {e}")
        # Return a user-friendly error but log the real one
        raise HTTPException(status_code=500, detail=f"Error al enviar el correo. Por favor, inténtalo de nuevo más tarde.")
