import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Text, Integer, Numeric, JSON, ForeignKey

from database import Base


class CalibrationRecord(Base):
    """One requirement-level comparison between AI output and a trusted result."""

    __tablename__ = "calibration_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assessment_id = Column(String(36), ForeignKey("assessments.id"), nullable=False, index=True)
    requirement_id = Column(String(120), nullable=False, index=True)
    requirement_name = Column(String(120), nullable=False)
    predicted_score = Column(Numeric(5, 4), nullable=True)
    gold_score = Column(Numeric(5, 4), nullable=True)
    absolute_error = Column(Numeric(5, 4), nullable=True)
    predicted_status = Column(String(20), nullable=True)
    gold_status = Column(String(20), nullable=True)
    status = Column(String(20), nullable=False)  # passed / needs_review / rejected
    is_correct = Column(Integer, nullable=False, default=0)
    trusted = Column(Integer, nullable=False, default=1)
    source_type = Column(String(30), nullable=False, default="expert")
    reference_answer = Column(Text, nullable=True)
    evidence_ids = Column(JSON, nullable=True)
    details = Column(JSON, nullable=True)
    calibration_version = Column(String(60), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
