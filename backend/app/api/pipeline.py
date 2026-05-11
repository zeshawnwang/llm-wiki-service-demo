from fastapi import APIRouter, HTTPException
from typing import Optional, List
from pydantic import BaseModel

from app.services.pipeline_service import IngestionPipeline

router = APIRouter()
pipeline = IngestionPipeline()


# ==================== Request Models ====================

class PipelineRunRequest(BaseModel):
    """执行流水线请求"""
    doc_ids: Optional[List[str]] = None  # 为空则自动发现未处理文档
    auto_rebuild: bool = True


# ==================== Routes ====================

@router.get("/status")
async def get_pipeline_status():
    """
    获取流水线状态
    - 有多少文档待处理
    - 有多少已处理
    - 是否可以运行
    """
    return await pipeline.get_pipeline_status()


@router.post("/run")
async def run_pipeline(request: PipelineRunRequest):
    """
    执行知识摄入流水线

    流程：
    1. 发现未处理的原始文档
    2. 对每篇文档，AI判断与已有Wiki的关系
    3. 执行新建/合并/跳过操作
    4. 重建搜索索引
    5. 重新评估知识结构（可选）
    """
    report = await pipeline.run(
        doc_ids=request.doc_ids,
        auto_rebuild_structure=request.auto_rebuild
    )

    return report.to_dict()


@router.post("/analyze/{doc_id}")
async def analyze_single_document(doc_id: str):
    """
    预览单篇文档的处理策略（不实际执行）
    用于在运行流水线前查看AI的建议
    """
    from app.services.document_service import DocumentService
    from app.services.wiki_service import WikiService

    doc_service = DocumentService()
    wiki_service = WikiService()

    doc = await doc_service.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 获取已有Wiki页面
    existing_wiki_pages = []
    all_wiki = await wiki_service.list_pages()
    for wp in all_wiki:
        existing_wiki_pages.append({
            "id": wp.id,
            "title": wp.metadata.title,
            "tags": wp.metadata.tags,
            "category": wp.metadata.category,
            "status": wp.metadata.status.value
        })

    # 分析
    analysis = await pipeline._analyze_new_document(
        new_doc={
            "id": doc.id,
            "title": doc.metadata.title,
            "content": doc.content,
            "tags": doc.metadata.tags,
            "category": doc.metadata.category,
            "doc_type": doc.metadata.doc_type.value
        },
        existing_wiki_pages=existing_wiki_pages
    )

    return {
        "doc_id": doc_id,
        "doc_title": doc.metadata.title,
        "analysis": analysis
    }


@router.get("/structure")
async def get_knowledge_structure():
    """
    获取当前知识库的结构分析
    - 建议的新分类
    - 建议的页面关联
    - 孤立页面
    - 知识缺口
    """
    suggestions = await pipeline._ai_rebuild_knowledge_structure()
    return suggestions
