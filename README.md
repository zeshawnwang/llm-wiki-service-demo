# LLM Wiki

> 基于 LLM 的智能知识库系统 — 将非结构化文档自动整理为结构化 Wiki，支持增量知识融合与 AI 问答。

## ✨ 核心特性

- 🧠 **智能知识归纳** — 上传文档，AI 自动分析主题、生成/合并/跳过 Wiki 页面
- 🔍 **AI 驱动问答** — 用户只管提问，AI 自动检索相关 Wiki 并生成回答（附带引用来源）
- 🔄 **增量知识融合** — 新文档进入后，AI 判断与已有知识的关系，自动合并或新建
- 📊 **知识图谱可视化** — Wiki 页面之间的关联关系，类似 Obsidian 的图谱视图
- ⚙️ **灵活配置** — 支持 OpenAI / Anthropic 切换，向量搜索可关闭以节省成本
- 📡 **Git 自动同步** — 定时将知识数据推送到远程 Git 仓库

## 🏗️ 架构

```
┌─────────────────────────────────────────────────────────┐
│                      Frontend (待开发)                   │
│              React + TypeScript + Vite                  │
└────────────────────────┬────────────────────────────────┘
                         │ REST API (JSON)
┌────────────────────────▼────────────────────────────────┐
│                     Backend (FastAPI)                   │
│                                                         │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Pipeline │  │  AI Service  │  │  Search Service  │   │
│  │ 知识摄入  │   │ LLM 调用路由  │  │ 关键词+可选向量    │   │
│  └────┬─────┘  └──────┬───────┘  └────────┬─────────┘   │
│       │               │                    │            │
│  ┌────▼───────────────▼────────────────────▼─────────┐  │
│  │              Document / Wiki Service              │  │
│  │                  本地文件存储                       │  │
│  └──────────────────────┬────────────────────────────┘  │
│                         │                               │
│  ┌──────────────────────▼────────────────────────────┐  │
│  │  data/raw/    原始资料层（AI 只读）                  │  │
│  │  data/wiki/   Wiki 知识层（AI 读写，Markdown）       │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 📁 项目结构

```
wiki-service/
├── backend/                    # 后端服务（Python / FastAPI）
│   ├── app/
│   │   ├── api/                # REST API 路由（全部 JSON Body）
│   │   ├── models/             # 数据模型（Pydantic）
│   │   ├── services/           # 核心业务服务
│   │   │   ├── ai_service.py          # AI 处理（OpenAI / Claude 路由）
│   │   │   ├── pipeline_service.py    # 知识摄入流水线（5 种场景）
│   │   │   ├── document_service.py    # 文档管理
│   │   │   ├── wiki_service.py        # Wiki 知识管理
│   │   │   ├── search_service.py      # 搜索（关键词 + 可选向量）
│   │   │   └── git_sync_service.py    # Git 定时同步
│   │   ├── tools/              # AI 工具（文件操作、代码执行）
│   │   ├── config.py           # 配置管理（唯一配置来源）
│   │   └── main.py             # 应用入口
│   ├── .env.example            # 环境变量模板
│   ├── requirements.txt
│   └── README.md               # 后端完整文档
│
├── frontend/                   # 前端应用（待开发）
│   └── README.md               # 前端设计方案（线框图 + API 对接清单）
│
├── .gitignore
└── README.md                   # 本文件
```

## 🚀 快速开始

### 后端

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，配置 LLM API Key（OPENAI_API_KEY 或 ANTHROPIC_API_KEY）
uvicorn app.main:app --reload
# 访问 http://localhost:8000/docs 查看 Swagger API 文档
```

### 前端（待开发）

```bash
cd frontend
pnpm install
pnpm dev
```

## 📖 使用流程

```
1️⃣  上传文档
    POST /api/documents
    {"filename": "rag.md", "content": "...", "tags": ["RAG"]}

2️⃣  AI 自动归纳
    POST /api/pipeline/run
    → AI 分析每篇文档主题
    → 新主题 → 创建新 Wiki
    → 已有主题 → 合并到已有 Wiki
    → 重复内容 → 跳过

3️⃣  提问
    POST /api/ai/ask
    {"query": "RAG有哪些优化手段？"}
    → AI 从 Wiki 中检索相关页面
    → 生成回答，附带引用来源
```

