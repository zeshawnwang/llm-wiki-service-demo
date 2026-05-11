"""
文档管理服务 - 处理原始资料层的所有操作
"""
import uuid
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

from app.config import get_settings
from app.models.document import Document, DocumentMetadata, DocumentCreate, DocumentType
from app.tools.file_tools import FileTools


class DocumentService:
    """文档管理服务"""
    
    def __init__(self):
        self.settings = get_settings()
        self.file_tools = FileTools(
            raw_dir=self.settings.raw_dir,
            wiki_dir=self.settings.wiki_dir
        )
    
    def _generate_id(self, content: str, filename: str) -> str:
        """生成文档ID"""
        # 使用内容哈希 + 文件名生成唯一ID
        hash_input = f"{content[:100]}{filename}{datetime.now().isoformat()}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:12]
    
    async def create_document(self, doc_create: DocumentCreate) -> Document:
        """创建新文档"""
        # 生成ID
        doc_id = self._generate_id(doc_create.content, doc_create.filename)
        
        # 准备元数据
        metadata = doc_create.metadata or DocumentMetadata()
        metadata.title = metadata.title or doc_create.filename
        metadata.file_size = len(doc_create.content.encode('utf-8'))
        metadata.file_type = Path(doc_create.filename).suffix.lower()
        metadata.updated_at = datetime.now()
        
        # 保存到文件系统
        metadata_dict = metadata.model_dump()
        success = await self.file_tools.write_raw_document(
            doc_id=doc_id,
            content=doc_create.content,
            metadata=metadata_dict
        )
        
        if not success:
            raise Exception("保存文档失败")
        
        return Document(
            id=doc_id,
            filename=doc_create.filename,
            content=doc_create.content,
            metadata=metadata
        )
    
    async def get_document(self, doc_id: str) -> Optional[Document]:
        """获取文档"""
        content = await self.file_tools.read_raw_document(doc_id)
        if content is None:
            return None
        
        # 解析frontmatter
        try:
            from python_frontmatter import loads
            post = loads(content)
            metadata = DocumentMetadata(**post.metadata) if post.metadata else DocumentMetadata()
            content = post.content
        except:
            metadata = DocumentMetadata()
        
        return Document(
            id=doc_id,
            filename=f"{doc_id}.md",
            content=content,
            metadata=metadata
        )
    
    async def list_documents(
        self,
        doc_type: Optional[DocumentType] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[Document]:
        """列出文档，支持过滤"""
        raw_docs = await self.file_tools.list_raw_documents()
        documents = []
        
        for doc_info in raw_docs:
            doc_id = doc_info["id"]
            doc = await self.get_document(doc_id)
            if doc:
                # 应用过滤器
                if doc_type and doc.metadata.doc_type != doc_type:
                    continue
                if category and doc.metadata.category != category:
                    continue
                if tags and not any(tag in doc.metadata.tags for tag in tags):
                    continue
                documents.append(doc)
        
        # 按更新时间排序
        documents.sort(key=lambda x: x.metadata.updated_at, reverse=True)
        return documents
    
    async def update_document(
        self,
        doc_id: str,
        content: Optional[str] = None,
        metadata: Optional[DocumentMetadata] = None
    ) -> Optional[Document]:
        """更新文档"""
        existing = await self.get_document(doc_id)
        if not existing:
            return None
        
        # 更新内容
        new_content = content if content is not None else existing.content
        
        # 更新元数据
        new_metadata = metadata if metadata else existing.metadata
        new_metadata.updated_at = datetime.now()
        if content is not None:
            new_metadata.file_size = len(content.encode('utf-8'))
        
        # 保存
        success = await self.file_tools.write_raw_document(
            doc_id=doc_id,
            content=new_content,
            metadata=new_metadata.model_dump()
        )
        
        if not success:
            raise Exception("更新文档失败")
        
        return Document(
            id=doc_id,
            filename=existing.filename,
            content=new_content,
            metadata=new_metadata
        )
    
    async def delete_document(self, doc_id: str) -> bool:
        """删除文档"""
        return await self.file_tools.delete_raw_document(doc_id)
    
    async def search_documents(self, query: str) -> List[Document]:
        """简单关键词搜索"""
        all_docs = await self.list_documents()
        results = []
        query_lower = query.lower()
        
        for doc in all_docs:
            # 搜索标题、内容、标签
            if (query_lower in doc.metadata.title.lower() or
                query_lower in doc.content.lower() or
                any(query_lower in tag.lower() for tag in doc.metadata.tags)):
                results.append(doc)
        
        return results
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取文档统计信息"""
        documents = await self.list_documents()
        
        type_counts = {}
        category_counts = {}
        total_size = 0
        
        for doc in documents:
            # 类型统计
            doc_type = doc.metadata.doc_type.value
            type_counts[doc_type] = type_counts.get(doc_type, 0) + 1
            
            # 分类统计
            category = doc.metadata.category or "未分类"
            category_counts[category] = category_counts.get(category, 0) + 1
            
            # 总大小
            total_size += doc.metadata.file_size
        
        return {
            "total_documents": len(documents),
            "total_size_bytes": total_size,
            "type_distribution": type_counts,
            "category_distribution": category_counts
        }