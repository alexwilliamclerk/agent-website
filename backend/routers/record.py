"""
学习记录模块 - 创建记录、标记完成
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models.learning_record import LearningRecord
from models.assessment import Assessment
from models.resource import Resource
from models.session import Session as LearningSession
from models.user import User
from routers.auth import get_current_user

router = APIRouter()


# ===== 请求/响应模型 =====

class CreateRecordRequest(BaseModel):
    session_id: str
    resource_id: str


class CompleteRecordRequest(BaseModel):
    score: float | None = Field(default=None, ge=0, le=100)
    time_spent: int | None = Field(default=None, ge=0, le=31_536_000)  # 秒


class RecordResponse(BaseModel):
    id: str
    user_id: str
    session_id: str
    resource_id: str
    status: str
    score: float | None = None
    time_spent: int
    started_at: datetime | None = None
    completed_at: datetime | None = None


def _get_owned_resource(resource_id: str, user_id: str, db: Session) -> Resource:
    resource = db.query(Resource).join(
        Assessment, Resource.assessment_id == Assessment.id
    ).filter(
        Resource.id == resource_id,
        Assessment.user_id == user_id,
        Resource.review_status.in_(["passed", "partial"]),
        Resource.source_chunk_id.isnot(None),
        Resource.source_text.isnot(None),
        Resource.is_legacy == 0,
    ).first()
    if not resource or resource.display_status != "show":
        raise HTTPException(status_code=404, detail="学习资源不存在")
    return resource


def _latest_record(resource_id: str, user_id: str, db: Session) -> LearningRecord | None:
    return db.query(LearningRecord).filter(
        LearningRecord.resource_id == resource_id,
        LearningRecord.user_id == user_id,
    ).order_by(LearningRecord.started_at.desc()).first()


# ===== 接口 =====

@router.post("/create", response_model=RecordResponse, status_code=201)
def create_record(
    request: CreateRecordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建学习记录（开始学习某个资源）"""
    learning_session = db.query(LearningSession).filter(
        LearningSession.id == request.session_id,
        LearningSession.user_id == current_user.id,
    ).first()
    if not learning_session:
        raise HTTPException(status_code=404, detail="学习会话不存在")
    resource = _get_owned_resource(request.resource_id, current_user.id, db)
    assessment = db.query(Assessment).filter(
        Assessment.id == resource.assessment_id,
        Assessment.user_id == current_user.id,
    ).first()
    if not assessment or learning_session.job_id != assessment.job_id:
        raise HTTPException(status_code=409, detail="学习会话与资源所属岗位不一致")
    existing = _latest_record(request.resource_id, current_user.id, db)
    if existing:
        return existing
    record = LearningRecord(
        user_id=current_user.id,
        session_id=request.session_id,
        resource_id=request.resource_id,
        status="in_progress",
        started_at=datetime.utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return record


@router.get("/list", response_model=list[RecordResponse])
def list_records(
    assessment_id: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询当前学习者的学习记录，可按一次诊断过滤。"""
    query = db.query(LearningRecord).join(
        Resource, LearningRecord.resource_id == Resource.id
    ).join(
        Assessment, Resource.assessment_id == Assessment.id
    ).filter(
        LearningRecord.user_id == current_user.id,
        Assessment.user_id == current_user.id,
    )
    if assessment_id:
        query = query.filter(Resource.assessment_id == assessment_id)
    return query.order_by(LearningRecord.started_at.desc()).all()


@router.get("/resource/{resource_id}", response_model=RecordResponse | None)
def get_resource_record(
    resource_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询一条资源最近的学习状态。"""
    _get_owned_resource(resource_id, current_user.id, db)
    return _latest_record(resource_id, current_user.id, db)


@router.post("/resource/{resource_id}/start", response_model=RecordResponse)
def start_resource(
    resource_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """开始或继续学习，重复点击不会创建重复记录。"""
    resource = _get_owned_resource(resource_id, current_user.id, db)
    existing = _latest_record(resource_id, current_user.id, db)
    if existing:
        if existing.status == "not_started":
            existing.status = "in_progress"
            existing.started_at = existing.started_at or datetime.utcnow()
            db.commit()
            db.refresh(existing)
        return existing

    assessment = db.query(Assessment).filter(
        Assessment.id == resource.assessment_id,
        Assessment.user_id == current_user.id,
    ).first()
    learning_session = db.query(LearningSession).filter(
        LearningSession.user_id == current_user.id,
        LearningSession.job_id == assessment.job_id,
        LearningSession.status == "active",
    ).order_by(LearningSession.last_active_at.desc()).first()
    if not learning_session:
        learning_session = LearningSession(
            user_id=current_user.id,
            job_id=assessment.job_id,
            status="active",
        )
        db.add(learning_session)
        db.flush()

    record = LearningRecord(
        user_id=current_user.id,
        session_id=learning_session.id,
        resource_id=resource.id,
        status="in_progress",
        started_at=datetime.utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.put("/{record_id}/complete", response_model=RecordResponse)
def complete_record(
    record_id: str,
    request: CompleteRecordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """标记学习记录为已完成"""
    record = db.query(LearningRecord).filter(
        LearningRecord.id == record_id,
        LearningRecord.user_id == current_user.id,
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="学习记录不存在")

    record.status = "completed"
    record.completed_at = datetime.utcnow()

    if request.score is not None:
        record.score = request.score
    if request.time_spent is not None:
        record.time_spent = request.time_spent

    db.commit()
    db.refresh(record)

    return record
