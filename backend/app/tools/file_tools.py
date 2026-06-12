"""
文件操作工具 - 供AI使用的工具函数
不依赖LangChain，直接实现简单清晰的文件操作
"""
import os
import re
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
import aiofiles
from datetime import datetime

from app.utils.logger import get_logger

logger = get_logger(__name__)


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
    
    def _make_filename(self, page_id: str, title: str = "") -> str:
        """生成可读的wiki页面文件名: title_id.md"""
        if title:
            # 清理标题：保留中英文、数字、连字符
            slug = re.sub(r'[^\w\u4e00-\u9fff\s-]', '', title)
            slug = re.sub(r'[\s]+', '-', slug.strip())
            slug = slug[:40]  # 限制长度
            return f"{slug}_{page_id}.md"
        return f"{page_id}.md"
    
    def _find_wiki_file(self, page_id: str) -> Optional[Path]:
        """根据page_id查找wiki文件（支持新旧文件名格式）"""
        pages_dir = self.wiki_dir / "pages"
        # 新格式：*_id.md
        for f in pages_dir.glob(f"*_{page_id}.md"):
            return f
        # 旧格式：id.md
        old_path = pages_dir / f"{page_id}.md"
        if old_path.exists():
            return old_path
        return None
    
    # ==================== Raw 层操作 ====================
    
    def _find_raw_file(self, doc_id: str) -> Optional[Path]:
        """根据doc_id查找raw文件（支持新旧文件名格式）"""
        # 新格式：*_id.md
        for f in self.raw_dir.glob(f"*_{doc_id}.md"):
            return f
        # 旧格式：id.md
        old_path = self.raw_dir / f"{doc_id}.md"
        if old_path.exists():
            return old_path
        return None
    
    async def read_raw_document(self, doc_id: str) -> Optional[str]:
        """读取原始文档内容"""
        file_path = self._find_raw_file(doc_id)
        if not file_path:
            return None
        
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            return await f.read()
    
    async def write_raw_document(self, doc_id: str, content: str, metadata: Optional[Dict] = None) -> bool:
        """写入原始文档（使用可读文件名）"""
        try:
            title = (metadata or {}).get("title", "")
            filename = self._make_filename(doc_id, title)
            file_path = self.raw_dir / filename
            
            # 如果旧文件名存在且不同，删除旧文件
            old_file = self._find_raw_file(doc_id)
            if old_file and old_file != file_path:
                old_file.unlink()
            
            logger.debug(f"尝试写入文档到: {file_path}")
            
            # 如果提供了元数据，写入YAML frontmatter
            if metadata:
                from frontmatter import Post, dumps
                post = Post(content, **metadata)
                content = dumps(post)
            
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(content)
            logger.info(f"文档写入成功: {file_path}")
            return True
        except Exception as e:
            logger.error(f"写入文档失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def delete_raw_document(self, doc_id: str) -> bool:
        """删除原始文档"""
        file_path = self._find_raw_file(doc_id)
        if file_path and file_path.exists():
            file_path.unlink()
            return True
        return False
    
    async def list_raw_documents(self) -> List[Dict[str, Any]]:
        """列出所有原始文档"""
        documents = []
        for file_path in self.raw_dir.glob("*.md"):
            stat = file_path.stat()
            doc_id = self._extract_id_from_filename(file_path.name)
            content = await self.read_raw_document(doc_id)
            
            # 尝试解析frontmatter
            metadata = {}
            if content:
                try:
                    from frontmatter import loads
                    post = loads(content)
                    metadata = post.metadata
                    content = post.content
                except:
                    pass
            
            documents.append({
                "id": doc_id,
                "filename": file_path.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "metadata": metadata
            })
        return documents
    
    # ==================== Wiki 层操作 ====================
    
    def _extract_id_from_filename(self, filename: str) -> str:
        """从文件名中提取page_id"""
        stem = Path(filename).stem
        # 新格式: title_id → 取最后一个 _ 后面的部分
        if '_' in stem:
            return stem.rsplit('_', 1)[-1]
        # 旧格式: id
        return stem
    
    async def read_wiki_page(self, page_id: str) -> Optional[Dict[str, Any]]:
        """读取Wiki页面"""
        file_path = self._find_wiki_file(page_id)
        if not file_path:
            return None
        
        async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
            content = await f.read()
        
        # 解析frontmatter
        try:
            from frontmatter import loads
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
        """写入Wiki页面（使用可读文件名）"""
        try:
            title = (metadata or {}).get("title", "")
            filename = self._make_filename(page_id, title)
            file_path = self.wiki_dir / "pages" / filename
            
            # 如果旧文件名存在且不同，删除旧文件
            old_file = self._find_wiki_file(page_id)
            if old_file and old_file != file_path:
                old_file.unlink()
            
            # 添加frontmatter
            from frontmatter import Post, dumps
            post = Post(content, **(metadata or {}))
            
            async with aiofiles.open(file_path, 'w', encoding='utf-8') as f:
                await f.write(dumps(post))
            return True
        except Exception as e:
            logger.error(f"写入Wiki页面失败: {e}")
            return False
    
    async def delete_wiki_page(self, page_id: str) -> bool:
        """删除Wiki页面"""
        file_path = self._find_wiki_file(page_id)
        if file_path and file_path.exists():
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
            page_id = self._extract_id_from_filename(file_path.name)
            page_data = await self.read_wiki_page(page_id)
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
        """写入Wiki索引（同时生成 index.json 和 index.md）"""
        try:
            # 写 JSON 版本
            index_path = self.wiki_dir / "index" / "index.json"
            async with aiofiles.open(index_path, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(index, indent=2, ensure_ascii=False))
            
            # 同步生成 Markdown 版本（Obsidian 友好）
            await self._generate_index_md(index)
            return True
        except Exception as e:
            logger.error(f"写入索引失败: {e}")
            return False
    
    async def _generate_index_md(self, index: Dict[str, Any]):
        """生成 index.md（不使用 [[wikilinks]]，避免在图谱中产生噪音连接）"""
        lines = [
            "---",
            "title: Wiki 索引",
            f"updated_at: '{datetime.now().isoformat()}'",
            "---",
            "",
            "# Wiki 知识库索引",
            "",
            f"> 共 {len(index.get('pages', []))} 个页面 | "
            f"{len(index.get('tags', []))} 个标签 | "
            f"{len(index.get('categories', []))} 个分类",
            "",
        ]
        
        # 按分类分组
        categorized: Dict[str, List] = {}
        for page in index.get("pages", []):
            cat = page.get("category") or "未分类"
            categorized.setdefault(cat, []).append(page)
        
        for category, pages in sorted(categorized.items()):
            lines.append(f"## {category}")
            lines.append("")
            for page in pages:
                title = page.get("title", "Untitled")
                tags_str = ", ".join(f"`{t}`" for t in page.get("tags", [])[:5])
                lines.append(f"- {title} {tags_str}")
            lines.append("")
        
        # 标签汇总
        if index.get("tags"):
            lines.append("## 标签")
            lines.append("")
            lines.append(" ".join(f"`{t}`" for t in index["tags"]))
            lines.append("")
        
        index_md_path = self.wiki_dir / "index.md"
        async with aiofiles.open(index_md_path, 'w', encoding='utf-8') as f:
            await f.write("\n".join(lines))
    
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
    
    # ==================== 日志操作 ====================
    
    async def append_log(self, action: str, title: str, details: str = ""):
        """追加操作日志到 log.md"""
        log_path = self.wiki_dir / "log.md"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        entry = f"## [{timestamp}] {action} | {title}\n"
        if details:
            entry += f"{details}\n"
        entry += "\n"
        
        # 如果文件不存在，先写头部
        if not log_path.exists():
            header = "---\ntitle: 操作日志\n---\n\n# Wiki 操作日志\n\n"
            async with aiofiles.open(log_path, 'w', encoding='utf-8') as f:
                await f.write(header + entry)
        else:
            async with aiofiles.open(log_path, 'a', encoding='utf-8') as f:
                await f.write(entry)
    
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
            },
            {
                "name": "append_log",
                "description": "追加操作日志到log.md，输入action、title和details",
                "parameters": {"action": "操作类型", "title": "标题", "details": "详情(可选)"}
            }
        ]
