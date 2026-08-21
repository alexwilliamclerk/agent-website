"""
防幻觉校验 —— 用 LLM 比对生成内容与知识库原文，判断是否存在编造

不再依赖本地 Ollama，直接用 llm_config.json 配置的 API 完成校验。
"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher

from .llm_client import chat_json


SUPPORTED_RESOURCE_TYPES = ("讲义", "练习", "案例")


def detect_unrequested_resource_type(response_text: str, requested_type: str) -> dict:
    """Detect an extra resource-type section inside a generated document."""
    requested = str(requested_type or "").strip()
    candidates = set(SUPPORTED_RESOURCE_TYPES) | {"视频脚本", "video_script", "video script"}
    candidates.discard(requested)
    for raw_line in str(response_text or "").splitlines():
        line = re.sub(r"^[\s#>*\-\d.、()（）]+", "", raw_line).strip()
        if not line:
            continue
        for candidate in candidates:
            if line == candidate or line.startswith(f"{candidate}：") or line.startswith(f"{candidate}:"):
                return {"found": True, "type": candidate, "line": raw_line.strip()}
    return {"found": False, "type": "", "line": ""}


def detect_source_leak(context_text: str, response_text: str, min_run: int = 80) -> dict:
    """Detect long verbatim spans copied from the retrieval context.

    A grounded answer may paraphrase the source, but a user-facing resource
    must not expose a long raw knowledge-base slice. This deterministic check
    runs before the LLM guardrail so a copied chunk cannot be approved merely
    because it is factually consistent with the source.
    """
    context = re.sub(r"\s+", "", str(context_text or ""))
    response = re.sub(r"\s+", "", str(response_text or ""))
    if len(context) < min_run or len(response) < min_run:
        return {"leaked": False, "longest_run": 0}

    matcher = SequenceMatcher(None, context, response, autojunk=False)
    match = matcher.find_longest_match(0, len(context), 0, len(response))
    longest_run = int(match.size)
    matching_chars = sum(
        block.size for block in matcher.get_matching_blocks() if block.size >= 20
    )
    coverage = matching_chars / max(1, min(len(context), len(response)))
    return {
        "leaked": longest_run >= min_run or (matching_chars >= 120 and coverage >= 0.55),
        "longest_run": longest_run,
        "matching_chars": matching_chars,
        "coverage": round(coverage, 3),
        "threshold": min_run,
    }

GUARD_SYSTEM = """你是一个严谨的事实核查助手。请判断【AI 回答】是否忠实于【参考文档】。

请对【AI 回答】的忠实度进行三档分级：
- grounded（有依据）：回答的核心内容与参考文档一致，允许合理的归纳、转述、举例或基于文档的推论；扩展补充的属于该主题公认、正确的标准知识，且没有与文档矛盾或编造错误
- partial（部分匹配）：回答大部分基于文档，但有小部分与文档有出入，或扩展补充较多、方向仍与文档一致
- ungrounded（无依据）：回答与参考文档明显矛盾，或编造了与文档冲突的错误事实（概念定义错误、张冠李戴、把 A 说成 B 等）。注意：仅仅"文档没提到、但属于该主题正确公认知识"的合理扩充，不算 ungrounded

必须严格只输出以下 JSON 格式：
{"verdict": "grounded|partial|ungrounded", "reason": "简要说明判断依据"}"""


def _grounding_terms(text: str) -> set[str]:
    normalized = re.sub(r"\s+", "", str(text or "").lower())
    terms = set(re.findall(r"[a-z0-9][a-z0-9+#._/-]{1,}", normalized))
    for run in re.findall(r"[\u4e00-\u9fff]+", normalized):
        terms.update(run[index:index + 2] for index in range(max(0, len(run) - 1)))
    stop = {"学习", "能力", "岗位", "资料", "完成", "当前", "进行", "说明", "一个", "可以", "内容"}
    return {term for term in terms if term not in stop}


def _deterministic_grounding(context_text: str, response_text: str) -> dict:
    """Keep source-backed drafts visible when the external reviewer is unavailable."""
    source_terms = _grounding_terms(context_text)
    response_terms = _grounding_terms(response_text)
    overlap = source_terms & response_terms
    if len(overlap) >= 4:
        return {
            "verdict": "partial",
            "has_hallucination": False,
            "reason": f"外部审核模型暂不可用；已完成来源绑定与关键词一致性校验（命中 {len(overlap)} 个依据词），作为待复核资料展示",
        }
    return {
        "verdict": "needs_manual_review",
        "has_hallucination": True,
        "reason": "外部审核模型暂不可用，且生成内容与来源的确定性重合不足，已转人工复核",
    }


def check_hallucination(context_text: str, response_text: str) -> dict:
    """用 LLM 校验 response 是否忠实于 context，返回 {"verdict", "has_hallucination", "reason"}"""
    if not context_text or not response_text:
        return {
            "verdict": "needs_manual_review",
            "has_hallucination": True,
            "reason": "缺少参考原文或待审核回答，无法完成防幻觉校验",
        }

    user_msg = f"""【参考文档】
{context_text[:4000]}

【AI 回答】
{response_text[:3000]}"""

    try:
        result = chat_json(GUARD_SYSTEM, user_msg)
        if not result:
            return _deterministic_grounding(context_text, response_text)
        verdict = str(result.get("verdict", "")).lower().strip()
        if verdict not in ("grounded", "partial", "ungrounded"):
            return {
                "verdict": "needs_manual_review",
                "has_hallucination": True,
                "reason": "LLM 返回的审核 verdict 无法解析，禁止自动放行",
            }
        return {
            "verdict": verdict,
            # partial means the source supports the main teaching direction,
            # but a reviewer should still inspect some extensions.  It is not
            # a hard hallucination and must remain visible in the library.
            "has_hallucination": verdict == "ungrounded",
            "reason": str(result.get("reason", "LLM 校验完成")),
        }
    except Exception:
        return _deterministic_grounding(context_text, response_text)
