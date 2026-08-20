"""Prompt loader for the backend's real DeepSeek/Qwen adapter.

The deterministic runtime does not call a model.  The backend model adapter
can import this registry to build the exact serial prompt for each stage.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json


ROOT = Path(__file__).resolve().parent
PROMPT_ROOT = ROOT / "prompts"
WORKFLOW_PATH = ROOT / "workflow" / "serial-workflow.json"


def load_workflow() -> dict[str, Any]:
    return json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))


def build_prompt(stage_id: str, payload: dict[str, Any]) -> str:
    workflow = load_workflow()
    stage = next((item for item in workflow["stages"] if item["id"] == stage_id), None)
    if stage is None:
        raise ValueError(f"未知 Agent 阶段：{stage_id}")
    shared = (PROMPT_ROOT / "00_shared_output_rules.md").read_text(encoding="utf-8")
    specialist = (ROOT / stage["prompt"]).read_text(encoding="utf-8")
    injected = json.dumps(payload, ensure_ascii=False, indent=2)
    return "\n\n".join([
        f"Prompt-Version: {workflow['version']}",
        f"Stage-Order: {stage['order']}",
        f"Expected-Output-Fields: {', '.join(stage['output'])}",
        f"On-Failure: {stage.get('on_failure', 'manual_review')}",
        shared,
        specialist,
        "程序注入的 JSON 输入：\n```json\n" + injected + "\n```",
        "只返回当前阶段约定的 JSON 输出，不要返回下一阶段内容。",
    ])


def build_serial_prompt(stage_id: str, state: dict[str, Any]) -> str:
    """Build one stage prompt from the accumulated serial workflow state.

    The model adapter should call this function after the previous stage has
    passed validation. It prevents a stage from accidentally receiving the
    whole mutable state or inventing fields that were not produced upstream.
    """
    workflow = load_workflow()
    stage = next((item for item in workflow["stages"] if item["id"] == stage_id), None)
    if stage is None:
        raise ValueError(f"未知 Agent 阶段：{stage_id}")
    missing = [key for key in stage["input"] if key not in state]
    if missing:
        raise ValueError(f"阶段 {stage_id} 缺少上游输出：{', '.join(missing)}")
    payload = {key: state[key] for key in stage["input"]}
    return build_prompt(stage_id, payload)
