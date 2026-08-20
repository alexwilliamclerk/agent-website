"""
向量库接口适配层
队友接口格式（Qdrant + BGE-M3） -> 我的格式

依赖 qdrant-client、FlagEmbedding，仅在调用检索函数时按需导入，
未安装时后端其余功能不受影响，搜索接口返回空列表。
"""

import json
import os
import re

# ─── 岗位 → Qdrant career_id 映射 ──────────────────
# 队友用英文 career_id 标识岗位，这里做中文名到英文的映射

JOB_CAREER_MAP: dict[str, str] = {
    "产品经理":      "product_manager",
    "前端开发工程师": "frontend_engineer",
    "后端开发工程师": "java_backend_engineer",
    "运维工程师":    "operations_engineer",
}

_BACKEND_DIR = os.path.dirname(os.path.dirname(__file__))
_QDRANT_PATH = os.getenv("QDRANT_PATH", os.path.join(_BACKEND_DIR, "qdrant_storage"))
_QDRANT_URL = os.getenv("QDRANT_URL", "").strip()
_QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "").strip() or None
_QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "career_knowledge_v1")
_MODEL_PATH = os.getenv("EMBEDDING_MODEL_PATH", os.path.join(_BACKEND_DIR, "bge-m3"))
_KNOWLEDGE_DIR = os.getenv(
    "KNOWLEDGE_DIR",
    os.path.join(os.path.dirname(_BACKEND_DIR), "knowledge", "active"),
)

_client = None
_model = None
_imports_checked: bool = False
_lexical_records: list[dict] | None = None


def _ensure_imports() -> bool:
    """按需导入 qdrant-client / FlagEmbedding，未安装返回 False"""
    global _imports_checked, QdrantClient, Filter, FieldCondition, MatchValue, BGEM3FlagModel
    if _imports_checked:
        return True
    try:
        from qdrant_client import QdrantClient as _QdrantClient
        from qdrant_client.models import Filter as _Filter, FieldCondition as _FieldCondition, MatchValue as _MatchValue
        from FlagEmbedding import BGEM3FlagModel as _BGEM3FlagModel

        QdrantClient = _QdrantClient
        Filter = _Filter
        FieldCondition = _FieldCondition
        MatchValue = _MatchValue
        BGEM3FlagModel = _BGEM3FlagModel
        _imports_checked = True
        return True
    except ImportError:
        return False


def _get_client():
    """获取 Qdrant 客户端：配置 URL 时使用服务模式，否则使用本地文件模式。"""
    global _client
    if _client is None:
        if _QDRANT_URL:
            _client = QdrantClient(url=_QDRANT_URL, api_key=_QDRANT_API_KEY)
        else:
            _client = QdrantClient(path=_QDRANT_PATH)
    return _client


def _get_model():
    """获取或创建 BGE-M3 嵌入模型（单例）"""
    global _model
    if _model is None:
        _model = BGEM3FlagModel(_MODEL_PATH, use_fp16=True)
    return _model


def _serialize_hit(hit) -> dict:
    """将 Qdrant 点转换为统一的知识库来源结构。

    `point_id` 是 Qdrant 的内部存储 ID，不能作为业务来源 ID；
    `source_chunk_id` 必须来自知识库 payload，供资源审核和页面追溯。
    """
    payload = hit.payload or {}
    source_chunk_id = str(payload.get("source_chunk_id") or "").strip()
    content = str(payload.get("content") or "")
    try:
        score = round(float(hit.score), 2)
    except (TypeError, ValueError):
        score = 0.0

    candidate_requirement_ids = payload.get("candidate_requirement_ids") or []
    if not isinstance(candidate_requirement_ids, list):
        candidate_requirement_ids = [str(candidate_requirement_ids)]

    return {
        # 兼容旧调用方，但不再把 Qdrant point ID 当作业务 ID。
        "id": source_chunk_id,
        "source_chunk_id": source_chunk_id,
        "parent_source_chunk_id": str(payload.get("parent_source_chunk_id") or ""),
        "point_id": str(hit.id),
        "career_id": str(payload.get("career_id") or ""),
        "candidate_requirement_ids": [str(x) for x in candidate_requirement_ids],
        "review_status": str(payload.get("review_status") or ""),
        "title": str(payload.get("source_document") or ""),
        "content": content,
        "score": score,
    }


