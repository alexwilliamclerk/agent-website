"""一次性清理历史资源，阻止原始切片或未审核资源继续展示。

用法：
    python sanitize_resources.py --dry-run
    python sanitize_resources.py --apply

该脚本只修改业务数据库中的资源审核状态，不修改 Qdrant 知识库。
"""

from __future__ import annotations

import sys

from database import SessionLocal
from models.resource import Resource
from adapters.guardrail import detect_source_leak, detect_unrequested_resource_type


def classify(resource: Resource) -> tuple[str | None, str | None]:
    """返回需要写入的状态和原因；None 表示当前记录无需修改。"""
    source_id = str(resource.source_chunk_id or "").strip()
    source_text = str(resource.source_text or "").strip()
    body = str(resource.body or "").strip()

    if resource.review_status != "passed":
        return "blocked", "历史资源未通过正式审核，已从学习者资料库隔离"
    if not source_id or not source_text:
        return "blocked", "历史资源缺少可追溯来源，已从学习者资料库隔离"

    extra_type = detect_unrequested_resource_type(body, resource.content_type or "")
    if extra_type.get("found"):
        return "blocked", f"历史资源追加了未请求的{extra_type.get('type')}章节，已从学习者资料库隔离"

    leak = detect_source_leak(source_text, body)
    if leak.get("leaked"):
        return "blocked", f"历史资源包含知识库原文连续复制，最长重复约 {leak.get('longest_run', 0)} 个字符"
    return None, None


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--dry-run"
    if mode not in {"--dry-run", "--apply"}:
        raise SystemExit("用法: python sanitize_resources.py [--dry-run|--apply]")

    db = SessionLocal()
    try:
        resources = db.query(Resource).all()
        changed = 0
        for resource in resources:
            status, reason = classify(resource)
            if status is None:
                continue
            changed += 1
            print(f"[{mode}] {resource.id} -> {status}: {reason}")
            if mode == "--apply":
                resource.review_status = status
                resource.review_reason = reason
                resource.is_legacy = 1

        if mode == "--apply":
            db.commit()
        print(f"待隔离资源: {changed}/{len(resources)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
