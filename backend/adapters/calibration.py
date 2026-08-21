"""Ground-truth calibration for learner capability diagnoses.

This module deliberately separates three concepts:

* confidence: how much evidence the system had;
* calibration: how close a prediction is to a trusted reference result;
* hallucination review: whether generated content is grounded in the RAG source.

The calibrator never treats an LLM's self-reported confidence as ground truth.
It compares requirement-level predictions with objective results, unit tests,
expert labels, or human-reviewed practical outcomes supplied by an evaluator.
"""

from __future__ import annotations

import copy
import hashlib
import re
from statistics import mean
from typing import Any


CALIBRATION_VERSION = "ground-truth-calibration-v1"
AUTO_CALIBRATION_VERSION = "automatic-evidence-review-v3"
PASS_ACCURACY = 0.90
PASS_MAE = 0.15
REVIEW_ACCURACY = 0.75
REVIEW_MAE = 0.25
AUTO_REVIEW_TOLERANCE = 0.10

_ROLE_CODES = {
    "前端开发工程师": "frontend",
    "后端开发工程师": "backend",
    "运维工程师": "operations",
    "产品经理": "product",
}

_SKILL_CODES = {
    "HTML": "html",
    "CSS": "css",
    "JavaScript": "javascript",
    "Vue": "vue",
    "React": "react",
    "TypeScript": "typescript",
    "浏览器原理": "browser_principles",
    "响应式设计": "responsive_design",
    "Webpack/Vite": "bundler",
    "前端性能优化": "frontend_performance",
    "API设计": "api_design",
    "接口联调": "api_integration",
    "Git": "git",
    "单元测试": "unit_testing",
    "网络协议": "network_protocols",
    "安全编码": "secure_coding",
    "Python": "python",
    "Java": "java",
    "数据结构与算法": "data_structures_algorithms",
    "Spring Boot": "spring_boot",
    "FastAPI": "fastapi",
    "并发编程": "concurrency",
    "MySQL": "mysql",
    "Redis": "redis",
    "系统设计": "system_design",
    "Linux": "linux",
    "Docker": "docker",
    "认证与授权": "authentication_authorization",
    "Kubernetes": "kubernetes",
    "Nginx": "nginx",
    "Shell脚本": "shell",
    "监控告警": "monitoring_alerting",
    "CI/CD": "cicd",
    "日志管理": "logging",
    "故障排查": "troubleshooting",
    "数据库": "database",
    "安全规范": "security_practices",
    "云服务": "cloud_services",
    "自动化测试": "automated_testing",
    "需求分析": "requirements_analysis",
    "用户研究": "user_research",
    "产品设计": "product_design",
    "数据分析": "data_analysis",
    "竞品分析": "competitive_analysis",
    "业务理解": "business_understanding",
    "原型设计": "prototyping",
    "文档撰写": "documentation",
    "沟通协调": "communication",
    "项目推进": "project_delivery",
    "项目管理": "project_management",
    "逻辑思维": "logical_thinking",
    "技术理解": "technical_understanding",
    "接口基础": "api_basics",
    "数据安全": "data_security",
    "用户体验": "user_experience",
}


def requirement_id(target_job: str, requirement_name: str) -> str:
    """Return the stable ID used by tests, traces, and calibration records."""
    role_code = _ROLE_CODES.get(str(target_job).strip(), "unknown")
    name = str(requirement_name or "").strip()
    code = _SKILL_CODES.get(name)
    if not code:
        code = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "unknown"
    return f"{role_code}.{code}"


