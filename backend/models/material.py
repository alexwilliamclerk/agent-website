import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from database import Base


class UserMaterial(Base):
    """A learner-owned file or text evidence submitted for review."""

    __tablename__ = "user_materials"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=True, index=True)
    assessment_id = Column(String(36), ForeignKey("assessments.id"), nullable=True, index=True)
    original_name = Column(String(255), nullable=False)
    storage_name = Column(String(255), nullable=True)
    content_type = Column(String(120), nullable=True)
    size_bytes = Column(Integer, default=0)
    status = Column(String(24), nullable=False, default="uploaded")
    extracted_text = Column(Text, nullable=True)
    source_url = Column(String(1000), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
