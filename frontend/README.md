# LLM Wiki 前端设计方案

> 本文档为后续前端开发的参考方案，待实施。

## 一、技术选型

| 类别 | 选型 | 说明 |
|------|------|------|
| 框架 | React 18 + TypeScript | 生态丰富，组件库多 |
| 构建 | Vite | 快速开发，HMR |
| 路由 | React Router v6 | SPA路由 |
| 状态管理 | Zustand | 轻量，适合中小项目 |
| 样式 | Tailwind CSS | 快速开发，不用写CSS文件 |
| Markdown渲染 | react-markdown + remark-gfm + rehype-highlight | 支持GFM和代码高亮 |
| Markdown编辑 | Milkdown 或 @uiw/react-md-editor | 所见即所得 |
| 文件树 | react-arborist 或自写 | 展示Wiki页面层级 |
| 图谱 | react-force-graph-2d | 力导向图，支持拖拽缩放 |
| HTTP客户端 | ky 或 fetch封装 | 轻量HTTP客户端 |
| 包管理 | pnpm | 快速、省空间 |

## 二、页面结构

```
┌─────────────────────────────────────────────────────────┐
│  Logo   LLM Wiki                                       │
├────────┬────────────────────────────────────────────────┤
│        │                                                │
│  首页   │  (各菜单对应的右侧内容区)                       │
│        │                                                │
│  知识库  │                                                │
│        │                                                │
│  导入   │                                                │
│        │                                                │
│  问答   │                                                │
│        │                                                │
│  设置   │                                                │
│        │                                                │
└────────┴────────────────────────────────────────────────┘
```

## 三、各页面详细设计

### 3.1 首页

```
┌─────────────────────────────────────────────────────────┐
│  首页                                                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │ Wiki页面  │  │ 原始文档  │  │ 未处理    │               │
│  │   42      │  │   128     │  │    7      │               │
│  └──────────┘  └──────────┘  └──────────┘               │
│                                                         │
│  最近活动                                                │
│  ┌─────────────────────────────────────────────────┐    │
│  │ 15:30  新建Wiki: RAG技术原理                       │    │
│  │ 15:28  合并Wiki: RAG技术综述 v1→v2                │    │
│  │ 15:25  上传文档: rag-optimization.md              │    │
│  │ 14:50  新建Wiki: Prompt工程指南                    │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  快速操作                                                │
│  [ 导入文档 ]  [ 运行归纳 ]  [ 提问 ]                    │
│                                                         │
└─────────────────────────────────────────────────────────┘

调用API:
  - GET /api/wiki/stats/statistics → Wiki统计
  - GET /api/documents/stats/statistics → 文档统计
  - GET /api/pipeline/status → 未处理文档数
```

### 3.2 知识库（核心页面）

支持两种视图切换：**列表视图** 和 **图谱视图**。

#### 列表视图（默认）

```
┌──────────┬──────────────────────────────────────────────┐
│ 文件树    │  # RAG技术原理                    [编辑] [删除] │
│          │                                              │
│ ▼ 全部    │  ## 核心概念                                 │
│ ▼ AI技术   │  RAG是检索增强生成...                        │
│   ├ RAG   │                                              │
│   │ ├ 原理 │  ## 相关主题                                 │
│   │ └ 优化 │  - [[Prompt工程]] ← 可点击跳转               │
│   └ 向量DB │  - [[向量数据库选型]]                        │
│ ▼ AI工程   │                                              │
│   ├ Prompt│  ──────────────────────                      │
│   └ 微调  │  来源文档: rag-article.md, rag-intro.md      │
│          │  版本: v2 | 更新于: 2026-05-12 15:30           │
│          │                                              │
│ [搜索Wiki]│  标签: RAG, LLM, 检索增强                      │
│          │  分类: AI技术                                  │
└──────────┴──────────────────────────────────────────────┘

调用API:
  - GET /api/wiki/pages → 文件树数据
  - GET /api/wiki/pages/{id} → 页面内容
  - GET /api/wiki/pages/{id}/related → 相关页面
  - PUT /api/wiki/pages/{id} → 编辑保存
```

