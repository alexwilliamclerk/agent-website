"""
评估模块 - 创建评估、提交用户输入、查询结果
"""

import asyncio
import json
import traceback
import uuid
from datetime import datetime, timezone
from threading import Lock
from time import monotonic
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models.assessment import Assessment
from models.calibration import CalibrationRecord
from models.path import LearningPath
from models.resource import Resource
from models.job import Job
from models.user import User
from models.material import UserMaterial
from models.learning_record import LearningRecord
from models.resource_bookmark import ResourceBookmark
from models.session import Session as LearningSession, SessionMessage
from routers.auth import get_current_user
from adapters import agent_adapter

router = APIRouter()


# ===== 诊断进度（当前单进程运行时的实时状态）=====
_PROGRESS: dict[str, dict] = {}
_PROGRESS_LOCK = Lock()


def _progress_stage(percent: int) -> tuple[str, str]:
    """Map a numeric progress value to the Agent currently responsible for the work."""
    if percent >= 100:
        return "complete", "协同调度器"
    if percent >= 92:
        return "review", "审核纠偏 Agent"
    if percent >= 55:
        return "resource", "资源生成 Agent"
    if percent >= 50:
        return "path", "路径规划 Agent"
    if percent >= 42:
        return "calibration", "真实结果校准 Agent"
    if percent >= 30:
        return "diagnosis", "能力诊断 Agent"
    if percent >= 18:
        return "retrieval", "知识库检索 Agent"
    return "material", "资料解析 Agent"


def _set_progress(
    assessment_id: str,
    label: str,
    percent: int,
    *,
    status: str = "running",
    stage: str | None = None,
    agent: str | None = None,
) -> None:
    """Record current progress and retain a bounded event history for the live Agent panel."""
    safe_percent = max(0, min(100, int(percent)))
    mapped_stage, mapped_agent = _progress_stage(safe_percent)
    stage = stage or mapped_stage
    agent = agent or mapped_agent
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    with _PROGRESS_LOCK:
        previous = _PROGRESS.get(assessment_id, {})
        if status != "failed" and safe_percent < int(previous.get("percent", 0) or 0):
            safe_percent = int(previous.get("percent", 0) or 0)
        events = list(previous.get("events", []))
        event = {
            "stage": stage,
            "agent": agent,
            "label": label,
            "percent": safe_percent,
            "status": status,
            "updated_at": now,
        }
        if not events or any(event[key] != events[-1].get(key) for key in ("stage", "label", "percent", "status")):
            events.append(event)
        # Resource generation can produce dozens of fine-grained events. Keep
        # a bounded but complete-enough audit window so early material/RAG/
        # diagnosis stages are not pushed out of the final Agent trace.
        _PROGRESS[assessment_id] = {**event, "events": events[-200:]}


def _get_progress(assessment_id: str) -> dict:
    """Read a snapshot so the streaming endpoint never iterates a live mutable list."""
    with _PROGRESS_LOCK:
        current = _PROGRESS.get(assessment_id)
        if current is None:
            return {
                "stage": "material",
                "agent": "资料解析 Agent",
                "label": "等待任务启动",
                "percent": 0,
                "status": "waiting",
                "updated_at": None,
                "events": [],
            }
        return {**current, "events": list(current.get("events", []))}


def _persist_calibration_records(db: Session, assessment_id: str, calibration: dict, records: list[dict]) -> None:
    """Replace the requirement-level records for one assessment."""
    db.query(CalibrationRecord).filter(
        CalibrationRecord.assessment_id == assessment_id
    ).delete(synchronize_session=False)
    for item in records or []:
        db.add(CalibrationRecord(
            assessment_id=assessment_id,
            requirement_id=str(item.get("requirement_id") or "unknown"),
            requirement_name=str(item.get("requirement_name") or "未命名能力"),
            predicted_score=item.get("predicted_score"),
            gold_score=item.get("gold_score"),
            absolute_error=item.get("absolute_error"),
            predicted_status=item.get("predicted_status"),
            gold_status=item.get("gold_status"),
            status=str(item.get("status") or "needs_review"),
            is_correct=1 if item.get("is_correct") else 0,
            trusted=1 if item.get("trusted", True) else 0,
            source_type=str(item.get("source_type") or "expert"),
            reference_answer=str(item.get("reference_answer") or ""),
            evidence_ids=item.get("evidence_ids") or [],
            details=item,
            calibration_version=str(calibration.get("version") or "ground-truth-calibration-v1"),
        ))


