"""Bounded multi-turn intake for the existing material-review Agent.

This module is deliberately a dialogue policy for Agent 1, not an additional
business Agent.  It turns an otherwise one-shot material check into a
two-turn minimum conversation and persists only compact, structured state.
"""

from __future__ import annotations

import re
from typing import Any

from .context_manager import ContextManager
from .llm_client import chat_json


MINIMUM_TURNS = 2
MAX_RECENT_MESSAGES = 6
MAX_MESSAGE_CHARS = 1800

REVIEW_DIALOGUE_SYSTEM = """你是“资料审查 Agent”的对话准入模块，不是新的 Agent，也不负责给学习者打分。

目标：根据学习者已经提供的资料，提出一个最有价值的补充问题；默认必须完成至少两轮学习者输入后，才可以进入正式能力诊断。

规则：
1. 只能依据程序注入的岗位信息、结构化摘要、最近对话和当前输入回答，不能编造简历、项目或技能。
2. 第 1 轮学习者输入后，decision 必须为 ask_followup，并且 question 只能问一个最关键的缺口。
3. 第 2 轮及以后：若已具备技能/实践/待补强方向中的足够证据，可 decision=ready_for_diagnosis；否则继续 ask_followup，每次只追问一个最重要的缺口。
4. force_finish=true 代表学习者明确选择“按当前资料进入诊断”。此时 decision 必须为 ready_for_diagnosis，但 missing 必须保留仍缺少的证据。
5. 问题应具体、简短、易回答，例如询问本人在项目中的职责、技术实现、验证方式或不熟悉的能力；不得泛泛要求“补充更多内容”。
6. summary 只保留已在用户输入中出现的事实，数组字段每项不超过 32 个汉字。

严格只输出 JSON：
{
  "decision": "ask_followup" | "ready_for_diagnosis",
  "question": "给学习者的一句追问；ready 时写空字符串",
  "missing": ["仍需补充的证据类型"],
  "summary": {
    "known_skills": ["已明确的技能"],
    "practice_evidence": ["已明确的实践"],
    "weak_or_unknown": ["不熟或未知能力"],
    "learning_goals": ["目标或方向"]
  },
  "reason": "一句准入判断依据"
}"""


def _clean_text(value: Any, limit: int = MAX_MESSAGE_CHARS) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _unique_items(values: Any, limit: int = 8) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        item = _clean_text(value, 32)
        if item and item not in seen:
            seen.add(item)
            output.append(item)
        if len(output) >= limit:
            break
    return output


def _summary_from(value: Any) -> dict[str, list[str]]:
    raw = value if isinstance(value, dict) else {}
    return {
        "known_skills": _unique_items(raw.get("known_skills")),
        "practice_evidence": _unique_items(raw.get("practice_evidence")),
        "weak_or_unknown": _unique_items(raw.get("weak_or_unknown")),
        "learning_goals": _unique_items(raw.get("learning_goals")),
    }


def _terms(text: str, candidates: list[str]) -> list[str]:
    return [item for item in candidates if item.lower() in text.lower()][:8]


def _fallback_summary(previous: dict[str, list[str]], text: str, target_job: str) -> dict[str, list[str]]:
    """Deterministic fallback when the external LLM is unavailable."""
    summary = _summary_from(previous)
    skills = _terms(text, [
        "Python", "Java", "JavaScript", "TypeScript", "Vue", "React", "Spring Boot",
        "FastAPI", "MySQL", "Redis", "Linux", "Docker", "Kubernetes", "Nginx",
        "需求分析", "用户研究", "原型", "数据分析", "Git", "接口", "测试",
    ])
    if skills:
        summary["known_skills"] = _unique_items(summary["known_skills"] + skills)
    if re.search(r"项目|实践|负责|开发|部署|实习|作品|实现", text):
        summary["practice_evidence"] = _unique_items(summary["practice_evidence"] + [text[:32]])
    if re.search(r"不会|不熟|欠缺|不足|不了解|没做过|不确定", text):
        summary["weak_or_unknown"] = _unique_items(summary["weak_or_unknown"] + [text[:32]])
    if re.search(r"想|目标|希望|提升|准备", text):
        summary["learning_goals"] = _unique_items(summary["learning_goals"] + [target_job])
    return summary


def _missing(summary: dict[str, list[str]]) -> list[str]:
    missing: list[str] = []
    if not summary["known_skills"]:
        missing.append("已掌握的技术或知识点")
    if not summary["practice_evidence"]:
        missing.append("项目或实践中的本人职责")
    if not summary["weak_or_unknown"]:
        missing.append("尚不熟悉或希望补强的能力")
    return missing