#### 图谱视图

```
┌─────────────────────────────────────────────────────────┐
│  知识库图谱                    [列表] [图谱]    [搜索]     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│              ┌─────────┐                                │
│              │  RAG    │                                │
│              └────┬────┘                                │
│           ┌───────┼───────┐                             │
│           ▼       ▼       ▼                             │
│     ┌─────────┐ ┌──────┐ ┌──────────┐                   │
│     │向量DB   │ │Prompt│ │ Embedding │                   │
│     └────┬────┘ └──┬───┘ └──────────┘                   │
│          ▼        ▼                                      │
│     ┌─────────┐ ┌──────┐                                │
│     │ Milvus │ │微调  │                                │
│     └─────────┘ └──────┘                                │
│                                                         │
│  节点大小 = 被引用次数                                    │
│  节点颜色 = 按 category 区分                              │
│  连线粗细 = 关联类型                                     │
│                                                         │
│  点击节点 → 右侧弹出该Wiki页面内容                         │
│  拖拽节点 → 手动调整布局                                  │
│  滚轮 → 缩放                                             │
└─────────────────────────────────────────────────────────┘

调用API:
  - GET /api/wiki/graph → 图谱数据（nodes + edges）
  - GET /api/wiki/pages/{id} → 点击节点后加载内容
```

### 3.3 导入

```
┌─────────────────────────────────────────────────────────┐
│  导入                                                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ① 上传文档                                              │
│  ┌─────────────────────────────────────────────────┐    │
│  │  拖拽文件到此处，或点击上传                         │    │
│  │  支持 .md / .txt 文件                              │    │
│  │                                                  │    │
│  │  或直接粘贴文本内容：                               │    │
│  │  ┌──────────────────────────────────────────┐    │    │
│  │  │ (Markdown编辑器)                          │    │    │
│  │  │ # 文章标题                                │    │    │
│  │  │ 文章内容...                               │    │    │
│  │  └──────────────────────────────────────────┘    │    │
│  │                                                  │    │
│  │  标题: [________]  分类: [________]               │    │
│  │  标签: [tag1] [tag2] [+]                         │    │
│  │                                                  │    │
│  │  [ 上传 ]                                        │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ② 运行归纳                                              │
│  ┌─────────────────────────────────────────────────┐    │
│  │  待处理文档: 7 篇                                  │    │
│  │                                                  │    │
│  │  ☐ rag-optimization.md                           │    │
│  │  ☐ prompt-guide.pdf                              │    │
│  │  ☐ agent-design.md                               │    │
│  │  ...                                             │    │
│  │                                                  │    │
│  │  [ 运行归纳 ]                                     │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ③ 处理结果                                              │
│  ┌─────────────────────────────────────────────────┐    │
│  │  ✅ rag-optimization.md → 合并到 RAG技术综述 v2    │    │
│  │  ✅ prompt-guide.pdf → 新建 Prompt工程指南         │    │
│  │  ✅ agent-design.md → 新建 Agent设计 + 微调        │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
└─────────────────────────────────────────────────────────┘

调用API:
  - POST /api/documents → 提交文本
  - POST /api/documents/upload → 上传文件
  - GET /api/pipeline/status → 待处理文档列表
  - POST /api/pipeline/run → 运行归纳
  - POST /api/pipeline/analyze/{doc_id} → 预览处理策略
```

### 3.4 问答

