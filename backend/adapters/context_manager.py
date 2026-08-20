"""Explicit, bounded context management for the serial Agent workflow.

The manager is deliberately small and dependency-free. It does not replace
the business agents; it controls what each stage is allowed to receive and
records an auditable context ledger for the Agent dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


CONTEXT_SCHEMA_VERSION = "agent-context.v1"
DEFAULT_PROMPT_VERSION = "2026-08-17"


STAGE_POLICIES: dict[str, dict[str, Any]] = {
    "review_conversation": {
        # Conversation is intentionally bounded: the Agent receives a compact
        # factual summary, the latest turns and the current reply, never an
        # unbounded chat transcript or unrelated RAG material.
        "allowed_inputs": {
            "target_job", "required_skills", "dialogue_summary", "recent_messages",
            "current_message", "turn_count", "minimum_turns", "force_finish",
        },
        "max_text_chars": 1800,
    },
    "parse_input": {
        "allowed_inputs": {"user_id", "target_job", "user_input", "career_skills"},
        "max_text_chars": 6000,
    },
    "retrieve_knowledge": {
        "allowed_inputs": {"target_job", "matched_skills", "negative_skills", "queries"},
        "max_text_chars": 1200,
        "max_sources": 120,
    },
    "diagnose_capability": {
        "allowed_inputs": {
            "target_job", "career_model_version", "matched_skills",
            "negative_skills", "action_evidence_count", "knowledge_catalog",
        },
        "max_text_chars": 4000,
    },
    "calibrate_result": {
        "allowed_inputs": {"diagnosis", "evidence_ids", "user_input_length"},
        "max_text_chars": 4000,
    },
    "calibrate_against_ground_truth": {
        "allowed_inputs": {"requirement_scores", "gold_labels", "apply_corrections"},
        "max_text_chars": 3000,
        "max_sources": 200,
    },
    "generate_resource": {
        "allowed_inputs": {
            "target_job", "knowledge_point", "user_level", "resource_type",
            "approved_sources", "requirement_id", "ability_gap_id",
        },
        "max_text_chars": 1200,
        "max_sources": 10,
    },
    "plan_path": {
        "allowed_inputs": {"user_id", "target_job", "ability_vector", "knowledge_catalog"},
        "max_text_chars": 2500,
    },
}


def _trim(value: Any, max_chars: int) -> Any:
    if isinstance(value, str):
        return value[:max_chars]
    if isinstance(value, list):
        return [_trim(item, max_chars) for item in value[:200]]
    if isinstance(value, tuple):
        return [_trim(item, max_chars) for item in value[:200]]
    if isinstance(value, dict):
        return {str(key): _trim(item, max_chars) for key, item in list(value.items())[:200]}
    return value


def _trim_sources(value: Any, max_chars: int, max_sources: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    sources: list[dict[str, Any]] = []
    for raw in value[:max_sources]:
        if not isinstance(raw, dict):
            continue
        source_id = str(raw.get("source_chunk_id") or raw.get("id") or "").strip()
        if not source_id:
            continue
        sources.append({
            "source_chunk_id": source_id,
            "title": str(raw.get("title") or "")[:240],
            "score": raw.get("score"),
            "content": str(raw.get("content") or "")[:max_chars],
        })
    return sources


@dataclass(frozen=True)
class ContextSnapshot:
    trace_id: str
    stage: str
    sequence: int
    schema_version: str
    prompt_version: str
    allowed_inputs: tuple[str, ...]
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    evidence_ids: tuple[str, ...] = ()
    source_chunk_ids: tuple[str, ...] = ()
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "stage": self.stage,
            "sequence": self.sequence,
            "schema_version": self.schema_version,
            "prompt_version": self.prompt_version,
            "allowed_inputs": list(self.allowed_inputs),
            "inputs": self.inputs,
            "outputs": self.outputs,
            "evidence_ids": list(self.evidence_ids),
            "source_chunk_ids": list(self.source_chunk_ids),
            "created_at": self.created_at,
        }


class ContextManager:
    """Create bounded stage contexts and an immutable audit ledger."""

    def __init__(self, trace_id: str | None = None, prompt_version: str = DEFAULT_PROMPT_VERSION):
        self.trace_id = trace_id or f"trace_{uuid4().hex[:12]}"
        self.prompt_version = prompt_version
        self._sequence = 0
        self._ledger: list[ContextSnapshot] = []

    def record(
        self,
        stage: str,
        inputs: dict[str, Any],
        outputs: dict[str, Any] | None = None,
        *,
        evidence_ids: list[str] | None = None,
        source_chunk_ids: list[str] | None = None,
    ) -> ContextSnapshot:
        policy = STAGE_POLICIES.get(stage, {"allowed_inputs": set(), "max_text_chars": 1200})
        allowed = set(policy.get("allowed_inputs", set()))
        max_chars = int(policy.get("max_text_chars", 1200))
        clean_inputs = {
            key: _trim(value, max_chars)
            for key, value in inputs.items()
            if key in allowed
        }
        if "retrieval_hits" in inputs:
            clean_inputs["approved_sources"] = _trim_sources(
                inputs.get("retrieval_hits"),
                max_chars,
                int(policy.get("max_sources", 20)),
            )
        if "approved_sources" in clean_inputs:
            clean_inputs["approved_sources"] = _trim_sources(
                clean_inputs["approved_sources"],
                max_chars,
                int(policy.get("max_sources", 20)),
            )
        clean_outputs = _trim(outputs or {}, max_chars)
        source_ids = set(str(item).strip() for item in (source_chunk_ids or []) if str(item).strip())
        for source in clean_inputs.get("approved_sources", []):
            source_ids.add(str(source.get("source_chunk_id")))
        self._sequence += 1
        snapshot = ContextSnapshot(
            trace_id=self.trace_id,
            stage=stage,
            sequence=self._sequence,
            schema_version=CONTEXT_SCHEMA_VERSION,
            prompt_version=self.prompt_version,
            allowed_inputs=tuple(sorted(allowed)),
            inputs=clean_inputs,
            outputs=clean_outputs,
            evidence_ids=tuple(sorted(set(str(item) for item in (evidence_ids or []) if str(item).strip()))),
            source_chunk_ids=tuple(sorted(source_ids)),
        )
        self._ledger.append(snapshot)
        return snapshot

    def as_dicts(self) -> list[dict[str, Any]]:
        return [snapshot.as_dict() for snapshot in self._ledger]
