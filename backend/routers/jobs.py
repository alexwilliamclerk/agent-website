"""
职业模块 - 查询职业列表
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db
from models.job import Job

router = APIRouter()


class JobResponse(BaseModel):
    id: str
    job_title: str
    description: str | None = None
    required_skills: list | None = None


@router.get("/list", response_model=list[JobResponse])
def list_jobs(db: Session = Depends(get_db)):
    """获取所有职业列表（无需登录）"""
    return db.query(Job).order_by(Job.created_at).all()
