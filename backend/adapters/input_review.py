"""
输入完整性审查 —— 用 LLM 判断学习者描述是否足以支撑一次能力诊断

仿照 guardrail.py：固定 system prompt + chat_json + 容错兜底。
宽松标准：能识别目标职业 + 至少一类实质内容（会什么/不会什么/做过项目/想提升）即放行。
"""

from __future__ import annotations

import re

from .llm_client import chat_json

INPUT_REVIEW_SYSTEM = """你是一个学习情况输入的完整性审查器。学习者会用自由文本描述自己的目标职业、已会技能、项目经历、不会/不熟的知识点、想提升的方向。

请判断这段描述是否「足够支撑一次能力诊断」。宽松标准：
- sufficient=true：能识别出目标职业，且能提取到「会/熟悉的技术或知识点」「做过的项目或实践」「不会或没做过的知识点」「想提升的方向」中至少一类实质内容。
- sufficient=false：内容几乎空白、只有一句空话、只说了目标职业但没有任何技能或经历、或含糊到无法用于诊断。

必须严格只输出以下 JSON 格式：
{"sufficient": true|false, "missing": ["缺少/不足的方面"], "hint": "一句话告诉用户该怎么补充（中文、友善、具体）"}"""

MIN_CHARS = 20


def review_input(user_input: str, target_job: str) -> dict:
    """判断输入是否足以支撑诊断，返回 {"sufficient", "missing", "hint"}"""
    text = re.sub(r"\s+", " ", str(user_input or "")).strip()

    # 规则预检：过短直接判不足，不发 LLM
    if len(text) < MIN_CHARS:
        return {
            "sufficient": False,
            "missing": ["实质内容过少"],
            "hint": "描述太短了，请再补充一些你会什么、做过什么项目、或者不会什么（参考填写格式）。",
        }

    user_msg = f"""目标职业：{target_job}

学习者描述：
{text}"""

    try:
        result = chat_json(INPUT_REVIEW_SYSTEM, user_msg)
        if not result:
            return {"sufficient": True, "missing": [], "hint": ""}
        sufficient = bool(result.get("sufficient", True))
        missing = result.get("missing") or []
        if not isinstance(missing, list):
            missing = [str(missing)]
        hint = str(result.get("hint", "") or "")
        return {"sufficient": sufficient, "missing": missing, "hint": hint}
    except Exception:
        return {"sufficient": True, "missing": [], "hint": ""}