# ===== 请求/响应模型 =====

class CreateAssessmentRequest(BaseModel):
    job_id: str


class SubmitAssessmentRequest(BaseModel):
    user_input: str  # 用户自由文本输入
    # 仅供测试/评审阶段提交。普通学习者不需要填写。
    gold_labels: list[dict] = Field(default_factory=list)
    apply_corrections: bool = False
    material_ids: list[str] = Field(default_factory=list)
    # A ready review session is the authoritative multi-turn input source.
    session_id: str | None = None


class CalibrationSubmissionRequest(BaseModel):
    """专家/客观测评回填的真实结果。"""

    gold_labels: list[dict] = Field(default_factory=list)
    apply_corrections: bool = False


class ReviewInputRequest(BaseModel):
    job_id: str
    user_input: str


class ReviewInputResponse(BaseModel):
    sufficient: bool
    missing: list[str]
    hint: str


def _review_session_context(
    db: Session,
    *,
    session_id: str,
    user_id: str,
    job_id: str,
) -> tuple[LearningSession, str]:
    """Build a bounded, learner-authored context from a completed review session."""
    review_session = db.query(LearningSession).filter(
        LearningSession.id == session_id,
        LearningSession.user_id == user_id,
    ).first()
    if not review_session:
        raise HTTPException(status_code=404, detail="资料审查会话不存在")
    if review_session.job_id != job_id:
        raise HTTPException(status_code=400, detail="资料审查会话与当前目标岗位不一致")
    if not bool(review_session.ready_for_diagnosis):
        raise HTTPException(status_code=409, detail="请先完成至少两轮资料审查，或选择按当前资料进入诊断")

    user_turns = (
        db.query(SessionMessage)
        .filter(
            SessionMessage.session_id == review_session.id,
            SessionMessage.user_id == user_id,
            SessionMessage.role == "user",
        )
        .order_by(SessionMessage.created_at.asc(), SessionMessage.id.asc())
        .limit(8)
        .all()
    )
    if len(user_turns) < max(2, int(review_session.minimum_turns or 2)):
        raise HTTPException(status_code=409, detail="资料审查轮次不足，无法进入正式诊断")
    turns_text = "\n".join(
        f"【第{row.turn_index}轮学习者描述】\n{(row.content or '').strip()[:1800]}"
        for row in user_turns
        if (row.content or "").strip()
    )
    review_state = review_session.review_state if isinstance(review_session.review_state, dict) else {}
    summary = review_state.get("summary") if isinstance(review_state.get("summary"), dict) else {}
    summary_text = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))[:1600]
    return review_session, f"【多轮资料审查上下文】\n{turns_text}\n\n【已确认的能力证据摘要】\n{summary_text}".strip()


class DimensionItem(BaseModel):
    """能力向量的单个维度"""
    index: int
    name: str
    value: float
    weight: Literal["high", "mid", "low"]
    category: str


class AssessmentResponse(BaseModel):
    id: str
    user_id: str
    job_id: str
    user_input: str | None = None
    overall_mastery: float | None = None
    ability_vector: list[DimensionItem] | None = None
    ability_matrix: list | None = None
    knowledge_gaps: list | None = None
    gap_validation: list | None = None
    confidence: float | None = None
    requirement_scores: list | None = None
    calibration_status: str | None = None
    calibration_summary: dict | None = None
    created_at: datetime


class DiagnosisResponse(BaseModel):
    overall_mastery: float
    ability_vector: list[DimensionItem]
    ability_matrix: list
    knowledge_gaps: list
    confidence: float
    requirement_scores: list = Field(default_factory=list)
    calibration_status: str = "unvalidated"
    calibration_summary: dict = Field(default_factory=dict)


