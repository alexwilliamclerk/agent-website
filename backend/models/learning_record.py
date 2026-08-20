import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Integer, Numeric, ForeignKey

from database import Base


class LearningRecord(Base):
    __tablename__ = "learning_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=False)
    resource_id = Column(String(36), ForeignKey("resources.id"), nullable=False)
    status = Column(String(20), default="not_started")  # not_started, in_progress, completed
    score = Column(Numeric(5, 4), nullable=True)
    time_spent = Column(Integer, default=0)  # 秒
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
