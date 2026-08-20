"""
资源模块 - 资源列表、资源详情
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models.resource import Resource
from models.assessment import Assessment
from models.resource_bookmark import ResourceBookmark
from models.user import User
from routers.auth import get_current_user
from adapters import vector_adapter
from adapters.guardrail import detect_source_leak, detect_unrequested_resource_type

router = APIRouter()


# ===== 响应模型 =====

class SearchResult(BaseModel):
    title: str
    score: float
    source_chunk_id: str | None = None
    parent_source_chunk_id: str | None = None
    career_id: str | None = None


class SearchResponse(BaseModel):
    items: list[SearchResult]


class BookmarkResponse(BaseModel):
    resource_id: str
    created_at: datetime


class ResourceResponse(BaseModel):
    id: str
    assessment_id: str | None = None
    knowledge_point: str
    content_type: str
    title: str
    body: str
    difficulty: int | None = None
    source_chunk_id: str | None = None
    source_title: str | None = None
    source_score: float | None = None
    review_status: str | None = None
    review_reason: str | None = None
    generation_method: str | None = None
    display_status: str = "show"
    created_at: datetime


# ===== 接口 =====

@router.get("/search", response_model=SearchResponse)
def search_resources(
    q: str = Query(..., description="搜索关键词"),
    job: str = Query("产品经理", description="目标岗位"),
    top_k: int = Query(5, ge=1, le=20, description="返回条数"),
):
    """向量检索知识库"""
    items = vector_adapter.search_similar_resources(query=q, job=job, top_k=top_k)
    return {"items": items}


def _get_visible_owned_resource(resource_id: str, user_id: str, db: Session) -> Resource:
    resource = db.query(Resource).join(
        Assessment, Resource.assessment_id == Assessment.id
    ).filter(
        Resource.id == resource_id,
        Assessment.user_id == user_id,
        Resource.review_status.in_(["passed", "partial"]),
        Resource.source_chunk_id.isnot(None),
        Resource.source_text.isnot(None),
        Resource.is_legacy == 0,
    ).first()
    if not resource or resource.display_status != "show":
        raise HTTPException(status_code=404, detail="资源不存在")
    if detect_source_leak(resource.source_text or "", resource.body or "").get("leaked"):
        raise HTTPException(status_code=404, detail="资源正在复核，暂不可展示")
    if detect_unrequested_resource_type(resource.body or "", resource.content_type or "").get("found"):
        raise HTTPException(status_code=404, detail="资源类型不匹配，暂不可展示")
    return resource


@router.get("/bookmarks", response_model=list[BookmarkResponse])
def list_bookmarks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """返回当前学习者仍然可见的收藏资源。"""
    return db.query(ResourceBookmark).join(
        Resource, ResourceBookmark.resource_id == Resource.id
    ).join(
        Assessment, Resource.assessment_id == Assessment.id
    ).filter(
        ResourceBookmark.user_id == current_user.id,
        Assessment.user_id == current_user.id,
        Resource.review_status.in_(["passed", "partial"]),
        Resource.source_chunk_id.isnot(None),
        Resource.source_text.isnot(None),
        Resource.is_legacy == 0,
    ).order_by(ResourceBookmark.created_at.desc()).all()


@router.post("/{resource_id}/bookmark", response_model=BookmarkResponse)
def add_bookmark(
    resource_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """收藏一条属于当前学习者且已经通过来源审核的资源。"""
    _get_visible_owned_resource(resource_id, current_user.id, db)
    bookmark = db.query(ResourceBookmark).filter(
        ResourceBookmark.user_id == current_user.id,
        ResourceBookmark.resource_id == resource_id,
    ).first()
    if bookmark:
        return bookmark
    bookmark = ResourceBookmark(user_id=current_user.id, resource_id=resource_id)
    db.add(bookmark)
    db.commit()
    db.refresh(bookmark)
    return bookmark


@router.delete("/{resource_id}/bookmark")
def remove_bookmark(
    resource_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """取消收藏；重复调用保持幂等。"""
    bookmark = db.query(ResourceBookmark).filter(
        ResourceBookmark.user_id == current_user.id,
        ResourceBookmark.resource_id == resource_id,
    ).first()
    if bookmark:
        db.delete(bookmark)
        db.commit()
    return {"message": "已取消收藏"}


@router.get("/list", response_model=list[ResourceResponse])
def list_resources(
    knowledge_point: str | None = Query(None, description="按知识点过滤"),
    type: str | None = Query(None, alias="type", description="按资源类型过滤（讲义/练习/案例）"),
    assessment_id: str | None = Query(None, description="按诊断记录过滤"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取学习者可见资源。

    检索原文不属于资料库展示内容；只有已经通过审核、拥有来源链且
    非历史旧资源的内容才允许从这个面向学习者的接口返回。
    """
    # 资源无论是否按 assessment_id 查询，都必须属于当前学习者；
    # 仅依赖前端传入 assessment_id 会留下跨账户枚举的入口。
    q = db.query(Resource).join(
        Assessment, Resource.assessment_id == Assessment.id
    ).filter(
        Assessment.user_id == current_user.id,
        Resource.review_status.in_(["passed", "partial"]),
        Resource.source_chunk_id.isnot(None),
        Resource.source_text.isnot(None),
        Resource.is_legacy == 0,
    )

    if knowledge_point:
        q = q.filter(Resource.knowledge_point == knowledge_point)
    if type:
        q = q.filter(Resource.content_type == type)
    if assessment_id:
        assessment = db.query(Assessment).filter(
            Assessment.id == assessment_id,
            Assessment.user_id == current_user.id,
        ).first()
        if not assessment:
            raise HTTPException(status_code=404, detail="诊断记录不存在")
        q = q.filter(Resource.assessment_id == assessment_id)

    candidates = q.order_by(Resource.created_at.desc()).all()
    return [
        resource for resource in candidates
        if resource.display_status == "show"
        and not detect_source_leak(resource.source_text or "", resource.body or "").get("leaked")
        and not detect_unrequested_resource_type(resource.body or "", resource.content_type or "").get("found")
    ]


@router.get("/{resource_id}", response_model=ResourceResponse)
def get_resource(
    resource_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查询已审核通过的学习资源详情，不暴露被拦截或旧资源。"""
    return _get_visible_owned_resource(resource_id, current_user.id, db)
