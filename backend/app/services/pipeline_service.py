"""
知识摄入流水线服务
核心功能：新文档进入后，自动与已有知识库融合、更新Wiki、重新归纳方向
"""
import json
import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from app.config import get_settings
from app.services.document_service import DocumentService
from app.services.wiki_service import WikiService, WikiPageUpdate, WikiPageMetadata, WikiPageStatus
from app.services.ai_service import AIService
from app.services.search_service import SearchService
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class IngestionResult:
    """单次摄入结果"""
    doc_id: str
    status: str  # "new_wiki", "merged", "skipped", "error"
    wiki_page_id: Optional[str] = None  # 主Wiki页面ID（兼容单页面场景）
    wiki_page_ids: List[str] = field(default_factory=list)  # 所有产出的Wiki页面ID
    merge_type: Optional[str] = None  # "update", "split", "new", "new_multi"
    changes: List[str] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class PipelineReport:
    """流水线执行报告"""
    started_at: str
    finished_at: str = ""
    total_documents: int = 0
    results: List[IngestionResult] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_documents": self.total_documents,
            "results": [
                {
                    "doc_id": r.doc_id,
                    "status": r.status,
                    "wiki_page_id": r.wiki_page_id,
                    "wiki_page_ids": r.wiki_page_ids,
                    "merge_type": r.merge_type,
                    "changes": r.changes,
                    "error": r.error
                }
                for r in self.results
            ],
            "summary": self.summary
        }


