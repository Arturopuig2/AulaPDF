import secrets
import string
from passlib.context import CryptContext
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from . import models

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def generate_access_code():
    """
    Generates a secure access code: PDF + 5 digits + 3 uppercase letters (excluding I, L, O).
    Format: PDF12345QTR
    """
    prefix = "PDF"
    digits = ''.join(secrets.choice(string.digits) for _ in range(5))
    
    # Exclude I, L, O to avoid confusion
    allowed_letters = "".join(set(string.ascii_uppercase) - {"I", "L", "O"})
    letters = ''.join(secrets.choice(allowed_letters) for _ in range(3))
    
    return f"{prefix}{digits}{letters}"

def check_rate_limit(db: Session, ip_address: str):
    """
    Checks if an IP is allowed to attempt login.
    Returns (allowed: bool, wait_time_minutes: int)
    """
    record = db.query(models.RateLimit).filter(models.RateLimit.ip_address == ip_address).first()
    
    if not record:
        return True, 0

    if record.locked_until and record.locked_until > datetime.utcnow():
        wait_time = (record.locked_until - datetime.utcnow()).seconds // 60
        return False, wait_time + 1

    return True, 0

def register_failed_attempt(db: Session, ip_address: str):
    """
    Registers a failed login attempt and applies backoff if needed.
    """
    record = db.query(models.RateLimit).filter(models.RateLimit.ip_address == ip_address).first()
    
    if not record:
        record = models.RateLimit(ip_address=ip_address, failed_attempts=1)
        db.add(record)
    else:
        record.failed_attempts += 1
        record.last_attempt = datetime.utcnow()
        
        # Lockout logic after 6 failures
        if record.failed_attempts >= 6:
            # Backoff strategy: 5m, 15m, 1h, 6h...
            excess_failures = record.failed_attempts - 6
            if excess_failures == 0:
                lockout_min = 5
            elif excess_failures == 1:
                lockout_min = 15
            elif excess_failures == 2:
                lockout_min = 60
            else:
                lockout_min = 360 # Max 6 hours cap effectively for simplicity or continue exponential
            
            record.locked_until = datetime.utcnow() + timedelta(minutes=lockout_min)

    db.commit()

def reset_rate_limit(db: Session, ip_address: str):
    """
    Clears failed attempts on successful login.
    """
    record = db.query(models.RateLimit).filter(models.RateLimit.ip_address == ip_address).first()
    if record:
        db.delete(record)
        db.commit()
