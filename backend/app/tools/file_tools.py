"""
文件操作工具 - 供AI使用的工具函数
不依赖LangChain，直接实现简单清晰的文件操作
"""
import os
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
import aiofiles
from datetime import datetime


class FileTools:
    """文件操作工具类"""
    
    def __init__(self, raw_dir: str = "./data/raw", wiki_dir: str = "./data/wiki"):
        self.raw_dir = Path(raw_dir)
        self.wiki_dir = Path(wiki_dir)
        self._ensure_directories()
    
    def _ensure_directories(self):
        """确保目录存在"""
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        (self.wiki_dir / "pages").mkdir(exist_ok=True)
        (self.wiki_dir / "index").mkdir(exist_ok=True)
    
    # ==================== Raw 层操作 ====================
    
    async def read_raw_document(self, doc_id: str) -> Optional[str]:
        """读取原始文档内容"""
        file_path = self.raw_dir / f"{doc_id}.md"
        if not file_path.exists():
            return None
        
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            return await f.read()
    
    async def write_raw_document(self, doc_id: str, content: str, metadata: Optional[Dict] = None) -> bool:
        """写入原始文档"""
        try:
            file_path = self.raw_dir / f"{doc_id}.md"
            
            # 如果提供了元数据，写入YAML frontmatter
            if metadata:
                from python_frontmatter import Post
                post = Post(content, **metadata)
                content = post.dumps()
            
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(content)
            return True
        except Exception as e:
            print(f"写入文档失败: {e}")
            return False
    
    async def delete_raw_document(self, doc_id: str) -> bool:
        """删除原始文档"""
        file_path = self.raw_dir / f"{doc_id}.md"
        if file_path.exists():
            file_path.unlink()
            return True
        return False
    
    async def list_raw_documents(self) -> List[Dict[str, Any]]:
        """列出所有原始文档"""
        documents = []
        for file_path in self.raw_dir.glob("*.md"):
            stat = file_path.stat()
            content = await self.read_raw_document(file_path.stem)
            
            # 尝试解析frontmatter
            metadata = {}
            if content:
                try:
                    from python_frontmatter import loads
                    post = loads(content)
                    metadata = post.metadata
                    content = post.content
                except:
                    pass
            
            documents.append({
                "id": file_path.stem,
                "filename": file_path.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "metadata": metadata
            })
        return documents
    
    # ==================== Wiki 层操作 ====================
    
    async def read_wiki_page(self, page_id: str) -> Optional[Dict[str, Any]]:
        """读取Wiki页面"""
        file_path = self.wiki_dir / "pages" / f"{page_id}.md"
        if not file_path.exists():
            return None
        
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
        
        # 解析frontmatter
        try:
            from python_frontmatter import loads
            post = loads(content)
            return {
                "id": page_id,
                "content": post.content,
                "metadata": post.metadata
            }
        except:
            return {
                "id": page_id,
                "content": content,
                "metadata": {}
            }
    
    async def write_wiki_page(self, page_id: str, content: str, metadata: Optional[Dict] = None) -> bool:
        """写入Wiki页面"""
        try:
            file_path = self.wiki_dir / "pages" / f"{page_id}.md"
            
            # 添加frontmatter
            from python_frontmatter import Post
            post = Post(content, **(metadata or {}))
            
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(post.dumps())
            return True
        except Exception as e:
            print(f"写入Wiki页面失败: {e}")
            return False
    
    async def delete_wiki_page(self, page_id: str) -> bool:
        """删除Wiki页面"""
        file_path = self.wiki_dir / "pages" / f"{page_id}.md"
        if file_path.exists():
            file_path.unlink()
            return True
        return False
    
    async def list_wiki_pages(self) -> List[Dict[str, Any]]:
        """列出所有Wiki页面"""
        pages = []
        pages_dir = self.wiki_dir / "pages"
        if not pages_dir.exists():
            return pages
            
        for file_path in pages_dir.glob("*.md"):
            page_data = await self.read_wiki_page(file_path.stem)
            if page_data:
                pages.append(page_data)
        return pages
    
    # ==================== 索引操作 ====================
    
    async def read_index(self) -> Dict[str, Any]:
        """读取Wiki索引"""
        index_path = self.wiki_dir / "index" / "index.json"
        if not index_path.exists():
            return {"pages": [], "tags": [], "categories": []}
        
        async with aiofiles.open(index_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            return json.loads(content)
    
    async def write_index(self, index: Dict[str, Any]) -> bool:
        """写入Wiki索引"""
        try:
            index_path = self.wiki_dir / "index" / "index.json"
            async with aiofiles.open(index_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(index, indent=2, ensure_ascii=False))
            return True
        except Exception as e:
            print(f"写入索引失败: {e}")
            return False
    
    async def update_index(self, page_id: str, metadata: Dict[str, Any]) -> bool:
        """更新索引"""
        index = await self.read_index()
        
        # 更新页面列表
        existing = False
        for page in index.get("pages", []):
            if page.get("id") == page_id:
                page.update(metadata)
                existing = True
                break
        
        if not existing:
            index.setdefault("pages", []).append({"id": page_id, **metadata})
        
        # 更新标签和分类
        for tag in metadata.get("tags", []):
            if tag not in index.get("tags", []):
                index.setdefault("tags", []).append(tag)
        
        category = metadata.get("category")
        if category and category not in index.get("categories", []):
            index.setdefault("categories", []).append(category)
        
        return await self.write_index(index)
    
    # ==================== 工具描述（供AI使用） ====================
    
    @classmethod
    def get_tool_descriptions(cls) -> List[Dict[str, str]]:
        """获取工具描述，供AI理解如何使用"""
        return [
            {
                "name": "read_raw_document",
                "description": "读取原始文档内容，输入doc_id，返回文档内容",
                "parameters": {"doc_id": "文档ID"}
            },
            {
                "name": "write_raw_document", 
                "description": "写入原始文档，输入doc_id、content和可选的metadata",
                "parameters": {"doc_id": "文档ID", "content": "文档内容", "metadata": "元数据字典(可选)"}
            },
            {
                "name": "list_raw_documents",
                "description": "列出所有原始文档，返回文档列表",
                "parameters": {}
            },
            {
                "name": "read_wiki_page",
                "description": "读取Wiki页面，输入page_id，返回页面内容和元数据",
                "parameters": {"page_id": "页面ID"}
            },
            {
                "name": "write_wiki_page",
                "description": "写入Wiki页面，输入page_id、content和metadata",
                "parameters": {"page_id": "页面ID", "content": "页面内容", "metadata": "元数据字典"}
            },
            {
                "name": "list_wiki_pages",
                "description": "列出所有Wiki页面",
                "parameters": {}
            },
            {
                "name": "read_index",
                "description": "读取Wiki索引，返回索引结构",
                "parameters": {}
            },
            {
                "name": "update_index",
                "description": "更新索引，输入page_id和metadata",
                "parameters": {"page_id": "页面ID", "metadata": "元数据字典"}
            }
        ]