import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint

from database import Base


class ResourceBookmark(Base):
    __tablename__ = "resource_bookmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "resource_id", name="uq_resource_bookmark_user_resource"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    resource_id = Column(String(36), ForeignKey("resources.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
