"""
路径模块 - 查询学习路径
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.path import LearningPath
from models.resource import Resource
from models.learning_record import LearningRecord
from models.job import Job
from models.user import User
from routers.auth import get_current_user
from dimensions import get_weight_for_knowledge
from adapters.guardrail import detect_unrequested_resource_type

router = APIRouter()


# ===== 响应模型 =====

class PathStep(BaseModel):
    step: int
    knowledge_point: str
    resource_type: str
    resource_id: str | None = None
    estimated_time: int
    prerequisite: str | None = None
    status: str = "not_started"
    record_id: str | None = None
    weight: str = "mid"


class LearningPathResponse(BaseModel):
    id: str
    user_id: str
    job_id: str
    assessment_id: str | None = None
    steps: list[PathStep] | None = None
    current_step: int
    status: str
    created_at: datetime
    updated_at: datetime


# ===== 工具函数 =====

def _enrich_steps(steps: list[dict], user_id: str, target_job: str, db: Session, assessment_id: str | None = None) -> list[dict]:
    """为每个 step 补上 resource_id、status、record_id、weight"""
    if not steps:
        return steps

    for s in steps:
        # 知识点 → 维度 → 岗位权重
        s["weight"] = get_weight_for_knowledge(s["knowledge_point"], target_job)

        # 查 resource_id（按诊断隔离：优先匹配本诊断的资源）
        q = (
            db.query(Resource)
            .filter(
                Resource.knowledge_point == s["knowledge_point"],
                Resource.content_type == s["resource_type"],
                Resource.review_status.in_(["passed", "partial"]),
                Resource.source_chunk_id.isnot(None),
                Resource.source_text.isnot(None),
                Resource.is_legacy == 0,
            )
        )
        if assessment_id:
            q = q.filter(Resource.assessment_id == assessment_id)
        resource = q.order_by(Resource.created_at.desc()).first()
        if resource and detect_unrequested_resource_type(resource.body or "", resource.content_type or "").get("found"):
            resource = None
        s["resource_id"] = resource.id if resource else None

        # 查学习状态
        if resource:
            record = (
                db.query(LearningRecord)
                .filter(
                    LearningRecord.resource_id == resource.id,
                    LearningRecord.user_id == user_id,
                )
                .order_by(LearningRecord.started_at.desc())
                .first()
            )
            s["status"] = record.status if record else "not_started"
            s["record_id"] = record.id if record else None
        else:
            s["status"] = "not_started"
            s["record_id"] = None

    return steps


# ===== 接口 =====

@router.get("/{user_id}", response_model=list[LearningPathResponse])
def get_learning_paths(
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询用户学习路径"""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问")

    paths = db.query(LearningPath).filter(
        LearningPath.user_id == user_id,
    ).order_by(LearningPath.created_at.desc()).all()

    # 为每条路径的每个 step 补上 resource_id、status、record_id、weight
    for path in paths:
        if path.steps:
            job = db.query(Job).filter(Job.id == path.job_id).first()
            target_job = job.job_title if job else ""
            path.steps = _enrich_steps(path.steps, user_id, target_job, db, path.assessment_id)

    return paths
