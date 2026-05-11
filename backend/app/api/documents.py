from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Optional, List
from pydantic import BaseModel, Field

from app.models.document import Document, DocumentCreate, DocumentMetadata, DocumentType
from app.services.document_service import DocumentService

router = APIRouter()
doc_service = DocumentService()


# ==================== Request Models ====================

class DocumentCreateRequest(BaseModel):
    """创建文档请求"""
    filename: str
    content: str
    title: Optional[str] = None
    doc_type: Optional[DocumentType] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None


class DocumentUpdateRequest(BaseModel):
    """更新文档请求"""
    content: Optional[str] = None
    title: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None


class DocumentUploadMetadata(BaseModel):
    """上传文档的元数据"""
    title: Optional[str] = None
    doc_type: Optional[DocumentType] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None


# ==================== Routes ====================

@router.post("", response_model=Document)
async def create_document(request: DocumentCreateRequest):
    """创建新文档"""
    metadata = DocumentMetadata(
        title=request.title or request.filename,
        doc_type=request.doc_type or DocumentType.OTHER,
        category=request.category,
        tags=request.tags or []
    )

    doc_create = DocumentCreate(
        filename=request.filename,
        content=request.content,
        metadata=metadata
    )

    return await doc_service.create_document(doc_create)


@router.post("/upload", response_model=Document)
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = None,
    doc_type: Optional[DocumentType] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None
):
    """上传文档文件（保留multipart/form-data，因为需要接收文件）"""
    content = await file.read()
    content_str = content.decode('utf-8')

    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    metadata = DocumentMetadata(
        title=title or file.filename,
        doc_type=doc_type or DocumentType.OTHER,
        category=category,
        tags=tag_list
    )

    doc_create = DocumentCreate(
        filename=file.filename,
        content=content_str,
        metadata=metadata
    )

    return await doc_service.create_document(doc_create)


@router.get("", response_model=List[Document])
async def list_documents(
    doc_type: Optional[DocumentType] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None
):
    """列出所有文档"""
    tags = [tag] if tag else None
    return await doc_service.list_documents(doc_type, category, tags)


@router.get("/{doc_id}", response_model=Document)
async def get_document(doc_id: str):
    """获取文档详情"""
    doc = await doc_service.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


@router.put("/{doc_id}", response_model=Document)
async def update_document(doc_id: str, request: DocumentUpdateRequest):
    """更新文档"""
    existing = await doc_service.get_document(doc_id)
    if not existing:
        raise HTTPException(status_code=404, detail="文档不存在")

    metadata = None
    if any([request.title, request.category, request.tags is not None]):
        metadata = DocumentMetadata(
            title=request.title or existing.metadata.title,
            doc_type=existing.metadata.doc_type,
            category=request.category or existing.metadata.category,
            tags=request.tags if request.tags is not None else existing.metadata.tags
        )

    updated = await doc_service.update_document(doc_id, request.content, metadata)
    if not updated:
        raise HTTPException(status_code=500, detail="更新失败")
    return updated


@router.delete("/{doc_id}")
async def delete_document(doc_id: str):
    """删除文档"""
    success = await doc_service.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"message": "删除成功"}


@router.get("/stats/statistics")
async def get_statistics():
    """获取文档统计信息"""
    return await doc_service.get_statistics()
