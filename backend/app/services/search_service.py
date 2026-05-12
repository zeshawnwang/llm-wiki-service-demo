"""
搜索服务 - 处理全文搜索和语义搜索
简化版：使用本地存储，不依赖外部向量数据库
"""
import json
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import hashlib

from app.config import get_settings
from app.services.document_service import DocumentService
from app.services.wiki_service import WikiService
from app.services.ai_service import AIService
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SearchService:
    """搜索服务"""
    
    def __init__(self):
        self.settings = get_settings()
        self.doc_service = DocumentService()
        self.wiki_service = WikiService()
        self.ai_service = AIService()
        
        # 向量存储路径
        self.vector_dir = Path(self.settings.data_dir) / "vectors"
        self.vector_dir.mkdir(parents=True, exist_ok=True)
        
        # 内存中的向量索引
        self._vector_cache = {}
        self._id_to_content = {}
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """计算余弦相似度"""
        a = np.array(a)
        b = np.array(b)
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    
    async def _load_or_create_embedding(self, content_id: str, content: str) -> Optional[List[float]]:
        """加载或创建embedding"""
        # 检查缓存
        if content_id in self._vector_cache:
            return self._vector_cache[content_id]
        
        # 检查本地存储
        vector_file = self.vector_dir / f"{content_id}.json"
        if vector_file.exists():
            with open(vector_file, 'r') as f:
                embedding = json.load(f)
                self._vector_cache[content_id] = embedding
                return embedding
        
        # 创建新的embedding
        try:
            embedding = await self.ai_service._get_embedding(content[:8000])
            # 保存到本地
            with open(vector_file, 'w') as f:
                json.dump(embedding, f)
            self._vector_cache[content_id] = embedding
            self._id_to_content[content_id] = content[:200]  # 缓存预览
            return embedding
        except Exception as e:
            logger.error(f"创建embedding失败: {e}")
            return None
    
    async def index_document(self, doc_id: str, content: str) -> bool:
        """为文档创建索引"""
        embedding = await self._load_or_create_embedding(f"doc_{doc_id}", content)
        return embedding is not None
    
    async def index_wiki_page(self, page_id: str, content: str) -> bool:
        """为Wiki页面创建索引"""
        embedding = await self._load_or_create_embedding(f"wiki_{page_id}", content)
        return embedding is not None
    
    async def search(
        self,
        query: str,
        search_type: str = "hybrid",  # keyword, semantic, hybrid
        limit: int = 10,
        doc_type: Optional[str] = None  # "document", "wiki", None表示全部
    ) -> List[Dict[str, Any]]:
        """
        搜索
        
        Args:
            query: 搜索关键词
            search_type: 搜索类型 (keyword/semantic/hybrid)
            limit: 返回结果数量
            doc_type: 限制搜索类型
        """
        results = []
        
        if search_type in ["keyword", "hybrid"]:
            keyword_results = await self._keyword_search(query, doc_type)
            results.extend(keyword_results)
        
        # 仅在启用向量搜索时执行语义搜索
        if search_type in ["semantic", "hybrid"] and self.settings.enable_vector_search:
            semantic_results = await self._semantic_search(query, doc_type)
            results.extend(semantic_results)
        elif search_type in ["semantic"] and not self.settings.enable_vector_search:
            # 用户请求语义搜索但未启用，回退到关键词搜索并提示
            keyword_results = await self._keyword_search(query, doc_type)
            results.extend(keyword_results)
            for r in results:
                r["_fallback"] = True
        
        # 去重和排序
        seen_ids = set()
        unique_results = []
        for r in sorted(results, key=lambda x: x.get("score", 0), reverse=True):
            item_id = r.get("id")
            if item_id not in seen_ids:
                seen_ids.add(item_id)
                unique_results.append(r)
        
        return unique_results[:limit]
    
    async def _keyword_search(
        self,
        query: str,
        doc_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """关键词搜索（改进的中文支持）"""
        results = []
        query_lower = query.lower()
        
        # 搜索文档
        if doc_type in [None, "document"]:
            docs = await self.doc_service.list_documents()
            for doc in docs:
                score = self._calculate_keyword_score(
                    query_lower,
                    doc.metadata.title,
                    doc.content,
                    doc.metadata.tags
                )
                if score > 0:
                    results.append({
                        "id": doc.id,
                        "type": "document",
                        "title": doc.metadata.title,
                        "snippet": doc.content[:200] + "..." if len(doc.content) > 200 else doc.content,
                        "score": score,
                        "metadata": {
                            "tags": doc.metadata.tags,
                            "category": doc.metadata.category,
                            "updated_at": doc.metadata.updated_at.isoformat()
                        }
                    })
        
        # 搜索Wiki页面
        if doc_type in [None, "wiki"]:
            pages = await self.wiki_service.list_pages()
            for page in pages:
                score = self._calculate_keyword_score(
                    query_lower,
                    page.metadata.title,
                    page.content,
                    page.metadata.tags
                )
                if score > 0:
                    results.append({
                        "id": page.id,
                        "type": "wiki",
                        "title": page.metadata.title,
                        "slug": page.slug,
                        "snippet": page.content[:200] + "..." if len(page.content) > 200 else page.content,
                        "score": score,
                        "metadata": {
                            "tags": page.metadata.tags,
                            "category": page.metadata.category,
                            "status": page.metadata.status.value
                        }
                    })
        
        return results
    
    def _calculate_keyword_score(
        self,
        query_lower: str,
        title: str,
        content: str,
        tags: List[str]
    ) -> float:
        """计算关键词匹配分数（支持中文）"""
        score = 0.0
        title_lower = title.lower()
        content_lower = content.lower()
        tags_lower = [t.lower() for t in tags]
        
        # 方法1: 完整查询匹配
        if query_lower in title_lower:
            score += 15.0
        
        # 方法2: 单个字符匹配（中文）
        for char in query_lower:
            if char in title_lower:
                score += 0.5
            if any(char in tag for tag in tags_lower):
                score += 0.3
            if char in content_lower:
                score += 0.2
        
        # 方法3: 如果有空格（英文），按单词匹配
        if " " in query_lower:
            query_terms = query_lower.split()
            for term in query_terms:
                if term in title_lower:
                    score += 10.0
                if any(term in tag for tag in tags_lower):
                    score += 5.0
                content_count = content_lower.count(term)
                score += min(content_count * 0.5, 3.0)
        
        return score
    
    async def _semantic_search(
        self,
        query: str,
        doc_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """语义搜索"""
        results = []
        
        # 获取查询的embedding
        try:
            query_embedding = await self.ai_service._get_embedding(query)
        except Exception as e:
            logger.error(f"获取查询embedding失败: {e}")
            return results
        
        # 搜索文档
        if doc_type in [None, "document"]:
            docs = await self.doc_service.list_documents()
            for doc in docs:
                doc_embedding = await self._load_or_create_embedding(
                    f"doc_{doc.id}",
                    doc.content
                )
                if doc_embedding:
                    similarity = self._cosine_similarity(query_embedding, doc_embedding)
                    if similarity > 0.7:  # 相似度阈值
                        results.append({
                            "id": doc.id,
                            "type": "document",
                            "title": doc.metadata.title,
                            "snippet": doc.content[:200] + "..." if len(doc.content) > 200 else doc.content,
                            "score": float(similarity),
                            "metadata": {
                                "tags": doc.metadata.tags,
                                "category": doc.metadata.category
                            }
                        })
        
        # 搜索Wiki页面
        if doc_type in [None, "wiki"]:
            pages = await self.wiki_service.list_pages()
            for page in pages:
                page_embedding = await self._load_or_create_embedding(
                    f"wiki_{page.id}",
                    page.content
                )
                if page_embedding:
                    similarity = self._cosine_similarity(query_embedding, page_embedding)
                    if similarity > 0.7:
                        results.append({
                            "id": page.id,
                            "type": "wiki",
                            "title": page.metadata.title,
                            "slug": page.slug,
                            "snippet": page.content[:200] + "..." if len(page.content) > 200 else page.content,
                            "score": float(similarity),
                            "metadata": {
                                "tags": page.metadata.tags,
                                "category": page.metadata.category
                            }
                        })
        
        return results
    
    async def get_recommendations(
        self,
        content_id: str,
        content_type: str,  # "document" or "wiki"
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """获取相关内容推荐（需要启用向量搜索）"""
        if not self.settings.enable_vector_search:
            return []  # 向量搜索未启用时，推荐功能不可用
        # 获取源内容的embedding
        embedding_id = f"{content_type}_{content_id}"
        
        if content_type == "document":
            doc = await self.doc_service.get_document(content_id)
            if not doc:
                return []
            source_embedding = await self._load_or_create_embedding(embedding_id, doc.content)
            source_title = doc.metadata.title
        else:
            page = await self.wiki_service.get_page(content_id)
            if not page:
                return []
            source_embedding = await self._load_or_create_embedding(embedding_id, page.content)
            source_title = page.metadata.title
        
        if not source_embedding:
            return []
        
        # 搜索相似内容
        results = []
        
        # 搜索其他文档
        if content_type != "document":
            docs = await self.doc_service.list_documents()
            for doc in docs:
                if doc.id == content_id:
                    continue
                doc_embedding = await self._load_or_create_embedding(
                    f"doc_{doc.id}",
                    doc.content
                )
                if doc_embedding:
                    similarity = self._cosine_similarity(source_embedding, doc_embedding)
                    if similarity > 0.75:
                        results.append({
                            "id": doc.id,
                            "type": "document",
                            "title": doc.metadata.title,
                            "score": float(similarity)
                        })
        
        # 搜索其他Wiki页面
        if content_type != "wiki":
            pages = await self.wiki_service.list_pages()
            for page in pages:
                if page.id == content_id:
                    continue
                page_embedding = await self._load_or_create_embedding(
                    f"wiki_{page.id}",
                    page.content
                )
                if page_embedding:
                    similarity = self._cosine_similarity(source_embedding, page_embedding)
                    if similarity > 0.75:
                        results.append({
                            "id": page.id,
                            "type": "wiki",
                            "title": page.metadata.title,
                            "slug": page.slug,
                            "score": float(similarity)
                        })
        
        # 按相似度排序
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
    
    async def rebuild_index(self) -> Dict[str, int]:
        """重建所有索引（向量搜索未启用时跳过向量索引）"""
        stats = {"documents": 0, "wiki_pages": 0, "vector_enabled": self.settings.enable_vector_search}
        
        if not self.settings.enable_vector_search:
            return stats
        
        # 索引所有文档
        docs = await self.doc_service.list_documents()
        for doc in docs:
            if await self.index_document(doc.id, doc.content):
                stats["documents"] += 1
        
        # 索引所有Wiki页面
        pages = await self.wiki_service.list_pages()
        for page in pages:
            if await self.index_wiki_page(page.id, page.content):
                stats["wiki_pages"] += 1
        
        return stats