class AssessmentListItem(BaseModel):
    """评估历史列表项（轻量，不含ability_vector）"""
    id: str
    user_id: str
    job_id: str
    overall_mastery: float | None = None
    knowledge_gaps: list | None = None
    created_at: datetime


# ===== 接口 =====

@router.get("/list", response_model=list[AssessmentListItem])
def list_assessments(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的评估历史，按创建时间倒序"""
    return (
        db.query(Assessment)
        .filter(Assessment.user_id == current_user.id)
        .order_by(Assessment.created_at.desc())
        .all()
    )


@router.post("/create", response_model=AssessmentResponse, status_code=201)
def create_assessment(
    request: CreateAssessmentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建评估"""
    assessment = Assessment(
        user_id=current_user.id,
        job_id=request.job_id,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)

    return assessment


@router.post("/review-input", response_model=ReviewInputResponse)
def review_input(
    request: ReviewInputRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """兼容旧客户端的轻量预检；该接口不能启动正式诊断。"""
    job = db.query(Job).filter(Job.id == request.job_id).first()
    target_job = job.job_title if job else ""
    from adapters.input_review import review_input as _review

    return _review(request.user_input, target_job)


def _run_assessment(
    assessment_id: str,
    user_id: str,
    target_job: str,
    agent_input: str,
    gold_labels: list[dict],
    apply_corrections: bool,
) -> None:
    """Run the expensive seven-Agent workflow outside the submit request.

    The request only persists the input and queues this function.  A separate
    SQLAlchemy session is required because the request session is closed as
    soon as FastAPI sends the 200 response.
    """
    db = SessionLocal()
    try:
        assessment = db.query(Assessment).filter(
            Assessment.id == assessment_id,
            Assessment.user_id == user_id,
        ).first()
        if not assessment:
            _set_progress(assessment_id, "评估不存在，任务已停止", 0, status="failed")
            return

        _set_progress(assessment_id, "正在解析学习情况", 5, stage="material", agent="资料解析 Agent")

        def report(stage: str, percent: int, label: str) -> None:
            _set_progress(assessment_id, label, percent, stage=stage)

        # ① 七 Agent 串行诊断：解析 → RAG → 能力诊断 → 校准 → 真实结果校准。
        # 解析、检索和评分阶段由 runtime 回调报告，避免提交接口提前制造跳跃进度。
        diagnosis = agent_adapter.diagnose(
            user_id=user_id,
            target_job=target_job,
            user_input=agent_input,
            gold_labels=gold_labels,
            apply_corrections=apply_corrections,
            progress_callback=report,
        )
        assessment.agent_trace = agent_adapter.get_last_trace()
        _set_progress(assessment_id, "能力诊断与真实结果校准完成", 49, stage="calibration", agent="真实结果校准 Agent")

        print(f"[DEBUG] knowledge_gaps: {diagnosis.get('knowledge_gaps')}", flush=True)
        print(f"[DEBUG] overall_mastery: {diagnosis.get('overall_mastery')}", flush=True)
        print(f"[DEBUG] ability_vector count: {len(diagnosis.get('ability_vector', []))}", flush=True)

        # ② 更新评估结果。
        assessment.overall_mastery = diagnosis["overall_mastery"]
        assessment.ability_vector = diagnosis["ability_vector"]
        assessment.ability_matrix = diagnosis.get("ability_matrix", [])
        assessment.knowledge_gaps = diagnosis["knowledge_gaps"]
        assessment.gap_validation = diagnosis.get("gap_validation", [])
        assessment.confidence = diagnosis["confidence"]
        assessment.requirement_scores = diagnosis.get("requirement_scores", [])
        calibration = diagnosis.get("calibration") or {
            "status": "unvalidated",
            "evaluated_count": 0,
            "accuracy": None,
            "mean_absolute_error": None,
        }
        assessment.calibration_status = calibration.get("status", "unvalidated")
        assessment.calibration_summary = calibration
        _persist_calibration_records(db, assessment.id, calibration, diagnosis.get("calibration_records", []))
        db.commit()

        # ③ 路径规划 Agent。
        raw_vector = [item["value"] for item in diagnosis["ability_vector"]]
        _set_progress(assessment_id, "路径规划 Agent 正在生成学习顺序", 50, stage="path", agent="路径规划 Agent")
        path_steps = agent_adapter.plan_learning_path(
            user_id=user_id,
            target_job=target_job,
            current_ability=raw_vector,
        )
        _set_progress(assessment_id, "路径规划 Agent 已生成学习顺序", 54, stage="path", agent="路径规划 Agent")
        if path_steps:
            db.add(LearningPath(
                user_id=user_id,
                job_id=assessment.job_id,
                assessment_id=assessment.id,
                steps=path_steps,
                current_step=1,
                status="active",
            ))

        # ④ 资源生成 Agent：每个资源生成前、后都发出进度事件。
        seen_points = set()
        path_knowledge_points = []
        for step in path_steps:
            knowledge_point = step.get("knowledge_point", "")
            if knowledge_point and knowledge_point not in seen_points:
                seen_points.add(knowledge_point)
                path_knowledge_points.append(knowledge_point)

        resource_types = ["讲义", "练习"]
        generated_resources = []
        resource_by_id = {}
        total_resources = max(1, len(path_knowledge_points) * len(resource_types))
        generated_count = 0

        def add_generated_resource(generated: dict, knowledge_point: str, gap_id: str) -> None:
            resource = Resource(
                id=str(uuid.uuid4()),
                assessment_id=assessment.id,
                knowledge_point=knowledge_point,
                content_type=generated["content_type"],
                title=generated["title"],
                body=generated["body"],
                difficulty=generated.get("difficulty"),
                source_chunk_id=generated.get("source_chunk_id"),
                source_text=generated.get("source_text"),
                source_title=generated.get("source_title"),
                source_score=generated.get("source_score"),
                generation_method=generated.get("generation_method"),
            )
            db.add(resource)
            resource_by_id[resource.id] = resource
            generated_resources.append({
                "resource_id": resource.id,
                "title": generated["title"],
                "body": generated["body"],
                "content_type": generated["content_type"],
                "gap_id": generated.get("gap_id", gap_id),
                "source_chunk_id": generated.get("source_chunk_id", ""),
                "source_text": generated.get("source_text", ""),
            })

        for index, knowledge_point in enumerate(path_knowledge_points):
            gap_id = f"gap_{index + 1:03d}"
            for resource_type in resource_types:
                next_percent = min(91, 55 + round(35 * generated_count / total_resources))
                _set_progress(
                    assessment_id,
                    f"资源生成 Agent 正在生成「{knowledge_point}」{resource_type}",
                    next_percent,
                    stage="resource",
                    agent="资源生成 Agent",
                )
                generated = agent_adapter.generate_resource(
                    knowledge_point=knowledge_point,
                    user_level=diagnosis["overall_mastery"],
                    resource_type=resource_type,
                    gap_id=gap_id,
                )
                add_generated_resource(generated, knowledge_point, gap_id)
                generated_count += 1
                _set_progress(
                    assessment_id,
                    f"资源生成 Agent 已完成 ({generated_count}/{total_resources})",
                    min(91, 55 + round(35 * generated_count / total_resources)),
                    stage="resource",
                    agent="资源生成 Agent",
                )

        # ⑤ 完整性兜底：低分维度缺少路径覆盖时补资源，仍走同一条审核链。
        from adapters.agent_runtime import ROLE_PROFILES as _ROLES
        role = _ROLES.get(target_job, _ROLES["后端开发工程师"])
        skill_to_dimension = {skill: dimension for skill, dimension in role["skills"]}
        covered_dimensions = set()
        for knowledge_point in path_knowledge_points:
            dimension = skill_to_dimension.get(knowledge_point)
            if dimension:
                covered_dimensions.add(dimension)
            else:
                for skill, dimension in skill_to_dimension.items():
                    if skill.lower() in knowledge_point.lower() or any(keyword.lower() in knowledge_point.lower() for keyword in skill.lower().split()):
                        covered_dimensions.add(dimension)
                        break
        low_dimensions = [item["name"] for item in diagnosis["ability_vector"] if item["value"] < 0.6]
        missing_dimensions = [dimension for dimension in low_dimensions if dimension not in covered_dimensions]
        if missing_dimensions:
            print(f"[CHECK] 低分维度缺失: {missing_dimensions}，自动补资源", flush=True)
            for dimension_name in missing_dimensions[:3]:
                dimension_skills = [(skill, dimension) for skill, dimension in role["skills"] if dimension == dimension_name]
                if not dimension_skills:
                    continue
                skill_name = dimension_skills[0][0]
                if skill_name in seen_points:
                    continue
                seen_points.add(skill_name)
                for resource_type in resource_types:
                    _set_progress(
                        assessment_id,
                        f"资源生成 Agent 正在补齐「{skill_name}」{resource_type}",
                        min(91, 55 + round(35 * generated_count / max(total_resources, generated_count + 1))),
                        stage="resource",
                        agent="资源生成 Agent",
                    )
                    generated = agent_adapter.generate_resource(
                        knowledge_point=skill_name,
                        user_level=diagnosis["overall_mastery"],
                        resource_type=resource_type,
                        gap_id=f"gap_fill_{dimension_name}",
                    )
                    add_generated_resource(generated, skill_name, f"gap_fill_{dimension_name}")
                    generated_count += 1
        print(f"[CHECK] 覆盖维度: {len(covered_dimensions)}/{len(low_dimensions)} 低分维度, 资源总数: {len(generated_resources)}", flush=True)

        # ⑥ 审核纠偏 Agent：正式资源在完成来源绑定和幻觉校验后才可展示。
        _set_progress(assessment_id, "审核纠偏 Agent 正在校验来源与生成内容", 92, stage="review", agent="审核纠偏 Agent")
        review_results = agent_adapter.review_resources(f"pkg_{assessment.id}", generated_resources)
        for result in review_results:
            resource = resource_by_id.get(result.get("resource_id"))
            if resource:
                resource.review_status = result.get("status")
                resource.review_reason = result.get("reason")
        _set_progress(assessment_id, "审核纠偏 Agent 已完成来源校验", 98, stage="review", agent="审核纠偏 Agent")

        # ⑦ 持久化并关闭任务。
        db.commit()
        db.refresh(assessment)
        _set_progress(assessment_id, "诊断、资源生成与审核全部完成", 100, status="completed", stage="complete", agent="协同调度器")
    except Exception as error:
        traceback.print_exc()
        db.rollback()
        current = _get_progress(assessment_id)
        _set_progress(
            assessment_id,
            f"任务执行失败：{error}",
            current.get("percent", 0),
            status="failed",
            stage=current.get("stage", "material"),
            agent=current.get("agent", "资料解析 Agent"),
        )
    finally:
        db.close()


@router.post("/{assessment_id}/submit", response_model=AssessmentResponse)
def submit_assessment(
    assessment_id: str,
    request: SubmitAssessmentRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persist the submission and queue the expensive Agent workflow.

    Returning before the LLM/RAG work starts is essential: the browser can
    immediately query ``/progress`` and render the actual Agent state.
    """
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.user_id == current_user.id,
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="评估不存在")

    materials = []
    if request.material_ids:
        materials = db.query(UserMaterial).filter(
            UserMaterial.id.in_(request.material_ids),
            UserMaterial.user_id == current_user.id,
        ).all()
        if len(materials) != len(set(request.material_ids)):
            raise HTTPException(status_code=400, detail="存在无权限或不存在的资料")
    usable_materials = [item for item in materials if item.status == "parsed" and (item.extracted_text or "").strip()]
    material_context = "\n\n".join(
        f"【已提交资料：{item.original_name}】\n{(item.extracted_text or '')[:6000]}"
        for item in usable_materials
    )
    if not request.session_id:
        raise HTTPException(status_code=409, detail="请先完成至少两轮资料审查，再启动正式能力诊断")
    review_session, conversation_context = _review_session_context(
        db,
        session_id=request.session_id,
        user_id=current_user.id,
        job_id=assessment.job_id,
    )
    # Do not trust a browser-assembled transcript. The server rebuilds the
    # diagnosis input from persisted, learner-authored conversation turns.
    agent_input = conversation_context
    if material_context:
        agent_input = f"{agent_input}\n\n{material_context}".strip()

    job = db.query(Job).filter(Job.id == assessment.job_id).first()
    target_job = job.job_title if job else ""
    assessment.user_input = agent_input
    assessment.material_ids = [item.id for item in materials]
    for item in materials:
        item.assessment_id = assessment.id
    review_session.assessment_id = assessment.id
    review_session.status = "completed"
    review_session.current_step = 3
    db.commit()
    _set_progress(assessment.id, "任务已创建，等待 Agent 启动", 2, status="waiting", stage="material", agent="资料解析 Agent")

    background_tasks.add_task(
        _run_assessment,
        assessment.id,
        current_user.id,
        target_job,
        agent_input,
        request.gold_labels,
        request.apply_corrections,
    )
    db.refresh(assessment)
    return assessment


@router.post("/{assessment_id}/calibrate")
def calibrate_assessment(
    assessment_id: str,
    request: CalibrationSubmissionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """回填客观题、实操结果或专家标注，重新校准已有诊断。"""
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.user_id == current_user.id,
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="评估不存在")
    if assessment.overall_mastery is None:
        raise HTTPException(status_code=400, detail="评估尚未完成，不能校准")

    job = db.query(Job).filter(Job.id == assessment.job_id).first()
    target_job = job.job_title if job else ""
    diagnosis = {
        "overall_mastery": float(assessment.overall_mastery),
        "ability_vector": assessment.ability_vector or [],
        "knowledge_gaps": assessment.knowledge_gaps or [],
        "requirement_scores": assessment.requirement_scores or [],
        "confidence": float(assessment.confidence or 0.3),
    }
    result = agent_adapter.calibrate_existing(
        user_id=current_user.id,
        target_job=target_job,
        diagnosis=diagnosis,
        user_input=assessment.user_input or "",
        gold_labels=request.gold_labels,
        apply_corrections=request.apply_corrections,
    )
    calibrated = result["diagnosis"]
    summary = result["summary"]
    assessment.calibration_status = summary.get("status", "unvalidated")
    assessment.calibration_summary = summary
    assessment.requirement_scores = calibrated.get("requirement_scores", diagnosis["requirement_scores"])
    if summary.get("correction_applied"):
        assessment.overall_mastery = calibrated.get("overall_mastery", assessment.overall_mastery)
        assessment.ability_vector = calibrated.get("ability_vector", assessment.ability_vector)
        assessment.knowledge_gaps = calibrated.get("knowledge_gaps", assessment.knowledge_gaps)
    _persist_calibration_records(db, assessment.id, summary, result.get("records", []))
    db.commit()
    db.refresh(assessment)
    return {
        "assessment_id": assessment.id,
        "calibration": summary,
        "records": result.get("records", []),
        "diagnosis_updated": bool(summary.get("correction_applied")),
    }


@router.get("/{assessment_id}/calibration")
def get_calibration(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询一次评估的校准汇总和逐能力项误差。"""
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.user_id == current_user.id,
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="评估不存在")
    records = db.query(CalibrationRecord).filter(
        CalibrationRecord.assessment_id == assessment.id
    ).order_by(CalibrationRecord.created_at.asc()).all()
    return {
        "assessment_id": assessment.id,
        "status": assessment.calibration_status or "unvalidated",
        "summary": assessment.calibration_summary or {
            "status": "unvalidated",
            "evaluated_count": 0,
            "accuracy": None,
            "mean_absolute_error": None,
        },
        "records": [
            {
                "id": record.id,
                "requirement_id": record.requirement_id,
                "requirement_name": record.requirement_name,
                "predicted_score": float(record.predicted_score) if record.predicted_score is not None else None,
                "gold_score": float(record.gold_score) if record.gold_score is not None else None,
                "absolute_error": float(record.absolute_error) if record.absolute_error is not None else None,
                "predicted_status": record.predicted_status,
                "gold_status": record.gold_status,
                "status": record.status,
                "is_correct": bool(record.is_correct),
                "trusted": bool(record.trusted),
                "source_type": record.source_type,
                "evidence_ids": record.evidence_ids or [],
                "created_at": record.created_at,
            }
            for record in records
        ],
    }


@router.get("/{assessment_id}", response_model=AssessmentResponse)
def get_assessment(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询评估结果"""
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.user_id == current_user.id,
    ).first()

    if not assessment:
        raise HTTPException(status_code=404, detail="评估不存在")

    return assessment


@router.get("/{assessment_id}/progress")
def get_progress(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询某次诊断的当前进度（供前端轮询）"""
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.user_id == current_user.id,
    ).first()

    if not assessment:
        raise HTTPException(status_code=404, detail="评估不存在")

    return _get_progress(assessment_id)


@router.get("/{assessment_id}/progress/stream")
async def stream_progress(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream verified Agent progress so the UI does not wait for the final result."""
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.user_id == current_user.id,
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="评估不存在")

    async def events():
        last_payload = ""
        deadline = monotonic() + 15 * 60
        while monotonic() < deadline:
            snapshot = _get_progress(assessment_id)
            payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
            if payload != last_payload:
                yield f"event: progress\ndata: {payload}\n\n"
                last_payload = payload
            if snapshot.get("status") in {"completed", "failed"}:
                yield f"event: done\ndata: {payload}\n\n"
                return
            await asyncio.sleep(0.45)

        snapshot = _get_progress(assessment_id)
        payload = json.dumps({
            **snapshot,
            "status": "failed",
            "label": "实时进度连接超时，请刷新后查看任务状态",
        }, ensure_ascii=False, separators=(",", ":"))
        yield f"event: done\ndata: {payload}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/{assessment_id}/agents")
def get_agent_trace(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the persisted trace for the review workspace, plus live progress while running."""
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.user_id == current_user.id,
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="评估不存在")
    return {
        "assessment_id": assessment.id,
        "progress": _get_progress(assessment_id),
        "trace": assessment.agent_trace or {"agents": []},
    }


@router.get("/{assessment_id}/diagnosis", response_model=DiagnosisResponse)
def get_diagnosis(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询诊断报告"""
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.user_id == current_user.id,
    ).first()

    if not assessment:
        raise HTTPException(status_code=404, detail="评估不存在")

    if not assessment.overall_mastery:
        raise HTTPException(status_code=400, detail="评估尚未完成")

    return {
        "overall_mastery": float(assessment.overall_mastery),
        "ability_vector": assessment.ability_vector,
        "ability_matrix": assessment.ability_matrix or [],
        "knowledge_gaps": assessment.knowledge_gaps,
        "confidence": float(assessment.confidence),
        "requirement_scores": assessment.requirement_scores or [],
        "calibration_status": assessment.calibration_status or "unvalidated",
        "calibration_summary": assessment.calibration_summary or {
            "status": "unvalidated",
            "evaluated_count": 0,
            "accuracy": None,
            "mean_absolute_error": None,
        },
    }


@router.delete("/{assessment_id}")
def delete_assessment(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除评估记录"""
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.user_id == current_user.id,
    ).first()

    if not assessment:
        raise HTTPException(status_code=404, detail="评估不存在")

    resource_ids = [row[0] for row in db.query(Resource.id).filter(
        Resource.assessment_id == assessment.id
    ).all()]
    if resource_ids:
        db.query(ResourceBookmark).filter(
            ResourceBookmark.resource_id.in_(resource_ids)
        ).delete(synchronize_session=False)
        db.query(LearningRecord).filter(
            LearningRecord.resource_id.in_(resource_ids)
        ).delete(synchronize_session=False)
        db.query(Resource).filter(
            Resource.id.in_(resource_ids)
        ).delete(synchronize_session=False)
    db.query(LearningPath).filter(
        LearningPath.assessment_id == assessment.id
    ).delete(synchronize_session=False)
    db.query(CalibrationRecord).filter(
        CalibrationRecord.assessment_id == assessment.id
    ).delete(synchronize_session=False)
    db.query(UserMaterial).filter(
        UserMaterial.assessment_id == assessment.id,
        UserMaterial.user_id == current_user.id,
    ).update({UserMaterial.assessment_id: None}, synchronize_session=False)
    db.delete(assessment)
    db.commit()
    _PROGRESS.pop(assessment_id, None)

    return {"message": "已删除"}
