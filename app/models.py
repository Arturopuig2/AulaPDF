from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    is_admin = Column(Boolean, default=False)

class PDF(Base):
    __tablename__ = "pdfs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    filename = Column(String, unique=True)
    subject = Column(String, index=True) # Asignatura
    grade = Column(String, index=True)   # Curso
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    access_codes = relationship("AccessCode", back_populates="pdf")

class AccessCode(Base):
    __tablename__ = "access_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True) # 11 chars
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    pdf_id = Column(Integer, ForeignKey("pdfs.id"))

    pdf = relationship("PDF", back_populates="access_codes")

class RateLimit(Base):
    __tablename__ = "rate_limits"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String, index=True)
    failed_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    last_attempt = Column(DateTime, default=datetime.utcnow)
