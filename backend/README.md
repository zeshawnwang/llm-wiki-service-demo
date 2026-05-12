# LLM Wiki Service

一个轻量级的 LLM Wiki 后端服务，基于 FastAPI 实现。将非结构化文档通过 AI 自动整理为结构化知识库，支持增量知识融合。

## 项目结构

```
llm-wiki-service/
├── app/
│   ├── main.py                    # FastAPI 应用入口（含Git同步定时器）
│   ├── config.py                  # 配置管理（唯一配置来源，读取 .env）
│   ├── models/                    # 数据模型
│   │   ├── document.py            # 文档模型
│   │   └── wiki.py                # Wiki模型
│   ├── services/                  # 核心业务服务
│   │   ├── document_service.py    # 文档管理
│   │   ├── wiki_service.py        # Wiki知识管理
│   │   ├── ai_service.py          # AI处理（自动路由LLM供应商）
│   │   ├── search_service.py      # 搜索（关键词+可选向量）
│   │   ├── pipeline_service.py    # 知识摄入流水线
│   │   └── git_sync_service.py    # Git定时同步
│   ├── tools/                     # AI工具（不依赖LangChain）
│   │   ├── file_tools.py          # 文件读写操作
│   │   └── code_tools.py          # 代码执行
│   └── api/                       # REST API路由
│       ├── documents.py
│       ├── wiki.py
│       ├── ai.py
│       ├── search.py
│       └── pipeline.py
├── data/                          # 本地数据存储（自动创建）
│   ├── raw/                       # 原始资料层（AI只读）
│   ├── wiki/                      # Wiki知识层（AI读写）
│   │   ├── pages/                 # Wiki页面（Markdown + frontmatter）
│   │   └── index/                 # 索引文件
│   └── vectors/                   # 向量索引缓存
├── .env.example                   # 环境变量模板（唯一配置文件）
├── requirements.txt
└── README.md
```

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，配置 API Key 和开关
uvicorn app.main:app --reload
# 访问 http://localhost:8000/docs 查看API文档
```

## 配置说明

所有配置项都在 `.env` 文件中，`config.py` 是唯一的配置读取点。

### 完整配置清单

```env
# ===== LLM 供应商 =====
LLM_PROVIDER=openai                          # openai | anthropic
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
ANTHROPIC_API_KEY=
ANTHROPIC_BASE_URL=https://api.anthropic.com
ANTHROPIC_CHAT_MODEL=claude-sonnet-4-20250514

# ===== 向量搜索 =====
ENABLE_VECTOR_SEARCH=true                    # true | false

# ===== 问答检索 =====
QA_RETRIEVAL_MODE=ai                         # ai | auto
QA_AI_DIRECT_THRESHOLD=200                   # auto模式阈值（Wiki页面数）

# ===== Git 同步 =====
GIT_SYNC_ENABLED=false                       # true | false
GIT_SYNC_INTERVAL_MINUTES=30
GIT_REPO_PATH=./data
GIT_REMOTE_URL=
GIT_USER_NAME=LLM Wiki Bot
GIT_USER_EMAIL=llm-wiki-bot@example.com
GIT_BRANCH=main
GIT_COMMIT_MESSAGE=                          # 留空自动生成

# ===== 存储 =====
DATA_DIR=./data
RAW_DIR=./data/raw
WIKI_DIR=./data/wiki

# ===== 服务 =====
APP_NAME=LLM Wiki Service
DEBUG=true
LOG_LEVEL=INFO
HOST=0.0.0.0
PORT=8000
```

### 配置项说明

| 配置项 | 默认值 | 说明 |
|-------|--------|------|
| `LLM_PROVIDER` | `openai` | 选择 LLM 供应商，`openai` 或 `anthropic` |
| `ENABLE_VECTOR_SEARCH` | `true` | 是否启用向量语义搜索，关闭后搜索零成本 |
| `QA_RETRIEVAL_MODE` | `ai` | 问答检索模式，`ai` 直接给AI全量目录，`auto` 大库先关键词预筛 |
| `QA_AI_DIRECT_THRESHOLD` | `200` | `auto` 模式下，Wiki页面数低于此值直接全部给AI |
| `GIT_SYNC_ENABLED` | `false` | 是否启用定时 Git 推送同步 |
| `GIT_SYNC_INTERVAL_MINUTES` | `30` | Git 同步间隔（分钟） |

---

## 用户使用指南：输入什么，得到什么

### 一、导入知识（给系统喂内容）

#### 1. 上传原始文档

**你给的：** 文本内容（Markdown/纯文本）

```bash
# 方式A：直接提交文本（JSON Body）
POST /api/documents
Content-Type: application/json

