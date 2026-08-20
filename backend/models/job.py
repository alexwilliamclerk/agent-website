import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Text, JSON

from database import Base


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_title = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    required_skills = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
