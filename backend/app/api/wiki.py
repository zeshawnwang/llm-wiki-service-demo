from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from app.models.wiki import WikiPage, WikiPageCreate, WikiPageUpdate, WikiPageMetadata, WikiPageStatus
from app.services.wiki_service import WikiService

router = APIRouter()
wiki_service = WikiService()


# ==================== Request Models ====================

class WikiPageCreateRequest(BaseModel):
    """创建Wiki页面请求"""
    title: str
    content: str = ""
    slug: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    status: WikiPageStatus = WikiPageStatus.DRAFT


class WikiPageUpdateRequest(BaseModel):
    """更新Wiki页面请求"""
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[WikiPageStatus] = None


# ==================== Routes ====================

@router.post("/pages", response_model=WikiPage)
async def create_page(request: WikiPageCreateRequest):
    """创建Wiki页面"""
    metadata = WikiPageMetadata(
        title=request.title,
        category=request.category,
        tags=request.tags or [],
        status=request.status
    )

    page_create = WikiPageCreate(
        title=request.title,
        slug=request.slug,
        content=request.content,
        metadata=metadata
    )

    return await wiki_service.create_page(page_create)


@router.get("/pages", response_model=List[WikiPage])
async def list_pages(
    status: Optional[WikiPageStatus] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None
):
    """列出Wiki页面"""
    tags = [tag] if tag else None
    return await wiki_service.list_pages(status, category, tags)


@router.get("/pages/{page_id}", response_model=WikiPage)
async def get_page(page_id: str):
    """获取Wiki页面"""
    page = await wiki_service.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    return page


@router.get("/pages/slug/{slug}", response_model=WikiPage)
async def get_page_by_slug(slug: str):
    """通过slug获取页面"""
    page = await wiki_service.get_page_by_slug(slug)
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")
    return page


@router.put("/pages/{page_id}", response_model=WikiPage)
async def update_page(page_id: str, request: WikiPageUpdateRequest):
    """更新Wiki页面"""
    existing = await wiki_service.get_page(page_id)
    if not existing:
        raise HTTPException(status_code=404, detail="页面不存在")

    metadata = None
    if any([request.category, request.tags is not None, request.status is not None]):
        metadata = WikiPageMetadata(
            title=request.title or existing.metadata.title,
            category=request.category if request.category is not None else existing.metadata.category,
            tags=request.tags if request.tags is not None else existing.metadata.tags,
            status=request.status if request.status is not None else existing.metadata.status
        )

    page_update = WikiPageUpdate(
        title=request.title,
        content=request.content,
        metadata=metadata
    )

    updated = await wiki_service.update_page(page_id, page_update)
    if not updated:
        raise HTTPException(status_code=500, detail="更新失败")
    return updated


@router.delete("/pages/{page_id}")
async def delete_page(page_id: str):
    """删除Wiki页面"""
    success = await wiki_service.delete_page(page_id)
    if not success:
        raise HTTPException(status_code=404, detail="页面不存在")
    return {"message": "删除成功"}


@router.get("/index")
async def get_index():
    """获取Wiki索引"""
    return await wiki_service.get_index()


@router.get("/pages/{page_id}/related", response_model=List[WikiPage])
async def get_related_pages(page_id: str):
    """获取相关页面"""
    return await wiki_service.get_related_pages(page_id)


@router.post("/pages/{page_id}/related/{related_id}")
async def add_related_page(page_id: str, related_id: str):
    """添加相关页面关联"""
    success = await wiki_service.add_related_page(page_id, related_id)
    if not success:
        raise HTTPException(status_code=404, detail="页面不存在")
    return {"message": "关联添加成功"}


@router.get("/stats/statistics")
async def get_statistics():
    """获取Wiki统计信息"""
    return await wiki_service.get_statistics()


@router.get("/graph")
async def get_knowledge_graph():
    """获取知识图谱数据"""
    return await wiki_service.get_knowledge_graph()
