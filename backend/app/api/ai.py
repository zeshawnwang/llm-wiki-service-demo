from fastapi import APIRouter, HTTPException
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from app.services.ai_service import AIService
from app.services.document_service import DocumentService
from app.services.wiki_service import WikiService
from app.config import get_settings

router = APIRouter()
ai_service = AIService()
doc_service = DocumentService()
wiki_service = WikiService()


# ==================== Request Models ====================

class ContentInput(BaseModel):
    """通过doc_id或content输入内容"""
    doc_id: Optional[str] = None
    content: Optional[str] = None


class SummarizeRequest(ContentInput):
    """生成摘要请求"""
    max_length: int = 500


class GenerateWikiRequest(BaseModel):
    """生成Wiki请求"""
    doc_id: str
    title: Optional[str] = None
    related_docs: Optional[List[str]] = None


class ChatRequest(BaseModel):
    """知识库问答请求（需手动指定文档ID）"""
    query: str
    doc_ids: Optional[List[str]] = None
    page_ids: Optional[List[str]] = None


class AskRequest(BaseModel):
    """智能问答请求（自动检索）"""
    query: str
    top_k: int = 5
    retrieval: Optional[str] = None  # 不传则使用 .env 中的 QA_RETRIEVAL_MODE


class ProcessRequest(BaseModel):
    """工具处理请求"""
    message: str
    history: Optional[List[Dict[str, str]]] = None


# ==================== Routes ====================

@router.post("/summarize")
async def summarize_document(request: SummarizeRequest):
    """生成文档摘要"""
    content = await _resolve_content(request.doc_id, request.content)
    summary = await ai_service.summarize_document(content, request.max_length)
    return {"summary": summary}


@router.post("/classify")
async def classify_document(request: ContentInput):
    """自动分类文档"""
    content = await _resolve_content(request.doc_id, request.content)
    classification = await ai_service.classify_document(content)
    return classification


@router.post("/generate-wiki")
async def generate_wiki_page(request: GenerateWikiRequest):
    """从原始文档生成Wiki页面"""
    doc = await doc_service.get_document(request.doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    result = await ai_service.generate_wiki_page(
        source_content=doc.content,
        title=request.title or doc.metadata.title,
        related_docs=request.related_docs or []
    )

    return result


@router.post("/chat")
async def chat_with_knowledge(request: ChatRequest):
    """基于知识库进行问答（需手动指定文档ID）"""
    answer = await ai_service.chat_with_knowledge(
        query=request.query,
        context_docs=request.doc_ids,
        context_pages=request.page_ids
    )

    return {"answer": answer}


@router.post("/ask")
async def smart_ask(request: AskRequest):
    """
    智能问答：用户只管提问，系统从Wiki知识库中检索相关内容并生成回答。

    检索模式（retrieval参数）：
    - "ai"（默认）: AI理解问题后从Wiki目录中选取相关条目
    - "auto": Wiki页面数低于阈值时直接全部给AI，超过则先关键词预筛再AI精选
    """
    valid_retrievals = ["ai", "auto"]
    retrieval_mode = request.retrieval or get_settings().qa_retrieval_mode
    if retrieval_mode not in valid_retrievals:
        raise HTTPException(
            status_code=400,
            detail=f"无效的检索模式: {retrieval_mode}，可选: {', '.join(valid_retrievals)}"
        )

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    result = await ai_service.smart_qa(
        query=request.query,
        top_k=request.top_k,
        retrieval=retrieval_mode
    )

    return result


@router.post("/extract-entities")
async def extract_entities(request: ContentInput):
    """从内容中提取实体"""
    content = await _resolve_content(request.doc_id, request.content)
    entities = await ai_service.extract_entities(content)
    return {"entities": entities}


@router.post("/suggest-links")
async def suggest_links(page_id: str):
    """建议页面链接"""
    page = await wiki_service.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="页面不存在")

    all_pages = await wiki_service.list_pages()
    existing_pages = [
        {"id": p.id, "title": p.metadata.title}
        for p in all_pages if p.id != page_id
    ]

    suggestions = await ai_service.suggest_links(page.content, existing_pages)
    return {"suggestions": suggestions}


@router.post("/process")
async def process_with_tools(request: ProcessRequest):
    """使用工具处理用户请求"""
    result = await ai_service.process_with_tools(request.message, request.history)
    return result


# ==================== Helpers ====================

async def _resolve_content(doc_id: Optional[str], content: Optional[str]) -> str:
    """解析内容：优先用doc_id，否则用content"""
    if doc_id:
        doc = await doc_service.get_document(doc_id)
        if not doc:
            raise HTTPException(status_code=404, detail="文档不存在")
        return doc.content
    if content:
        return content
    raise HTTPException(status_code=400, detail="需要提供doc_id或content")
