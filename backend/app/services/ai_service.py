"""
AI处理服务 - 处理所有AI相关的任务
直接调用OpenAI/Claude API，不依赖LangChain
"""
import os
from typing import Optional, List, Dict, Any, AsyncGenerator
import httpx
import json

from app.config import get_settings
from app.tools.file_tools import FileTools
from app.tools.code_tools import CodeTools
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AIService:
    """AI处理服务 - 根据 LLM_PROVIDER 配置自动选择供应商"""
    
    def __init__(self):
        self.settings = get_settings()
        self.file_tools = FileTools(
            raw_dir=self.settings.raw_dir,
            wiki_dir=self.settings.wiki_dir
        )
        self.code_tools = CodeTools()
        
        # 当前供应商
        self.provider = self.settings.llm_provider  # "openai" | "anthropic"
    
    async def call_llm(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """
        统一的LLM调用入口，根据 LLM_PROVIDER 配置自动路由。
        所有业务方法应调用此方法，而非直接调用 _call_openai / _call_anthropic / _call_minimax。
        """
        if self.provider == "anthropic":
            return await self._call_anthropic(messages, model=model, temperature=temperature)
        elif self.provider == "minimax":
            return await self._call_minimax(messages, model=model, temperature=temperature)
        else:
            return await self._call_openai(messages, model=model, temperature=temperature)
    
    async def _call_openai(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        stream: bool = False
    ) -> Dict[str, Any]:
        """调用OpenAI API"""
        model_name = model or self.settings.openai_chat_model
        logger.info(f"[OpenAI] 开始调用 - 模型: {model_name}, temperature: {temperature}")
        
        api_key = self.settings.openai_api_key
        if not api_key:
            logger.error(f"[OpenAI] 调用失败 - API Key未配置")
            raise ValueError("OpenAI API Key未配置，请检查 OPENAI_API_KEY")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": stream
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.settings.openai_base_url}/chat/completions",
                    headers=headers,
                    json=data,
                    timeout=120.0
                )
                response.raise_for_status()
                result = response.json()
                logger.info(f"[OpenAI] 调用成功 - 模型: {model_name}, 响应tokens: {len(result.get('choices', []))}")
                return result
        except Exception as e:
            logger.error(f"[OpenAI] 调用失败 - 模型: {model_name}, 错误: {str(e)}")
            raise
    
    async def _call_anthropic(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """调用Claude API"""
        model_name = model or self.settings.anthropic_chat_model
        logger.info(f"[Anthropic] 开始调用 - 模型: {model_name}, temperature: {temperature}")
        
        api_key = self.settings.anthropic_api_key
        if not api_key:
            logger.error(f"[Anthropic] 调用失败 - API Key未配置")
            raise ValueError("Anthropic API Key未配置，请检查 ANTHROPIC_API_KEY")
        
        headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }
        
        # 提取system消息
        system_message = ""
        user_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_message = msg.get("content", "")
            else:
                user_messages.append(msg)
        
        data = {
            "model": model_name,
            "messages": user_messages,
            "system": system_message,
            "temperature": temperature,
            "max_tokens": 4096
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.settings.anthropic_base_url}/v1/messages",
                    headers=headers,
                    json=data,
                    timeout=120.0
                )
                response.raise_for_status()
                result = response.json()
                # 转换为OpenAI格式
                # 兼容不同的响应格式（Anthropic和MiniMax等代理服务）
                content = ""
                if "content" in result and result["content"]:
                    if isinstance(result["content"], list):
                        # 遍历content列表，找到type为"text"的项
                        for content_item in result["content"]:
                            if isinstance(content_item, dict):
                                if content_item.get("type") == "text" and "text" in content_item:
                                    content = content_item["text"]
                                    break
                                elif "text" in content_item:
                                    content = content_item["text"]
                                    break
                                elif "content" in content_item:
                                    content = content_item["content"]
                                    break
                    elif isinstance(result["content"], str):
                        content = result["content"]
                elif "text" in result:
                    content = result["text"]
                elif "message" in result and isinstance(result["message"], dict):
                    content = result["message"].get("content", result["message"].get("text", ""))
                
                logger.info(f"[Anthropic] 调用成功 - 模型: {model_name}")
                return {
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": content
                        }
                    }]
                }
        except Exception as e:
            logger.error(f"[Anthropic] 调用失败 - 模型: {model_name}, 错误: {str(e)}")
            raise
    
    async def _call_minimax(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """调用Minimax API（支持通过Anthropic兼容代理访问）"""
        model_name = model or self.settings.minimax_chat_model
        logger.info(f"[Minimax] 开始调用 - 模型: {model_name}, temperature: {temperature}")
        
        api_key = self.settings.minimax_api_key
        if not api_key:
            logger.error(f"[Minimax] 调用失败 - API Key未配置")
            raise ValueError("Minimax API Key未配置，请检查 MINIMAX_API_KEY")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        system_message = ""
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg.get("content", "")
            else:
                user_messages.append(msg)
        
        data = {
            "model": model_name,
            "messages": user_messages,
            "system": system_message,
            "temperature": temperature,
            "max_tokens": 4096
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.settings.minimax_base_url}/v1/messages",
                    headers=headers,
                    json=data,
                    timeout=120.0
                )
                response.raise_for_status()
                result = response.json()
                
                # Minimax响应格式处理（兼容Anthropic格式的代理服务）
                content = ""
                if "content" in result and result["content"]:
                    if isinstance(result["content"], list):
                        # 遍历content列表，找到type为"text"的项
                        for content_item in result["content"]:
                            if isinstance(content_item, dict):
                                if content_item.get("type") == "text" and "text" in content_item:
                                    content = content_item["text"]
                                    break
                                elif "text" in content_item:
                                    content = content_item["text"]
                                    break
                                elif "content" in content_item:
                                    content = content_item["content"]
                                    break
                    elif isinstance(result["content"], str):
                        content = result["content"]
                elif "choices" in result and result["choices"]:
                    # OpenAI兼容格式
                    message = result["choices"][0].get("message", {})
                    content = message.get("content", "")
                elif "text" in result:
                    content = result["text"]
                
                logger.info(f"[Minimax] 调用成功 - 模型: {model_name}")
                return {
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": content
                        }
                    }]
                }
        except Exception as e:
            logger.error(f"[Minimax] 调用失败 - 模型: {model_name}, 错误: {str(e)}")
            raise
    
    async def _get_embedding(self, text: str) -> List[float]:
        """获取文本的embedding向量（目前仅OpenAI支持）"""
        api_key = self.settings.openai_api_key
        if not api_key:
            raise ValueError("OpenAI API Key未配置，embedding功能需要OpenAI")
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.settings.openai_embedding_model,
            "input": text
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.settings.openai_base_url}/embeddings",
                headers=headers,
                json=data,
                timeout=60.0
            )
            response.raise_for_status()
            result = response.json()
            return result["data"][0]["embedding"]
    
    async def summarize_document(self, content: str, max_length: int = 500) -> str:
        """生成文档摘要"""
        system_prompt = f"""你是一个专业的文档摘要助手。请为以下文档生成一个简洁的摘要，不超过{max_length}字。
摘要应该包含文档的核心观点和关键信息。"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请为以下文档生成摘要：\n\n{content[:8000]}"}
        ]
        
        try:
            result = await self.call_llm(messages, temperature=0.3)
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            return f"生成摘要失败: {str(e)}"
    
    async def classify_document(self, content: str) -> Dict[str, Any]:
        """自动分类文档"""
        system_prompt = """你是一个文档分类助手。请分析文档内容，返回以下JSON格式的分类结果：
{
    "doc_type": "article|paper|transcript|note|code|other",
    "category": "分类名称",
    "tags": ["标签1", "标签2", "标签3"],
    "confidence": 0.95
}"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请分类以下文档：\n\n{content[:5000]}"}
        ]
        
        try:
            result = await self.call_llm(messages, temperature=0.3)
            content = result["choices"][0]["message"]["content"]
            # 提取JSON
            import re
            json_match = re.search(r'\{[^}]*\}', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return {"doc_type": "other", "category": "未分类", "tags": [], "confidence": 0}
        except Exception as e:
            return {"doc_type": "other", "category": "未分类", "tags": [], "error": str(e)}
    
    async def generate_wiki_page(
        self,
        source_content: str,
        title: str,
        related_docs: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """从原始内容生成Wiki页面"""
        related_content = ""
        if related_docs:
            for doc_id in related_docs[:3]:  # 最多3个相关文档
                doc = await self.file_tools.read_raw_document(doc_id)
                if doc:
                    related_content += f"\n\n相关文档 {doc_id}:\n{doc[:2000]}"
        
        system_prompt = """你是一个知识管理专家。请将提供的原始内容整理成结构化的Wiki页面。
要求：
1. 使用Markdown格式
2. 包含清晰的标题层级
3. 提取关键概念并加粗
4. 添加适当的链接引用
5. 保持客观、准确

输出格式：
- 第一行：页面标题
- 然后是Markdown格式的内容"""
        
        user_content = f"原始内容：\n{source_content[:10000]}"
        if related_content:
            user_content += f"\n\n{related_content}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        
        try:
            result = await self.call_llm(messages, temperature=0.5)
            generated_content = result["choices"][0]["message"]["content"]
            
            # 检查内容是否为空
            if not generated_content or generated_content.strip() == "":
                logger.warning(f"生成Wiki页面内容为空 - 标题: {title}")
                return {
                    "title": title,
                    "content": f"生成失败: AI返回内容为空"
                }
            
            # 提取标题
            lines = generated_content.split('\n')
            generated_title = title
            content_start = 0
            
            for i, line in enumerate(lines):
                if line.startswith('# '):
                    generated_title = line[2:].strip()
                    content_start = i + 1
                    break
            
            final_content = '\n'.join(lines[content_start:]).strip()
            
            if not final_content:
                # 如果提取后内容为空，使用原始内容
                final_content = generated_content.strip()
            
            return {
                "title": generated_title,
                "content": final_content
            }
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"生成Wiki页面失败 - 标题: {title}, 错误类型: {type(e).__name__}, 错误: {str(e)}")
            logger.debug(f"生成Wiki页面失败 - 完整堆栈: {error_trace}")
            return {
                "title": title,
                "content": f"生成失败: {str(e)}"
            }
    
    async def chat_with_knowledge(
        self,
        query: str,
        context_docs: Optional[List[str]] = None,
        context_pages: Optional[List[str]] = None
    ) -> str:
        """基于知识库进行问答"""
        # 构建上下文
        context_parts = []
        
        if context_docs:
            for doc_id in context_docs[:5]:
                doc = await self.file_tools.read_raw_document(doc_id)
                if doc:
                    context_parts.append(f"【原始文档 {doc_id}】\n{doc[:3000]}")
        
        if context_pages:
            for page_id in context_pages[:5]:
                page = await self.file_tools.read_wiki_page(page_id)
                if page:
                    context_parts.append(f"【Wiki页面 {page_id}】\n{page['content'][:3000]}")
        
        context = "\n\n---\n\n".join(context_parts)
        
        system_prompt = """你是一个基于知识库的AI助手。请根据提供的上下文回答用户问题。
如果上下文中没有相关信息，请明确说明。
回答要求：
1. 基于提供的上下文
2. 准确、客观
3. 可以引用具体的文档或页面
4. 如果不确定，说明不确定"""
        
        user_content = f"上下文信息：\n{context}\n\n用户问题：{query}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        
        try:
            result = await self.call_llm(messages, temperature=0.7)
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            return f"回答失败: {str(e)}"
    
    async def extract_entities(self, content: str) -> List[Dict[str, Any]]:
        """从内容中提取实体"""
        system_prompt = """请从以下文本中提取关键实体（人名、组织、概念、技术等），返回JSON数组格式：
[
    {"name": "实体名称", "type": "person|organization|concept|technology|other", "description": "简要描述"}
]"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content[:8000]}
        ]
        
        try:
            result = await self.call_llm(messages, temperature=0.3)
            content = result["choices"][0]["message"]["content"]
            import re
            json_match = re.search(r'\[[^\]]*\]', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return []
        except Exception as e:
            return [{"error": str(e)}]
    
    async def suggest_links(self, page_content: str, existing_pages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """建议页面链接"""
        if not existing_pages:
            return []
        
        pages_text = "\n".join([f"- {p['title']} (ID: {p['id']})" for p in existing_pages[:20]])
        
        system_prompt = """请分析当前页面内容，从现有页面列表中建议可以建立链接的页面。
返回JSON格式：
[
    {"page_id": "页面ID", "reason": "建议链接的原因", "anchor_text": "建议的锚文本"}
]"""
        
        user_content = f"当前页面内容：\n{page_content[:5000]}\n\n现有页面：\n{pages_text}"
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
        
        try:
            result = await self.call_llm(messages, temperature=0.5)
            content = result["choices"][0]["message"]["content"]
            import re
            json_match = re.search(r'\[[^\]]*\]', content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return []
        except Exception as e:
            return []
    
    async def process_with_tools(
        self,
        user_message: str,
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        使用工具处理用户请求
        让AI决定调用哪些工具来完成任务
        """
        # 获取工具描述
        file_tool_descs = self.file_tools.get_tool_descriptions()
        code_tool_descs = self.code_tools.get_tool_descriptions()
        all_tools = file_tool_descs + code_tool_descs
        
        system_prompt = f"""你是一个智能助手，可以使用以下工具来帮助用户：

{json.dumps(all_tools, indent=2, ensure_ascii=False)}

请分析用户的请求，决定需要调用哪些工具。
如果需要调用工具，请返回JSON格式：
{{
    "thought": "你的思考过程",
    "actions": [
        {{"tool": "工具名", "params": {{参数}}}}
    ],
    "response": "给用户的回复"
}}

如果不需要工具，直接回复即可。"""
        
        messages = [{"role": "system", "content": system_prompt}]
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_message})
        
        try:
            result = await self.call_llm(messages, temperature=0.7)
            content = result["choices"][0]["message"]["content"]
            
            # 尝试解析JSON
            import re
            json_match = re.search(r'\{[^}]*"actions"[^}]*\}', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                
                # 执行工具调用
                tool_results = []
                for action in parsed.get("actions", []):
                    tool_name = action.get("tool")
                    params = action.get("params", {})
                    
                    # 执行文件工具
                    if hasattr(self.file_tools, tool_name):
                        method = getattr(self.file_tools, tool_name)
                        result = await method(**params)
                        tool_results.append({"tool": tool_name, "result": result})
                    
                    # 执行代码工具
                    elif hasattr(self.code_tools, tool_name):
                        method = getattr(self.code_tools, tool_name)
                        result = await method(**params)
                        tool_results.append({"tool": tool_name, "result": result})
                
                return {
                    "thought": parsed.get("thought", ""),
                    "tool_results": tool_results,
                    "response": parsed.get("response", "")
                }
            
            return {"response": content}
            
        except Exception as e:
            return {"error": str(e), "response": f"处理失败: {str(e)}"}

    async def _ai_select_relevant(
        self,
        query: str,
        wiki_pages: List[Dict[str, Any]],
        documents: List[Dict[str, Any]],
        top_k: int = 5
    ) -> List[Dict[str, str]]:
        """
        让AI从所有Wiki页面和文档的标题/摘要中，选出与问题最相关的条目。
        
        适合小规模知识库（几十~几百篇），比关键词/向量搜索更准确。
        
        Args:
            query: 用户问题
            wiki_pages: [{"id", "title", "description", "tags", "category"}]
            documents: [{"id", "title", "summary", "tags", "category"}]
            top_k: 最多返回多少条
            
        Returns:
            [{"id": "xxx", "type": "wiki|document"}]
        """
        # 构建知识库目录
        catalog_lines = []

        if wiki_pages:
            catalog_lines.append("=== Wiki知识页面 ===")
            for wp in wiki_pages:
                desc = wp.get("description", "") or ""
                tags = ", ".join(wp.get("tags", []))
                cat = wp.get("category", "") or ""
                line = f"- [ID: {wp['id']}] {wp['title']}"
                if desc:
                    line += f" — {desc[:100]}"
                if tags:
                    line += f" (标签: {tags})"
                if cat:
                    line += f" [分类: {cat}]"
                catalog_lines.append(line)

        if documents:
            catalog_lines.append("\n=== 原始资料文档 ===")
            for doc in documents:
                summary = doc.get("summary", "") or ""
                tags = ", ".join(doc.get("tags", []))
                cat = doc.get("category", "") or ""
                line = f"- [ID: {doc['id']}] {doc['title']}"
                if summary:
                    line += f" — {summary[:100]}"
                if tags:
                    line += f" (标签: {tags})"
                if cat:
                    line += f" [分类: {cat}]"
                catalog_lines.append(line)

        if not catalog_lines:
            return []

        catalog = "\n".join(catalog_lines)

        system_prompt = f"""你是一个知识库检索助手。用户会提出一个问题，你需要从下面的知识库目录中，选出与问题最相关的条目。

目录中每个条目都有 ID、标题、简短描述和标签。
请仔细分析用户问题的真实意图，选择最可能包含答案的条目。

返回JSON数组格式（按相关度从高到低排序，最多{top_k}个）：
[
    {{"id": "条目ID", "type": "wiki", "reason": "选择原因"}},
    {{"id": "条目ID", "type": "document", "reason": "选择原因"}}
]

注意：
- type字段必须是 "wiki" 或 "document"
- 如果没有明显相关的条目，返回空数组 []
- 不要返回目录中不存在的ID"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"知识库目录：\n{catalog}\n\n用户问题：{query}"}
        ]

        try:
            result = await self.call_llm(messages, temperature=0.3)
            content = result["choices"][0]["message"]["content"]
            import re
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                selected = json.loads(json_match.group())
                # 验证返回的ID确实存在
                valid_ids = set()
                for wp in wiki_pages:
                    valid_ids.add(wp["id"])
                for doc in documents:
                    valid_ids.add(doc["id"])
                return [item for item in selected if item.get("id") in valid_ids][:top_k]
        except Exception as e:
            logger.error(f"AI选择相关条目失败: {e}")

        return []

    async def smart_qa(
        self,
        query: str,
        top_k: int = 5,
        retrieval: str = "ai"
    ) -> Dict[str, Any]:
        """
        智能问答：用户只提问题，系统从Wiki知识库中检索相关内容 → AI生成回答
        
        Args:
            query: 用户的问题
            top_k: 检索返回的最大结果数
            retrieval: 检索模式
                - "ai"（默认）: AI理解问题后从Wiki目录中选取相关条目
                - "auto": Wiki页面数低于阈值时直接全部给AI，超过则先关键词预筛再AI精选
            
        Returns:
            {
                "answer": "AI生成的回答",
                "sources": [...],
                "retrieval": "实际使用的检索模式",
                "search_query": "检索关键词"
            }
        """
        from app.services.search_service import SearchService
        from app.services.document_service import DocumentService
        from app.services.wiki_service import WikiService

        wiki_service = WikiService()

        # ========== Step 1: 从Wiki中检索相关内容 ==========
        selected_items = []  # [{"id", "type": "wiki"}]
        actual_retrieval = retrieval

        if retrieval == "auto":
            # 只看Wiki页面数，不包含原始文档
            wiki_count = len(await wiki_service.list_pages())
            if wiki_count <= self.settings.qa_ai_direct_threshold:
                actual_retrieval = "ai"
            else:
                actual_retrieval = "ai_prefilter"

        if actual_retrieval == "ai":
            # ---- AI判断模式：直接把全部Wiki条目给AI ----
            all_wiki = await wiki_service.list_pages()
            wiki_catalog = []
            for wp in all_wiki:
                wiki_catalog.append({
                    "id": wp.id,
                    "title": wp.metadata.title,
                    "description": wp.metadata.description,
                    "tags": wp.metadata.tags,
                    "category": wp.metadata.category
                })

            selected_items = await self._ai_select_relevant(
                query=query,
                wiki_pages=wiki_catalog,
                documents=[],  # 不包含原始文档
                top_k=top_k
            )

        elif actual_retrieval == "ai_prefilter":
            # ---- AI预筛模式：先关键词粗筛Wiki，再AI精选 ----
            from app.services.search_service import SearchService
            search_service = SearchService()
            candidate_count = max(top_k * 3, 20)
            search_results = await search_service.search(
                query=query,
                search_type="keyword",
                limit=candidate_count,
                doc_type="wiki"  # 只搜Wiki，不搜原始文档
            )

            if not search_results:
                # 关键词没搜到，回退到全量给AI（取前100条Wiki）
                all_wiki = await wiki_service.list_pages()[:100]
            else:
                # 从搜索结果中构建候选目录（只取Wiki类型）
                all_wiki = []
                seen_ids = set()
                for r in search_results:
                    rid = r["id"]
                    if r["type"] != "wiki" or rid in seen_ids:
                        continue
                    seen_ids.add(rid)
                    page = await wiki_service.get_page(rid)
                    if page:
                        all_wiki.append({
                            "id": page.id,
                            "title": page.metadata.title,
                            "description": page.metadata.description,
                            "tags": page.metadata.tags,
                            "category": page.metadata.category
                        })

            # 把候选目录给AI精选
            selected_items = await self._ai_select_relevant(
                query=query,
                wiki_pages=all_wiki,
                documents=[],  # 不包含原始文档
                top_k=top_k
            )

        # ========== Step 2: 读取Wiki全文，构建上下文 ==========
        if not selected_items:
            return {
                "answer": "抱歉，知识库中没有找到与您问题相关的内容。您可以尝试换一种方式描述，或者通过 /api/documents 上传相关资料。",
                "sources": [],
                "retrieval": actual_retrieval,
                "search_query": query
            }

        context_parts = []
        sources = []

        for item in selected_items:
            page = await wiki_service.get_page(item["id"])
            if page:
                context_parts.append(
                    f"【Wiki：{page.metadata.title}】\n{page.content[:4000]}"
                )
                sources.append({
                    "id": page.id,
                    "title": page.metadata.title,
                    "type": "wiki",
                    "slug": page.slug,
                    "relevance_reason": item.get("reason", "")
                })

        context = "\n\n---\n\n".join(context_parts)

        # ========== Step 3: AI基于上下文回答问题 ==========
        system_prompt = """你是一个知识库问答助手。用户会提出一个问题，你会收到从知识库中检索到的相关Wiki页面。

请根据这些资料回答用户的问题，遵循以下规则：
1. **仅基于提供的资料回答**，不要编造资料中没有的信息
2. 如果资料不足以完整回答，明确说明哪些部分无法确认
3. 在回答中引用资料来源，格式如「参考：[Wiki标题]」
4. 如果多份资料有矛盾，指出矛盾之处
5. 回答要结构清晰、简洁有用"""

        user_content = f"""知识库检索到的相关Wiki页面：

{context}

---

用户的问题：{query}

请基于以上资料回答用户的问题。"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            result = await self.call_llm(messages, temperature=0.7)
            answer = result["choices"][0]["message"]["content"]
        except Exception as e:
            answer = f"生成回答失败: {str(e)}"

        return {
            "answer": answer,
            "sources": sources,
            "retrieval": actual_retrieval,
            "search_query": query
        }