{
  "filename": "rag-article.md",
  "content": "# RAG技术原理\nRAG是...(你的文章全文)",
  "title": "RAG技术原理",
  "tags": ["RAG", "LLM"],
  "category": "AI技术"
}

# 方式B：上传文件（multipart，唯一保留的表单接口）
POST /api/documents/upload
Content-Type: multipart/form-data

file=@rag-article.md
```

**你得到的：** 文档元数据 JSON

```json
{
  "id": "a1b2c3d4e5f6",
  "filename": "rag-article.md",
  "content": "# RAG技术原理\nRAG是...",
  "metadata": {
    "title": "rag-article.md",
    "tags": [],
    "category": null,
    "doc_type": "other",
    "created_at": "2026-05-12T15:30:00",
    "file_size": 2048
  }
}
```

#### 2. 让AI自动归纳（核心功能）

**你给的：** 一条指令（不需要指定文档ID）

```bash
POST /api/pipeline/run
Content-Type: application/json

# 不传参数 = 自动处理所有未归纳的文档
{}

# 或者指定特定文档
{
  "doc_ids": ["a1b2c3d4e5f6", "g7h8i9j0k1l2"],
  "auto_rebuild": true
}
```

**你得到的：** 处理报告（AI做了什么）

```json
{
  "started_at": "2026-05-12T15:30:00",
  "finished_at": "2026-05-12T15:32:30",
  "total_documents": 2,
  "summary": { "new_wiki": 2, "merged": 0, "skipped": 0, "error": 0 },
  "results": [
    {
      "doc_id": "a1b2c3d4e5f6",
      "status": "new_wiki",
      "wiki_page_id": "x1y2z3",
      "wiki_page_ids": ["x1y2z3"],
      "merge_type": "new",
      "changes": ["创建Wiki页面: RAG技术原理", "共创建 1 个Wiki页面（主题数: 1）"]
    }
  ]
}
```

> **这就是"喂内容 → 得到知识"的核心流程。** 你只需要上传文档，然后调一次 pipeline，AI 会自动判断是新建 Wiki、合并到已有 Wiki、还是跳过。

### 二、提问（从知识库获取答案）

**你给的：** 一个自然语言问题

```bash
POST /api/ai/ask
Content-Type: application/json

{
  "query": "RAG有哪些优化手段？"
}
```

**你得到的：** AI 生成的回答 + 引用来源

```json
{
  "answer": "RAG的主要优化手段包括：\n1. 混合检索（参考：[RAG技术原理]）\n2. 查询改写...",
  "sources": [
    {
      "id": "x1y2z3",
      "title": "RAG技术原理",
      "type": "wiki",
      "slug": "rag-ji-shu-yuan-li",
      "relevance_reason": "直接讲述了RAG的核心技术"
    }
  ],
  "retrieval": "ai",
  "search_query": "RAG有哪些优化手段？"
}
```

### 三、管理Wiki（手动编辑知识）

**你给的：** 标题 + Markdown内容

```bash
# 创建Wiki页面（JSON Body）
POST /api/wiki/pages
Content-Type: application/json

{
  "title": "Prompt工程指南",
  "content": "# Prompt工程\n## 基础概念\n...",
  "tags": ["prompt", "AI工程"],
  "category": "AI工程",
  "status": "published"
}

# 获取所有Wiki页面
GET /api/wiki/pages

