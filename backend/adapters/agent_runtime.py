"""Multi-Agent runtime with DeepSeek LLM integration.

Each Agent has a distinct identity (system prompt) and calls the DeepSeek API
for semantic reasoning.  When DEEPSEEK_API_KEY is not set, agents fall back to
the deterministic rule-based logic.

Agent pipeline (serial, seven stages):
  InputParsingAgent → RAGEvidenceAgent → CapabilityScoringAgent → CalibrationAgent
  → GroundTruthCalibrationAgent → ResourceAgent → PathAgent

The post-generation guardrail is a review service, not an eighth Agent. It checks
source binding, source leakage and hallucination before resources become visible.

Public contracts:
  * diagnose(user_id, target_job, user_input, gold_labels=None)
  * generate_resource(knowledge_point, user_level, resource_type)
  * plan_learning_path(user_id, target_job, current_ability)
"""

from __future__ import annotations

import json
import os
import re
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
from uuid import uuid4

from .guardrail import check_hallucination, detect_unrequested_resource_type
from .llm_client import chat, chat_json, chat_json_value
from .calibration import (
    AUTO_CALIBRATION_VERSION,
    GroundTruthCalibrationAgent,
    build_automatic_evidence_labels,
    build_requirement_scores,
)
from .context_manager import ContextManager

def _check_llm() -> bool:
    try:
        from .llm_client import _load_config
        cfg = _load_config()
        return bool(cfg.get("api_key", ""))
    except Exception:
        return False

_LLM_AVAILABLE = _check_llm()


DIMENSIONS = [
    (1, "编程基础", "通用基础"),
    (2, "数据结构与算法", "通用基础"),
    (3, "计算机网络", "通用基础"),
    (4, "操作系统", "通用基础"),
    (5, "前端技术", "专业方向"),
    (6, "后端技术", "专业方向"),
    (7, "数据库", "专业方向"),
    (8, "系统设计", "专业方向"),
    (9, "运维部署", "专业方向"),
    (10, "测试与质量", "专业方向"),
    (11, "产品分析", "专业方向"),
    (12, "项目管理", "专业方向"),
    (13, "沟通表达", "综合素质"),
    (14, "逻辑思维", "综合素质"),
    (15, "学习能力", "综合素质"),
    (16, "安全规范", "综合素质"),
]


JOB_ALIASES = {
    "前端工程师": "前端开发工程师",
    "前端开发": "前端开发工程师",
    "后端工程师": "后端开发工程师",
    "后端开发": "后端开发工程师",
    "Java后端工程师": "后端开发工程师",
    "java后端工程师": "后端开发工程师",
    "运维": "运维工程师",
    "DevOps工程师": "运维工程师",
    "产品": "产品经理",
}


def normalize_job(job: str) -> str:
    name = str(job or "").strip()
    return JOB_ALIASES.get(name, name)


_TOPIC_NOISE = re.compile(
    r"构建失败|加载失败|生成失败|视频脚本|开场引入|总结提问|复制粘贴|"
    r"点击这里|暂无内容|待生成|unknown|error|failed|dedication|主要作者|本文编写中",
    re.IGNORECASE,
)