```
┌─────────────────────────────────────────────────────────┐
│  问答                                                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  输入你的问题...                        [发送]   │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  👤 RAG有哪些优化手段？                            │    │
│  │                                                  │    │
│  │  🤖 RAG的主要优化手段包括：                       │    │
│  │                                                  │    │
│  │  1. 混合检索 — 结合关键词和语义搜索               │    │
│  │     参考：[RAG技术原理]                           │    │
│  │  2. 查询改写 — 优化用户的原始查询                 │    │
│  │     参考：[RAG优化实践]                           │    │
│  │  3. 重排序 — 对检索结果进行二次排序               │    │
│  │     参考：[RAG技术原理]                           │    │
│  │                                                  │    │
│  │  ─── 引用来源 ───                                 │    │
│  │  📄 RAG技术原理 (Wiki)                            │    │
│  │  📄 RAG优化实践 (Wiki)                            │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  历史问答（可选）                                        │
│  ┌─────────────────────────────────────────────────┐    │
│  │  Q: 什么是向量数据库？                             │    │
│  │  A: 向量数据库是专门存储和检索高维向量的...          │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
└─────────────────────────────────────────────────────────┘

调用API:
  - POST /api/ai/ask → 提问并获取回答
```

### 3.5 设置

```
┌─────────────────────────────────────────────────────────┐
│  设置                                                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  LLM 供应商                                              │
│  ○ OpenAI    API Key: [sk-xxx]    模型: [gpt-4o-mini]   │
│  ○ Anthropic API Key: [sk-ant]    模型: [claude-sonnet]  │
│                                                         │
│  向量搜索    [ 开启 / 关闭 ]                               │
│                                                         │
│  Git 同步                                                │
│  [ 开启 ]  间隔: [30] 分钟                                │
│  远程地址: [https://github.com/xxx/wiki-data.git]        │
│  分支: [main]                                           │
│                                                         │
│  [ 保存设置 ]                                            │
│                                                         │
└─────────────────────────────────────────────────────────┘

调用API:
  - GET /api/config → 获取当前配置（需新增后端端点）
  - PUT /api/config → 更新配置（需新增后端端点）
```

## 四、API对接清单

所有POST端点已统一为 JSON Body（`Content-Type: application/json`），
仅 `POST /api/documents/upload` 保留 `multipart/form-data`（因为需要接收文件）。

### 文档管理

| 方法 | 路径 | Request Body | Response |
|------|------|-------------|----------|
| POST | /api/documents | `{"filename", "content", "title?", "doc_type?", "category?", "tags?[]}` | Document |
| POST | /api/documents/upload | multipart/form-data (file) | Document |
| GET | /api/documents | Query: `doc_type?, category?, tag?` | Document[] |
| GET | /api/documents/{id} | - | Document |
| PUT | /api/documents/{id} | `{"content?", "title?", "category?", "tags?[]}` | Document |
| DELETE | /api/documents/{id} | - | {message} |
| GET | /api/documents/stats/statistics | - | 统计JSON |

### Wiki管理

| 方法 | 路径 | Request Body | Response |
|------|------|-------------|----------|
| POST | /api/wiki/pages | `{"title", "content?", "slug?", "category?", "tags?[]", "status?"}` | WikiPage |
| GET | /api/wiki/pages | Query: `status?, category?, tag?` | WikiPage[] |
| GET | /api/wiki/pages/{id} | - | WikiPage |
| GET | /api/wiki/pages/slug/{slug} | - | WikiPage |
| PUT | /api/wiki/pages/{id} | `{"title?", "content?", "category?", "tags?[]", "status?"}` | WikiPage |
| DELETE | /api/wiki/pages/{id} | - | {message} |
| GET | /api/wiki/index | - | 索引JSON |
| GET | /api/wiki/pages/{id}/related | - | WikiPage[] |
| POST | /api/wiki/pages/{id}/related/{related_id} | - | {message} |
| GET | /api/wiki/stats/statistics | - | 统计JSON |
| GET | /api/wiki/graph | - | {nodes[], edges[]} |

### AI处理

