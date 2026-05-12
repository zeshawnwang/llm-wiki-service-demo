"""
Wiki知识服务 - 处理Wiki层的所有操作
"""
import re
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any

from app.config import get_settings
from app.models.wiki import WikiPage, WikiPageMetadata, WikiPageCreate, WikiPageUpdate, WikiPageStatus
from app.tools.file_tools import FileTools
from app.utils.logger import get_logger

logger = get_logger(__name__)


class WikiService:
    """Wiki知识服务"""
    
    def __init__(self):
        self.settings = get_settings()
        self.file_tools = FileTools(
            raw_dir=self.settings.raw_dir,
            wiki_dir=self.settings.wiki_dir
        )
    
    def _generate_slug(self, title: str) -> str:
        """从标题生成URL友好的slug"""
        # 转换为小写，替换空格为连字符，移除特殊字符
        slug = title.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug[:50]  # 限制长度
    
    def _generate_id(self, title: str) -> str:
        """生成页面ID"""
        hash_input = f"{title}{datetime.now().isoformat()}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:12]
    
    async def create_page(self, page_create: WikiPageCreate) -> WikiPage:
        """创建Wiki页面"""
        # 生成ID和slug
        page_id = self._generate_id(page_create.title)
        slug = page_create.slug or self._generate_slug(page_create.title)
        
        # 准备元数据
        metadata = page_create.metadata or WikiPageMetadata(title=page_create.title)
        metadata.title = page_create.title
        metadata.updated_at = datetime.now()
        
        # 保存页面
        metadata_dict = metadata.model_dump(mode="json")
        success = await self.file_tools.write_wiki_page(
            page_id=page_id,
            content=page_create.content,
            metadata=metadata_dict
        )
        
        if not success:
            raise Exception("保存Wiki页面失败")
        
        # 更新索引
        await self.file_tools.update_index(page_id, {
            "title": metadata.title,
            "slug": slug,
            "tags": metadata.tags,
            "category": metadata.category,
            "status": metadata.status.value,
            "updated_at": metadata.updated_at.isoformat()
        })
        
        return WikiPage(
            id=page_id,
            slug=slug,
            content=page_create.content,
            metadata=metadata
        )
    
    async def get_page(self, page_id: str) -> Optional[WikiPage]:
        """获取Wiki页面"""
        page_data = await self.file_tools.read_wiki_page(page_id)
        if not page_data:
            return None
        
        # 构建元数据
        meta_dict = page_data.get("metadata", {})
        # 确保title存在
        if "title" not in meta_dict:
            meta_dict["title"] = "Untitled"
        
        # 清理 related_pages 中的 None 值
        if "related_pages" in meta_dict and isinstance(meta_dict["related_pages"], list):
            meta_dict["related_pages"] = [
                page_id for page_id in meta_dict["related_pages"] 
                if page_id is not None and isinstance(page_id, str) and page_id.strip()
            ]
        
        # 清理 source_documents 中的 None 值
        if "source_documents" in meta_dict and isinstance(meta_dict["source_documents"], list):
            meta_dict["source_documents"] = [
                doc_id for doc_id in meta_dict["source_documents"] 
                if doc_id is not None and isinstance(doc_id, str) and doc_id.strip()
            ]
        
        metadata = WikiPageMetadata(**meta_dict)
        
        return WikiPage(
            id=page_id,
            slug=self._generate_slug(metadata.title),
            content=page_data["content"],
            metadata=metadata
        )
    
    async def get_page_by_slug(self, slug: str) -> Optional[WikiPage]:
        """通过slug获取页面"""
        # 获取所有页面，查找匹配的slug
        pages = await self.list_pages()
        for page in pages:
            if page.slug == slug:
                return page
        return None
    
    async def list_pages(
        self,
        status: Optional[WikiPageStatus] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> List[WikiPage]:
        """列出Wiki页面，支持过滤"""
        all_pages_data = await self.file_tools.list_wiki_pages()
        pages = []
        
        for page_data in all_pages_data:
            page_id = page_data.get("id")
            if not page_id:
                continue
                
            page = await self.get_page(page_id)
            if page:
                # 应用过滤器
                if status and page.metadata.status != status:
                    continue
                if category and page.metadata.category != category:
                    continue
                if tags and not any(tag in page.metadata.tags for tag in tags):
                    continue
                pages.append(page)
        
        # 按更新时间排序
        pages.sort(key=lambda x: x.metadata.updated_at, reverse=True)
        return pages
    
    async def update_page(
        self,
        page_id: str,
        page_update: WikiPageUpdate
    ) -> Optional[WikiPage]:
        """更新Wiki页面"""
        existing = await self.get_page(page_id)
        if not existing:
            return None
        
        # 更新内容
        new_content = page_update.content if page_update.content is not None else existing.content
        
        # 更新元数据
        if page_update.metadata:
            new_metadata = page_update.metadata
        else:
            new_metadata = existing.metadata
        
        # 如果有新标题，更新slug
        new_slug = existing.slug
        if page_update.title:
            new_metadata.title = page_update.title
            new_slug = self._generate_slug(page_update.title)
        
        new_metadata.updated_at = datetime.now()
        new_metadata.version = existing.metadata.version + 1
        
        # 保存
        success = await self.file_tools.write_wiki_page(
            page_id=page_id,
            content=new_content,
            metadata=new_metadata.model_dump(mode="json")
        )
        
        if not success:
            raise Exception("更新Wiki页面失败")
        
        # 更新索引
        await self.file_tools.update_index(page_id, {
            "title": new_metadata.title,
            "slug": new_slug,
            "tags": new_metadata.tags,
            "category": new_metadata.category,
            "status": new_metadata.status.value,
            "updated_at": new_metadata.updated_at.isoformat()
        })
        
        return WikiPage(
            id=page_id,
            slug=new_slug,
            content=new_content,
            metadata=new_metadata
        )
    
    async def delete_page(self, page_id: str) -> bool:
        """删除Wiki页面"""
        return await self.file_tools.delete_wiki_page(page_id)
    
    async def get_index(self) -> Dict[str, Any]:
        """获取Wiki索引"""
        return await self.file_tools.read_index()
    
    async def get_related_pages(self, page_id: str) -> List[WikiPage]:
        """获取相关页面"""
        page = await self.get_page(page_id)
        if not page:
            return []
        
        related_ids = page.metadata.related_pages
        related_pages = []
        
        for related_id in related_ids:
            related = await self.get_page(related_id)
            if related:
                related_pages.append(related)
        
        return related_pages
    
    async def add_related_page(self, page_id: str, related_id: str) -> bool:
        """添加相关页面关联"""
        page = await self.get_page(page_id)
        if not page:
            return False
        
        if related_id not in page.metadata.related_pages:
            page.metadata.related_pages.append(related_id)
            await self.update_page(page_id, WikiPageUpdate(metadata=page.metadata))
        
        return True
    
    async def search_pages(self, query: str) -> List[WikiPage]:
        """搜索Wiki页面"""
        all_pages = await self.list_pages()
        results = []
        query_lower = query.lower()
        
        for page in all_pages:
            # 搜索标题、内容、标签
            if (query_lower in page.metadata.title.lower() or
                query_lower in page.content.lower() or
                any(query_lower in tag.lower() for tag in page.metadata.tags)):
                results.append(page)
        
        return results
    
    async def get_statistics(self) -> Dict[str, Any]:
        """获取Wiki统计信息"""
        pages = await self.list_pages()
        
        status_counts = {}
        category_counts = {}
        total_tags = set()
        
        for page in pages:
            # 状态统计
            status = page.metadata.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
            
            # 分类统计
            category = page.metadata.category or "未分类"
            category_counts[category] = category_counts.get(category, 0) + 1
            
            # 标签统计
            total_tags.update(page.metadata.tags)
        
        return {
            "total_pages": len(pages),
            "status_distribution": status_counts,
            "category_distribution": category_counts,
            "total_tags": len(total_tags),
            "tags": list(total_tags)
        }
    
    async def get_knowledge_graph(self) -> Dict[str, Any]:
        """获取知识图谱数据"""
        pages = await self.list_pages()
        
        nodes = []
        edges = []
        
        for page in pages:
            # 添加节点
            nodes.append({
                "id": page.id,
                "title": page.metadata.title,
                "slug": page.slug,
                "category": page.metadata.category,
                "tags": page.metadata.tags
            })
            
            # 添加边（相关页面关系）
            for related_id in page.metadata.related_pages:
                edges.append({
                    "source": page.id,
                    "target": related_id,
                    "type": "related"
                })
            
            # 添加边（父子关系）
            if page.metadata.parent_id:
                edges.append({
                    "source": page.metadata.parent_id,
                    "target": page.id,
                    "type": "parent-child"
                })
        
        return {
            "nodes": nodes,
            "edges": edges
        }