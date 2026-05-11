from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class DocumentType(str, Enum):
    """文档类型"""
    ARTICLE = "article"
    PAPER = "paper"
    TRANSCRIPT = "transcript"
    NOTE = "note"
    CODE = "code"
    OTHER = "other"


class DocumentMetadata(BaseModel):
    """文档元数据"""
    title: Optional[str] = None
    author: Optional[str] = None
    source: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    category: Optional[str] = None
    doc_type: DocumentType = DocumentType.OTHER
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    file_size: int = 0
    file_type: str = ""
    summary: Optional[str] = None
    custom_fields: Dict[str, Any] = Field(default_factory=dict)


class Document(BaseModel):
    """文档模型"""
    id: str
    filename: str
    content: str
    metadata: DocumentMetadata
    
    class Config:
        from_attributes = True


class DocumentCreate(BaseModel):
    """创建文档请求"""
    filename: str
    content: str
    metadata: Optional[DocumentMetadata] = None