def _fallback_question(missing: list[str], target_job: str) -> str:
    if "项目或实践中的本人职责" in missing:
        return "请补充一个你亲自完成过的项目或实践：你负责了什么、用了哪些技术，以及如何验证结果？"
    if "已掌握的技术或知识点" in missing:
        return f"针对{target_job}，请补充你已经能独立完成的技术或任务，并说明掌握到什么程度。"
    if "尚不熟悉或希望补强的能力" in missing:
        return "请补充一项你目前还不熟悉、不会做或最希望提升的能力，便于系统识别补强方向。"
    return "请补充一个最能说明你能力层次的细节：项目中的个人职责、关键技术选择或遇到的问题如何解决。"


def _bounded_history(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for item in messages[-MAX_RECENT_MESSAGES:]:
        role = str(item.get("role") or "").strip()
        content = _clean_text(item.get("content"))
        if role in {"user", "assistant"} and content:
            history.append({"role": role, "content": content})
    return history


def review_turn(
    *,
    target_job: str,
    required_skills: list[str] | None,
    state: dict[str, Any] | None,
    history: list[dict[str, Any]],
    current_message: str,
    turn_count: int,
    minimum_turns: int = MINIMUM_TURNS,
    force_finish: bool = False,
) -> dict[str, Any]:
    """Return the next material-review dialogue decision with a bounded ledger."""
    safe_state = state if isinstance(state, dict) else {}
    prior_summary = _summary_from(safe_state.get("summary"))
    clean_message = _clean_text(current_message)
    recent_messages = _bounded_history(history)
    manager = ContextManager(trace_id=str(safe_state.get("trace_id") or "") or None)
    payload = {
        "target_job": _clean_text(target_job, 120),
        "required_skills": _unique_items(required_skills or [], 12),
        "dialogue_summary": prior_summary,
        "recent_messages": recent_messages,
        "current_message": clean_message,
        "turn_count": int(turn_count),
        "minimum_turns": int(max(MINIMUM_TURNS, minimum_turns)),
        "force_finish": bool(force_finish),
    }

    result: dict[str, Any] = {}
    try:
        result = chat_json(REVIEW_DIALOGUE_SYSTEM, str(payload)) or {}
    except Exception:
        result = {}

    llm_summary = _summary_from(result.get("summary"))
    fallback_summary = _fallback_summary(prior_summary, clean_message, target_job)
    summary = {
        key: _unique_items(fallback_summary[key] + llm_summary[key])
        for key in fallback_summary
    }
    missing = _unique_items(result.get("missing")) or _missing(summary)
    min_turns = max(MINIMUM_TURNS, int(minimum_turns or MINIMUM_TURNS))
    model_decision = str(result.get("decision") or "")
    requested_ready = model_decision == "ready_for_diagnosis"
    # “暂不补充” is a recorded second learner turn, not a way to bypass the
    # initial mandatory prompt through a hand-crafted first API request.
    can_force_finish = bool(force_finish and turn_count >= min_turns)
    ready = bool(can_force_finish or (turn_count >= min_turns and requested_ready and len(missing) <= 1))
    # A deterministic fallback may release a well-described second turn even
    # when an API response is unavailable; lack of an API must not block use.
    if turn_count >= min_turns and not missing:
        ready = True
    # When the external model is unavailable, do not trap the learner in an
    # endless follow-up loop. Two of the three evidence groups are sufficient
    # for a provisional diagnosis; the remaining gap stays visible downstream.
    if turn_count >= min_turns and not model_decision and len(missing) <= 1:
        ready = True
    if can_force_finish:
        ready = True

    question = "" if ready else _clean_text(result.get("question"), 180)
    if not ready and not question:
        question = _fallback_question(missing, target_job)
    decision = "ready_for_diagnosis" if ready else "ask_followup"
    reason = _clean_text(result.get("reason"), 180) or (
        "学习者选择按当前资料进入正式诊断。" if can_force_finish else
        "至少需要两轮学习者输入；请先补充第一轮资料后再决定是否跳过。" if force_finish else
        "已完成最少两轮资料审查，可以进入正式能力诊断。" if ready else
        "当前资料仍需要一项关键补充，才能更可靠地识别能力证据。"
    )
    output = {
        "decision": decision,
        "question": question,
        "missing": missing,
        "summary": summary,
        "reason": reason,
    }
    snapshot = manager.record("review_conversation", payload, output)
    previous_ledger = safe_state.get("context_ledger") if isinstance(safe_state.get("context_ledger"), list) else []
    return {
        **output,
        "trace_id": manager.trace_id,
        "context_ledger": (previous_ledger + [snapshot.as_dict()])[-12:],
    }
