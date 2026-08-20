"""
一次性回填脚本：给 review_status IS NULL 的旧资源补 source_text + review_status。

用法：
  python backfill_review.py --dry-run   # 只探针（检索命中率），不写库、不调 LLM 校验
  python backfill_review.py --apply     # 真正回填（重新检索 + 逐条 LLM 校验 + 落库）

依赖：llm_config.json（DeepSeek）+ qdrant_storage（向量库）+ bge-m3（嵌入模型）
"""

from __future__ import annotations

import sys

from database import SessionLocal
from models.resource import Resource
from adapters.guardrail import check_hallucination, detect_source_leak
from adapters import vector_adapter

VERDICT_TO_STATUS = {"grounded": "passed", "partial": "partial", "ungrounded": "blocked"}

# 检索最高分低于该阈值 → 视为「无可靠匹配来源」，标 blocked，禁止进入资料库。
SCORE_THRESHOLD = 0.60


def _verify(source_text: str, body: str) -> tuple[str, str]:
    """返回 (review_status, review_reason)"""
    leak = detect_source_leak(source_text, body)
    if leak.get("leaked"):
        return "blocked", f"检测到正文连续复制知识库原文，最长重复约 {leak.get('longest_run', 0)} 个字符"
    guard = check_hallucination(source_text, body)
    status = VERDICT_TO_STATUS.get(guard.get("verdict", ""), "needs_manual_review")
    return status, guard.get("reason", "")


def _llm_reachable() -> bool:
    """LLM 连通性冒烟测试，避免审核失败时误标 passed。"""
    from adapters.llm_client import chat

    try:
        return bool(chat("你是助手", "回：OK"))
    except Exception:
        return False


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "--dry-run"
    if mode not in ("--dry-run", "--apply"):
        print("用法: python backfill_review.py [--dry-run|--apply]")
        return
    dry_run = mode == "--dry-run"

    if not vector_adapter.ensure_accessible():
        print("[backfill] 向量库不可访问：很可能后端正在运行占用 Qdrant 锁（本地模式单进程）。")
        print("[backfill] 请先停止后端（Ctrl+C 停 uvicorn），再重新运行本脚本。")
        return

    if not _llm_reachable():
        print("[backfill] DeepSeek 不可达（Connection error）。为避免误标 passed，已中止。")
        print("[backfill] 请检查网络/API 后重试。")
        return

    db = SessionLocal()
    resources = db.query(Resource).filter(Resource.review_status.is_(None)).all()
    total = len(resources)
    print(f"[backfill] review_status IS NULL 共 {total} 条，模式={'dry-run' if dry_run else 'apply'}", flush=True)

    stat = {"有原文": 0, "命中补源": 0, "弱匹配跳过": 0, "未命中": 0, "passed": 0, "partial": 0, "blocked": 0, "skipped": 0, "error": 0}
    scores: list[float] = []  # dry-run 收集最高分，用于定阈值

    for i, r in enumerate(resources, 1):
        try:
            # 1. 确定原文（用「知识点 + 标题」检索，避免只按知识点名抓到跨岗位不相干文档）
            if r.source_text:
                source_text = r.source_text
                new_source = None
                stat["有原文"] += 1
            else:
                query = f"{r.knowledge_point} {r.title}".strip()
                hits = vector_adapter.search_all_careers(query, top_k=5)
                if hits:
                    top = hits[0]
                    score = float(top.get("score", 0.0) or 0.0)
                    scores.append(score)
                    source_chunk_id = str(top.get("source_chunk_id") or "").strip()
                    if score >= SCORE_THRESHOLD and source_chunk_id:
                        source_text = str(top.get("content", ""))[:1500]
                        new_source = (
                            source_chunk_id,
                            source_text,
                            str(top.get("title", "")),
                            score,
                        )
                        stat["命中补源"] += 1
                    else:
                        # 弱匹配：没有可靠来源时必须拦截，不能进入学习者资料库。
                        source_text = ""
                        new_source = None
                        stat["弱匹配拦截"] = stat.get("弱匹配拦截", 0) + 1
                else:
                    source_text = ""
                    new_source = None
                    stat["未命中"] += 1

            # 2. dry-run 只统计命中率，不校验不写库
            if dry_run:
                continue

            # 3. 校验 + 落库
            if source_text:
                status, reason = _verify(source_text, r.body)
                if new_source:
                    r.source_chunk_id, r.source_text, r.source_title, r.source_score = new_source
            else:
                status, reason = "blocked", "知识库无可靠匹配来源，禁止进入正式资料库"

            stat[status] = stat.get(status, 0) + 1
            r.review_status = status
            r.review_reason = reason

            if i % 10 == 0:
                db.commit()
                print(f"[backfill] 已处理 {i}/{total}", flush=True)
        except Exception as e:
            stat["error"] += 1
            print(f"[backfill] 第 {i} 条异常({getattr(r, 'knowledge_point', '?')}): {e}", flush=True)

    if not dry_run:
        db.commit()
    db.close()

    if dry_run and scores:
        scores.sort()
        n = len(scores)
        avg = sum(scores) / n
        print(f"[backfill] 检索最高分统计（{n} 条）：min={scores[0]:.2f} avg={avg:.2f} max={scores[-1]:.2f}", flush=True)
        buckets = [("<0.50", 0.50), ("0.50-0.55", 0.55), ("0.55-0.60", 0.60), ("0.60-0.65", 0.65), ("0.65-0.70", 0.70), (">=0.70", 2.0)]
        prev = 0.0
        for label, hi in buckets:
            c = sum(1 for s in scores if prev <= s < hi)
            print(f"    {label}: {c}", flush=True)
            prev = hi

    print("[backfill] 完成，统计：", flush=True)
    for k, v in stat.items():
        print(f"  {k}: {v}", flush=True)


if __name__ == "__main__":
    main()
