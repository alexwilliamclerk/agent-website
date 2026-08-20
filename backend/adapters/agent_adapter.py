"""Drop-in adapter for PK-MACDM backend/adapters/agent_adapter.py.

The three public functions intentionally match the reference repository's
existing calls.  Do not change them to accept separate score, weekly-hours,
materials, or dialogue fields.
"""

from __future__ import annotations

from typing import Callable

from .agent_runtime import AgentRuntime


_runtime = AgentRuntime()


def diagnose(
    user_id: str,
    target_job: str,
    user_input: str,
    gold_labels: list[dict] | None = None,
    apply_corrections: bool = False,
    progress_callback: Callable[[str, int, str], None] | None = None,
) -> dict:
    """Diagnose one free-text description and optionally compare it with gold labels."""
    return _runtime.diagnose(
        user_id=user_id,
        target_job=target_job,
        user_input=user_input,
        gold_labels=gold_labels,
        apply_corrections=apply_corrections,
        progress_callback=progress_callback,
    )


def calibrate_existing(
    user_id: str,
    target_job: str,
    diagnosis: dict,
    user_input: str,
    gold_labels: list[dict],
    apply_corrections: bool = False,
) -> dict:
    """Calibrate an already stored diagnosis against reviewed outcomes."""
    return _runtime.calibrate_existing(
        user_id=user_id,
        target_job=target_job,
        diagnosis=diagnosis,
        user_input=user_input,
        gold_labels=gold_labels,
        apply_corrections=apply_corrections,
    )


def generate_resource(knowledge_point: str, user_level: float, resource_type: str, gap_id: str = "") -> dict:
    """Generate one resource using the current request's target-role context."""
    return _runtime.generate_resource(
        knowledge_point=knowledge_point,
        user_level=user_level,
        resource_type=resource_type,
    )


def plan_learning_path(user_id: str, target_job: str, current_ability: list) -> list:
    """Generate a path from the backend's raw 16-dimension vector."""
    return _runtime.plan_learning_path(
        user_id=user_id,
        target_job=target_job,
        current_ability=current_ability,
    )


def review_resources(package_id: str, resources: list[dict]) -> list[dict]:
    """层2：逐条资源做知识库校验（防幻觉），返回每条的校验结论。

    verdict → status 映射：grounded→passed / partial→partial /
    ungrounded→blocked / needs_manual_review→needs_manual_review
    """
    from .guardrail import check_hallucination, detect_source_leak, detect_unrequested_resource_type

    verdict_to_status = {
        "grounded": "passed",
        "partial": "partial",
        "ungrounded": "blocked",
        "needs_manual_review": "needs_manual_review",
    }
    results = []
    for r in resources:
        source_chunk_id = str(r.get("source_chunk_id") or "").strip()
        source_text = str(r.get("source_text") or "").strip()
        body = str(r.get("body") or "").strip()
        content_type = str(r.get("content_type") or "").strip()
        if not source_chunk_id or not source_text or not body or not content_type:
            results.append({
                "resource_id": r.get("resource_id", ""),
                "status": "blocked",
                "reason": "缺少资源类型、source_chunk_id、来源原文或资源正文，禁止进入正式资源包",
            })
            continue

        extra_type = detect_unrequested_resource_type(body, content_type)
        if extra_type.get("found"):
            results.append({
                "resource_id": r.get("resource_id", ""),
                "status": "blocked",
                "reason": f"资源类型为{content_type}，但正文追加了未请求的{extra_type.get('type')}章节，已拦截",
            })
            continue

        leak = detect_source_leak(source_text, body)
        if leak.get("leaked"):
            results.append({
                "resource_id": r.get("resource_id", ""),
                "status": "blocked",
                "reason": (
                    "检测到资源正文连续复制知识库原文，已拦截；"
                    f"最长连续重复约 {leak.get('longest_run', 0)} 个字符"
                ),
            })
            continue

        guard = check_hallucination(source_text, body)
        results.append({
            "resource_id": r.get("resource_id", ""),
            "status": verdict_to_status.get(guard.get("verdict"), "needs_manual_review"),
            "reason": guard.get("reason", ""),
        })
    return results


def get_last_trace() -> dict:
    """Optional hook for the future Agent dashboard; current backend ignores it."""
    return dict(_runtime.last_trace)
