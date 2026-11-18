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

ALPHABET_UPPER_NO_CONFUSING = "ABCDEFGHJKMNPQRSTUVWXYZ"  # Excludes I, L, O
DIGITS_NO_CONFUSING = "23456789"  # Excludes 0, 1


def generate_user_license():
    """
    Generates a 9-char code: combination of digits (2-9) and uppercase letters (excluding I, L, O).
    No lowercase, no 0, 1, I, L, O. Guarantees at least one digit and one letter.
    """
    chars = DIGITS_NO_CONFUSING + ALPHABET_UPPER_NO_CONFUSING
    result = [
        secrets.choice(DIGITS_NO_CONFUSING),
        secrets.choice(ALPHABET_UPPER_NO_CONFUSING),
    ] + [secrets.choice(chars) for _ in range(7)]
    secrets.SystemRandom().shuffle(result)
    return ''.join(result)


def get_user_access_status(db: Session, user: models.User):
    """
    Computes (has_active_license, can_download, exp_str) from both single-use licenses
    and reusable license redemptions, and syncs user.has_active_license in DB.
    """
    if user.is_admin:
        return True, True, None

    has_active_license = False
    can_download = False
    exp_str = None

    user_licenses = db.query(models.License).filter(
        models.License.user_id == user.id,
        models.License.is_used == True
    ).order_by(models.License.created_at.desc()).all()

    for lic in user_licenses:
        if getattr(lic, "is_revoked", False):
            continue
        if check_license_validity(lic.expires_at):
            has_active_license = True
            if lic.allow_download:
                can_download = True
            if lic.expires_at and not exp_str:
                exp_str = lic.expires_at.strftime("%d/%m/%Y")

    user_redemptions = db.query(models.LicenseRedemption).filter(
        models.LicenseRedemption.user_id == user.id
    ).order_by(models.LicenseRedemption.redeemed_at.desc()).all()

    for red in user_redemptions:
        if getattr(red, "is_revoked", False):
            continue
        if check_license_validity(red.expires_at):
            has_active_license = True
            if red.allow_download:
                can_download = True
            if red.expires_at and not exp_str:
                exp_str = red.expires_at.strftime("%d/%m/%Y")

    if bool(user.has_active_license) != has_active_license:
        user.has_active_license = has_active_license
        try:
            db.commit()
        except Exception:
            db.rollback()

    return has_active_license, can_download, exp_str
