import uuid
from datetime import datetime

from sqlalchemy import Column, String, DateTime, Integer, Numeric, JSON, Text, ForeignKey

from database import Base


class Session(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=False)
    status = Column(String(20), default="active")  # active, reviewing, ready_for_diagnosis, completed
    current_step = Column(Integer, default=1)
    progress = Column(Numeric(5, 4), default=0)
    # The review gate defaults to two learner turns.  It is state, not an Agent.
    turn_count = Column(Integer, default=0, nullable=False)
    minimum_turns = Column(Integer, default=2, nullable=False)
    ready_for_diagnosis = Column(Integer, default=0, nullable=False)
    review_state = Column(JSON, nullable=True)
    assessment_id = Column(String(36), ForeignKey("assessments.id"), nullable=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    last_active_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SessionMessage(Base):
    """Persisted learner/Agent turns for bounded, auditable review dialogue."""

    __tablename__ = "session_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("sessions.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(16), nullable=False)  # user / assistant
    content = Column(Text, nullable=False)
    turn_index = Column(Integer, nullable=False, default=0)
    context_snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