def _clean_topic(value: Any, fallback: str = "") -> str:
    """Turn a retrieved heading into a stable learner-facing knowledge point."""
    text = str(value or "").strip()
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^[\s#>*`_\-–—\d.、()（）]+", "", text)
    text = re.sub(r"^(问题|Q|Question)[：:]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip(" ：:，,。；;|-")
    if not text or _TOPIC_NOISE.search(text):
        return str(fallback or "").strip()
    if len(text) > 54:
        text = re.split(r"[。；;！？!?]", text, maxsplit=1)[0].strip()
    if len(text) > 54:
        text = text[:53].rstrip() + "…"
    return text or str(fallback or "").strip()


def _topic_from_source(content: str, fallback: str) -> str:
    candidates = []
    for pattern in (
        r"(?:问题|Question)[：:]\s*(.+?)(?:\n|$)",
        r"(?:^|\n)\s*[-*]?\s*Q[：:]\s*(.+?)(?:\n|$)",
        r"(?:^|\n)\s*#{1,4}\s+(.+?)(?:\n|$)",
    ):
        match = re.search(pattern, str(content or ""), flags=re.IGNORECASE)
        if match:
            candidates.append(match.group(1))
    for candidate in candidates:
        topic = _clean_topic(candidate)
        if topic:
            if fallback and fallback.lower() not in topic.lower() and len(topic) < 30:
                return f"{fallback}：{topic}"
            return topic
    return _clean_topic(fallback, "岗位核心能力")


def _clean_source_for_learning(content: str) -> str:
    """Remove transport/Markdown noise while preserving teachable source facts."""
    text = str(content or "")
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"^[\s#>*`_\-]+", "", raw).strip()
        if not line or _TOPIC_NOISE.search(line):
            continue
        if re.match(r"^(参考资料|提取码|作者|source|id)[：:]", line, re.IGNORECASE):
            continue
        lines.append(line)
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


def _source_learning_points(hits: list[dict[str, Any]], limit: int = 4) -> list[str]:
    """Extract short source-grounded points without exposing raw chunks."""
    points: list[str] = []
    seen = set()
    for hit in hits:
        cleaned = _clean_source_for_learning(str(hit.get("content") or ""))
        for segment in re.split(r"[。！？!?；;]", cleaned):
            point = segment.strip(" ：:，,")
            if len(point) < 12:
                continue
            point = point[:56].rstrip("，,：:")
            key = re.sub(r"\s+", "", point).lower()
            if key in seen:
                continue
            seen.add(key)
            points.append(point)
            if len(points) >= limit:
                return points
    return points


def _usable_source_hits(hits: list[dict[str, Any]], knowledge_point: str) -> list[dict[str, Any]]:
    """Prefer readable, topic-related chunks over noisy repository fragments."""
    english_terms = set(re.findall(r"[a-z0-9+#._/-]{2,}", knowledge_point.lower()))
    chinese_terms = set()
    for run in re.findall(r"[\u4e00-\u9fff]+", knowledge_point):
        chinese_terms.update(run[index:index + 2] for index in range(max(0, len(run) - 1)))
    terms = english_terms | chinese_terms
    ranked = []
    for hit in hits:
        source_id = str(hit.get("source_chunk_id") or "").strip()
        content = str(hit.get("content") or "")
        cleaned = _clean_source_for_learning(content)
        if not source_id or len(cleaned) < 70:
            continue
        if re.search(r"dedication|提取码|加群|二维码", cleaned[:260], re.IGNORECASE):
            continue
        raw_requirement_ids = hit.get("candidate_requirement_ids") or []
        if isinstance(raw_requirement_ids, (list, tuple, set)):
            requirement_ids = " ".join(str(value) for value in raw_requirement_ids)
        else:
            requirement_ids = str(raw_requirement_ids)
        searchable = f"{hit.get('title', '')} {content} {requirement_ids}".lower()
        relevance = sum(1 for term in terms if term.lower() in searchable)
        ranked.append((relevance, float(hit.get("score") or 0), hit))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    related = [item[2] for item in ranked if item[0] > 0]
    return related[:8] or [item[2] for item in ranked[:5]]


def sanitize_learning_path_steps(
    steps: list[Any] | None,
    target_job: str = "",
    knowledge_catalog: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Normalize generated and persisted path steps for learner-facing APIs."""
    role = normalize_job(target_job)
    role_fallbacks = [skill for skill, _dimension in ROLE_PROFILES.get(role, {}).get("skills", [])]
    fallbacks = [
        topic for topic in (_clean_topic(value) for value in (knowledge_catalog or [])) if topic
    ] + role_fallbacks
    if not fallbacks:
        fallbacks = ["岗位基础巩固", "岗位项目实践", "岗位综合复测"]

    result: list[dict[str, Any]] = []
    used: set[str] = set()
    for index, raw in enumerate((steps or [])[:8], start=1):
        item = raw if isinstance(raw, dict) else {}
        fallback = next((value for value in fallbacks if value not in used), f"岗位能力进阶 {index}")
        raw_topic = _clean_topic(item.get("knowledge_point"), fallback)
        topic = next(
            (
                skill for skill in role_fallbacks
                if skill.lower() in raw_topic.lower() or raw_topic.lower() in skill.lower()
            ),
            fallback,
        )
        if not topic or topic in used:
            topic = _clean_topic(fallback, f"岗位能力进阶 {index}")
        used.add(topic)
        raw_type = str(item.get("resource_type") or "")
        resource_type = "练习" if "练" in raw_type or "实操" in raw_type else "讲义"
        try:
            estimated_time = int(item.get("estimated_time") or 30)
        except (TypeError, ValueError):
            estimated_time = 30
        prerequisite = _clean_topic(item.get("prerequisite")) if item.get("prerequisite") else None
        result.append({
            "step": index,
            "knowledge_point": topic,
            "resource_type": resource_type,
            "estimated_time": min(120, max(15, estimated_time)),
            "prerequisite": prerequisite,
            **({key: item[key] for key in ("resource_id", "status", "record_id", "weight") if key in item}),
        })
    return result


# The profile is intentionally kept in the Agent package so all four roles
# follow the same workflow.  The repository's job seed data remains the UI
# source of truth; these lists are the Agent's scoring and retrieval keywords.
ROLE_PROFILES: dict[str, dict[str, Any]] = {
    "前端开发工程师": {
        "skills": [
            ("HTML", "前端技术"), ("CSS", "前端技术"),
            ("JavaScript", "前端技术"), ("Vue", "前端技术"),
            ("React", "前端技术"), ("TypeScript", "前端技术"),
            ("浏览器原理", "前端技术"), ("响应式设计", "前端技术"),
            ("Webpack/Vite", "前端技术"), ("前端性能优化", "前端技术"),
            ("API设计", "后端技术"), ("接口联调", "后端技术"),
            ("Git", "项目管理"), ("单元测试", "测试与质量"),
            ("网络协议", "计算机网络"), ("安全编码", "安全规范"),
        ],
        "weights": {"前端技术": "high", "编程基础": "high", "后端技术": "mid", "数据库": "mid", "测试与质量": "mid", "沟通表达": "mid"},
    },
    "后端开发工程师": {
        "skills": [
            ("Python", "编程基础"), ("Java", "编程基础"),
            ("数据结构与算法", "数据结构与算法"), ("Spring Boot", "后端技术"),
            ("FastAPI", "后端技术"), ("API设计", "后端技术"),
            ("并发编程", "后端技术"), ("MySQL", "数据库"),
            ("Redis", "数据库"), ("系统设计", "系统设计"),
            ("Linux", "操作系统"), ("Docker", "运维部署"),
            ("Git", "项目管理"), ("单元测试", "测试与质量"),
            ("认证与授权", "安全规范"), ("网络协议", "计算机网络"),
        ],
        "weights": {"编程基础": "high", "数据结构与算法": "high", "后端技术": "high", "数据库": "high", "系统设计": "high", "计算机网络": "mid", "操作系统": "mid", "运维部署": "mid", "测试与质量": "mid", "安全规范": "mid", "学习能力": "mid"},
    },
    "运维工程师": {
        "skills": [
            ("Linux", "操作系统"), ("网络协议", "计算机网络"),
            ("Docker", "运维部署"), ("Kubernetes", "运维部署"),
            ("Nginx", "运维部署"), ("Shell脚本", "编程基础"),
            ("监控告警", "运维部署"), ("CI/CD", "运维部署"),
            ("日志管理", "运维部署"), ("故障排查", "运维部署"),
            ("数据库", "数据库"), ("安全规范", "安全规范"),
            ("云服务", "运维部署"), ("Git", "项目管理"),
            ("自动化测试", "测试与质量"), ("系统设计", "系统设计"),
        ],
        "weights": {"计算机网络": "high", "操作系统": "high", "运维部署": "high", "安全规范": "high", "后端技术": "mid", "数据库": "mid", "测试与质量": "mid", "编程基础": "mid", "系统设计": "mid"},
    },
    "产品经理": {
        "skills": [
            ("需求分析", "产品分析"), ("用户研究", "产品分析"),
            ("产品设计", "产品分析"), ("数据分析", "产品分析"),
            ("竞品分析", "产品分析"), ("业务理解", "产品分析"),
            ("原型设计", "产品分析"), ("文档撰写", "沟通表达"),
            ("沟通协调", "沟通表达"), ("项目推进", "项目管理"),
            ("项目管理", "项目管理"), ("逻辑思维", "逻辑思维"),
            ("技术理解", "编程基础"), ("接口基础", "后端技术"),
            ("数据安全", "安全规范"), ("用户体验", "产品分析"),
        ],
        "weights": {"产品分析": "high", "项目管理": "high", "沟通表达": "high", "逻辑思维": "high", "学习能力": "mid", "前端技术": "mid", "后端技术": "low", "数据分析": "high"},
    },
}


class Retriever(Protocol):
    def search(self, query: str, job: str, top_k: int = 5) -> list[dict[str, Any]]:
        ...


class BackendVectorRetriever:
    """Lazy bridge to the reference backend's existing Chroma adapter."""

    def search(self, query: str, job: str, top_k: int = 5) -> list[dict[str, Any]]:
        try:
            from adapters.vector_adapter import search_similar_resources

            return search_similar_resources(query=query, job=job, top_k=top_k)
        except Exception:
            # 检索异常允许规则链继续运行，但空结果不能被伪装成有知识库依据。
            return []


@dataclass
class AgentEvent:
    name: str
    status: str
    input_summary: str
    output_summary: str
    confidence: float
    review_result: str | None = None


@dataclass
class ParsedProfile:
    text: str
    matched_skills: dict[str, float] = field(default_factory=dict)
    negative_skills: set[str] = field(default_factory=set)
    action_evidence_count: int = 0
    retrieval_hits: list[dict[str, Any]] = field(default_factory=list)
    knowledge_catalog: list[str] = field(default_factory=list)  # 知识库中检索到的知识点主题（"问题"行）
    knowledge_catalog_map: dict[str, list[str]] = field(default_factory=dict)  # 技能→相关主题的映射


class InputParsingAgent:
    name = "自由文本学情解析 Agent"

    def run(self, target_job: str, user_input: str) -> ParsedProfile:
        if not _LLM_AVAILABLE:
            return self._run_rules(target_job, user_input)
        try:
            return self._run_llm(target_job, user_input)
        except Exception:
            return self._run_rules(target_job, user_input)

    def _run_llm(self, target_job: str, user_input: str) -> ParsedProfile:
        text = re.sub(r"\s+", " ", str(user_input or "")).strip()
        role = ROLE_PROFILES.get(target_job, ROLE_PROFILES["后端开发工程师"])
        skill_list = [skill for skill, _ in role["skills"]]

        system = f"""你是「{target_job}」岗位的学情分析师。你的任务是从学习者的自由描述中提取技能掌握情况。

你需要输出严格的 JSON 格式（不要包含其他文字）：
{{
  "matched_skills": {{"技能名": 0.0~1.0}},
  "negative_skills": ["技能名"],
  "action_evidence_count": 数字
}}

评估原则：
- "精通/熟练掌握/多年经验" → 0.80~0.90
- "熟悉/使用过/做过项目" → 0.55~0.75
- "了解/接触过/学过课程" → 0.30~0.50
- "不会/不熟/没学过/未接触" → 放入 negative_skills
- 未提及的技能不要放入 matched_skills
- action_evidence_count 统计"掌握、开发、负责、搭建、实现、部署、优化、排查、完成、参与、实习、项目"等动作词的次数

该岗位的技能清单供参考：{json.dumps(skill_list, ensure_ascii=False)}"""

        result = chat_json(system, f"学习者描述：{text}")
        profile = ParsedProfile(text=text)
        profile.action_evidence_count = int(result.get("action_evidence_count", 0))
        for skill, level in result.get("matched_skills", {}).items():
            profile.matched_skills[skill] = float(level)
        profile.negative_skills = set(result.get("negative_skills", []))
        return profile

    def _run_rules(self, target_job: str, user_input: str) -> ParsedProfile:
        text = re.sub(r"\s+", " ", str(user_input or "")).strip()
        profile = ParsedProfile(text=text)
        role = ROLE_PROFILES.get(target_job, ROLE_PROFILES["后端开发工程师"])
        action_terms = "掌握|熟悉|使用|实现|开发|负责|搭建|设计|部署|维护|优化|排查|完成|参与|实习|工作|项目"
        profile.action_evidence_count = len(re.findall(action_terms, text, flags=re.IGNORECASE))

        for skill, _dimension in role["skills"]:
            if not _contains_skill(text, skill):
                continue
            if _is_negative_claim(text, skill):
                profile.negative_skills.add(skill)
                profile.matched_skills[skill] = 0.2
                continue
            ctx = _skill_context(text, skill)
            has_action = bool(re.search(action_terms, ctx, flags=re.IGNORECASE))
            profile.matched_skills[skill] = 0.72 if has_action else 0.52
        return profile


class RAGEvidenceAgent:
    name = "岗位知识库检索 Agent"

    def __init__(self, retriever: Retriever):
        self.retriever = retriever

    def run(self, target_job: str, profile: ParsedProfile, events: list[AgentEvent]) -> None:
        role = ROLE_PROFILES[target_job]
        # 第一轮：检索用户已提及的技能（了解已有程度）
        matched_queries = list(profile.matched_skills.keys())[:10]
        # 第二轮：检索岗位全部技能（确保全量覆盖，不遗漏核心内容）
        all_role_skills = [skill for skill, _ in role["skills"]]
        unmentioned = [s for s in all_role_skills if s not in matched_queries]
        # 全部岗位技能都检索（不再取前 N 个）
        all_queries = matched_queries + unmentioned
        # 按 source_chunk_id 去重；同一岗位的切片往往共享 source_document，
        # 不能按文件名去重，否则整个岗位只会保留一个知识片段。
        seen_chunks = set()
        for skill in all_queries:
            # 用疑问模板增强查询语义匹配
            query_text = f"{target_job} {skill} 常见问题 核心知识点"
            hits = self.retriever.search(query_text, target_job, top_k=15)
            for hit in hits:
                chunk_key = (
                    str(hit.get("source_chunk_id") or hit.get("id") or "").strip()
                    or f"{hit.get('title', '')}:{hit.get('content', '')[:80]}"
                )
                if chunk_key in seen_chunks:
                    continue
                seen_chunks.add(chunk_key)
                profile.retrieval_hits.append(
                    {"query": skill, "job": target_job, **hit}
                )
        # 按 score 降序排序，取前 120 条控制上下文量
        profile.retrieval_hits.sort(key=lambda h: h.get("score", 0), reverse=True)
        profile.retrieval_hits = profile.retrieval_hits[:120]

        # 从检索结果中提取知识目录（去重）。知识库同时包含问答、Markdown
        # 章节和技术文档，不能只识别“问题：”这一种格式。
        seen_topics = set()
        for hit in profile.retrieval_hits:
            content = hit.get("content", "")
            query = hit.get("query", "")
            if not content:
                continue
            topic = _topic_from_source(content, query)
            if topic and topic not in seen_topics:
                seen_topics.add(topic)
                profile.knowledge_catalog.append(topic)
            # 构建技能→主题映射（供 PathAgent 降级模式精准匹配）
            if query and topic:
                profile.knowledge_catalog_map.setdefault(query, []).append(topic)
        events.append(AgentEvent(
            name=self.name,
            status="completed",
            input_summary=f"按 {target_job} 检索全部 {len(all_queries)} 个岗位技能（top_k=15），含 {len(matched_queries)} 个已提及 + {len(unmentioned)} 个未提及。",
            output_summary=f"去重后 {len(profile.retrieval_hits)} 条 RAG 片段，提取 {len(profile.knowledge_catalog)} 个知识主题。",
            confidence=0.88 if profile.retrieval_hits else 0.55,
        ))


class CapabilityScoringAgent:
    name = "岗位能力诊断 Agent"

    def run(self, target_job: str, profile: ParsedProfile, events: list[AgentEvent]) -> dict[str, Any]:
        if not _LLM_AVAILABLE:
            return self._run_rules(target_job, profile, events)
        try:
            return self._run_llm(target_job, profile, events)
        except Exception:
            return self._run_rules(target_job, profile, events)

    def _run_llm(self, target_job: str, profile: ParsedProfile, events: list[AgentEvent]) -> dict[str, Any]:
        role = ROLE_PROFILES[target_job]
        dims_text = json.dumps([{"index": idx, "name": name, "category": cat} for idx, name, cat in DIMENSIONS], ensure_ascii=False)
        skill_map = json.dumps([[s, d] for s, d in role["skills"]], ensure_ascii=False)

        system = f"""你是「{target_job}」岗位的能力评估专家。请根据学情分析结果和岗位能力模型，对学习者进行 16 维度量化评估。

【16 个能力维度】
{dims_text}

【岗位技能→维度映射】
{skill_map}

【维度权重】
{json.dumps(role["weights"], ensure_ascii=False)}

【知识库可推荐主题目录（你推荐的 knowledge_gaps 应优先从以下主题中选择）】
{json.dumps(profile.knowledge_catalog[:80], ensure_ascii=False)}

【评分规则】
1. 每个维度值在 0.12~0.92 之间
2. high 权重维度对 overall_mastery 影响更大（系数 high=1.6, mid=1.0, low=0.5）
3. knowledge_gaps 取掌握度低（<0.6）的主题，参照知识库目录选择，从低到高排列，最多 15 个
4. **必须覆盖所有得分<0.6 的维度，每个低分维度至少对应 1 个薄弱主题**
5. confidence 只作为输入证据充分度的辅助信号，不等同于准确率
6. 必须包含全部 16 个维度
7. 学习者未提及但岗位需要的维度，给 0.50 的中性先验分（不判为不会）
8. supplement_suggestions：若你认为知识库目录缺少某重要主题，可在此列出最多 3 个补充建议

请输出严格 JSON：{{"overall_mastery": 0.0, "ability_vector": [...], "requirement_scores": [{{"requirement_id": "岗位代码.能力代码", "requirement_name": "能力名称", "score": 0.0, "status": "qualified|partial|gap", "evidence_ids": []}}], "knowledge_gaps": [...], "supplement_suggestions": [...], "confidence": 0.0}}"""

        user_msg = json.dumps({
            "matched_skills": profile.matched_skills,
            "negative_skills": sorted(profile.negative_skills),
            "action_evidence_count": profile.action_evidence_count,
            "knowledge_catalog": profile.knowledge_catalog[:80],
        }, ensure_ascii=False)

        result = chat_json(system, user_msg)
        if not result:
            return self._run_rules(target_job, profile, events)

        # 确保 16 维完整
        vector = result.get("ability_vector", [])
        if len(vector) != 16:
            return self._run_rules(target_job, profile, events)

        # 规范化 weight 值（LLM 可能返回 "High"/"medium" 等变体）
        weight_map = {"high": "high", "mid": "mid", "medium": "mid", "low": "low"}
        normalized_vector = []
        for item in vector:
            raw_weight = str(item.get("weight", "low")).lower()
            normalized_vector.append({
                "index": int(item.get("index", 0)),
                "name": str(item.get("name", "")),
                "value": min(1.0, max(0.0, float(item.get("value", 0.2)))),
                "weight": weight_map.get(raw_weight, "low"),
                "category": str(item.get("category", "")),
            })

        # 规范化 knowledge_gaps（LLM 可能返回非列表）
        raw_gaps = result.get("knowledge_gaps", [])
        if not isinstance(raw_gaps, list):
            raw_gaps = []
        knowledge_gaps = [str(g) for g in raw_gaps[:15]]

        # 处理补充建议：若 LLM 认为 catalog 缺少某些主题，补充到 catalog
        supplement = result.get("supplement_suggestions", [])
        if isinstance(supplement, list) and supplement:
            for s in supplement:
                s_str = str(s).strip()
                if s_str and s_str not in profile.knowledge_catalog:
                    profile.knowledge_catalog.append(s_str)

        requirement_scores = build_requirement_scores(
            target_job,
            role["skills"],
            profile,
            result.get("requirement_scores"),
        )
        confidence = round(min(0.99, max(0.30, float(result.get("confidence", 0.7)))), 2)
        events.append(AgentEvent(
            name=self.name, status="completed",
            input_summary=f"DeepSeek 对照 {len(role['skills'])} 个岗位能力项，输入 {len(profile.text)} 字。",
            output_summary=f"LLM 生成 16 维能力向量，识别 {len(knowledge_gaps)} 个薄弱知识点（supplement={len(supplement) if isinstance(supplement, list) else 0}）。",
            confidence=confidence,
        ))
        return {
            "overall_mastery": round(float(result.get("overall_mastery", 0.3)), 4),
            "ability_vector": normalized_vector,
            "requirement_scores": requirement_scores,
            "knowledge_gaps": knowledge_gaps,
            "confidence": confidence,
        }

    def _run_rules(self, target_job: str, profile: ParsedProfile, events: list[AgentEvent]) -> dict[str, Any]:
        role = ROLE_PROFILES[target_job]
        skill_by_dimension: dict[str, list[float]] = {name: [] for _, name, _ in DIMENSIONS}
        gaps: list[tuple[str, float]] = []
        for skill, dimension in role["skills"]:
            value = profile.matched_skills.get(skill, 0.50)
            if skill in profile.negative_skills:
                value = 0.2
            skill_by_dimension.setdefault(dimension, []).append(value)
            if value < 0.60:
                gaps.append((skill, value))

        vector: list[dict[str, Any]] = []
        for index, name, category in DIMENSIONS:
            values = skill_by_dimension.get(name) or [0.18]
            value = min(0.92, max(0.12, sum(values) / len(values)))
            weight = role["weights"].get(name, "low")
            vector.append({"index": index, "name": name, "value": round(value, 4), "weight": weight, "category": category})

        gap_names = [skill for skill, _v in sorted(gaps, key=lambda item: item[1])[:15]]
        if not gap_names:
            gap_names = [skill for skill, _ in role["skills"][:3]]

        wv = {"high": 1.6, "mid": 1.0, "low": 0.5}
        overall = round(sum(item["value"] * wv[item["weight"]] for item in vector) / sum(wv[item["weight"]] for item in vector), 4)
        coverage = len(profile.matched_skills) / len(role["skills"])
        confidence = min(0.99, max(0.30, 0.48 + min(0.18, len(profile.text) / 600) + min(0.18, coverage * 0.45) + (0.08 if profile.action_evidence_count else 0)))

        events.append(AgentEvent(
            name=self.name, status="completed",
            input_summary=f"规则引擎对照 {len(role['skills'])} 个岗位能力项。",
            output_summary=f"生成 16 维能力向量，识别 {len(gap_names)} 个薄弱知识点。",
            confidence=round(confidence, 2),
        ))
        return {
            "overall_mastery": overall,
            "ability_vector": vector,
            "requirement_scores": build_requirement_scores(target_job, role["skills"], profile),
            "knowledge_gaps": gap_names,
            "confidence": round(confidence, 2),
        }


class CalibrationAgent:
    name = "诊断结果校正 Agent"

    def run(self, diagnosis: dict[str, Any], profile: ParsedProfile, events: list[AgentEvent]) -> dict[str, Any]:
        errors: list[str] = []
        vector = diagnosis.get("ability_vector")
        if not isinstance(vector, list) or len(vector) != 16:
            errors.append("ability_vector 必须包含 16 个维度")
        for item in vector or []:
            value = item.get("value")
            if not isinstance(value, (int, float)) or not 0 <= value <= 1:
                errors.append(f"维度 {item.get('name')} 的 value 不在 0 到 1 范围内")
        if not isinstance(diagnosis.get("knowledge_gaps"), list):
            errors.append("knowledge_gaps 必须是字符串列表")
        if len(profile.text) < 10:
            diagnosis["confidence"] = min(float(diagnosis.get("confidence", 0.4)), 0.45)
        events.append(AgentEvent(
            name=self.name,
            status="completed" if not errors else "rejected",
            input_summary="校验诊断输出字段、向量长度、数值范围和自由文本证据充分度。",
            output_summary="诊断结果通过结构校验。" if not errors else "诊断结果需要退回修正。",
            confidence=1.0 if not errors else 0.2,
            review_result="approved" if not errors else "rejected",
        ))
        if errors:
            raise ValueError("；".join(errors))
        return diagnosis


class ResourceAgent:
    name = "个性化资源生成 Agent"

    def __init__(self, retriever: Retriever):
        self.retriever = retriever

    def run(
        self,
        knowledge_point: str,
        user_level: float,
        resource_type: str,
        target_job: str,
        learner_context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        knowledge_point = _clean_topic(knowledge_point, "岗位核心能力")
        learner_context = dict(learner_context or {})
        if str(resource_type or "").strip() not in {"讲义", "练习", "案例"}:
            return {
                "content_type": str(resource_type or ""),
                "title": f"{knowledge_point}学习资源",
                "body": "当前资源类型未启用，本次不生成正式学习内容。",
                "difficulty": 1,
                "generation_method": "none",
            }, []
        hits = self.retriever.search(f"{target_job} {knowledge_point}", target_job, top_k=10)
        hits = _usable_source_hits(hits, knowledge_point)
        if not hits:
            return {
                "content_type": resource_type,
                "title": f"{knowledge_point}{resource_type}",
                "body": "当前岗位知识库未返回可用来源，本次不生成正式学习内容，请先检查 RAG 服务或补充知识库。",
                "difficulty": min(5, max(1, int(round(float(user_level or 0.2) * 5)))),
                "generation_method": "none",
            }, []

        if not _LLM_AVAILABLE:
            return self._run_rules(knowledge_point, user_level, resource_type, target_job, hits, learner_context)
        try:
            return self._run_llm(knowledge_point, user_level, resource_type, target_job, hits, learner_context)
        except Exception:
            return self._run_rules(knowledge_point, user_level, resource_type, target_job, hits, learner_context)

    def _run_llm(
        self,
        knowledge_point: str,
        user_level: float,
        resource_type: str,
        target_job: str,
        hits: list,
        learner_context: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        rag_text = "\n---\n".join([
            f"[{h.get('title', '')}] {h.get('content', '')[:800]}"
            for h in hits[:10]
        ])

        role_persona = {
            "讲义": f"你是「{target_job}」岗位的资深讲师，擅长将复杂概念拆解为清晰易懂的讲解。",
            "练习": f"你是「{target_job}」岗位的技术教练，擅长设计层层递进的实战练习。",
            "案例": f"你是「{target_job}」岗位的项目导师，擅长用真实案例讲解技术决策和问题解决。",
        }
        persona = role_persona.get(resource_type, role_persona["讲义"])

        system = f"""{persona}

请为学习者生成关于「{knowledge_point}」的{resource_type}内容。
学习者当前岗位综合掌握度：{max(0.0, min(1.0, user_level)):.0%}
目标岗位：{target_job}

【本次学习者诊断上下文】
{json.dumps(learner_context, ensure_ascii=False)[:2200]}

【知识库参考资料】
{rag_text}

【生成要求】
- 先列出检索片段中必须覆盖的关键概念（3-6 个），再逐一写入正文，不得遗漏
- 开头必须用一段“为什么为你推荐”说明本资源对应的能力缺口和已有证据；不得写成面向所有人的通用推荐
- 内容必须包含可直接学习的解释或可直接执行的步骤，不得只返回知识点名称、目录或空模板
- 只生成当前请求的「{resource_type}」，不得追加其他资源类型章节
- {"讲义：学习目标 + 核心概念讲解 + 关键原理 + 自检问题" if resource_type == "讲义" else "练习：任务背景 + 具体步骤 + 参考提示 + 验收标准" if resource_type == "练习" else "案例：项目背景 + 问题分析 + 解决方案 + 复盘要点"}

必须基于知识库参考内容，不要编造知识库中没有的技术事实。
- 知识库内容只用于内部参考，不得逐字复制参考资料，不得输出连续大段原文。
- 不得输出“知识库参考资料”“依据片段”“参考原文”等内部检索标签。
- 对参考资料进行重新组织、解释和教学化表达；如果无法完成改写，返回空 body，不要复制原文。

请输出 JSON：{{"title": "标题", "body": "内容（先列出关键概念清单，再展开正文）", "difficulty": 1~5}}"""

        result = chat_json(system, "")
        if not result:
            return self._run_rules(knowledge_point, user_level, resource_type, target_job, hits, learner_context)

        body = str(result.get("body", "") or "").strip()
        # A model timeout can still return a syntactically valid but unusable
        # shell.  Never persist a title-only or near-empty learning resource.
        if len(re.sub(r"\s+", "", body)) < 160:
            return self._run_rules(knowledge_point, user_level, resource_type, target_job, hits, learner_context)
        if detect_unrequested_resource_type(body, resource_type).get("found"):
            # Keep the requested resource available by regenerating it through
            # the deterministic source-bound template instead of publishing a
            # mixed document or leaving an empty card in the learner library.
            return self._run_rules(knowledge_point, user_level, resource_type, target_job, hits, learner_context)

        return {
            "content_type": resource_type,
            "title": result.get("title", f"{knowledge_point}{resource_type}"),
            "body": body,
            "difficulty": min(5, max(1, int(result.get("difficulty", 2)))),
            "generation_method": "llm",
        }, hits

    def _run_rules(
        self,
        knowledge_point: str,
        user_level: float,
        resource_type: str,
        target_job: str,
        hits: list,
        learner_context: dict[str, Any],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Build a usable, source-grounded resource when the external LLM is unavailable."""
        title = f"{knowledge_point}{resource_type}"
        difficulty = min(5, max(1, int(round(float(user_level or 0.2) * 5)) + (1 if resource_type == "练习" else 0)))
        gap = str(learner_context.get("focus_gap") or knowledge_point).strip()
        evidence = str(learner_context.get("evidence_summary") or "当前提交资料中缺少可核验的完整产出").strip()
        dimension = str(learner_context.get("focus_dimension") or "岗位核心能力").strip()
        # The persisted evidence chain currently stores one source_chunk_id.
        # Generate the grounded outline from that exact chunk so the reviewer
        # validates the same evidence that the learner-facing resource used.
        source_points = _source_learning_points(hits[:1])
        if not source_points:
            source_points = [f"围绕 {knowledge_point} 建立概念、场景、实现与验证之间的联系"]
        grounded_outline = "\n".join(
            f"{index}. {point}" for index, point in enumerate(source_points, start=1)
        )
        reason = (
            f"为什么为你推荐：本次诊断将「{dimension}」识别为优先补强方向；"
            f"对应缺口为“{gap}”。现有证据显示：{evidence[:160]}。"
        )
        if resource_type == "讲义":
            body = (
                f"{reason}\n\n学习目标：完成后能够解释「{knowledge_point}」的核心机制，"
                f"并说明它在「{target_job}」实际任务中的使用边界。\n\n"
                f"知识库提炼要点：\n{grounded_outline}\n\n"
                "学习方法：先画出概念关系，再写一个最小示例；对每个输入记录预期输出、异常分支和验证方式。\n\n"
                f"自检问题：你能否不看资料说明 {knowledge_point} 解决什么问题、何时不应使用，以及如何证明实现有效？"
            )
        elif resource_type == "练习":
            body = (
                f"{reason}\n\n练习主题：{knowledge_point}\n\n可用知识依据：\n{grounded_outline}\n\n"
                "执行步骤：\n1. 定义一个与目标岗位相关的最小任务和成功条件。\n"
                "2. 完成可运行实现，并保存关键配置、输入与输出。\n"
                "3. 主动构造一个异常场景，记录定位过程和修正结果。\n"
                "4. 用截图、测试结果或提交记录形成能力证据。\n\n"
                "验收标准：结果可复现、异常可解释、关键决策有记录，并能说明本次产出如何补上诊断缺口。"
            )
        elif resource_type == "案例":
            body = (
                f"{reason}\n\n案例主题：围绕「{knowledge_point}」完成一次岗位化问题拆解。\n\n"
                f"案例依据：\n{grounded_outline}\n\n"
                "分析顺序：业务目标、约束条件、候选方案、取舍理由、验证结果和复盘。\n\n"
                "交付物：问题定义、方案说明、实现或原型、验证记录与下一步改进清单。"
            )
        else:
            body = f"{reason}\n\n{grounded_outline}"
        return {"content_type": resource_type, "title": title, "body": body, "difficulty": difficulty, "generation_method": "rules"}, hits


class PathAgent:
    name = "个性化学习路径 Agent"

    def run(self, user_id: str, target_job: str, current_ability: list[float], knowledge_catalog: list[str], knowledge_catalog_map: dict[str, list[str]], events: list[AgentEvent]) -> list[dict[str, Any]]:
        cleaned_catalog = []
        for value in knowledge_catalog:
            topic = _clean_topic(value)
            if topic and topic not in cleaned_catalog:
                cleaned_catalog.append(topic)
        cleaned_map = {
            skill: [topic for topic in (_clean_topic(value) for value in values) if topic]
            for skill, values in knowledge_catalog_map.items()
        }
        if not _LLM_AVAILABLE:
            return self._run_rules(target_job, current_ability, cleaned_catalog, cleaned_map, events)
        try:
            return self._run_llm(target_job, current_ability, cleaned_catalog, cleaned_map, events)
        except Exception:
            return self._run_rules(target_job, current_ability, cleaned_catalog, cleaned_map, events)

    def _run_llm(self, target_job: str, current_ability: list[float], knowledge_catalog: list[str], knowledge_catalog_map: dict[str, list[str]], events: list[AgentEvent]) -> list[dict[str, Any]]:
        role = ROLE_PROFILES[target_job]
        dims = [{"name": name, "score": float(current_ability[idx]) if idx < len(current_ability) else 0.18} for idx, (_, name, _) in enumerate(DIMENSIONS)]
        skills_list = [{"skill": s, "dimension": d} for s, d in role["skills"]]
        catalog_text = json.dumps(knowledge_catalog[:80], ensure_ascii=False) if knowledge_catalog else "（暂无，请根据岗位技能列表自行规划）"

        system = f"""你是「{target_job}」岗位的学习路径规划师。根据能力诊断结果和知识库可用内容，设计 8 步个性化学习路径。

【16 维能力得分】
{json.dumps(dims, ensure_ascii=False)}

【岗位技能→维度】
{json.dumps(skills_list, ensure_ascii=False)}

【知识库可用主题（knowledge_point 必须从以下主题中选取，或与主题紧密相关）】
{catalog_text}

【规划规则】
1. knowledge_point 必须从上述知识库主题中挑选具体的问题/概念（不能只写"Java""Python"等笼统词），或写出与某个主题紧密相关的细化知识点
2. **必须覆盖所有得分<0.6 的能力维度**，每个低分维度至少安排 1 步，尽量让每步属于不同维度
3. 优先补强得分最低的维度
4. 考虑前置依赖（编程基础应在框架前，网络基础应在部署前）
5. 交替安排"讲义"和"练习"
6. 弱项(<0.3)给 45 分钟，中等(0.3~0.5)给 30 分钟，较强(>0.5)给 20 分钟
7. 第一步 prerequisite 为 null，后续步骤可设前置技能名

请输出 JSON 数组：[{{"step":1,"knowledge_point":"具体问题/概念","resource_type":"讲义","estimated_time":30,"prerequisite":null}}, ...]"""

        steps = chat_json_value(system, "")
        # 必须恰好 8 步，否则 LLM 输出不可靠，降级为规则模式
        if not steps or not isinstance(steps, list) or len(steps) != 8:
            return self._run_rules(target_job, current_ability, knowledge_catalog, knowledge_catalog_map, events)
        steps = self._normalize_steps(steps, target_job, knowledge_catalog)
        if len(steps) != 8:
            return self._run_rules(target_job, current_ability, knowledge_catalog, knowledge_catalog_map, events)

        events.append(AgentEvent(
            name=self.name, status="completed",
            input_summary=f"DeepSeek 根据 {target_job} 的 16 维能力向量和 {len(knowledge_catalog)} 个知识库主题规划学习顺序。",
            output_summary=f"LLM 生成 {len(steps)} 个学习步骤。",
            confidence=0.82,
        ))
        return steps

    def _normalize_steps(self, steps: list[Any], target_job: str, knowledge_catalog: list[str]) -> list[dict[str, Any]]:
        return sanitize_learning_path_steps(steps, target_job, knowledge_catalog)

    def _run_rules(self, target_job: str, current_ability: list[float], knowledge_catalog: list[str], knowledge_catalog_map: dict[str, list[str]], events: list[AgentEvent]) -> list[dict[str, Any]]:
        role = ROLE_PROFILES[target_job]
        values_by_dimension = {
            name: float(current_ability[index - 1]) if index - 1 < len(current_ability) else 0.18
            for index, name, _category in DIMENSIONS
        }
        # 按维度分组技能，每个维度取最低分技能
        dim_skills: dict[str, list[tuple[float, str]]] = {}
        for skill, dimension in role["skills"]:
            score = values_by_dimension.get(dimension, 0.18)
            dim_skills.setdefault(dimension, []).append((score, skill))
        for dimension in dim_skills:
            dim_skills[dimension].sort(key=lambda x: x[0])  # 最低分在前

        # 第一阶段：从每个得分<0.6 的维度各选 1 个技能（优先低分维度）
        low_dims = [(dim, skills[0][0]) for dim, skills in dim_skills.items() if values_by_dimension.get(dim, 1.0) < 0.6]
        low_dims.sort(key=lambda x: x[1])  # 按维度得分排序
        covered_dims = set()
        phase1 = []
        for dim_name, _ in low_dims:
            if dim_name in dim_skills:
                for score, skill in dim_skills[dim_name]:
                    if skill not in phase1:
                        phase1.append((score, skill, dim_name))
                        covered_dims.add(dim_name)
                        break

        # 第二阶段：从所有技能中补足到 8 步（优先低分技能，跳过已在 phase1 中的）
        all_sorted = []
        selected_skill_names = {item[1] for item in phase1}
        for dim, skills in dim_skills.items():
            for score, skill in skills:
                if skill not in selected_skill_names:
                    all_sorted.append((score, skill, dim))
        all_sorted.sort(key=lambda x: x[0])
        remaining_needed = 8 - len(phase1)
        phase2 = [(s, sk, dim) for s, sk, dim in all_sorted[:remaining_needed]]

        selected = phase1 + phase2
        # 确保恰好 8 个
        selected = selected[:8]

        # 预取每个技能的知识库具体主题
        skill_topics: dict[str, list[str]] = {}
        for _, skill, _ in selected:
            related = knowledge_catalog_map.get(skill, [])
            if not related:
                skill_kw = skill.lower()
                for cat_skill, topics in knowledge_catalog_map.items():
                    if skill_kw in cat_skill.lower() or any(kw in cat_skill.lower() for kw in skill_kw.split()):
                        related.extend(topics)
                related = list(set(related))
            skill_topics[skill] = related

        steps: list[dict[str, Any]] = []
        previous = None
        for index, (value, skill, dimension) in enumerate(selected, start=1):
            # Persist canonical role skills as path/resource query keys.
            # Retrieved article headings remain internal RAG context.
            topic = skill
            steps.append({
                "step": index, "knowledge_point": topic,
                "resource_type": "讲义" if index % 2 else "练习",
                "estimated_time": 30 if value < 0.45 else 20,
                "prerequisite": previous,
            })
            previous = topic

        events.append(AgentEvent(
            name=self.name, status="completed",
            input_summary=f"规则引擎按 {target_job} 的 16 维能力向量跨维度编排（覆盖 {len(covered_dims)} 个低分维度）。",
            output_summary=f"生成 {len(steps)} 个学习步骤。",
            confidence=0.82,
        ))
        return self._normalize_steps(steps, target_job, knowledge_catalog)


class AgentRuntime:
    """Serial supervisor for all four jobs."""

    def __init__(self, retriever: Retriever | None = None):
        self.retriever = retriever or BackendVectorRetriever()
        self.last_trace: dict[str, Any] = {}
        self._current_job: ContextVar[str] = ContextVar("agent_current_job", default="后端开发工程师")
        self._last_catalog: ContextVar[list[str]] = ContextVar("agent_last_catalog", default=[])
        self._last_catalog_map: ContextVar[dict[str, list[str]]] = ContextVar("agent_last_catalog_map", default={})

    def _role(self, target_job: str) -> str:
        role = normalize_job(target_job)
        if role not in ROLE_PROFILES:
            raise ValueError(f"不支持的目标职业：{target_job}")
        return role

    def diagnose(
        self,
        user_id: str,
        target_job: str,
        user_input: str,
        gold_labels: list[dict[str, Any]] | None = None,
        apply_corrections: bool = False,
        progress_callback: Callable[[str, int, str], None] | None = None,
    ) -> dict[str, Any]:
        def report(stage: str, percent: int, label: str) -> None:
            if progress_callback:
                progress_callback(stage, percent, label)

        role = self._role(target_job)
        self._current_job.set(role)
        trace_id = f"trace_{uuid4().hex[:12]}"
        context_manager = ContextManager(trace_id=trace_id)
        events: list[AgentEvent] = []
        parser = InputParsingAgent()
        report("material", 5, "资料解析 Agent 正在解析学习经历")
        profile = parser.run(role, user_input)
        report("material", 12, "资料解析 Agent 已完成证据抽取")
        context_manager.record(
            "parse_input",
            {"user_id": user_id, "target_job": role, "user_input": user_input, "career_skills": [skill for skill, _ in ROLE_PROFILES[role]["skills"]]},
            {"matched_skills": profile.matched_skills, "negative_skills": sorted(profile.negative_skills), "action_evidence_count": profile.action_evidence_count},
        )
        events.append(AgentEvent(
            name=parser.name,
            status="completed",
            input_summary="接收一段自由文本，不额外要求测评分数、每周学时或多字段资料提交。",
            output_summary=f"识别 {len(profile.matched_skills)} 个岗位关键词，发现 {len(profile.negative_skills)} 个否定表述。",
            confidence=0.84 if len(profile.text) >= 30 else 0.58,
        ))
        report("retrieval", 18, "知识库检索 Agent 正在检索岗位知识片段")
        RAGEvidenceAgent(self.retriever).run(role, profile, events)
        report("retrieval", 28, "知识库检索 Agent 已完成来源片段检索")
        context_manager.record(
            "retrieve_knowledge",
            {"target_job": role, "matched_skills": profile.matched_skills, "negative_skills": sorted(profile.negative_skills), "retrieval_hits": profile.retrieval_hits},
            {"knowledge_catalog": profile.knowledge_catalog[:80], "hit_count": len(profile.retrieval_hits)},
            source_chunk_ids=[str(hit.get("source_chunk_id")) for hit in profile.retrieval_hits],
        )
        self._last_catalog.set(profile.knowledge_catalog)  # 存储供 PathAgent 使用
        self._last_catalog_map.set(profile.knowledge_catalog_map)
        report("diagnosis", 30, "能力诊断 Agent 正在计算岗位能力向量")
        diagnosis = CapabilityScoringAgent().run(role, profile, events)
        report("diagnosis", 40, "能力诊断 Agent 已完成能力对照")
        context_manager.record(
            "diagnose_capability",
            {"target_job": role, "career_model_version": "role-profile.v1", "matched_skills": profile.matched_skills, "negative_skills": sorted(profile.negative_skills), "action_evidence_count": profile.action_evidence_count, "knowledge_catalog": profile.knowledge_catalog[:80]},
            {"overall_mastery": diagnosis.get("overall_mastery"), "ability_vector": diagnosis.get("ability_vector"), "knowledge_gaps": diagnosis.get("knowledge_gaps", []), "requirement_scores": diagnosis.get("requirement_scores", [])},
            evidence_ids=[str(item.get("evidence_id")) for item in diagnosis.get("requirement_scores", []) if isinstance(item, dict) for _ in [0] if item.get("evidence_id")],
        )
        report("calibration", 42, "诊断结果校验 Agent 正在复核评分")
        diagnosis = CalibrationAgent().run(diagnosis, profile, events)
        report("calibration", 44, "诊断结果校验 Agent 已完成交叉审核")
        context_manager.record(
            "calibrate_result",
            {"diagnosis": {"overall_mastery": diagnosis.get("overall_mastery"), "ability_vector": diagnosis.get("ability_vector"), "knowledge_gaps": diagnosis.get("knowledge_gaps", [])}, "user_input_length": len(profile.text)},
            {"validation": "approved", "confidence": diagnosis.get("confidence")},
        )

        # ── 层2：真实结果校准 ──
        # 没有标准结果时只返回 unvalidated，不把模型自报置信度冒充准确率。
        report("calibration", 46, "真实结果校准 Agent 正在比对标准结果")
        ground_truth = GroundTruthCalibrationAgent().run(
            target_job=role,
            diagnosis=diagnosis,
            role_skills=ROLE_PROFILES[role]["skills"],
            dimensions=DIMENSIONS,
            profile=profile,
            gold_labels=gold_labels or [],
            apply_corrections=apply_corrections,
        )
        diagnosis = ground_truth["diagnosis"]
        diagnosis["calibration"] = ground_truth["summary"]
        diagnosis["calibration_records"] = ground_truth["records"]
        report("calibration", 48, "真实结果校准 Agent 已完成校准判断")
        events.append(AgentEvent(
            name=GroundTruthCalibrationAgent.name,
            status="completed" if ground_truth["summary"]["status"] != "rejected" else "needs_review",
            input_summary=(
                f"接收 {len(gold_labels or [])} 条标准结果，按 requirement_id 对照 AI 能力判断。"
            ),
            output_summary=(
                "没有可信标准结果，标记为未校准。"
                if not ground_truth["summary"]["evaluated_count"]
                else (
                    f"完成 {ground_truth['summary']['evaluated_count']} 项比对，"
                    f"准确率 {ground_truth['summary']['accuracy']:.0%}，"
                    f"平均绝对误差 {ground_truth['summary']['mean_absolute_error'] if ground_truth['summary']['mean_absolute_error'] is not None else '—'}。"
                )
            ),
            confidence=1.0 if ground_truth["summary"]["evaluated_count"] else 0.3,
            review_result=ground_truth["summary"]["status"],
        ))
        context_manager.record(
            "calibrate_against_ground_truth",
            {"requirement_scores": diagnosis.get("requirement_scores", []), "gold_labels": gold_labels or [], "apply_corrections": apply_corrections},
            {"summary": ground_truth["summary"], "record_count": len(ground_truth["records"])},
            evidence_ids=[str(item.get("evidence_id")) for item in diagnosis.get("requirement_scores", []) if isinstance(item, dict) and item.get("evidence_id")],
        )

        # ── 层1：知识缺口校验（防幻觉）——过滤掉岗位能力模型/知识库无依据的缺口 ──
        kept_gaps, gap_validation = _validate_gaps(
            diagnosis.get("knowledge_gaps", []), role, profile.knowledge_catalog
        )
        diagnosis["knowledge_gaps"] = kept_gaps
        diagnosis["gap_validation"] = gap_validation

        # ── 防幻觉护栏：用本地小模型校验诊断结果是否基于 RAG 上下文 ──
        context_text = json.dumps(profile.retrieval_hits, ensure_ascii=False)
        response_text = json.dumps(diagnosis, ensure_ascii=False)
        guard_res = check_hallucination(context_text, response_text)
        if guard_res.get("has_hallucination"):
            diagnosis["hallucination_warning"] = guard_res.get("reason", "防幻觉校验未通过")

        self.last_trace = self._trace(trace_id, user_id, role, events, profile, diagnosis, None)
        self.last_trace["context_ledger"] = context_manager.as_dicts()
        return diagnosis

    def calibrate_existing(
        self,
        user_id: str,
        target_job: str,
        diagnosis: dict[str, Any],
        user_input: str,
        gold_labels: list[dict[str, Any]],
        apply_corrections: bool = False,
    ) -> dict[str, Any]:
        """Calibrate a stored diagnosis without regenerating resources.

        This endpoint is used by the test team after expert review or a
        practical task has produced the real result. It keeps the original AI
        output and stores the comparison separately.
        """
        role = self._role(target_job)
        profile = InputParsingAgent()._run_rules(role, user_input)
        context_manager = ContextManager()
        events: list[AgentEvent] = []
        result = GroundTruthCalibrationAgent().run(
            target_job=role,
            diagnosis=diagnosis,
            role_skills=ROLE_PROFILES[role]["skills"],
            dimensions=DIMENSIONS,
            profile=profile,
            gold_labels=gold_labels,
            apply_corrections=apply_corrections,
        )
        events.append(AgentEvent(
            name=GroundTruthCalibrationAgent.name,
            status="completed" if result["summary"]["status"] != "rejected" else "needs_review",
            input_summary=f"对已有诊断重新比对 {len(gold_labels)} 条可信标准结果。",
            output_summary=f"完成 {result['summary']['evaluated_count']} 项记录。",
            confidence=1.0 if result["summary"]["evaluated_count"] else 0.3,
            review_result=result["summary"]["status"],
        ))
        context_manager.record(
            "calibrate_against_ground_truth",
            {"requirement_scores": diagnosis.get("requirement_scores", []), "gold_labels": gold_labels, "apply_corrections": apply_corrections},
            {"summary": result["summary"], "record_count": len(result["records"])},
        )
        self.last_trace = {
            "trace_id": f"trace_{uuid4().hex[:12]}",
            "user_id": user_id,
            "target_job": role,
            "agents": [event.__dict__ for event in events],
            "calibration": result["summary"],
            "review": {"approved": result["summary"]["status"] == "passed", "errors": []},
            "context_ledger": context_manager.as_dicts(),
        }
        return result

    def auto_calibrate_existing(
        self,
        user_id: str,
        target_job: str,
        diagnosis: dict[str, Any],
        user_input: str,
    ) -> dict[str, Any]:
        """Run the existing calibration Agent with automatic evidence review."""
        role = self._role(target_job)
        profile = InputParsingAgent()._run_rules(role, user_input)
        labels = build_automatic_evidence_labels(role, ROLE_PROFILES[role]["skills"], profile)
        result = GroundTruthCalibrationAgent().run(
            target_job=role,
            diagnosis=diagnosis,
            role_skills=ROLE_PROFILES[role]["skills"],
            dimensions=DIMENSIONS,
            profile=profile,
            gold_labels=labels,
            apply_corrections=False,
        )
        result["summary"].update({
            "version": AUTO_CALIBRATION_VERSION,
            "mode": "automatic_evidence_review",
            "metric_label": "自动证据校准准确率",
            "is_ground_truth": False,
            "needs_human_review": False,
        })
        return result

    def generate_resource(
        self,
        knowledge_point: str,
        user_level: float,
        resource_type: str,
        learner_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        role = self._current_job.get()
        if role not in ROLE_PROFILES:
            role = "后端开发工程师"
        events: list[AgentEvent] = []
        resource, hits = ResourceAgent(self.retriever).run(
            knowledge_point,
            user_level,
            resource_type,
            role,
            learner_context=learner_context,
        )
        context_manager = ContextManager()
        source = next(
            (
                hit for hit in hits
                if str(hit.get("source_chunk_id") or "").strip()
                and str(hit.get("content") or "").strip()
            ),
            None,
        )
        events.append(AgentEvent(
            name=ResourceAgent.name,
            status="completed" if source else "blocked",
            input_summary=f"针对 {role} 的「{knowledge_point}」生成{resource_type}。",
            output_summary=(
                "已绑定现有岗位知识库片段。"
                if source
                else "没有可追溯的 source_chunk_id 和原文，禁止生成正式内容。"
            ),
            confidence=0.86 if source else 0.15,
            review_result="pending" if source else "blocked",
        ))
        context_manager.record(
            "generate_resource",
            {"target_job": role, "knowledge_point": knowledge_point, "user_level": user_level, "resource_type": resource_type, "learner_context": learner_context or {}, "approved_sources": hits},
            {"content_type": resource.get("content_type"), "title": resource.get("title"), "generation_status": resource.get("generation_status", "pending")},
            source_chunk_ids=[str(source.get("source_chunk_id"))] if source else [],
        )
        self.last_trace = {
            "trace_id": f"trace_{uuid4().hex[:12]}",
            "target_job": role,
            "agents": [event.__dict__ for event in events],
            "retrieval_sources": hits,
            "review": {
                "approved": bool(source),
                "errors": [] if source else ["知识库无可追溯来源"],
            },
            "context_ledger": context_manager.as_dicts(),
        }
        if source:
            resource["source_chunk_id"] = str(source["source_chunk_id"])
            resource["source_text"] = str(source["content"])[:1500]
            resource["source_title"] = str(source.get("title", ""))
            resource["source_score"] = float(source.get("score", 0.0) or 0.0)
        else:
            resource["source_chunk_id"] = ""
            resource["source_text"] = ""
            resource["source_title"] = ""
            resource["source_score"] = 0.0
            resource["generation_status"] = "blocked"
        return resource

    def plan_learning_path(self, user_id: str, target_job: str, current_ability: list[float]) -> list[dict[str, Any]]:
        role = self._role(target_job)
        self._current_job.set(role)
        events: list[AgentEvent] = []
        knowledge_catalog = list(self._last_catalog.get())
        knowledge_catalog_map = dict(self._last_catalog_map.get())
        context_manager = ContextManager()
        steps = PathAgent().run(user_id, role, current_ability, knowledge_catalog, knowledge_catalog_map, events)
        context_manager.record(
            "plan_path",
            {"user_id": user_id, "target_job": role, "ability_vector": current_ability, "knowledge_catalog": knowledge_catalog},
            {"step_count": len(steps), "steps": steps},
        )
        self.last_trace = {
            "trace_id": f"trace_{uuid4().hex[:12]}",
            "target_job": role,
            "agents": [event.__dict__ for event in events],
            "review": {"approved": True, "errors": []},
            "context_ledger": context_manager.as_dicts(),
        }
        return steps

    def _trace(self, trace_id: str, user_id: str, role: str, events: list[AgentEvent], profile: ParsedProfile, diagnosis: dict[str, Any], hits: Any) -> dict[str, Any]:
        return {
            "trace_id": trace_id,
            "user_id": user_id,
            "target_job": role,
            "agents": [event.__dict__ for event in events],
            "matched_skills": profile.matched_skills,
            "negative_skills": sorted(profile.negative_skills),
            "retrieval_sources": profile.retrieval_hits if hits is None else hits,
            "diagnosis": diagnosis,
            "calibration_status": (diagnosis.get("calibration") or {}).get("status", "unvalidated"),
            "calibration_accuracy": (diagnosis.get("calibration") or {}).get("accuracy"),
            "review": {"approved": True, "errors": []},
        }


def _contains_skill(text: str, skill: str) -> bool:
    if skill.lower() in text.lower():
        return True
    aliases = {
        "JavaScript": ["js"], "TypeScript": ["ts"], "Spring Boot": ["springboot"],
        "MySQL": ["mysql", "sql"], "Kubernetes": ["k8s"], "CI/CD": ["cicd"],
        "Webpack/Vite": ["webpack", "vite"], "API设计": ["api", "接口"],
        "用户研究": ["用户调研"], "文档撰写": ["prd", "需求文档"],
        "网络协议": ["tcp", "http", "dns"], "安全编码": ["安全", "权限"],
    }
    return any(alias.lower() in text.lower() for alias in aliases.get(skill, []))


def _skill_context(text: str, skill: str, window: int = 18) -> str:
    lowered = text.lower()
    needles = [skill.lower()]
    aliases = {"JavaScript": ["js"], "MySQL": ["sql"], "Spring Boot": ["springboot"], "Kubernetes": ["k8s"]}
    needles.extend(aliases.get(skill, []))
    for needle in needles:
        index = lowered.find(needle)
        if index >= 0:
            return text[max(0, index - window): index + len(needle) + window]
    return text


def _is_negative_claim(text: str, skill: str) -> bool:
    """Return true only when a negative claim is local to this skill.

    Multi-turn review input contains more than one learner statement.  A broad
    character window can incorrectly attach a later statement such as
    “缓存穿透还不熟” to an earlier positive claim about Redis.  Evaluate each
    occurrence inside its sentence / turn boundary instead.
    """
    negative_pattern = r"不会|不熟|没学过|未接触|不了解|没做过|不懂|未掌握"
    lowered = text.lower()
    needles = [skill.lower()]
    aliases = {"JavaScript": ["js"], "MySQL": ["sql"], "Spring Boot": ["springboot"], "Kubernetes": ["k8s"]}
    needles.extend(aliases.get(skill, []))
    for needle in needles:
        start = 0
        while True:
            index = lowered.find(needle, start)
            if index < 0:
                break
            # Do not cross a conversation-turn label or a sentence boundary.
            left_boundary = max(
                lowered.rfind("\n", 0, index),
                lowered.rfind("。", 0, index),
                lowered.rfind("！", 0, index),
                lowered.rfind("？", 0, index),
            ) + 1
            right_candidates = [
                marker for marker in (
                    lowered.find("\n", index + len(needle)),
                    lowered.find("。", index + len(needle)),
                    lowered.find("！", index + len(needle)),
                    lowered.find("？", index + len(needle)),
                ) if marker >= 0
            ]
            right_boundary = min(right_candidates) if right_candidates else len(text)
            sentence = text[left_boundary:right_boundary]
            if re.search(negative_pattern, sentence, flags=re.IGNORECASE):
                return True
            start = index + len(needle)
    return False


_GAP_STATUS_REASON = {
    "grounded": "命中本岗位能力模型",
    "partial": "非本岗位核心技能，或知识库部分匹配",
    "ungrounded": "岗位能力模型与知识库均无依据，已拦截",
}


def _share_token(a: str, b: str) -> bool:
    """a/b 是否共享一个英文/技术 token（如 docker、java、spring）"""
    return bool(
        set(re.findall(r"[a-z][a-z0-9+#./-]{1,}", a))
        & set(re.findall(r"[a-z][a-z0-9+#./-]{1,}", b))
    )


def _validate_gaps(gaps: list[str], role: str, catalog: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    """层1：校验诊断出的知识/能力缺口是否属于该岗位的能力模型/知识库。

    返回 (过滤后的缺口, 校验明细)。分类：
      grounded  — 命中本岗位技能名（精确/包含）
      partial   — 命中其它岗位技能（真实技术但非本岗位核心），或出现在知识库目录，或关键词重叠
      ungrounded — 所有岗位技能模型与知识库均无依据（幻觉缺口，过滤掉不进下游）
    """
    role_profile = ROLE_PROFILES.get(role, ROLE_PROFILES["后端开发工程师"])
    role_skill_lower = [s.lower() for s, _d in role_profile["skills"]]
    # 全局技能池（所有岗位），用于区分"真实技术但非本岗位核心"与"完全无依据"
    global_skill_lower = list({
        s.lower() for rp in ROLE_PROFILES.values() for s, _d in rp["skills"]
    })
    catalog_lower = [str(c).lower() for c in (catalog or []) if str(c).strip()]

    kept: list[str] = []
    details: list[dict[str, str]] = []
    for gap in gaps:
        g = str(gap).strip()
        if not g:
            continue
        gl = g.lower()

        if any(s in gl or gl in s for s in role_skill_lower):
            status = "grounded"
        elif any(s in gl or gl in s for s in global_skill_lower):
            status = "partial"
        elif any(c in gl or gl in c for c in catalog_lower):
            status = "partial"
        elif any(_share_token(gl, s) for s in global_skill_lower):
            status = "partial"
        else:
            status = "ungrounded"

        details.append({"gap": g, "status": status, "reason": _GAP_STATUS_REASON[status]})
        if status != "ungrounded":
            kept.append(g)

    return kept, details