# 获取知识图谱（页面之间的关联关系）
GET /api/wiki/graph
```

**你得到的：** Wiki页面 JSON / 知识图谱 JSON

### 四、辅助功能

| 功能 | 你给的 | 你得到的 |
|------|--------|---------|
| 生成摘要 | 文档ID或文本 | `{"summary": "这篇文章讲了..."}` |
| 自动分类 | 文档ID或文本 | `{"doc_type": "paper", "tags": ["RAG", "LLM"], "category": "AI技术"}` |
| 提取实体 | 文档ID或文本 | `{"entities": [{"name": "RAG", "type": "technology"}]}` |
| 搜索 | 关键词 | 匹配的文档/Wiki列表 |
| 预览处理策略 | 文档ID | AI建议的处理方式（不执行） |
| 知识结构分析 | 无 | 建议的新分类、页面关联、知识缺口 |

### 输入输出类型总结

| 你给的内容类型 | 系统返回的内容类型 |
|--------------|-----------------|
| **文本**（Markdown文章、笔记、代码） | **结构化Wiki**（AI归纳后的知识页面） |
| **自然语言问题** | **自然语言回答**（基于知识库生成，附带引用来源） |
| **文件**（.md / .txt） | **文档元数据**（ID、标题、标签、分类） |
| **指令**（"归纳"、"分类"、"摘要"） | **AI处理结果**（JSON格式的结构化数据） |

---

## 新内容输入的五种场景

当新文档通过 `POST /api/pipeline/run` 进入系统时，AI 会分析文档与已有知识库的关系，产生以下五种场景：

### 场景一：单主题全新内容

```
输入: 一篇关于"RAG技术原理"的文章
知识库: 空的（或无相关Wiki）

AI分析:
  topic_count: 1
  topics: [{ topic: "RAG技术原理", action: "create_new" }]

产出: 1个新Wiki页面
调用链路:
  POST /api/pipeline/run
    → find_unprocessed_documents()
    → _analyze_new_document()          # AI判断：单主题，全新
    → _create_new_wiki()               # topic_count=1，直接生成
      → ai_service.generate_wiki_page()  # AI生成结构化Wiki内容
      → wiki_service.create_page()       # 写入 data/wiki/pages/
      → _mark_document_processed()       # 标记文档已处理
    → search_service.rebuild_index()    # 重建搜索索引
```

### 场景二：多主题全新内容

```
输入: 一篇长文同时讲了"Prompt工程"、"模型微调"、"Agent设计"
知识库: 空的（或无相关Wiki）

AI分析:
  topic_count: 3
  topics: [
    { topic: "Prompt工程", action: "create_new" },
    { topic: "模型微调",   action: "create_new" },
    { topic: "Agent设计",  action: "create_new" }
  ]

产出: 3个新Wiki页面 + 互相建立关联
调用链路:
  POST /api/pipeline/run
    → _analyze_new_document()          # AI判断：3个独立主题
    → _create_new_wiki()               # topic_count>1，进入多主题分支
      → _ai_split_by_topics()           # AI按主题拆分文档内容
      → 循环每个segment:
          → ai_service.generate_wiki_page()  # 分别生成Wiki
          → wiki_service.create_page()
      → wiki_service.add_related_page()     # 同源页面互相链接
    → _mark_document_processed()
    → search_service.rebuild_index()
```

### 场景三：单主题内容合并到已有Wiki

```
输入: 一篇关于"RAG优化技巧"的文章
知识库: 已有Wiki页面 "RAG技术综述"

AI分析:
  topic_count: 1
  topics: [{ topic: "RAG优化技巧", action: "merge_into", target: "abc123" }]

产出: 0个新Wiki，已有Wiki从v1更新到v2
调用链路:
  POST /api/pipeline/run
    → _analyze_new_document()          # AI判断：与已有Wiki相关
    → _merge_into_existing()
      → wiki_service.get_page("abc123")  # 读取已有Wiki内容
      → _ai_merge_content()               # AI智能合并新旧内容
      → wiki_service.update_page()        # 更新版本 v1→v2
      → _mark_document_processed()
```

### 场景四：混合策略（部分新建 + 部分合并）

```
输入: 一篇关于"大模型技术栈"的文章，涉及RAG和Prompt工程
知识库: 已有Wiki页面 "RAG技术综述"，但没有Prompt工程相关Wiki

AI分析:
  topic_count: 2
  topics: [
    { topic: "RAG技术",   action: "merge_into", target: "abc123" },
    { topic: "Prompt工程", action: "create_new" }
  ]

产出: 1个新Wiki + 更新1个已有Wiki
调用链路:
  POST /api/pipeline/run
    → _analyze_new_document()          # AI判断：混合策略
    → _split_and_merge()               # has_create=true, has_merge=true
      → _ai_split_document()             # AI拆分文档
      → 对merge段: _ai_merge_content() + update_page()
      → 对create段: generate_wiki_page() + create_page()
    → _mark_document_processed()
    → _ai_rebuild_knowledge_structure()  # 重建知识结构
      → 自动建立页面关联
      → 发现新的分类方向
```

### 场景五：内容已被覆盖（跳过）

```
输入: 一篇与已有Wiki内容高度重复的文章
知识库: 已有Wiki页面 "RAG技术综述"（内容已充分覆盖）