## ⚙️ 配置

所有配置在 `backend/.env` 中，主要配置项：

| 配置项 | 说明 | 默认值 |
|-------|------|--------|
| `LLM_PROVIDER` | LLM 供应商（`openai` / `anthropic`） | `openai` |
| `OPENAI_API_KEY` | OpenAI API Key | — |
| `ANTHROPIC_API_KEY` | Anthropic API Key | — |
| `ENABLE_VECTOR_SEARCH` | 是否启用向量搜索（关闭后零成本） | `true` |
| `QA_RETRIEVAL_MODE` | 问答检索模式（`ai` / `auto`） | `ai` |
| `QA_AI_DIRECT_THRESHOLD` | auto 模式阈值（Wiki 页面数） | `200` |
| `GIT_SYNC_ENABLED` | Git 定时同步开关 | `false` |

完整配置见 [backend/.env.example](./backend/.env.example)。

## 🧩 知识摄入的五种场景

当新文档进入系统时，AI 自动判断处理策略：

| 场景 | 说明 | 产出 |
|------|------|------|
| 单主题全新 | 知识库中无相关内容 | 创建 1 个新 Wiki |
| 多主题全新 | 文档包含多个独立主题 | 创建 N 个新 Wiki + 互链 |
| 单主题合并 | 与已有 Wiki 相关 | 更新已有 Wiki（版本 +1） |
| 混合策略 | 部分新建 + 部分合并 | M 个新 + K 个更新 |
| 内容重复 | 已被充分覆盖 | 跳过 |

详细调用链路见 [后端 README](./backend/README.md#新内容输入的五种场景)。

## 🔌 API 概览

### 文档管理
- `POST /api/documents` — 创建文档（JSON Body）
- `POST /api/documents/upload` — 上传文件（multipart）
- `GET /api/documents` — 列出文档
- `GET /api/documents/{id}` — 获取文档
- `PUT /api/documents/{id}` — 更新文档
- `DELETE /api/documents/{id}` — 删除文档

### Wiki 管理
- `POST /api/wiki/pages` — 创建 Wiki 页面
- `GET /api/wiki/pages` — 列出 Wiki 页面
- `GET /api/wiki/pages/{id}` — 获取页面
- `PUT /api/wiki/pages/{id}` — 更新页面
- `DELETE /api/wiki/pages/{id}` — 删除页面
- `GET /api/wiki/graph` — 获取知识图谱数据

### AI 处理
- `POST /api/ai/ask` — 智能问答（自动检索 + 回答）
- `POST /api/ai/summarize` — 生成摘要
- `POST /api/ai/classify` — 自动分类
- `POST /api/ai/generate-wiki` — 生成 Wiki 页面
- `POST /api/ai/chat` — 知识库问答（手动指定文档）
- `POST /api/ai/extract-entities` — 实体提取
- `POST /api/ai/suggest-links` — 建议页面链接

### 知识摄入流水线
- `GET /api/pipeline/status` — 查看待处理文档
- `POST /api/pipeline/run` — 执行流水线（自动融合）
- `POST /api/pipeline/analyze/{doc_id}` — 预览处理策略
- `GET /api/pipeline/structure` — 知识结构优化建议

### 搜索
- `GET /api/search?q={query}` — 搜索（keyword / semantic / hybrid）
- `POST /api/search/rebuild-index` — 重建搜索索引

## 🛠️ 技术栈

**后端：** Python 3.10+ · FastAPI · httpx · Pydantic · python-frontmatter

**前端（待开发）：** React 18 · TypeScript · Vite · Tailwind CSS · react-force-graph-2d

## 📚 文档

- [后端 README](./backend/README.md) — 完整配置说明、用户指南、五种摄入场景详解、API 列表、LangChain 对比与重构方向
- [前端设计文档](./frontend/README.md) — 技术选型、页面线框图、API 对接清单、项目结构、开发优先级

## License

MIT
