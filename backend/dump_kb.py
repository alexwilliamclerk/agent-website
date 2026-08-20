"""知识库内容查看工具（只读，不会修改任何数据）
用法：
  python dump_kb.py              → 全部
  python dump_kb.py frontend     → 前端开发工程师
  python dump_kb.py backend      → 后端开发工程师
  python dump_kb.py ops          → 运维工程师
  python dump_kb.py product      → 产品经理
"""
import sys
from qdrant_client import QdrantClient

CAREER_MAP = {
    "frontend": "frontend_engineer",
    "backend": "java_backend_engineer",
    "ops": "operations_engineer",
    "product": "product_manager",
}

filter_id = CAREER_MAP.get(sys.argv[1]) if len(sys.argv) > 1 else None

client = QdrantClient(path="./qdrant_storage")
points = client.scroll(
    collection_name="career_knowledge_v1",
    limit=9999,
    with_payload=True,
    with_vectors=False,
)[0]

count = 0
for p in points:
    pl = p.payload or {}
    cid = pl.get("career_id", "")
    if filter_id and cid != filter_id:
        continue
    count += 1
    print(f"[{cid}] {pl.get('source_document','')}")
    print(pl.get("content", ""))
    print("-" * 60)

label = filter_id or "全部"
print(f"\n= {label}: {count} 条")