AI分析:
  topic_count: 1
  topics: [{ topic: "RAG技术", action: "skip" }]

产出: 0个新Wiki，文档标记为已处理
调用链路:
  POST /api/pipeline/run
    → _analyze_new_document()          # AI判断：已充分覆盖
    → _mark_document_processed("skipped")  # 直接跳过
```

### 场景汇总

| 场景 | 主题数 | 产出 | merge_type | 适用情况 |
|------|--------|------|-----------|---------|
| 一 | 1 | 1个新Wiki | `new` | 单主题，知识库中无相关内容 |
| 二 | N | N个新Wiki + 互链 | `new_multi` | 多主题，全部是全新的 |
| 三 | 1 | 更新1个已有Wiki | `update` | 单主题，与已有Wiki相关 |
| 四 | N | M个新 + K个更新 | `split` | 多主题，部分新建部分合并 |
| 五 | 1 | 0（跳过） | — | 内容已被充分覆盖 |

---

## API 概览

### 文档管理
- `POST /api/documents` - 创建文档
- `POST /api/documents/upload` - 上传文件
- `GET /api/documents` - 列出文档
- `GET /api/documents/{id}` - 获取文档
- `PUT /api/documents/{id}` - 更新文档
- `DELETE /api/documents/{id}` - 删除文档

### Wiki管理
- `POST /api/wiki/pages` - 创建Wiki页面
- `GET /api/wiki/pages` - 列出Wiki页面
- `GET /api/wiki/pages/{id}` - 获取Wiki页面
- `PUT /api/wiki/pages/{id}` - 更新Wiki页面
- `DELETE /api/wiki/pages/{id}` - 删除Wiki页面
- `GET /api/wiki/graph` - 获取知识图谱数据

### AI处理
- `POST /api/ai/ask` - 智能问答（用户只管提问，系统自动检索+回答）
- `POST /api/ai/summarize` - 生成文档摘要
- `POST /api/ai/classify` - 自动分类
- `POST /api/ai/generate-wiki` - 从文档生成Wiki
- `POST /api/ai/chat` - 知识库问答（需手动指定文档ID）
- `POST /api/ai/extract-entities` - 实体提取
- `POST /api/ai/suggest-links` - 建议页面链接

### 知识摄入流水线
- `GET /api/pipeline/status` - 查看待处理文档
- `POST /api/pipeline/run` - 执行流水线（自动融合）
- `POST /api/pipeline/analyze/{doc_id}` - 预览单篇处理策略
- `GET /api/pipeline/structure` - 知识结构优化建议

### 搜索
- `GET /api/search?q={query}` - 搜索（支持 keyword/semantic/hybrid）
- `GET /api/search/recommendations/{type}/{id}` - 相关推荐
- `POST /api/search/rebuild-index` - 重建搜索索引

---

## 为什么不使用 LangChain

### 当前方案：直接调用 LLM API

本项目的 AI 调用方式是直接通过 `httpx` 调用 OpenAI / Anthropic 的 REST API，所有工具（文件读写、代码执行）都是自己实现的简单 Python 类。

### 优势

| 维度 | 说明 |
|------|------|
| **透明可控** | 每一行代码都可见，prompt 构造、API 调用、结果解析全部暴露，便于调试和定制 |
| **零学习成本** | 不需要理解 LangChain 的 Chain/Agent/Tool/Retriever 等抽象概念，新开发者可直接上手 |
| **轻量依赖** | 只依赖 `httpx` 发 HTTP 请求，不需要安装 LangChain 及其几十个子依赖 |
| **精确控制 prompt** | prompt 是纯字符串拼接，可以精确控制每个字，不会被框架的模板系统干扰 |
| **错误处理简单** | 直接 try/except HTTP 响应，没有框架内部的隐式重试/降级逻辑 |
| **启动速度快** | 无需加载 LangChain 的模块链，冷启动时间更短 |
| **版本稳定** | 不受 LangChain 频繁的 breaking changes 影响，API 变化时只需改一行 URL |

### 劣势

| 维度 | 说明 |
|------|------|
| **无标准化抽象** | 切换 LLM 供应商需要自己写适配代码（本项目通过 `call_llm()` 路由解决） |
| **无内置 RAG** | 需要自己实现文档切片、检索、上下文拼接（本项目通过 `SearchService` 解决） |
| **无 Agent 框架** | 工具调用逻辑是自己解析 JSON 实现的，缺少 LangChain 的 ReAct/Plan-and-Execute 等策略 |
| **无流式输出** | 当前实现是同步返回完整结果，不支持 SSE 流式输出 |
| **无 Memory 管理** | 对话历史需要自己管理，没有内置的会话记忆抽象 |
| **无生态集成** | 无法直接使用 LangChain 的数百个集成（向量库、文档加载器等） |
| **工具调用非原生** | 当前是让 AI 输出 JSON 再解析执行，而非使用 OpenAI Function Calling 原生工具调用 |

### 结论

对于本项目这种**场景明确、调用模式固定、需要精细控制 prompt** 的知识库系统，直接调用 API 的收益大于引入 LangChain 的收益。LangChain 更适合需要快速集成多种数据源、频繁切换 LLM 供应商、或需要复杂 Agent 编排的场景。

---

## 如果使用 LangChain 重构

如果未来需要引入 LangChain，以下是重构方向和具体改动点：

### 1. AIService 重构 → LangChain Chat Models

**当前代码：**
```python
# ai_service.py - 手动调用 httpx
async def _call_openai(self, messages, model, temperature):
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=data)
    return response.json()
