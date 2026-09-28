import secrets
import string
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from . import models
from jose import jwt, JWTError
import os

def check_license_validity(expires_at):
    if not expires_at:
        return True
    try:
        if getattr(expires_at, "tzinfo", None) is not None:
            return expires_at > datetime.now(timezone.utc)
        return expires_at > datetime.utcnow()
    except Exception:
        return True

SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-for-dev-only")
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

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

    if record.locked_until:
        try:
            if getattr(record.locked_until, "tzinfo", None) is not None:
                now_val = datetime.now(timezone.utc)
            else:
                now_val = datetime.utcnow()
            if record.locked_until > now_val:
                wait_time = (record.locked_until - now_val).seconds // 60
                return False, wait_time + 1
        except Exception:
            pass

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

import string
def generate_user_license():
    """
    Generates a secure user license code: 9 uppercase alphanumeric characters (excluding I, L, O).
    """
    allowed_chars = "".join(set(string.ascii_uppercase + string.digits) - {"I", "L", "O"})
    return ''.join(secrets.choice(allowed_chars) for _ in range(9))
