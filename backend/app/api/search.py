from fastapi import APIRouter, Query
from typing import Optional, List, Dict, Any

from app.services.search_service import SearchService

router = APIRouter()
search_service = SearchService()


@router.get("")
async def search(
    q: str = Query(..., description="搜索关键词"),
    search_type: str = Query("semantic", description="搜索类型: keyword, semantic, hybrid"),
    limit: int = Query(10, ge=1, le=50),
    doc_type: Optional[str] = Query(None, description="限制类型: document, wiki")
):
    """
    搜索文档和Wiki页面
    
    - **q**: 搜索关键词
    - **search_type**: 搜索类型 (keyword=关键词, semantic=语义, hybrid=混合)
    - **limit**: 返回结果数量
    - **doc_type**: 限制搜索类型 (document/wiki)
    """
    results = await search_service.search(
        query=q,
        search_type=search_type,
        limit=limit,
        doc_type=doc_type
    )
    return {
        "query": q,
        "search_type": search_type,
        "total": len(results),
        "results": results
    }


@router.get("/recommendations/{content_type}/{content_id}")
async def get_recommendations(
    content_type: str,  # document or wiki
    content_id: str,
    limit: int = Query(5, ge=1, le=20)
):
    """获取相关内容推荐"""
    if content_type not in ["document", "wiki"]:
        return {"error": "content_type必须是document或wiki"}
    
    recommendations = await search_service.get_recommendations(
        content_id=content_id,
        content_type=content_type,
        limit=limit
    )
    
    return {
        "content_id": content_id,
        "content_type": content_type,
        "recommendations": recommendations
    }


@router.post("/rebuild-index")
async def rebuild_index():
    """重建搜索索引"""
    stats = await search_service.rebuild_index()
    return {
        "message": "索引重建完成",
        "stats": stats
    }