```

**重构为：**
```python
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

def get_llm():
    if settings.llm_provider == "anthropic":
        return ChatAnthropic(model=settings.anthropic_chat_model, ...)
    return ChatOpenAI(model=settings.openai_chat_model, ...)
```

**改动范围：** `ai_service.py` 全部重写，删除 `_call_openai`、`_call_anthropic`、`call_llm`

### 2. 工具系统重构 → LangChain Tools

**当前代码：**
```python
# ai_service.py - process_with_tools() 手动解析JSON
json_match = re.search(r'\{.*"actions".*\}', content, re.DOTALL)
parsed = json.loads(json_match.group())
for action in parsed.get("actions", []):
    method = getattr(self.file_tools, action["tool"])
    result = await method(**action["params"])
```

**重构为：**
```python
from langchain_core.tools import tool

@tool
async def read_raw_document(doc_id: str) -> str:
    """读取原始文档内容"""
    return await file_tools.read_raw_document(doc_id)

@tool
async def write_wiki_page(page_id: str, content: str, metadata: dict) -> str:
    """写入Wiki页面"""
    return await file_tools.write_wiki_page(page_id, content, metadata)

# 使用 OpenAI 原生 Function Calling
llm_with_tools = llm.bind_tools([read_raw_document, write_wiki_page, ...])
```

**改动范围：** `tools/file_tools.py`、`tools/code_tools.py` 改为 `@tool` 装饰器，`ai_service.py` 的 `process_with_tools()` 删除

### 3. RAG 检索重构 → LangChain Retrievers

**当前代码：**
```python
# search_service.py - 手动实现关键词+向量混合搜索
results = await self._keyword_search(query, doc_type)
results.extend(await self._semantic_search(query, doc_type))
```

**重构为：**
```python
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS

# 关键词检索器
bm25_retriever = BM25Retriever.from_documents(documents, k=5)

# 向量检索器
vectorstore = FAISS.from_documents(documents, embeddings)
vector_retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

# 混合检索
from langchain.retrievers import EnsembleRetriever
ensemble = EnsembleRetriever(
    retrievers=[bm25_retriever, vector_retriever],
    weights=[0.4, 0.6]
)
```

**改动范围：** `search_service.py` 大幅重写，引入向量库依赖（FAISS/Chroma），删除手动向量计算逻辑

### 4. 知识摄入流水线重构 → LangChain Chains / LCEL

**当前代码：**
```python
# pipeline_service.py - 手动编排多个AI调用步骤
analysis = await self._analyze_new_document(new_doc, existing_wiki)
if action == "create_new":
    result = await self._create_new_wiki(new_doc, analysis)
elif action == "merge_into":
    result = await self._merge_into_existing(new_doc, analysis)
```

**重构为：**
```python
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import JsonOutputParser

# 用 LCEL 声明式编排
analysis_chain = (
    {"new_doc": RunnablePassthrough(), "existing_wiki": get_wiki_summary}
    | prompt
    | llm
    | JsonOutputParser()
)

create_chain = analysis_chain | RunnableLambda(handle_create)
merge_chain = analysis_chain | RunnableLambda(handle_merge)

