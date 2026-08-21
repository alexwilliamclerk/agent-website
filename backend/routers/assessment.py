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
        .all()
    )
    if len(user_turns) < max(2, int(review_session.minimum_turns or 2)):
        raise HTTPException(status_code=409, detail="资料审查轮次不足，无法进入正式诊断")
    # Every learner turn participates in diagnosis. To keep model context
    # bounded for long conversations, distribute a fixed text budget across
    # all turns instead of silently dropping everything after turn eight.
    per_turn_chars = max(240, min(1800, 12000 // max(1, len(user_turns))))
    turns_text = "\n".join(
        f"【第{row.turn_index}轮学习者描述】\n{(row.content or '').strip()[:per_turn_chars]}"
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
    if not db.query(Job.id).filter(Job.id == request.job_id).first():
        raise HTTPException(status_code=404, detail="目标岗位不存在")
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
    if not job:
        raise HTTPException(status_code=404, detail="目标岗位不存在")
    target_job = job.job_title
    from adapters.input_review import review_input as _review

    return _review(request.user_input, target_job)


def _run_assessment(
    assessment_id: str,
    user_id: str,
    target_job: str,
    agent_input: str,
    gold_labels: list[dict],
    apply_corrections: bool,
    preserve_diagnosis: bool = False,
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

        _set_progress(
            assessment_id,
            "正在读取已有诊断" if preserve_diagnosis else "正在解析学习情况",
            44 if preserve_diagnosis else 5,
            stage="calibration" if preserve_diagnosis else "material",
            agent="协同调度器" if preserve_diagnosis else "资料解析 Agent",
        )

        def report(stage: str, percent: int, label: str) -> None:
            _set_progress(assessment_id, label, percent, stage=stage)

        if preserve_diagnosis:
            # A package repair must not silently change the score selected by
            # the learner or overwrite an expert/automatic calibration.  It
            # resumes from the persisted, completed diagnosis and rebuilds
            # only the learning path, resources and source review records.
            diagnosis = {
                "overall_mastery": float(assessment.overall_mastery or 0),
                "ability_vector": list(assessment.ability_vector or []),
                "ability_matrix": list(assessment.ability_matrix or []),
                "knowledge_gaps": list(assessment.knowledge_gaps or []),
                "gap_validation": list(assessment.gap_validation or []),
                "confidence": float(assessment.confidence or 0.3),
                "requirement_scores": list(assessment.requirement_scores or []),
                "calibration": dict(assessment.calibration_summary or {}),
                "calibration_records": [],
            }
            resource_ids = [
                row[0] for row in db.query(Resource.id).filter(
                    Resource.assessment_id == assessment.id
                ).all()
            ]
            if resource_ids:
                db.query(LearningRecord).filter(
                    LearningRecord.resource_id.in_(resource_ids)
                ).delete(synchronize_session=False)
                db.query(ResourceBookmark).filter(
                    ResourceBookmark.resource_id.in_(resource_ids)
                ).delete(synchronize_session=False)
            db.query(Resource).filter(
                Resource.assessment_id == assessment.id
            ).delete(synchronize_session=False)
            db.query(LearningPath).filter(
                LearningPath.assessment_id == assessment.id
            ).delete(synchronize_session=False)
            db.flush()
            _set_progress(assessment_id, "已保留诊断结果，开始重建学习包", 49, stage="calibration", agent="协同调度器")
        else:
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
        calibration = diagnosis.get("calibration") or assessment.calibration_summary or {
            "status": "unvalidated",
            "evaluated_count": 0,
            "accuracy": None,
            "mean_absolute_error": None,
        }
        if not preserve_diagnosis:
            assessment.calibration_status = calibration.get("status", "unvalidated")
            assessment.calibration_summary = calibration
            _persist_calibration_records(db, assessment.id, calibration, diagnosis.get("calibration_records", []))
        # Keep the seven-Agent result atomic: a diagnosis is not publishable
        # until its path, resources and source reviews are all persisted.
        db.flush()

        # ③ 路径规划 Agent。
        raw_vector = [item["value"] for item in diagnosis["ability_vector"]]
        _set_progress(assessment_id, "路径规划 Agent 正在生成学习顺序", 50, stage="path", agent="路径规划 Agent")
        path_steps = agent_adapter.plan_learning_path(
            user_id=user_id,
            target_job=target_job,
            current_ability=raw_vector,
        )
        _set_progress(assessment_id, "路径规划 Agent 已生成学习顺序", 54, stage="path", agent="路径规划 Agent")
        if not path_steps:
            raise RuntimeError("路径规划 Agent 未生成有效学习步骤")
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

        from adapters.agent_runtime import ROLE_PROFILES as _ROLES
        role = _ROLES.get(target_job, _ROLES["后端开发工程师"])
        skill_to_dimension = {skill: dimension for skill, dimension in role["skills"]}
        dimension_scores = {
            str(item.get("name") or ""): float(item.get("value") or 0)
            for item in diagnosis.get("ability_vector", []) if isinstance(item, dict)
        }
        ordered_weak_dimensions = sorted(dimension_scores, key=dimension_scores.get)

        def build_learner_context(knowledge_point: str, gap_id: str) -> dict:
            focus_dimension = skill_to_dimension.get(knowledge_point, "")
            if not focus_dimension:
                for skill, dimension in role["skills"]:
                    if skill.lower() in knowledge_point.lower() or knowledge_point.lower() in skill.lower():
                        focus_dimension = dimension
                        break
            if not focus_dimension:
                focus_dimension = ordered_weak_dimensions[0] if ordered_weak_dimensions else "岗位核心能力"

            gaps = [str(value) for value in diagnosis.get("knowledge_gaps", []) if str(value).strip()]
            focus_gap = next(
                (gap for gap in gaps if focus_dimension in gap or knowledge_point.lower() in gap.lower()),
                gaps[0] if gaps else f"{knowledge_point} 的可验证能力证据不足",
            )
            related_requirements = []
            evidence_ids = []
            for item in diagnosis.get("requirement_scores", []):
                if not isinstance(item, dict):
                    continue
                haystack = " ".join(str(item.get(key) or "") for key in ("requirement_name", "dimension"))
                if focus_dimension in haystack or knowledge_point.lower() in haystack.lower():
                    related_requirements.append({
                        "requirement_id": item.get("requirement_id"),
                        "requirement_name": item.get("requirement_name"),
                        "score": item.get("score"),
                        "status": item.get("status"),
                    })
                    raw_ids = item.get("evidence_ids") or ([item.get("evidence_id")] if item.get("evidence_id") else [])
                    evidence_ids.extend(str(value) for value in raw_ids if value)

            score = dimension_scores.get(focus_dimension, diagnosis.get("overall_mastery", 0))
            evidence_summary = (
                f"{focus_dimension}得分约 {float(score or 0):.0%}；"
                f"已关联 {len(set(evidence_ids))} 条能力证据；"
                f"用户资料摘要：{str(agent_input or '').strip()[:260]}"
            )
            return {
                "target_job": target_job,
                "ability_gap_id": gap_id,
                "focus_dimension": focus_dimension,
                "dimension_score": round(float(score or 0), 3),
                "focus_gap": focus_gap,
                "evidence_summary": evidence_summary,
                "related_requirements": related_requirements[:4],
                "evidence_ids": sorted(set(evidence_ids))[:8],
            }

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
                    learner_context=build_learner_context(knowledge_point, gap_id),
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
        low_dimensions = [item["name"] for item in diagnosis["ability_vector"] if item["value"] < 0.55]
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
                        learner_context=build_learner_context(skill_name, f"gap_fill_{dimension_name}"),
                    )
                    add_generated_resource(generated, skill_name, f"gap_fill_{dimension_name}")
                    generated_count += 1
        print(f"[CHECK] 覆盖维度: {len(covered_dimensions)}/{len(low_dimensions)} 低分维度, 资源总数: {len(generated_resources)}", flush=True)

        # ⑥ 审核纠偏 Agent：正式资源在完成来源绑定和幻觉校验后才可展示。
        _set_progress(assessment_id, "审核纠偏 Agent 正在校验来源与生成内容", 92, stage="review", agent="审核纠偏 Agent")
        review_results = agent_adapter.review_resources(f"pkg_{assessment.id}", generated_resources)
        visible_review_count = 0
        for result in review_results:
            resource = resource_by_id.get(result.get("resource_id"))
            if resource:
                resource.review_status = result.get("status")
                resource.review_reason = result.get("reason")
                if (
                    resource.review_status in {"passed", "partial"}
                    and str(resource.source_chunk_id or "").strip()
                    and str(resource.source_text or "").strip()
                ):
                    visible_review_count += 1
        if not generated_resources:
            raise RuntimeError("资源生成 Agent 未生成学习资料")
        if visible_review_count == 0:
            raise RuntimeError("审核纠偏 Agent 未产生可展示的来源绑定资料")
        _set_progress(assessment_id, "审核纠偏 Agent 已完成来源校验", 98, stage="review", agent="审核纠偏 Agent")

        # ⑦ 持久化并关闭任务。新诊断只有在资源与审核全部成功后才
        # 成为诊断页和资料库共同使用的当前记录。
        learner = db.query(User).filter(User.id == user_id).first()
        newer_submission = db.query(Assessment.id).filter(
            Assessment.user_id == user_id,
            Assessment.id != assessment.id,
            Assessment.overall_mastery.isnot(None),
            Assessment.created_at > assessment.created_at,
        ).first()
        if learner and not newer_submission:
            learner.active_assessment_id = assessment.id
        db.commit()
        db.refresh(assessment)
        _set_progress(assessment_id, "诊断、资源生成与审核全部完成", 100, status="completed", stage="complete", agent="协同调度器")
    except Exception as error:
        traceback.print_exc()
        db.rollback()
        # Release the completed review conversation so the learner can retry
        # a failed formal workflow without repeating the mandatory dialogue.
        db.query(LearningSession).filter(
            LearningSession.assessment_id == assessment_id,
            LearningSession.user_id == user_id,
        ).update({
            LearningSession.assessment_id: None,
            LearningSession.status: "ready_for_diagnosis",
            LearningSession.current_step: 2,
        }, synchronize_session=False)
        db.commit()
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

    job = db.query(Job).filter(Job.id == assessment.job_id).first()
    if not job:
        raise HTTPException(status_code=409, detail="当前诊断绑定的目标岗位已失效")

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
    if review_session.assessment_id:
        if review_session.assessment_id == assessment.id and assessment.user_input:
            db.refresh(assessment)
            return assessment
        raise HTTPException(status_code=409, detail="该资料审查会话已用于另一条诊断")
    if assessment.user_input:
        raise HTTPException(status_code=409, detail="该诊断已提交，请勿重复启动")
    # Do not trust a browser-assembled transcript. The server rebuilds the
    # diagnosis input from persisted, learner-authored conversation turns.
    agent_input = conversation_context
    if material_context:
        agent_input = f"{agent_input}\n\n{material_context}".strip()

    target_job = job.job_title
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


@router.post("/{assessment_id}/auto-calibrate")
def auto_calibrate_assessment(
    assessment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run one-click evidence-consistency calibration without a user form."""
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.user_id == current_user.id,
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="评估不存在")
    if assessment.overall_mastery is None:
        raise HTTPException(status_code=409, detail="评估尚未完成，不能自动校准")
    job = db.query(Job).filter(Job.id == assessment.job_id).first()
    if not job:
        raise HTTPException(status_code=409, detail="当前诊断绑定的目标岗位已失效")
    diagnosis = {
        "overall_mastery": float(assessment.overall_mastery),
        "ability_vector": assessment.ability_vector or [],
        "knowledge_gaps": assessment.knowledge_gaps or [],
        "requirement_scores": assessment.requirement_scores or [],
        "confidence": float(assessment.confidence or 0.3),
    }
    result = agent_adapter.auto_calibrate_existing(
        user_id=current_user.id,
        target_job=job.job_title,
        diagnosis=diagnosis,
        user_input=assessment.user_input or "",
    )
    summary = result["summary"]
    assessment.calibration_status = summary.get("status", "needs_review")
    assessment.calibration_summary = summary
    _persist_calibration_records(db, assessment.id, summary, result.get("records", []))
    db.commit()
    return {
        "assessment_id": assessment.id,
        "calibration": summary,
        "records": result.get("records", []),
        "diagnosis_updated": False,
    }


@router.post("/{assessment_id}/repair-learning-package")
def repair_learning_package(
    assessment_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rebuild path/resources for completed historical diagnoses.

    This repairs records created by older builds whose resource gate hid every
    item. The diagnosis ID stays stable, so diagnosis and library remain in
    sync while the downstream package is regenerated.
    """
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id,
        Assessment.user_id == current_user.id,
    ).first()
    if not assessment:
        raise HTTPException(status_code=404, detail="诊断记录不存在")
    if not assessment.user_input or assessment.overall_mastery is None:
        raise HTTPException(status_code=409, detail="诊断尚未完成，不能修复学习包")
    progress = _get_progress(assessment_id)
    if progress.get("status") in {"running", "waiting"} and 0 < int(progress.get("percent") or 0) < 100:
        return {"assessment_id": assessment.id, "status": "already_running"}
    job = db.query(Job).filter(Job.id == assessment.job_id).first()
    if not job:
        raise HTTPException(status_code=409, detail="当前诊断绑定的目标岗位已失效")

    # Deletion and regeneration run inside one background transaction. If RAG,
    # generation or review fails, rollback keeps the previous visible package.
    _set_progress(assessment.id, "正在修复本次学习路径与资源包", 2, status="waiting", stage="material", agent="协同调度器")
    background_tasks.add_task(
        _run_assessment,
        assessment.id,
        current_user.id,
        job.job_title,
        assessment.user_input,
        [],
        False,
        True,
    )
    return {"assessment_id": assessment.id, "status": "queued"}


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

    if assessment.overall_mastery is None:
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
    db.query(LearningSession).filter(
        LearningSession.assessment_id == assessment.id,
        LearningSession.user_id == current_user.id,
    ).update({
        LearningSession.assessment_id: None,
        LearningSession.status: "ready_for_diagnosis",
        LearningSession.current_step: 2,
    }, synchronize_session=False)
    learner = db.query(User).filter(User.id == current_user.id).first()
    was_active = bool(learner and learner.active_assessment_id == assessment.id)
    db.delete(assessment)
    if learner and was_active:
        replacement = db.query(Assessment).filter(
            Assessment.user_id == current_user.id,
            Assessment.id != assessment.id,
            Assessment.overall_mastery.isnot(None),
        ).order_by(Assessment.created_at.desc()).first()
        learner.active_assessment_id = replacement.id if replacement else None
    db.commit()
    _PROGRESS.pop(assessment_id, None)

    return {"message": "已删除"}
