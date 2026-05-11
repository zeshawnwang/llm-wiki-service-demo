from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class WikiPageStatus(str, Enum):
    """Wiki页面状态"""
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class WikiPageMetadata(BaseModel):
    """Wiki页面元数据"""
    title: str
    description: Optional[str] = None
    author: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    category: Optional[str] = None
    status: WikiPageStatus = WikiPageStatus.DRAFT
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    version: int = 1
    parent_id: Optional[str] = None
    related_pages: List[str] = Field(default_factory=list)
    source_documents: List[str] = Field(default_factory=list)
    custom_fields: Dict[str, Any] = Field(default_factory=dict)


class WikiPage(BaseModel):
    """Wiki页面模型"""
    id: str
    slug: str  # URL友好的标识
    content: str  # Markdown内容
    metadata: WikiPageMetadata
    
    class Config:
        from_attributes = True


class WikiPageCreate(BaseModel):
    """创建Wiki页面请求"""
    title: str
    slug: Optional[str] = None
    content: str = ""
    metadata: Optional[WikiPageMetadata] = None


class WikiPageUpdate(BaseModel):
    """更新Wiki页面请求"""
    title: Optional[str] = None
    content: Optional[str] = None
    metadata: Optional[WikiPageMetadata] = None