def _load_lexical_records() -> list[dict]:
    """Load the normalized JSONL slices for a dependency-free fallback.

    Qdrant+BGE-M3 remains the primary retriever.  The fallback is deliberately
    limited to the same normalized, review-ready slices and returns the same
    source fields, so generation and guardrail behavior do not change when the
    embedding model is temporarily unavailable.
    """
    global _lexical_records
    if _lexical_records is not None:
        return _lexical_records

    records: list[dict] = []
    if not os.path.isdir(_KNOWLEDGE_DIR):
        _lexical_records = records
        return records

    for filename in sorted(os.listdir(_KNOWLEDGE_DIR)):
        if not filename.endswith(".jsonl"):
            continue
        path = os.path.join(_KNOWLEDGE_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as file:
                for line in file:
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(item, dict):
                        continue
                    if str(item.get("review_status") or "") != "ready_for_reembedding":
                        continue
                    source_chunk_id = str(item.get("source_chunk_id") or "").strip()
                    content = str(item.get("content") or "").strip()
                    career_id = str(item.get("career_id") or "").strip()
                    if source_chunk_id and content and career_id:
                        records.append({
                            "source_chunk_id": source_chunk_id,
                            "parent_source_chunk_id": str(item.get("parent_source_chunk_id") or ""),
                            "career_id": career_id,
                            "candidate_requirement_ids": [
                                str(value) for value in (item.get("candidate_requirement_ids") or [])
                            ],
                            "title": str(item.get("source_document") or ""),
                            "content": content,
                            "review_status": "ready_for_reembedding",
                        })
        except OSError:
            continue

    _lexical_records = records
    print(f"[RAG] 已加载词法降级索引: {len(records)} 条知识片段", flush=True)
    return records


def _query_terms(text: str) -> set[str]:
    """Extract searchable English tokens and Chinese bi/tri-grams."""
    normalized = re.sub(r"\s+", "", str(text or "").lower())
    terms = set(re.findall(r"[a-z0-9][a-z0-9+#._/-]{1,}", normalized))
    for run in re.findall(r"[\u4e00-\u9fff]+", normalized):
        for size in (2, 3):
            terms.update(run[index:index + size] for index in range(len(run) - size + 1))
    return {term for term in terms if len(term) >= 2}


_LEXICAL_STOP_TERMS = {
    "后端", "开发", "工程", "工程师", "前端", "运维", "产品", "经理",
    "常见", "问题", "核心", "知识", "知识点", "岗位", "学习", "什么",
    "作用", "原理", "如何", "以及", "分别", "哪些", "是否", "可以",
}


def _lexical_search(query: str, career_id: str | None, top_k: int) -> list[dict]:
    """Return source-traceable lexical matches when vector retrieval is unavailable."""
    terms = _query_terms(query)
    if not terms:
        return []

    normalized_query = re.sub(r"\s+", "", str(query or "").lower())
    specific_terms = {term for term in terms if term not in _LEXICAL_STOP_TERMS}
    if not specific_terms:
        specific_terms = terms
    scored: list[tuple[float, dict]] = []
    for record in _load_lexical_records():
        if career_id and record["career_id"] != career_id:
            continue
        searchable = re.sub(
            r"\s+", "", f"{record['title']} {record['content']}".lower()
        )
        metadata = " ".join(record.get("candidate_requirement_ids") or []).lower()
        content_matches = {term for term in specific_terms if term in searchable}
        metadata_matches = {term for term in specific_terms if term in metadata}
        if not content_matches and not metadata_matches:
            continue
        content_coverage = len(content_matches) / max(1, len(specific_terms))
        metadata_coverage = len(metadata_matches) / max(1, len(specific_terms))
        exact_bonus = 0.15 if normalized_query and normalized_query in searchable else 0.0
        score = min(0.99, 0.30 + 0.45 * content_coverage + 0.35 * metadata_coverage + exact_bonus)
        scored.append((score, record))

    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    for score, record in scored[:top_k]:
        results.append({
            "id": record["source_chunk_id"],
            "source_chunk_id": record["source_chunk_id"],
            "parent_source_chunk_id": record["parent_source_chunk_id"],
            "point_id": record["source_chunk_id"],
            "career_id": record["career_id"],
            "candidate_requirement_ids": record["candidate_requirement_ids"],
            "review_status": record["review_status"],
            "title": record["title"],
            "content": record["content"],
            "score": round(score, 2),
        })
    return results


def search_similar_resources(query: str, job: str = "产品经理", top_k: int = 5) -> list:
    """
    相似资源检索（向量检索）

    输入：
        query: 查询文本
        job: 目标岗位（用于过滤对应岗位的知识库）
        top_k: 返回数量

    输出：包含 `source_chunk_id`、原文、岗位、审核状态和检索分数的来源对象。

    如果 qdrant-client/FlagEmbedding 未安装或模型暂时不可用，自动使用
    knowledge/active 中的标准化 JSONL 做词法降级检索；岗位未配置时返回空列表。
    """
    career_id = JOB_CAREER_MAP.get(job)
    if not career_id:
        return []

    if not _ensure_imports():
        return _lexical_search(query, career_id, top_k)

    try:
        model = _get_model()
        client = _get_client()

        query_vec = model.encode([query], return_dense=True)["dense_vecs"][0].tolist()

        response = client.query_points(
            collection_name=_QDRANT_COLLECTION,
            query=query_vec,
            query_filter=Filter(must=[
                FieldCondition(key="career_id", match=MatchValue(value=career_id)),
                FieldCondition(key="review_status", match=MatchValue(value="ready_for_reembedding")),
            ]),
            limit=top_k,
        )

        result_list = [_serialize_hit(hit) for hit in response.points]
        return result_list or _lexical_search(query, career_id, top_k)
    except Exception as exc:
        print(f"[RAG] 向量检索不可用，切换词法降级检索: {exc}", flush=True)
        return _lexical_search(query, career_id, top_k)


def search_all_careers(query: str, top_k: int = 3) -> list:
    """
    跨岗位检索（资源表未存岗位，回填旧数据时用）

    与 search_similar_resources 同逻辑，但不按 career_id 过滤，
    仅保留 review_status == "ready_for_reembedding" 的质量过滤。

    返回结构同 search_similar_resources，`source_chunk_id` 仍必须来自 payload。
    """
    if not _ensure_imports():
        return _lexical_search(query, None, top_k)

    try:
        model = _get_model()
        client = _get_client()

        query_vec = model.encode([query], return_dense=True)["dense_vecs"][0].tolist()

        response = client.query_points(
            collection_name=_QDRANT_COLLECTION,
            query=query_vec,
            query_filter=Filter(must=[
                FieldCondition(key="review_status", match=MatchValue(value="ready_for_reembedding")),
            ]),
            limit=top_k,
        )

        result_list = [_serialize_hit(hit) for hit in response.points]
        return result_list or _lexical_search(query, None, top_k)
    except Exception as exc:
        print(f"[RAG] 跨岗位向量检索不可用，切换词法降级检索: {exc}", flush=True)
        return _lexical_search(query, None, top_k)


def ensure_accessible() -> bool:
    """预检向量库是否可访问（本地模式单进程，后端运行时 Qdrant 会被锁，返回 False）"""
    if not _ensure_imports():
        return False
    try:
        _get_client()
        return True
    except Exception:
        return False


def search_similar_cases(user_vector: list, top_k: int = 5) -> list:
    """
    相似案例检索（暂未接入，保留接口占位）

    输入：
        user_vector: 用户能力向量
        top_k: 返回数量

    输出：
        [
            {
                "case_id": "case_001",
                "similarity": 0.92,
                "user_profile": {"target_job": "前端开发", "study_months": 6},
                "learning_outcome": "成功入职"
            }
        ]
    """
    return []