# 路由
pipeline = RunnableBranch(
    (lambda x: x["action"] == "create_new", create_chain),
    (lambda x: x["action"] == "merge_into", merge_chain),
    RunnableLambda(handle_skip)
)
```

**改动范围：** `pipeline_service.py` 大幅重写，从命令式改为声明式

### 5. 需要新增的依赖

```
# requirements.txt 新增
langchain>=0.3.0
langchain-openai>=0.2.0
langchain-anthropic>=0.2.0
langchain-community>=0.3.0
faiss-cpu>=1.7.0          # 或 chromadb
rank-bm25>=0.2.2          # BM25关键词检索
```

### 6. 改动文件清单

| 文件 | 改动程度 | 说明 |
|------|---------|------|
| `app/services/ai_service.py` | **重写** | 替换为 LangChain Chat Models + Tools |
| `app/services/search_service.py` | **重写** | 替换为 LangChain Retrievers + VectorStore |
| `app/services/pipeline_service.py` | **大幅修改** | 改为 LCEL 声明式编排 |
| `app/tools/file_tools.py` | **中幅修改** | 改为 `@tool` 装饰器格式 |
| `app/tools/code_tools.py` | **中幅修改** | 改为 `@tool` 装饰器格式 |
| `app/config.py` | **小幅修改** | 新增 LangChain 相关配置 |
| `requirements.txt` | **更新** | 新增 LangChain 生态依赖 |
| `app/models/` | **不变** | 数据模型保持不变 |
| `app/api/` | **不变** | API 层保持不变（服务接口不变） |
| `app/services/document_service.py` | **不变** | 文件存储逻辑不变 |
| `app/services/wiki_service.py` | **不变** | Wiki 存储逻辑不变 |

### 7. 重构建议

- **渐进式重构**：先替换 `AIService` 的 LLM 调用（收益最大、风险最低），再逐步替换搜索和流水线
- **保留接口不变**：API 层和 Service 层的公开方法签名保持不变，只改内部实现
- **不要一次性全改**：LangChain 的抽象层会隐藏细节，一次性重构容易引入难以排查的 bug

---

## 前端方案

详细设计文档见 [../frontend/README.md](../frontend/README.md)。

### 架构选择：前后端分离

**推荐前后端彻底分离，不融合到同一个项目中。**

```
推荐方案：
llm-wiki-service-demo/        ← 父目录（Git仓库）
├── backend/                   ← 后端（当前项目）
│   ├── app/
│   ├── requirements.txt
│   └── ...
└── frontend/                  ← 前端（独立项目）
    ├── src/
    ├── package.json
    └── ...
```

**理由：**

| 维度 | 融合 | 分离（推荐） |
|------|------|-------------|
| **部署** | Python服务同时托管静态文件，耦合 | 前后端独立部署，可用Nginx反向代理 |
| **开发体验** | 前端热更新和后端重启互相干扰 | 各自独立开发，互不影响 |
| **技术栈** | Python模板或混合，不伦不类 | 前端用Node生态，后端用Python生态 |
| **扩展性** | 难以单独扩容前端或后端 | 可以独立扩容（如前端CDN、后端多实例） |
| **团队协作** | 前后端开发者改同一个仓库 | 清晰的接口边界，并行开发 |
| **构建** | 需要在Python项目中集成Node构建 | 各自CI/CD |

### 前端技术选型

| 类别 | 选型 |
|------|------|
| 框架 | React 18 + TypeScript |
| 构建 | Vite |
| 样式 | Tailwind CSS |
| Markdown渲染 | react-markdown + remark-gfm + rehype-highlight |
| Markdown编辑 | Milkdown 或 @uiw/react-md-editor |
| 图谱 | react-force-graph-2d |
| 状态管理 | Zustand |
| HTTP | ky 或 fetch封装 |

### 页面结构

```
├── 首页      统计面板：Wiki数量、文档数量、未处理文档数
├── 知识库    列表视图（文件树+Markdown渲染）+ 图谱视图（力导向图）
├── 导入      上传文档 + 运行pipeline + 查看处理结果
├── 问答      输入问题 → AI回答 + 引用来源
└── 设置      配置管理（低频）
```

### 开发优先级

1. **P0** 基础框架 + 知识库列表视图（文件树 + Markdown渲染）
2. **P1** 导入页面 + 问答页面
3. **P2** 首页统计 + 知识库图谱视图
4. **P3** 设置页面 + Markdown编辑器
