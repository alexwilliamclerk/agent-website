"""Persisted, bounded material-review dialogue endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session as DBSession

from database import get_db
from models.session import Session, SessionMessage
from models.job import Job
from models.user import User
from routers.auth import get_current_user
from adapters.review_dialogue import MINIMUM_TURNS, review_turn

router = APIRouter()


# ===== 请求/响应模型 =====

class CreateSessionRequest(BaseModel):
    job_id: str
    minimum_turns: int = Field(default=MINIMUM_TURNS, ge=MINIMUM_TURNS, le=5)


class SessionResponse(BaseModel):
    id: str
    user_id: str
    job_id: str
    status: str
    current_step: int
    progress: float
    turn_count: int = 0
    minimum_turns: int = MINIMUM_TURNS
    ready_for_diagnosis: bool = False
    review_state: dict | None = None
    assessment_id: str | None = None
    started_at: datetime
    last_active_at: datetime


class MessageResponse(BaseModel):
    id: str
    role: str  # user 或 assistant
    content: str
    turn_index: int
    created_at: datetime


class ReviewTurnRequest(BaseModel):
    content: str = Field(min_length=2, max_length=6000)
    # Explicitly choosing not to supplement counts as the learner's next turn.
    force_finish: bool = False

    @field_validator("content")
    @classmethod
    def reject_blank_turn(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("每轮回答至少需要 2 个有效字符")
        return normalized


class ReviewTurnResponse(BaseModel):
    session_id: str
    turn_count: int
    minimum_turns: int
    decision: str
    assistant_message: str
    question: str = ""
    missing: list[str] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)
    reason: str = ""
    ready_for_diagnosis: bool = False
    can_skip_followup: bool = False
    context_trace_id: str


# ===== 接口 =====

@router.post("/create", response_model=SessionResponse, status_code=201)
def create_session(
    request: CreateSessionRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """创建学习会话"""
    if not db.query(Job.id).filter(Job.id == request.job_id).first():
        raise HTTPException(status_code=404, detail="目标岗位不存在")
    session = Session(
        user_id=current_user.id,
        job_id=request.job_id,
        status="reviewing",
        minimum_turns=max(MINIMUM_TURNS, request.minimum_turns),
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    return session


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """查询会话详情"""
    session = db.query(Session).filter(
        Session.id == session_id,
        Session.user_id == current_user.id,
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return session


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
def get_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Return actual persisted user and Agent turns for review continuity."""
    session = db.query(Session).filter(
        Session.id == session_id,
        Session.user_id == current_user.id,
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return (
        db.query(SessionMessage)
        .filter(SessionMessage.session_id == session.id, SessionMessage.user_id == current_user.id)
        .order_by(SessionMessage.created_at.asc(), SessionMessage.id.asc())
        .all()
    )


@router.post("/{session_id}/review-turn", response_model=ReviewTurnResponse)
def submit_review_turn(
    session_id: str,
    request: ReviewTurnRequest,
    current_user: User = Depends(get_current_user),
    db: DBSession = Depends(get_db),
):
    """Store one learner turn and ask/resolve the next material-review step.

    The conversation always requires at least two learner turns. The Agent only
    receives the compact review state plus the most recent turns, not a full
    unbounded history. This is the multi-turn entry gate for Agent 1.
    """
    session = db.query(Session).filter(
        Session.id == session_id,
        Session.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    if bool(session.ready_for_diagnosis):
        raise HTTPException(status_code=409, detail="本会话已完成资料审查，请进入能力诊断")

    job = db.query(Job).filter(Job.id == session.job_id).first()
    target_job = job.job_title if job else "目标岗位"
    required_skills = list(job.required_skills or []) if job else []
    history_rows = (
        db.query(SessionMessage)
        .filter(SessionMessage.session_id == session.id, SessionMessage.user_id == current_user.id)
        .order_by(SessionMessage.created_at.asc(), SessionMessage.id.asc())
        .all()
    )
    history = [{"role": item.role, "content": item.content} for item in history_rows]
    next_turn = max(0, int(session.turn_count or 0)) + 1
    result = review_turn(
        target_job=target_job,
        required_skills=required_skills,
        state=session.review_state or {},
        history=history,
        current_message=request.content,
        turn_count=next_turn,
        minimum_turns=max(MINIMUM_TURNS, int(session.minimum_turns or MINIMUM_TURNS)),
        force_finish=request.force_finish,
    )
    ready = result.get("decision") == "ready_for_diagnosis"
    question = str(result.get("question") or "")
    assistant_message = (
        "资料审查已完成。我会基于这两轮对话中的能力证据进入正式诊断。"
        if ready else f"我已记录这一轮信息。{question}"
    )

    db.add(SessionMessage(
        session_id=session.id,
        user_id=current_user.id,
        role="user",
        content=request.content.strip(),
        turn_index=next_turn,
    ))
    db.add(SessionMessage(
        session_id=session.id,
        user_id=current_user.id,
        role="assistant",
        content=assistant_message,
        turn_index=next_turn,
        context_snapshot={
            "decision": result.get("decision"),
            "missing": result.get("missing") or [],
            "summary": result.get("summary") or {},
            "trace_id": result.get("trace_id"),
        },
    ))
    session.turn_count = next_turn
    session.ready_for_diagnosis = 1 if ready else 0
    session.status = "ready_for_diagnosis" if ready else "reviewing"
    session.current_step = 2 if ready else 1
    session.review_state = {
        "trace_id": result.get("trace_id"),
        "summary": result.get("summary") or {},
        "missing": result.get("missing") or [],
        "last_decision": result.get("decision"),
        "last_question": question,
        "context_ledger": result.get("context_ledger") or [],
    }
    db.commit()

    return ReviewTurnResponse(
        session_id=session.id,
        turn_count=next_turn,
        minimum_turns=max(MINIMUM_TURNS, int(session.minimum_turns or MINIMUM_TURNS)),
        decision=str(result.get("decision") or "ask_followup"),
        assistant_message=assistant_message,
        question=question,
        missing=list(result.get("missing") or []),
        summary=dict(result.get("summary") or {}),
        reason=str(result.get("reason") or ""),
        ready_for_diagnosis=ready,
        can_skip_followup=not ready and next_turn >= 1,
        context_trace_id=str(result.get("trace_id") or ""),
    )