def _clamp_score(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(min(1.0, max(0.0, number)), 4)


def _status_from_score(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 0.65:
        return "qualified"
    if score >= 0.35:
        return "partial"
    return "gap"


def _normalize_status(value: Any) -> str | None:
    value = str(value or "").strip().lower()
    aliases = {
        "qualified": "qualified",
        "达标": "qualified",
        "已达标": "qualified",
        "pass": "qualified",
        "passed": "qualified",
        "partial": "partial",
        "部分达标": "partial",
        "部分": "partial",
        "gap": "gap",
        "未达标": "gap",
        "缺口": "gap",
        "fail": "gap",
        "failed": "gap",
        "unknown": "unknown",
        "证据不足": "unknown",
    }
    return aliases.get(value)


def _profile_value(profile: Any, skill: str) -> tuple[float, list[str]]:
    matched = getattr(profile, "matched_skills", None)
    if matched is None and isinstance(profile, dict):
        matched = profile.get("matched_skills", {})
    matched = matched or {}
    negatives = getattr(profile, "negative_skills", None)
    if negatives is None and isinstance(profile, dict):
        negatives = profile.get("negative_skills", [])
    negatives = set(negatives or [])
    if skill in negatives:
        return 0.25, []
    raw = matched.get(skill, 0.52)
    score = _clamp_score(raw) or 0.52
    text = getattr(profile, "text", "")
    if isinstance(profile, dict):
        text = profile.get("text", "")
    digest = hashlib.sha1(str(text).encode("utf-8")).hexdigest()[:12]
    evidence = [f"ev_input_{digest}_{_SKILL_CODES.get(skill, 'skill')}"] if skill in matched else []
    return score, evidence


def build_requirement_scores(
    target_job: str,
    role_skills: list[tuple[str, str]],
    profile: Any,
    model_scores: Any = None,
) -> list[dict[str, Any]]:
    """Build a stable requirement-level prediction list.

    Model output is accepted only when it can be matched to a known role
    requirement. Missing or malformed model items fall back to the deterministic
    profile evidence score, so the calibration layer always has a comparable
    record and never invents a new requirement.
    """
    known = {requirement_id(target_job, name): (name, dimension) for name, dimension in role_skills}
    by_id: dict[str, dict[str, Any]] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for raw in model_scores if isinstance(model_scores, list) else []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("requirement_name") or raw.get("name") or raw.get("skill") or "").strip()
        rid = str(raw.get("requirement_id") or "").strip()
        if not rid and name:
            rid = requirement_id(target_job, name)
        if rid not in known and name not in {item[0] for item in role_skills}:
            continue
        if rid not in known:
            rid = requirement_id(target_job, name)
        if rid not in known:
            continue
        known_name, dimension = known[rid]
        score = _clamp_score(raw.get("score", raw.get("value")))
        if score is None:
            continue
        item = {
            "requirement_id": rid,
            "requirement_name": known_name,
            "dimension": dimension,
            "score": score,
            "status": _normalize_status(raw.get("status")) or _status_from_score(score),
            "evidence_ids": [str(x) for x in (raw.get("evidence_ids") or []) if str(x).strip()],
            "prediction_source": "model",
        }
        by_id[rid] = item
        by_name[known_name] = item

    result: list[dict[str, Any]] = []
    for skill, dimension in role_skills:
        rid = requirement_id(target_job, skill)
        item = by_id.get(rid) or by_name.get(skill)
        if item is None:
            score, evidence_ids = _profile_value(profile, skill)
            item = {
                "requirement_id": rid,
                "requirement_name": skill,
                "dimension": dimension,
                "score": round(score, 4),
                "status": _status_from_score(score),
                "evidence_ids": evidence_ids,
                "prediction_source": "evidence_rules",
            }
        else:
            item = dict(item)
            if not item.get("evidence_ids"):
                _, evidence_ids = _profile_value(profile, skill)
                item["evidence_ids"] = evidence_ids
        result.append(item)
    return result


def build_automatic_evidence_labels(
    target_job: str,
    role_skills: list[tuple[str, str]],
    profile: Any,
) -> list[dict[str, Any]]:
    """Create reproducible automatic evidence-review labels.

    These labels are not presented as human ground truth. They let the seventh
    Agent perform a one-click consistency calibration while the original
    expert-label API remains available for the competition test set.
    """
    labels: list[dict[str, Any]] = []
    matched = getattr(profile, "matched_skills", {}) or {}
    negatives = set(getattr(profile, "negative_skills", set()) or set())
    action_count = int(getattr(profile, "action_evidence_count", 0) or 0)
    text = str(getattr(profile, "text", "") or "")
    has_result = bool(re.search(
        r"测试|通过|上线|部署|压测|优化|指标|截图|提交|验收|复现|故障|修复|结果",
        text,
        flags=re.IGNORECASE,
    ))
    evidence_bonus = 0.06 if has_result else 0.0
    action_bonus = min(0.08, action_count * 0.01)
    for skill, _dimension in role_skills:
        if skill in negatives:
            score = 0.25
            explanation = "学习者明确表示尚未掌握该能力"
        elif skill in matched:
            score = min(0.92, max(0.35, float(matched[skill])) + evidence_bonus + action_bonus)
            explanation = "描述中存在能力关键词、行动表达和可验证结果信号"
        else:
            # 自动复核只能评价本轮明确出现的证据。把未提及能力统一
            # 设为 0.50 会制造大量伪标签，并在阈值附近把一致结果判错。
            continue
        labels.append({
            "requirement_id": requirement_id(target_job, skill),
            "requirement_name": skill,
            "gold_score": round(score, 4),
            "gold_status": _status_from_score(score),
            "source_type": "auto_evidence_review",
            "trusted": False,
            "reference_answer": explanation,
        })
    return labels


def _label_requirement_id(target_job: str, label: dict[str, Any]) -> str:
    rid = str(label.get("requirement_id") or "").strip()
    if rid:
        return rid
    name = str(label.get("requirement_name") or label.get("skill_name") or label.get("name") or "").strip()
    return requirement_id(target_job, name) if name else ""


class GroundTruthCalibrationAgent:
    """Compare AI predictions with trusted reference outcomes.

    The agent is intentionally deterministic. A different LLM judging the
    first LLM would still be an estimate, not ground truth. Ambiguous labels
    should be sent to human review and only then marked trusted.
    """

    name = "真实结果校准 Agent"

    def run(
        self,
        target_job: str,
        diagnosis: dict[str, Any],
        role_skills: list[tuple[str, str]],
        dimensions: list[tuple[int, str, str]],
        profile: Any,
        gold_labels: list[dict[str, Any]] | None = None,
        apply_corrections: bool = False,
    ) -> dict[str, Any]:
        predictions = build_requirement_scores(
            target_job,
            role_skills,
            profile,
            diagnosis.get("requirement_scores"),
        )
        prediction_by_id = {item["requirement_id"]: item for item in predictions}
        prediction_by_name = {item["requirement_name"]: item for item in predictions}
        labels = gold_labels if isinstance(gold_labels, list) else []
        records: list[dict[str, Any]] = []
        corrections: dict[str, float] = {}
        invalid_labels = 0

        for raw in labels:
            if not isinstance(raw, dict):
                invalid_labels += 1
                continue
            rid = _label_requirement_id(target_job, raw)
            prediction = prediction_by_id.get(rid)
            if prediction is None:
                name = str(raw.get("requirement_name") or raw.get("skill_name") or raw.get("name") or "").strip()
                prediction = prediction_by_name.get(name)
                if prediction:
                    rid = prediction["requirement_id"]
            if prediction is None:
                invalid_labels += 1
                continue

            gold_score = _clamp_score(
                raw.get("gold_score", raw.get("score", raw.get("mastery_score")))
            )
            gold_status = _normalize_status(raw.get("gold_status", raw.get("status")))
            if gold_status is None:
                gold_status = _status_from_score(gold_score)
            if gold_score is None and gold_status is None:
                invalid_labels += 1
                continue

            predicted_score = _clamp_score(prediction.get("score"))
            predicted_status = _normalize_status(prediction.get("status")) or _status_from_score(predicted_score)
            absolute_error = None
            if predicted_score is not None and gold_score is not None:
                absolute_error = round(abs(predicted_score - gold_score), 4)
            status_correct = (
                predicted_status is not None
                and gold_status is not None
                and predicted_status == gold_status
            )
            # 有连续分数时，优先按数值误差判定；0.65 的分类边界附近
            # 即使状态标签不同，也不能把 0.07 的分数误差算成完全错误。
            score_correct = absolute_error is not None and absolute_error <= PASS_MAE
            is_correct = score_correct if absolute_error is not None else status_correct
            if absolute_error is not None:
                if absolute_error <= PASS_MAE:
                    record_status = "passed"
                elif absolute_error <= REVIEW_MAE:
                    record_status = "needs_review"
                else:
                    record_status = "rejected"
            else:
                record_status = "passed" if status_correct else "rejected"

            source_type = str(raw.get("source_type") or "expert").strip()
            trusted = bool(raw.get("trusted", True))
            record = {
                "requirement_id": rid,
                "requirement_name": prediction["requirement_name"],
                "predicted_score": predicted_score,
                "gold_score": gold_score,
                "absolute_error": absolute_error,
                "predicted_status": predicted_status,
                "gold_status": gold_status,
                "status": record_status,
                "is_correct": bool(is_correct),
                "status_correct": bool(status_correct),
                "score_correct": bool(score_correct) if absolute_error is not None else None,
                "trusted": trusted,
                "source_type": source_type,
                "reference_answer": str(raw.get("reference_answer") or raw.get("actual_result") or ""),
                "evidence_ids": list(prediction.get("evidence_ids") or []),
            }
            records.append(record)
            if apply_corrections and trusted and gold_score is not None:
                corrections[rid] = gold_score

        evaluated_count = len(records)
        accuracy = round(sum(1 for item in records if item["is_correct"]) / evaluated_count, 4) if evaluated_count else None
        status_accuracy = round(sum(1 for item in records if item["status_correct"]) / evaluated_count, 4) if evaluated_count else None
        errors = [item["absolute_error"] for item in records if item["absolute_error"] is not None]
        mae = round(mean(errors), 4) if errors else None
        if evaluated_count == 0:
            status = "unvalidated"
        elif accuracy is not None and accuracy >= PASS_ACCURACY and (mae is None or mae <= PASS_MAE):
            status = "passed"
        elif accuracy is not None and accuracy >= REVIEW_ACCURACY and (mae is None or mae <= REVIEW_MAE):
            status = "needs_review"
        else:
            status = "rejected"

        corrected_diagnosis = copy.deepcopy(diagnosis)
        correction_applied = False
        if corrections:
            corrected_diagnosis = self._apply_corrections(
                corrected_diagnosis,
                predictions,
                corrections,
                role_skills,
                dimensions,
            )
            correction_applied = True

        summary = {
            "status": status,
            "version": CALIBRATION_VERSION,
            "evaluated_count": evaluated_count,
            "prediction_count": len(predictions),
            "label_coverage": round(evaluated_count / max(1, len(predictions)), 4),
            "accuracy": accuracy,
            "score_accuracy": accuracy,
            "status_accuracy": status_accuracy,
            "mean_absolute_error": mae,
            "pass_accuracy_target": PASS_ACCURACY,
            "pass_mae_target": PASS_MAE,
            "invalid_label_count": invalid_labels,
            "correction_applied": correction_applied,
            "needs_human_review": status in {"needs_review", "rejected"},
            "unvalidated_reason": "没有提供可信的标准结果" if evaluated_count == 0 else None,
        }
        return {
            "summary": summary,
            "records": records,
            "requirement_scores": corrected_diagnosis.get("requirement_scores", predictions),
            "diagnosis": corrected_diagnosis if correction_applied else diagnosis,
        }

    def _apply_corrections(
        self,
        diagnosis: dict[str, Any],
        predictions: list[dict[str, Any]],
        corrections: dict[str, float],
        role_skills: list[tuple[str, str]],
        dimensions: list[tuple[int, str, str]],
    ) -> dict[str, Any]:
        score_map = {item["requirement_id"]: float(item["score"]) for item in predictions}
        score_map.update(corrections)
        corrected_scores = []
        for item in predictions:
            score = round(score_map[item["requirement_id"]], 4)
            corrected_scores.append({
                **item,
                "score": score,
                "status": _status_from_score(score),
                "prediction_source": "trusted_ground_truth" if item["requirement_id"] in corrections else item.get("prediction_source", "evidence_rules"),
            })

        old_vector = {str(item.get("name")): dict(item) for item in diagnosis.get("ability_vector", []) if isinstance(item, dict)}
        corrected_vector: list[dict[str, Any]] = []
        for index, name, category in dimensions:
            items = [
                score_map[item["requirement_id"]]
                for item in predictions
                if item["dimension"] == name and item["requirement_id"] in score_map
            ]
            old = old_vector.get(name, {"index": index, "name": name, "weight": "low", "category": category, "value": 0.18})
            value = round(sum(items) / len(items), 4) if items else float(old.get("value", 0.18))
            corrected_vector.append({
                "index": int(old.get("index", index)),
                "name": name,
                "value": min(1.0, max(0.0, value)),
                "weight": old.get("weight", "low"),
                "category": old.get("category", category),
            })

        weighted = {"high": 1.6, "mid": 1.0, "low": 0.5}
        denominator = sum(weighted.get(item["weight"], 1.0) for item in corrected_vector) or 1.0
        overall = round(sum(item["value"] * weighted.get(item["weight"], 1.0) for item in corrected_vector) / denominator, 4)
        gaps = [item["requirement_name"] for item in corrected_scores if float(item["score"]) < 0.55][:15]
        diagnosis["ability_vector"] = corrected_vector
        diagnosis["overall_mastery"] = overall
        diagnosis["knowledge_gaps"] = gaps
        diagnosis["requirement_scores"] = corrected_scores
        diagnosis["calibration_corrections"] = corrections
        return diagnosis