class IngestionPipeline:
    """
    知识摄入流水线
    
    工作流程：
    1. 扫描新文档（未处理的raw文档）
    2. 对每篇新文档：
       a. 搜索已有Wiki，找到相关知识
       b. 让AI判断：应该新建Wiki、更新已有Wiki、还是跳过
       c. 执行对应操作（新建/合并/跳过）
    3. 更新全局索引
    4. 重新评估知识结构（分类/标签/关联）
    """

    # 标记文档已处理的元数据key
    PROCESSED_FLAG = "_wiki_processed"
    PROCESSED_AT = "_wiki_processed_at"

    def __init__(self):
        self.settings = get_settings()
        self.doc_service = DocumentService()
        self.wiki_service = WikiService()
        self.ai_service = AIService()
        self.search_service = SearchService()

    # ==================== Step 1: 发现新文档 ====================

    async def find_unprocessed_documents(self) -> List[Dict[str, Any]]:
        """找出尚未被Wiki处理过的原始文档"""
        all_docs = await self.doc_service.list_documents()
        unprocessed = []
        for doc in all_docs:
            # 检查是否已处理
            if doc.metadata.custom_fields.get(self.PROCESSED_FLAG):
                continue
            unprocessed.append({
                "id": doc.id,
                "title": doc.metadata.title,
                "content": doc.content,
                "tags": doc.metadata.tags,
                "category": doc.metadata.category,
                "doc_type": doc.metadata.doc_type.value
            })
        return unprocessed

    # ==================== Step 2: 知识融合判断 ====================

    async def _analyze_new_document(
        self,
        new_doc: Dict[str, Any],
        existing_wiki_pages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        让AI分析新文档与已有Wiki的关系，决定处理策略
        
        返回格式：
        {
            "action": "create_new" | "merge_into" | "split_and_merge" | "skip",
            "reason": "原因说明",
            "target_page_id": "要合并到的Wiki页面ID（如果merge）",
            "new_topics": ["新发现的知识主题"],
            "conflicts": ["与已有知识的冲突点"],
            "suggested_title": "建议的Wiki标题",
            "suggested_tags": ["建议标签"],
            "suggested_category": "建议分类"
        }
        """
        # 构建已有Wiki摘要
        wiki_summary = ""
        if existing_wiki_pages:
            wiki_lines = []
            for wp in existing_wiki_pages[:15]:  # 最多参考15个已有页面
                wiki_lines.append(
                    f"- [ID: {wp['id']}] {wp['title']} "
                    f"(标签: {', '.join(wp['tags'])}, "
                    f"分类: {wp.get('category', '无')})"
                )
            wiki_summary = "\n".join(wiki_lines)

        system_prompt = """你是一个知识库管理员。现在有一篇新文档需要纳入知识库。
请分析这篇新文档与已有Wiki页面的关系，决定最佳处理策略。

**第一步：判断文档包含几个独立知识主题**
- 如果文档只讨论一个核心主题 → topic_count = 1
- 如果文档涉及多个独立主题（如一篇长文同时讲了"RAG原理"和"向量数据库选型"）→ topic_count > 1

**第二步：对每个主题，分别判断处理策略**

可选策略：
1. "create_new" - 该主题是全新的，需要创建新Wiki页面
2. "merge_into" - 该主题的内容可以合并到某个已有Wiki页面中
3. "skip" - 该主题已被已有Wiki充分覆盖

请返回JSON格式：
{
    "action": "create_new" | "merge_into" | "split_and_merge" | "skip",
    "topic_count": 主题数量(整数),
    "reason": "整体判断原因",
    "topics": [
        {
            "topic_name": "主题名称",
            "action": "create_new" | "merge_into" | "skip",
            "target_page_id": "目标Wiki页面ID（merge_into时必填，否则null）",
            "suggested_title": "建议的Wiki标题",
            "suggested_tags": ["标签"],
            "suggested_category": "分类"
        }
    ],
    "conflicts": ["与已有知识的冲突点"],
    "new_topics": ["所有新主题名称列表"]
}"""

        user_content = f"""已有Wiki页面：
{wiki_summary if wiki_summary else "（知识库为空，这是第一批文档）"}

新文档：
标题：{new_doc['title']}
类型：{new_doc.get('doc_type', 'unknown')}
标签：{', '.join(new_doc.get('tags', []))}
分类：{new_doc.get('category', '无')}

内容摘要（前3000字）：
{new_doc['content'][:3000]}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            result = await self.ai_service.call_llm(messages, temperature=0.3)
            content = result["choices"][0]["message"]["content"]
            # 提取JSON（支持嵌套结构）
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                # 兼容：如果没有topics字段，从旧格式构造
                if "topics" not in parsed:
                    parsed["topics"] = [{
                        "topic_name": parsed.get("suggested_title", new_doc['title']),
                        "action": parsed.get("action", "create_new"),
                        "target_page_id": parsed.get("target_page_id"),
                        "suggested_title": parsed.get("suggested_title", new_doc['title']),
                        "suggested_tags": parsed.get("suggested_tags", []),
                        "suggested_category": parsed.get("suggested_category")
                    }]
                parsed.setdefault("topic_count", len(parsed.get("topics", [])))
                parsed.setdefault("new_topics", [t["topic_name"] for t in parsed.get("topics", [])])
                parsed.setdefault("conflicts", [])
                return parsed
        except Exception as e:
            pass

        # 默认：单主题，创建新页面
        return {
            "action": "create_new",
            "topic_count": 1,
            "reason": "AI分析失败，默认创建新页面",
            "topics": [{
                "topic_name": new_doc['title'],
                "action": "create_new",
                "target_page_id": None,
                "suggested_title": new_doc['title'],
                "suggested_tags": new_doc.get('tags', []),
                "suggested_category": new_doc.get('category')
            }],
            "new_topics": [new_doc['title']],
            "conflicts": []
        }

    # ==================== Step 3: 执行融合操作 ====================

    async def _create_new_wiki(self, new_doc: Dict[str, Any], analysis: Dict[str, Any]) -> IngestionResult:
        """
        创建新的Wiki页面
        支持单主题（创建1个Wiki）和多主题（拆分后创建多个Wiki）
        """
        topics = analysis.get('topics', [])
        topic_count = analysis.get('topic_count', len(topics))

        # 只保留需要 create_new 的主题
        create_topics = [t for t in topics if t.get('action') == 'create_new']

        if not create_topics:
            # 所有主题都被 skip 或 merge 了，没有需要新建的
            return IngestionResult(
                doc_id=new_doc['id'],
                status="skipped",
                changes=["没有需要新建的主题"]
            )

        created_page_ids = []
        changes = []

        if len(create_topics) == 1:
            # ========== 单主题：直接生成1个Wiki ==========
            topic = create_topics[0]
            try:
                gen_result = await self.ai_service.generate_wiki_page(
                    source_content=new_doc['content'],
                    title=topic.get('suggested_title', topic.get('topic_name', new_doc['title']))
                )

                from app.models.wiki import WikiPageCreate
                page = await self.wiki_service.create_page(WikiPageCreate(
                    title=gen_result['title'],
                    content=gen_result['content'],
                    metadata=WikiPageMetadata(
                        title=gen_result['title'],
                        tags=topic.get('suggested_tags', []),
                        category=topic.get('suggested_category'),
                        status=WikiPageStatus.PUBLISHED,
                        source_documents=[new_doc['id']]
                    )
                ))
                created_page_ids.append(page.id)
                changes.append(f"创建Wiki页面: {gen_result['title']}")
            except Exception as e:
                return IngestionResult(doc_id=new_doc['id'], status="error", error=str(e))

        else:
            # ========== 多主题：先拆分文档，再分别创建Wiki ==========
            try:
                # 让AI按主题拆分文档内容
                split_result = await self._ai_split_by_topics(
                    content=new_doc['content'],
                    title=new_doc['title'],
                    topics=create_topics
                )

                for segment in split_result.get('segments', []):
                    topic_name = segment.get('topic', '')
                    # 找到对应的topic配置
                    topic_config = next(
                        (t for t in create_topics if t.get('topic_name') == topic_name),
                        create_topics[0]  # fallback
                    )

                    gen_result = await self.ai_service.generate_wiki_page(
                        source_content=segment.get('content', ''),
                        title=topic_config.get('suggested_title', topic_name)
                    )

                    from app.models.wiki import WikiPageCreate
                    page = await self.wiki_service.create_page(WikiPageCreate(
                        title=gen_result['title'],
                        content=gen_result['content'],
                        metadata=WikiPageMetadata(
                            title=gen_result['title'],
                            tags=topic_config.get('suggested_tags', []),
                            category=topic_config.get('suggested_category'),
                            status=WikiPageStatus.PUBLISHED,
                            source_documents=[new_doc['id']]
                        )
                    ))
                    created_page_ids.append(page.id)
                    changes.append(f"创建Wiki页面: {gen_result['title']}")

                # 建立同源页面之间的关联
                for i, pid_a in enumerate(created_page_ids):
                    for pid_b in created_page_ids[i+1:]:
                        try:
                            await self.wiki_service.add_related_page(pid_a, pid_b)
                        except Exception:
                            pass

            except Exception as e:
                return IngestionResult(doc_id=new_doc['id'], status="error", error=str(e))

        # 标记文档已处理
        await self._mark_document_processed(new_doc['id'], ','.join(created_page_ids))

        merge_type = "new_multi" if len(created_page_ids) > 1 else "new"
        changes.append(f"共创建 {len(created_page_ids)} 个Wiki页面（主题数: {topic_count}）")

        return IngestionResult(
            doc_id=new_doc['id'],
            status="new_wiki",
            wiki_page_id=created_page_ids[0] if created_page_ids else None,
            wiki_page_ids=created_page_ids,
            merge_type=merge_type,
            changes=changes
        )

    async def _merge_into_existing(
        self,
        new_doc: Dict[str, Any],
        analysis: Dict[str, Any]
    ) -> IngestionResult:
        """将新文档内容合并到已有Wiki页面"""
        target_id = analysis.get('target_page_id')
        if not target_id:
            return IngestionResult(
                doc_id=new_doc['id'],
                status="error",
                error="未指定目标Wiki页面ID"
            )

        try:
            # 获取已有Wiki页面
            existing_page = await self.wiki_service.get_page(target_id)
            if not existing_page:
                return IngestionResult(
                    doc_id=new_doc['id'],
                    status="error",
                    error=f"目标Wiki页面不存在: {target_id}"
                )

            # 让AI合并内容
            merged_content = await self._ai_merge_content(
                existing_content=existing_page.content,
                existing_title=existing_page.metadata.title,
                new_content=new_doc['content'],
                new_title=new_doc['title'],
                conflicts=analysis.get('conflicts', [])
            )

            # 合并标签
            merged_tags = list(set(
                existing_page.metadata.tags + analysis.get('suggested_tags', [])
            ))

            # 更新页面
            new_metadata = WikiPageMetadata(
                title=existing_page.metadata.title,
                description=existing_page.metadata.description,
                author=existing_page.metadata.author,
                tags=merged_tags,
                category=analysis.get('suggested_category') or existing_page.metadata.category,
                status=existing_page.metadata.status,
                version=existing_page.metadata.version,
                parent_id=existing_page.metadata.parent_id,
                related_pages=existing_page.metadata.related_pages,
                source_documents=existing_page.metadata.source_documents + [new_doc['id']]
            )

            page_update = WikiPageUpdate(
                content=merged_content,
                metadata=new_metadata
            )

            updated_page = await self.wiki_service.update_page(target_id, page_update)

            # 标记文档已处理
            await self._mark_document_processed(new_doc['id'], target_id)

            changes = [
                f"更新已有Wiki页面: {existing_page.metadata.title}",
                f"新增标签: {', '.join(set(analysis.get('suggested_tags', [])) - set(existing_page.metadata.tags))}",
                f"版本: v{existing_page.metadata.version} → v{updated_page.metadata.version}"
            ]
            if analysis.get('conflicts'):
                changes.append(f"解决冲突: {', '.join(analysis['conflicts'][:3])}")

            return IngestionResult(
                doc_id=new_doc['id'],
                status="merged",
                wiki_page_id=target_id,
                merge_type="update",
                changes=changes
            )
        except Exception as e:
            return IngestionResult(
                doc_id=new_doc['id'],
                status="error",
                error=str(e)
            )

    async def _split_and_merge(
        self,
        new_doc: Dict[str, Any],
        analysis: Dict[str, Any],
        existing_wiki_pages: List[Dict[str, Any]]
    ) -> IngestionResult:
        """拆分新文档，分别合并到多个Wiki页面"""
        try:
            # 让AI拆分文档
            split_result = await self._ai_split_document(
                new_doc['content'],
                new_doc['title'],
                analysis.get('new_topics', []),
                existing_wiki_pages
            )

            changes = []
            processed_page_ids = []

            for segment in split_result.get('segments', []):
                target_id = segment.get('target_page_id')
                segment_content = segment.get('content', '')

                if target_id:
                    # 合并到已有页面
                    existing = await self.wiki_service.get_page(target_id)
                    if existing:
                        merged = await self._ai_merge_content(
                            existing_content=existing.content,
                            existing_title=existing.metadata.title,
                            new_content=segment_content,
                            new_title=segment.get('topic', ''),
                            conflicts=[]
                        )
                        new_meta = WikiPageMetadata(
                            title=existing.metadata.title,
                            tags=existing.metadata.tags + segment.get('tags', []),
                            category=existing.metadata.category,
                            status=existing.metadata.status,
                            version=existing.metadata.version,
                            source_documents=existing.metadata.source_documents + [new_doc['id']]
                        )
                        await self.wiki_service.update_page(
                            target_id, WikiPageUpdate(content=merged, metadata=new_meta)
                        )
                        changes.append(f"合并到: {existing.metadata.title}")
                        processed_page_ids.append(target_id)
                else:
                    # 创建新页面
                    from app.models.wiki import WikiPageCreate
                    page = await self.wiki_service.create_page(WikiPageCreate(
                        title=segment.get('topic', '新主题'),
                        content=segment_content,
                        metadata=WikiPageMetadata(
                            title=segment.get('topic', '新主题'),
                            tags=segment.get('tags', []),
                            category=analysis.get('suggested_category'),
                            status=WikiPageStatus.PUBLISHED,
                            source_documents=[new_doc['id']]
                        )
                    ))
                    changes.append(f"创建新页面: {segment.get('topic', '新主题')}")
                    processed_page_ids.append(page.id)

            # 标记文档已处理
            await self._mark_document_processed(new_doc['id'], ','.join(processed_page_ids))

            return IngestionResult(
                doc_id=new_doc['id'],
                status="merged",
                merge_type="split",
                changes=changes
            )
        except Exception as e:
            return IngestionResult(
                doc_id=new_doc['id'],
                status="error",
                error=str(e)
            )

    # ==================== AI辅助方法 ====================

    async def _ai_merge_content(
        self,
        existing_content: str,
        existing_title: str,
        new_content: str,
        new_title: str,
        conflicts: List[str]
    ) -> str:
        """让AI智能合并新旧内容"""
        system_prompt = """你是一个知识库编辑。请将新内容智能合并到已有Wiki页面中。

规则：
1. 保留已有Wiki的结构和核心内容
2. 将新内容中有价值的信息补充到对应章节
3. 如果新内容与已有内容矛盾，以新内容为准，但标注"更新于[日期]"
4. 去除重复信息
5. 保持Markdown格式
6. 不要删除已有章节，除非新内容完全替代

如果有冲突点，请在合并时特别注明。"""

        user_content = f"""已有Wiki页面「{existing_title}」：
{existing_content[:6000]}

新文档「{new_title}」：
{new_content[:6000]}

冲突点：{', '.join(conflicts) if conflicts else '无'}

请输出合并后的完整Wiki内容（Markdown格式）："""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            result = await self.ai_service.call_llm(messages, temperature=0.3)
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            # 合并失败，简单拼接
            return f"{existing_content}\n\n---\n\n## 补充内容（来自: {new_title}）\n\n{new_content[:3000]}"

    async def _ai_split_by_topics(
        self,
        content: str,
        title: str,
        topics: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        按指定的主题列表拆分文档内容
        与 _ai_split_document 不同，这里主题已经确定，只需提取对应内容
        """
        topic_names = [t.get('topic_name', t.get('suggested_title', '')) for t in topics]

        system_prompt = """请将文档按以下指定的主题列表进行拆分。
对每个主题，提取文档中与该主题相关的内容，整理成独立的Markdown段落。

要求：
1. 每个主题的内容必须来自原文，不要编造
2. 如果某个主题在文档中没有对应内容，返回空字符串
3. 保留原文的关键信息和结构

返回JSON格式：
{
    "segments": [
        {
            "topic": "主题名称（必须与输入的主题名称完全一致）",
            "content": "提取的内容（Markdown格式）"
        }
    ]
}"""

        user_content = f"""文档标题：{title}

需要拆分的主题：
{chr(10).join(f'- {name}' for name in topic_names)}

文档内容（前10000字）：
{content[:10000]}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            result = await self.ai_service.call_llm(messages, temperature=0.2)
            resp = result["choices"][0]["message"]["content"]
            json_match = re.search(r'\{.*\}', resp, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            pass

        # 默认：每个主题分配等量内容（粗略拆分）
        chunk_size = max(len(content) // max(len(topics), 1), 500)
        segments = []
        for i, t in enumerate(topics):
            start = i * chunk_size
            end = start + chunk_size
            segments.append({
                "topic": t.get('topic_name', t.get('suggested_title', f'主题{i+1}')),
                "content": content[start:end]
            })
        return {"segments": segments}

    async def _ai_split_document(
        self,
        content: str,
        title: str,
        topics: List[str],
        existing_wiki_pages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """让AI拆分文档为多个主题段"""
        wiki_list = "\n".join([
            f"- [ID: {wp['id']}] {wp['title']}"
            for wp in existing_wiki_pages
        ]) if existing_wiki_pages else "（空）"

        system_prompt = """请将文档按主题拆分成多个段落，每个段落对应一个知识主题。
对于每个段落，判断它应该合并到哪个已有Wiki页面，还是需要创建新页面。

返回JSON格式：
{
    "segments": [
        {
            "topic": "主题名称",
            "content": "该主题的内容（Markdown）",
            "target_page_id": "已有Wiki页面ID（如需合并）或null（需新建）",
            "tags": ["标签"]
        }
    ]
}"""

        user_content = f"""文档标题：{title}
发现的主题：{', '.join(topics)}

已有Wiki页面：
{wiki_list}

文档内容（前8000字）：
{content[:8000]}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            result = await self.ai_service.call_llm(messages, temperature=0.3)
            resp = result["choices"][0]["message"]["content"]
            json_match = re.search(r'\{[^}]*"segments"[^}]*\}', resp, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            pass

        # 默认：整体作为一个新主题
        return {
            "segments": [{
                "topic": title,
                "content": content[:5000],
                "target_page_id": None,
                "tags": []
            }]
        }

    async def _ai_rebuild_knowledge_structure(self) -> Dict[str, Any]:
        """
        重新评估整个知识库的结构
        - 发现新的分类方向
        - 建议页面关联
        - 标记过时内容
        """
        all_pages = await self.wiki_service.list_pages()
        if not all_pages:
            return {"suggestions": [], "new_categories": [], "orphans": []}

        pages_summary = "\n".join([
            f"- [ID: {p.id}] {p.metadata.title} "
            f"(标签: {', '.join(p.metadata.tags)}, "
            f"分类: {p.metadata.category or '无'}, "
            f"状态: {p.metadata.status.value})"
            for p in all_pages
        ])

        system_prompt = """你是一个知识库架构师。请分析当前知识库的整体结构，提出优化建议。

返回JSON格式：
{
    "new_categories": ["建议新增的分类"],
    "suggested_links": [
        {"source_id": "页面ID", "target_id": "页面ID", "reason": "建议关联原因"}
    ],
    "orphans": ["孤立页面ID（与其他页面缺少关联）"],
    "restructure_suggestions": [
        {"page_id": "页面ID", "suggestion": "建议（如合并、拆分、重命名）"}
    ],
    "knowledge_gaps": ["知识库中缺失的重要主题"]
}"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"当前知识库页面：\n{pages_summary}"}
        ]

        try:
            result = await self.ai_service.call_llm(messages, temperature=0.5)
            resp = result["choices"][0]["message"]["content"]
            json_match = re.search(r'\{.*\}', resp, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            pass

        return {"suggestions": [], "new_categories": [], "orphans": []}

    # ==================== 文档标记 ====================

    async def _mark_document_processed(self, doc_id: str, wiki_page_id: str):
        """标记文档已被Wiki处理"""
        doc = await self.doc_service.get_document(doc_id)
        if doc:
            new_meta = doc.metadata
            new_meta.custom_fields[self.PROCESSED_FLAG] = True
            new_meta.custom_fields[self.PROCESSED_AT] = datetime.now().isoformat()
            new_meta.custom_fields["wiki_page_id"] = wiki_page_id
            await self.doc_service.update_document(doc_id, metadata=new_meta)

    # ==================== 主流水线 ====================

    async def run(
        self,
        doc_ids: Optional[List[str]] = None,
        auto_rebuild_structure: bool = True
    ) -> PipelineReport:
        """
        执行知识摄入流水线

        Args:
            doc_ids: 指定要处理的文档ID列表。为None时自动发现未处理文档。
            auto_rebuild_structure: 是否在处理完后自动重建知识结构

        Returns:
            PipelineReport 执行报告
        """
        report = PipelineReport(
            started_at=datetime.now().isoformat(),
            total_documents=0
        )

        # Step 1: 发现待处理文档
        if doc_ids:
            unprocessed = []
            for did in doc_ids:
                doc = await self.doc_service.get_document(did)
                if doc:
                    unprocessed.append({
                        "id": doc.id,
                        "title": doc.metadata.title,
                        "content": doc.content,
                        "tags": doc.metadata.tags,
                        "category": doc.metadata.category,
                        "doc_type": doc.metadata.doc_type.value
                    })
        else:
            unprocessed = await self.find_unprocessed_documents()

        report.total_documents = len(unprocessed)
        if not unprocessed:
            report.finished_at = datetime.now().isoformat()
            report.summary = {"skipped": 0, "new_wiki": 0, "merged": 0, "error": 0}
            return report

        # Step 2: 获取已有Wiki页面（用于融合判断）
        existing_wiki_pages = []
        all_wiki = await self.wiki_service.list_pages()
        for wp in all_wiki:
            existing_wiki_pages.append({
                "id": wp.id,
                "title": wp.metadata.title,
                "tags": wp.metadata.tags,
                "category": wp.metadata.category,
                "status": wp.metadata.status.value
            })

        # Step 3: 逐文档处理
        for new_doc in unprocessed:
            # 3a. AI分析新文档与已有知识的关系
            analysis = await self._analyze_new_document(new_doc, existing_wiki_pages)
            action = analysis.get('action', 'create_new')
            topics = analysis.get('topics', [])
            topic_count = analysis.get('topic_count', len(topics))

            # 3b. 根据策略执行
            # 新逻辑：基于每个topic的action，支持混合策略
            has_create = any(t.get('action') == 'create_new' for t in topics)
            has_merge = any(t.get('action') == 'merge_into' for t in topics)
            has_skip = any(t.get('action') == 'skip' for t in topics)

            if has_create and has_merge:
                # 混合策略：部分新建 + 部分合并
                result = await self._split_and_merge(new_doc, analysis, existing_wiki_pages)
            elif has_create and not has_merge:
                # 纯新建（可能是多主题）
                result = await self._create_new_wiki(new_doc, analysis)
            elif has_merge and not has_create:
                # 纯合并
                result = await self._merge_into_existing(new_doc, analysis)
            elif action == 'skip' or (has_skip and not has_create and not has_merge):
                # 全部跳过
                result = IngestionResult(
                    doc_id=new_doc['id'],
                    status="skipped",
                    changes=[f"内容已被已有Wiki覆盖（{topic_count}个主题均跳过）"]
                )
                await self._mark_document_processed(new_doc['id'], 'skipped')
            else:
                # 兜底
                result = await self._create_new_wiki(new_doc, analysis)

            report.results.append(result)

            # 更新已有Wiki列表（后续文档可能需要参考新创建的页面）
            all_new_ids = result.wiki_page_ids or ([result.wiki_page_id] if result.wiki_page_id else [])
            for new_id in all_new_ids:
                if new_id and result.status != "error":
                    new_page = await self.wiki_service.get_page(new_id)
                    if new_page:
                        existing_wiki_pages.append({
                            "id": new_page.id,
                            "title": new_page.metadata.title,
                            "tags": new_page.metadata.tags,
                            "category": new_page.metadata.category,
                            "status": new_page.metadata.status.value
                        })

        # Step 4: 重建搜索索引
        try:
            index_stats = await self.search_service.rebuild_index()
        except Exception:
            index_stats = {}

        # Step 5: 可选 - 重建知识结构
        structure_suggestions = {}
        if auto_rebuild_structure and report.total_documents > 0:
            structure_suggestions = await self._ai_rebuild_knowledge_structure()

            # 自动执行关联建议
            for link in structure_suggestions.get('suggested_links', []):
                try:
                    await self.wiki_service.add_related_page(
                        link['source_id'], link['target_id']
                    )
                except Exception:
                    pass

        # 生成摘要统计
        summary = {"skipped": 0, "new_wiki": 0, "merged": 0, "error": 0}
        for r in report.results:
            if r.status in summary:
                summary[r.status] += 1
            elif r.status == "error":
                summary["error"] += 1
        report.summary = summary
        report.finished_at = datetime.now().isoformat()

        return report

    async def get_pipeline_status(self) -> Dict[str, Any]:
        """获取流水线状态概览"""
        unprocessed = await self.find_unprocessed_documents()
        all_docs = await self.doc_service.list_documents()
        all_pages = await self.wiki_service.list_pages()

        processed_count = len(all_docs) - len(unprocessed)

        return {
            "total_documents": len(all_docs),
            "processed_documents": processed_count,
            "unprocessed_documents": len(unprocessed),
            "total_wiki_pages": len(all_pages),
            "unprocessed_doc_ids": [d['id'] for d in unprocessed],
            "ready_to_run": len(unprocessed) > 0
        }
