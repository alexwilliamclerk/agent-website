import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Integer, JSON, ForeignKey

from database import Base


class LearningPath(Base):
    __tablename__ = "learning_paths"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=False)
    assessment_id = Column(String(36), ForeignKey("assessments.id"), nullable=True)  # 所属诊断，NULL=旧路径未绑定
    steps = Column(JSON, nullable=True)  # [{"step":1,"knowledge_point":"贪心算法",...}]
    current_step = Column(Integer, default=1)
    status = Column(String(20), default="active")  # active, completed, abandoned
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