| 方法 | 路径 | Request Body | Response |
|------|------|-------------|----------|
| POST | /api/ai/ask | `{"query", "top_k?", "retrieval?"}` | {answer, sources[]} |
| POST | /api/ai/summarize | `{"doc_id?", "content?", "max_length?"}` | {summary} |
| POST | /api/ai/classify | `{"doc_id?", "content?"}` | 分类JSON |
| POST | /api/ai/generate-wiki | `{"doc_id", "title?", "related_docs?[]"}` | {title, content} |
| POST | /api/ai/chat | `{"query", "doc_ids?[]", "page_ids?[]"}` | {answer} |
| POST | /api/ai/extract-entities | `{"doc_id?", "content?"}` | {entities[]} |
| POST | /api/ai/suggest-links | Query: `page_id` | {suggestions[]} |
| POST | /api/ai/process | `{"message", "history?[]}` | 处理结果JSON |

### 流水线

| 方法 | 路径 | Request Body | Response |
|------|------|-------------|----------|
| GET | /api/pipeline/status | - | 状态JSON |
| POST | /api/pipeline/run | `{"doc_ids?[]", "auto_rebuild?"}` | 执行报告JSON |
| POST | /api/pipeline/analyze/{doc_id} | - | {analysis} |
| GET | /api/pipeline/structure | - | 结构建议JSON |

### 搜索

| 方法 | 路径 | Request Body | Response |
|------|------|-------------|----------|
| GET | /api/search | Query: `q, search_type?, limit?, doc_type?` | {results[]} |
| GET | /api/search/recommendations/{type}/{id} | Query: `limit?` | 推荐JSON |
| POST | /api/search/rebuild-index | - | {message, stats} |

## 五、项目结构

```
frontend/
├── public/
├── src/
│   ├── main.tsx                  # 入口
│   ├── App.tsx                   # 路由配置
│   ├── api/                      # API调用封装
│   │   ├── client.ts             # HTTP客户端（ky/fetch封装）
│   │   ├── documents.ts          # 文档API
│   │   ├── wiki.ts               # Wiki API
│   │   ├── ai.ts                 # AI API
│   │   ├── pipeline.ts           # 流水线API
│   │   └── search.ts             # 搜索API
│   ├── components/               # 通用组件
│   │   ├── Layout.tsx            # 整体布局（侧边栏+内容区）
│   │   ├── Sidebar.tsx           # 侧边栏菜单
│   │   ├── MarkdownViewer.tsx    # Markdown渲染
│   │   ├── MarkdownEditor.tsx    # Markdown编辑器
│   │   ├── FileTree.tsx          # 文件树
│   │   ├── GraphView.tsx         # 知识图谱
│   │   ├── SearchBar.tsx         # 搜索框
│   │   └── TagInput.tsx          # 标签输入
│   ├── pages/                    # 页面
│   │   ├── Home.tsx              # 首页
│   │   ├── Wiki.tsx              # 知识库（列表+图谱切换）
│   │   ├── Import.tsx            # 导入
│   │   ├── Ask.tsx               # 问答
│   │   └── Settings.tsx          # 设置
│   ├── stores/                   # 状态管理
│   │   ├── wikiStore.ts
│   │   └── uiStore.ts
│   ├── types/                    # TypeScript类型
│   │   └── api.ts                # API响应类型
│   └── styles/
│       └── globals.css
├── package.json
├── tsconfig.json
├── vite.config.ts
└── tailwind.config.js
```

## 六、开发优先级

1. **P0 - 基础框架**：Layout + 路由 + API客户端封装
2. **P0 - 知识库列表视图**：文件树 + Markdown渲染 + 双向链接
3. **P1 - 导入页面**：上传文档 + 运行pipeline + 查看结果
4. **P1 - 问答页面**：输入问题 + 显示回答 + 引用来源
5. **P2 - 首页**：统计面板 + 最近活动
6. **P2 - 知识库图谱视图**：力导向图 + 节点交互
7. **P3 - 设置页面**：配置管理
8. **P3 - Markdown编辑**：所见即所得编辑Wiki页面
