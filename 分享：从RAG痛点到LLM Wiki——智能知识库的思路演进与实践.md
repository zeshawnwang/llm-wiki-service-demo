# 从 RAG 痛点到 LLM Wiki——智能知识库的思路演进与实践

> 从 RAG 的局限出发，到 Karpathy 的 llm-wiki skill 思路，再到一个可部署的 API 服务——本文完整梳理了"让 AI 帮你管理知识"这条路上的思考、选择和实现。

---

## 一、RAG 的痛点：为什么"检索增强生成"还不够？

### 1.1 RAG 的基本原理

RAG（Retrieval-Augmented Generation）是当前最主流的"AI + 知识"方案。它的核心流程是：

```
用户提问 → 从文档库中检索相关片段 → 将片段拼入 prompt → LLM 生成回答
```

这个思路很直观，也有大量成熟工具（LangChain、LlamaIndex、向量数据库等）支撑。NotebookLM、ChatGPT 文件上传、各类企业知识库产品，底层几乎都是 RAG。

### 1.2 RAG 的五个核心痛点

但在实际使用中，RAG 存在一些根本性的局限：

#### 痛点一：每次查询都是从零开始，没有知识积累

RAG 的本质是**即时检索 + 即时生成**。每次提问，LLM 都要从原始文档的碎片中重新发现和拼接答案。问同一个问题两次，LLM 做的工作完全一样。没有任何东西被"记住"或"沉淀"。

更关键的是，当你问一个需要综合五篇文档的复杂问题时，LLM 必须在单次检索中找到这五个片段，然后在一次生成中把它们拼起来。如果检索漏了任何一个片段，答案就是不完整的。**RAG 没有积累，只有每次的重新发现。**

#### 痛点二：文档切片破坏语义完整性

RAG 需要将文档切成小块（chunks）来做向量索引。但知识的语义边界和文档的物理边界往往不一致：

- 一个概念可能跨越三个段落，但切片把它拆成了三个独立片段
- 一个论证的"前提→推理→结论"可能被切到不同的 chunk 里
- 跨页的表格、图表说明、脚注补充，切片后全部断裂

检索到的碎片缺乏上下文，LLM 只能基于不完整的片段来生成回答，质量自然受限。

#### 痛点三：检索质量的天花板

RAG 的回答质量上限等于检索质量上限。如果检索不到相关片段，LLM 再强也无济于事。而检索质量受多种因素制约：

- **向量相似度不等于语义相关性**：embedding 的余弦相似度是一种粗粒度的语义近似，很多语义相关但用词不同的内容会被漏掉
- **关键词检索的局限**：对中文分词不友好，"LLM 落地"可能搜不到"大语言模型应用实践"
- **混合检索的调参难题**：关键词权重、向量权重、top-k 值、重排序阈值……每个参数都影响结果，但最优组合因场景而异

#### 痛点四：知识之间没有关联

RAG 把文档当作独立的碎片集合。碎片之间没有链接、没有引用、没有"这个概念和那个概念相关"的关系图谱。知识是孤立的，不是网络化的。

当你想理解一个领域的全貌时，RAG 只能给你零散的片段，而不是一张有结构、有层次、有关联的知识地图。

#### 痛点五：无法主动发现矛盾和缺口

RAG 是被动响应式的——你问它才答。它不会主动告诉你"你上传的两篇文章在这个观点上矛盾了"，也不会提醒"你一直在读 RAG 的内容，但还没看过 Fine-tuning 的对比"。

一个真正有用的知识库应该能主动发现知识中的矛盾、缺口和关联，而不是等你问到才检索。

#### 痛点六：LangChain 太重，简单场景被过度工程

RAG 的主流实现几乎都依赖 LangChain 或 LlamaIndex。这些框架提供了丰富的抽象——Chain、Agent、Tool、Retriever、Memory、VectorStore……但对于"文档 → 知识库 → 问答"这种场景明确、调用模式固定的系统来说，引入 LangChain 带来的问题往往比解决的问题多：

**1. 抽象层太多，调试是噩梦**

LangChain 的调用链是 `Chain → Agent → Tool → Retriever → VectorStore → LLM`，中间每一层都有自己的抽象和默认行为。当回答不符合预期时，你需要在多层抽象中定位问题：

- 是 prompt 模板的问题？还是 Chain 的默认参数问题？
- 是 Retriever 返回了错误的片段？还是 Agent 选择了错误的 Tool？
- 是 VectorStore 的 top-k 设置不对？还是 embedding 模型选错了？

每一层都可能出问题，但每一层的行为都被框架封装了。你需要理解 LangChain 的内部机制才能调试，这比直接调 API 的 `try/except` 复杂一个数量级。

**2. 依赖爆炸，项目臃肿**

一个最简单的 RAG 项目，`pip install langchain` 会拉入几十个子包：

```
langchain-core, langchain-community, langchain-text-splitters,
langchain-openai, langchain-anthropic, tiktoken, chromadb,
faiss-cpu, sentence-transformers, huggingface-hub, ...
```

这些依赖不仅增加了安装时间和磁盘占用，更带来了版本冲突的风险。LangChain 的子包之间版本依赖严格，升级一个可能破坏另一个。对于一个只需要"调 API + 读写文件"的项目来说，这些依赖完全是过度工程。

**3. 版本不稳定，breaking changes 频繁**

LangChain 的版本迭代非常快，且经常引入 breaking changes。从 0.1 到 0.2 到 0.3，每次大版本升级都有 API 变更。你的代码今天能跑，明天可能就报错了。而直接调 LLM 的 REST API，OpenAI 的 `/chat/completions` 端点已经稳定了很长时间，改一行 URL 就能适配新模型。

**4. 学习成本高，新人难以接手**

LangChain 引入了一套自己的概念体系：Chain、Agent、Tool、Retriever、Memory、OutputParser……新人需要先理解这些抽象，才能看懂代码。而直接调 API 的代码，任何会 Python 的人都能立刻理解：

```python
# 直接调 API：3 行代码，逻辑清晰
response = await client.post(url, headers=headers, json=data)
result = response.json()
return result["choices"][0]["message"]["content"]

# LangChain：需要理解 Chain、PromptTemplate、OutputParser
chain = PromptTemplate(...) | ChatOpenAI(...) | StrOutputParser()
result = chain.invoke({"input": query})
```

**5. prompt 控制不精确**

LangChain 的 PromptTemplate 有自己的变量语法（`{variable}`），还有各种默认的 system prompt 和 output parser。当你需要精确控制 prompt 的每一个字眼时，框架的模板系统反而成了阻碍。直接拼接字符串虽然"原始"，但每一行 prompt 都在你眼前，你知道 LLM 到底收到了什么。

**一句话总结：LangChain 解决的是"快速集成多种数据源、编排复杂 Agent 流程"的问题，但对于场景明确、调用模式固定的知识库系统，直接调 API 的收益远大于引入框架的成本。**

### 1.3 RAG 痛点的根源：缺少"编译"环节

如果把 RAG 比作"解释执行"——每次运行都从源码重新解释一遍，那么我们缺少的是一个"编译"环节：**把原始文档预先处理成结构化的、互相关联的、可复用的知识体系**。

这正是 llm-wiki 思路的出发点。

---

## 二、llm-wiki：Karpathy 的知识库思路

### 2.1 核心思想：从"即时检索"到"增量编译"

2025 年，Andrej Karpathy（前 OpenAI 联合创始人、前特斯拉 AI 总监）提出了一个名为 **llm-wiki** 的 skill 模式。它的核心思想可以用一句话概括：

> **不要在查询时才从原始文档中检索，而是让 LLM 增量地构建和维护一个持久的 Wiki——一个结构化的、互相关联的 Markdown 文件集合，位于你和原始来源之间。**

这个思路和 RAG 的根本区别在于：

| 维度 | RAG | llm-wiki |
|------|-----|----------|
| 知识形态 | 原始文档的碎片 | 结构化的 Wiki 页面 |
| 处理时机 | 查询时即时检索 | 摄入时增量编译 |
| 知识积累 | 无（每次从零开始） | 有（Wiki 持续增长） |
| 知识关联 | 无（碎片孤立） | 有（页面互链、交叉引用） |
| 矛盾发现 | 无（被动响应） | 有（LLM 主动标注） |
| 维护成本 | 低（无需维护） | 低（LLM 自动维护） |

### 2.2 三层架构

llm-wiki 设计了三层架构：

```
┌─────────────────────────────────────────────┐
│  Raw Sources（原始资料层）                     │
│  你收集的原始文档、文章、论文、图片              │
│  → 不可变，LLM 只读不修改                      │
│  → 知识的溯源依据                              │
└────────────────────┬────────────────────────┘
                     │ LLM 读取
┌────────────────────▼────────────────────────┐
│  The Wiki（知识层）                            │
│  LLM 生成的 Markdown 文件集合                  │
│  → 摘要页、实体页、概念页、对比页、综述页         │
│  → LLM 拥有这层，你只读                        │
│  → 持续增长、互相关联、保持一致                  │
└────────────────────┬────────────────────────┘
                     │ 你阅读
┌────────────────────▼────────────────────────┐
│  The Schema（模式层）                          │
│  告诉 LLM 如何组织 Wiki 的配置文件              │
│  → 页面命名规范、分类体系、摄入流程              │
│  → 你和 LLM 共同演化这份配置                    │
└─────────────────────────────────────────────┘
```

**关键洞察：Wiki 是一个持久的、复利的知识资产。** 交叉引用已经存在，矛盾已被标注，综合分析已反映所有读过的内容。每添加一个新来源，Wiki 就变得更丰富。

### 2.3 三种核心操作

#### Ingest（摄入）

你把新文档放入 raw 目录，告诉 LLM 处理。LLM 会：

1. 阅读文档，和你讨论关键要点
2. 写一个摘要页到 Wiki
3. 更新索引
4. 更新相关的实体页和概念页
5. 在操作日志中追加一条记录

**一篇文档可能影响 10-15 个 Wiki 页面。** 这就是"增量编译"的威力——新知识不是孤立添加的，而是融入已有的知识网络。

#### Query（查询）

你向 Wiki 提问。LLM 搜索相关页面、阅读它们、综合生成带引用的回答。关键洞察：**好的回答可以被归档回 Wiki 作为新页面。** 你做的一次对比分析、一个发现的关联——这些不应该消失在聊天历史中，而应该沉淀为 Wiki 的新页面。

#### Lint（检查）

定期让 LLM 健康检查 Wiki：页面之间的矛盾、过时的论断、孤立页面（没有入站链接）、缺失的交叉引用、可以用网络搜索填补的数据缺口。LLM 擅长建议新的研究方向和新来源。

### 2.4 索引与日志

两个特殊文件帮助导航 Wiki：

- **index.md**：内容导向的目录，按分类列出所有页面（链接 + 一行摘要 + 可选元数据）。LLM 每次摄入后更新。回答查询时，LLM 先读索引定位相关页面，再深入阅读。在中等规模（~100 来源，~数百页面）下，这种方式出奇地有效，完全不需要向量检索基础设施。
- **log.md**：时间导向的操作日志，append-only。每条记录以统一前缀开头（如 `## [2026-04-02] ingest | Article Title`），可以用简单的 unix 工具解析：`grep "^## \[" log.md | tail -5` 给你最近 5 条操作。

### 2.5 为什么这行得通

维护知识库的繁琐部分不是阅读和思考——而是簿记。更新交叉引用、保持摘要最新、标注新数据对旧论断的挑战、维护数十个页面的一致性。**人类放弃 Wiki 是因为维护负担增长得比价值快。LLM 不会厌倦，不会忘记更新交叉引用，可以一次触碰 15 个文件。Wiki 保持维护是因为维护成本接近零。**

人的工作是策划来源、引导分析、提出好问题、思考意义。LLM 的工作是其他一切。

### 2.6 llm-wiki 的 GitHub 地址

Karpathy 的 llm-wiki skill 原文：
👉 [https://github.com/karpathy/llm-wiki](https://github.com/karpathy/llm-wiki)

---

## 三、llm-wiki 与 RAG 的深度对比

### 3.1 知识表示方式

| 维度 | RAG | llm-wiki |
|------|-----|----------|
| 知识载体 | 文档切片（chunks） | 结构化 Wiki 页面 |
| 知识粒度 | 固定大小的文本块 | 按主题/实体/概念组织的完整页面 |
| 知识结构 | 扁平的碎片集合 | 有层次、有分类、有链接的网络 |
| 元数据 | 向量 embedding | 标签、分类、关联页面、版本号 |

### 3.2 知识生命周期

```
RAG 的知识生命周期：
  上传文档 → 切片 → 向量化 → 等待查询 → 检索片段 → 生成回答
  （知识始终处于"待检索"状态，没有被处理和整合）

llm-wiki 的知识生命周期：
  上传文档 → LLM 阅读 → 提取关键信息 → 创建/更新 Wiki 页面 → 建立交叉引用 → 更新索引
  （知识被"编译"成结构化形式，随时可以直接使用）
```

### 3.3 查询体验

| 维度 | RAG | llm-wiki |
|------|-----|----------|
| 简单事实查询 | ✅ 好（直接检索到相关片段） | ✅ 好（Wiki 页面已有答案） |
| 跨文档综合问题 | ⚠️ 受限（需检索到所有相关片段） | ✅ 好（Wiki 已整合多来源） |
| 探索性提问 | ❌ 差（只能返回已有片段） | ✅ 好（Wiki 的链接网络支持探索） |
| 追问和深入 | ❌ 差（每次都是独立查询） | ✅ 好（可以沿链接深入阅读） |
| 发现矛盾 | ❌ 不支持 | ✅ 好（LLM 在摄入时标注） |

### 3.4 适用场景

**RAG 更适合：**
- 一次性文档问答（上传文档 → 问几个问题 → 结束）
- 不需要知识积累的场景
- 文档量大但查询浅的场景
- 对实时性要求高的场景（新闻、实时数据）

**llm-wiki 更适合：**
- 长期知识积累（研究、学习、项目文档）
- 需要跨文档综合分析的场景
- 知识之间有关联和依赖的场景
- 想要"拥有"知识而不仅仅是"查询"知识的场景

### 3.5 成本对比

| 维度 | RAG | llm-wiki |
|------|-----|----------|
| 摄入成本 | 低（只需切片和 embedding） | 高（LLM 阅读并生成 Wiki） |
| 查询成本 | 中（每次查询需检索 + 生成） | 低（Wiki 已有结构化答案） |
| 长期成本 | 随查询次数线性增长 | 摄入后查询成本极低 |
| 总成本（高频使用） | 高 | 低 |

**一句话总结：RAG 是"即时编译"，llm-wiki 是"预编译"。如果你会反复使用同一批知识，预编译的长期成本更低。**

---

## 四、llm-wiki 与 Obsidian 的配合

### 4.1 为什么是 Obsidian

llm-wiki 生成的知识层是 Markdown 文件集合，而 Obsidian 是最好的本地 Markdown 知识库工具。两者的结合几乎是天然的：

- **双向链接**：Obsidian 的 `[[wikilinks]]` 语法和 llm-wiki 的页面互链完全一致
- **图谱视图**：Obsidian 的 Graph View 可以直观展示 Wiki 页面的关联网络
- **本地优先**：两者都是本地文件，不依赖云服务
- **可读可编辑**：LLM 生成的 Wiki 页面，人可以直接在 Obsidian 中阅读和微调
- **插件生态**：Dataview（查询 frontmatter）、Marp（生成演示文稿）、Web Clipper（快速收集网页）

### 4.2 实际工作流

Karpathy 描述的工作方式是：

> "我在一边开着 LLM agent，另一边开着 Obsidian。LLM 根据我们的对话做编辑，我实时在 Obsidian 中浏览结果——跟踪链接、查看图谱、阅读更新后的页面。**Obsidian 是 IDE，LLM 是程序员，Wiki 是代码库。**"

具体来说：

1. **摄入阶段**：你把新文章拖入 `raw/` 目录，告诉 LLM 处理。LLM 生成/更新 Wiki 页面后，你在 Obsidian 中刷新即可看到变化
2. **浏览阶段**：你在 Obsidian 中阅读 Wiki，跟踪 `[[wikilinks]]` 链接，查看 Graph View 发现新的关联
3. **探索阶段**：你向 LLM 提问，LLM 搜索 Wiki 页面生成回答。好的回答被归档为新页面，你在 Obsidian 中看到知识网络在增长
4. **维护阶段**：定期让 LLM 做 lint 检查，修复矛盾、补充交叉引用、清理孤立页面

### 4.3 Obsidian 的增强技巧

- **Web Clipper**：浏览器扩展，一键将网页转为 Markdown 存入 `raw/` 目录
- **本地图片下载**：设置 Attachment folder 为 `raw/assets/`，绑定快捷键下载图片到本地，LLM 可以直接查看
- **Dataview 插件**：如果 LLM 在 Wiki 页面的 frontmatter 中添加了 YAML 元数据（标签、日期、来源数），Dataview 可以生成动态表格
- **Marp 插件**：直接从 Wiki 内容生成演示文稿
- **Git 版本管理**：Wiki 就是 git 仓库，天然有版本历史、分支和协作能力

---

## 五、从 Agent 用法到平台化：为什么要脱离 Agent？

### 5.1 llm-wiki 的原始形态：Agent Skill

Karpathy 的 llm-wiki 是一个 **skill**——一段写给 LLM Agent（如 Claude Code、OpenAI Codex）的指令文档。你把它粘贴到 Agent 的配置文件中，Agent 就知道如何按照 llm-wiki 的模式来维护知识库。

这种用法的特点是：

- **人机对话驱动**：你和 Agent 在聊天中完成所有操作——摄入、查询、lint
- **Agent 直接操作文件**：Agent 读写本地 Markdown 文件，你就是 Obsidian 在看
- **高度灵活**：Agent 可以根据对话上下文做任何调整
- **依赖 Agent 能力**：不同 Agent 的实现质量参差不齐

### 5.2 Agent 用法的局限

但 Agent 用法在以下场景存在局限：

#### 局限一：无法被其他系统调用

Agent 是一个交互式工具，你必须在聊天界面中和它对话。其他系统（前端应用、自动化脚本、其他服务）无法调用它。如果你想让知识库通过 API 对外提供服务，Agent 做不到。

#### 局限二：过程不可解释

Agent 的操作过程是黑盒。你看到的是最终结果（Wiki 页面被创建了），但不知道：
- Agent 做了哪些 LLM 调用？
- 每次调用的 prompt 是什么？
- 为什么选择"合并"而不是"新建"？
- 哪些页面被更新了？更新了什么内容？

当结果不符合预期时，你很难定位问题。

#### 局限三：不可调优

Agent 的行为由 skill 文档和 Agent 自身的推理决定。如果你想调整某个具体行为（比如"合并时保留更多原文"、"新建页面时自动添加特定标签"），你只能修改 skill 文档然后祈祷 Agent 理解你的意图。没有参数、没有配置、没有 A/B 测试。

#### 局限四：不可扩展

Agent 的能力边界由 skill 文档定义。如果你想添加新功能（比如"自动生成 description"、"批量回填摘要"、"定时同步到 Git"），你需要修改 skill 文档并重新"教"Agent。每次修改都可能影响已有行为。

#### 局限五：不可多人协作

Agent 是单用户的。两个人无法同时和同一个 Agent 维护同一个知识库。没有并发控制、没有操作队列、没有权限管理。

### 5.3 平台化的思路

把 llm-wiki 从 Agent skill 转变为一个 **可部署的 API 服务**，可以解决以上所有问题：

| 维度 | Agent Skill | API 服务 |
|------|-------------|----------|
| 可调用性 | 仅限聊天界面 | 任何系统可通过 REST API 调用 |
| 过程可解释 | 黑盒 | 每步有日志、有中间结果、有 API 响应 |
| 可调优 | 改 skill 文档 | 改配置、改 prompt、改代码 |
| 可扩展 | 改 skill 文档 | 添加新 API 端点、新服务 |
| 多人协作 | 不支持 | API 天然支持多客户端 |
| 部署方式 | 本地 Agent | 本地/云端/容器化 |
| 前端集成 | 无 | 前端通过 API 对接 |

### 5.4 平台化的核心收益

1. **过程可解释**：每个 API 调用都有明确的输入输出，每次 LLM 调用都有日志记录，处理策略（新建/合并/跳过）有明确的判断依据
2. **可调优**：prompt 模板可以精确控制，合并策略可以配置，搜索权重可以调整——所有参数都是代码，不是自然语言指令
3. **可扩展**：新增功能就是新增 API 端点，不影响已有功能
4. **可集成**：前端、移动端、自动化脚本、其他服务——任何能发 HTTP 请求的客户端都可以使用
5. **可运维**：统一的日志、统一的错误处理、统一的配置管理、健康检查端点

**一句话总结：Agent skill 是"一个人用的工具"，API 服务是"一个团队用的平台"。当你想让知识库从个人工具升级为可共享、可集成、可运维的系统时，平台化是必然选择。**

---

## 六、LLM Wiki Service：从思路到实现

### 6.1 项目简介

**LLM Wiki Service** 是将 llm-wiki 思路从 Agent skill 转变为可部署 API 服务的实践。它保留了 llm-wiki 的核心思想——增量编译、双层存储、LLM 维护——同时通过平台化解决了 Agent 用法的局限。

```
上传文档 → AI 自动分析 → 创建/合并 Wiki 页面 → 支持 AI 问答
```

项目地址：[https://github.com/zeshawnwang/llm-wiki-service-demo](https://github.com/zeshawnwang/llm-wiki-service-demo) 🌟欢迎 Star！

### 6.2 项目架构

项目采用前后端分离架构，后端提供服务 API，前端独立开发部署：

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
│  │ 知识摄入   │  │ LLM 调用路由  │  │ 关键词+可选向量    │   │
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

### 6.3 项目目录结构

```
llm-wiki-service-demo/
├── backend/                    # 后端服务（Python / FastAPI）
│   ├── app/
│   │   ├── api/                # REST API 路由（全部 JSON Body）
│   │   │   ├── documents.py    # 文档管理 API
│   │   │   ├── wiki.py         # Wiki 管理 API
│   │   │   ├── ai.py           # AI 问答 API
│   │   │   ├── search.py       # 搜索 API
│   │   │   └── pipeline.py     # 流水线 API
│   │   ├── models/             # 数据模型（Pydantic）
│   │   │   ├── document.py     # 文档模型
│   │   │   └── wiki.py         # Wiki 模型
│   │   ├── services/           # 核心业务服务
│   │   │   ├── ai_service.py          # AI 处理（OpenAI / Claude / MiniMax / DeepSeek 路由）
│   │   │   ├── pipeline_service.py    # 知识摄入流水线（5 种场景）
│   │   │   ├── document_service.py    # 文档管理
│   │   │   ├── wiki_service.py        # Wiki 知识管理
│   │   │   ├── search_service.py      # 搜索（关键词 + 可选向量）
│   │   │   └── git_sync_service.py    # Git 定时同步
│   │   ├── tools/              # AI 工具（不依赖 LangChain）
│   │   │   ├── file_tools.py          # 文件读写操作
│   │   │   └── code_tools.py          # 代码执行
│   │   ├── utils/              # 工具模块（统一日志等）
│   │   ├── config.py           # 配置管理（唯一配置来源，读取 .env）
│   │   └── main.py             # 应用入口（含 Git 同步定时器）
│   ├── data/                   # 本地数据存储（可直接作为 Obsidian Vault 打开）
│   │   ├── raw/                # 原始资料层（AI 只读）
│   │   ├── wiki/               # Wiki 知识层（AI 读写）
│   │   │   ├── pages/          # Wiki 页面（标题_id.md，Obsidian 友好命名）
│   │   │   ├── index/          # 索引文件（index.json，API 使用）
│   │   │   ├── index.md        # Obsidian 索引页（[[wikilinks]] 格式）
│   │   │   └── log.md          # 操作时间线日志
│   │   └── vectors/            # 向量索引缓存
│   ├── .env.example            # 环境变量模板（唯一配置文件）
│   └── requirements.txt
│
├── frontend/                   # 前端应用（待开发）
│   └── README.md               # 前端设计方案（线框图 + API 对接清单）
│
└── README.md                   # 项目总文档
```

### 6.4 核心设计：双层存储

与 llm-wiki 的三层架构对应，本项目采用**双层存储架构**，所有数据以 Markdown 文件形式保存在本地磁盘：

- **raw/ 原始资料层**：用户上传的原始文档，AI 只读不修改，保留原始内容作为知识溯源
- **wiki/ 知识层**：AI 自动生成的 Wiki 页面，以 Markdown + YAML frontmatter 格式存储，包含标题、标签、分类、关联页面、版本号等元数据

Wiki 页面的 YAML frontmatter 示例：

```yaml
---
title: "RAG技术原理"
id: "abc123def456"
tags: ["RAG", "LLM", "检索增强"]
category: "AI技术"
related_pages: ["xyz789", "ghi012"]
version: 2
source_documents: ["doc_id_1", "doc_id_2"]
created_at: "2026-05-12T15:30:00"
updated_at: "2026-05-15T10:20:00"
description: "RAG（检索增强生成）的核心原理、优化手段和局限性分析"
---

# RAG技术原理

## 核心流程
...
```

这种设计的优势：

- **零数据库依赖**：无需安装 MySQL、PostgreSQL 等外部服务，拉起即用
- **可读可迁移**：Markdown 文件人人可读，可直接用 Obsidian、Typora 等工具编辑
- **天然版本管理**：Git 天然适合管理文本文件，每次修改都可追溯
- **简单可靠**：文件系统就是数据库，没有连接池、事务、迁移等问题
- **Obsidian 友好**：`data/` 目录可以直接用 Obsidian 打开作为 Vault，页面使用可读文件名（`标题_id.md`），内容使用 `[[wikilinks]]` 格式互相链接，图谱视图可直接展示页面关系

### 6.5 核心流程：知识摄入流水线

当新文档进入系统时，触发以下完整链路：

```
用户上传文档 → Document Service 存储到 raw/
       ↓
Pipeline 触发 → 读取 raw/ 中未处理的文档
       ↓
AI Service 分析文档主题 → 与已有 Wiki 知识库比对
       ↓
五种处理策略之一：
  ├─ create_new    → 生成新 Wiki 页面 → 写入 wiki/pages/
  ├─ create_multi  → 拆分多主题 → 生成多个新 Wiki + 互相关链
  ├─ merge_into    → 读取已有 Wiki → AI 合并内容 → 版本升级 v1→v2
  ├─ split_merge   → 部分新建 + 部分合并 → 混合处理
  └─ skip          → 内容重复 → 标记跳过
       ↓
重建搜索索引 → 更新知识图谱 → 完成
```

#### 场景一：单主题全新内容

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

#### 场景二：多主题全新内容

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

#### 场景三：单主题内容合并到已有Wiki

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

#### 场景四：混合策略（部分新建 + 部分合并）

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

#### 场景五：内容已被覆盖（跳过）

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
    → _mark_document_processed("skipped")  # 直接跳过，节省AI调用费用
```

#### 场景汇总

| 场景 | 主题数 | 产出 | merge_type | 适用情况 |
|------|--------|------|-----------|---------|
| 一 | 1 | 1个新Wiki | `new` | 单主题，知识库中无相关内容 |
| 二 | N | N个新Wiki + 互链 | `new_multi` | 多主题，全部是全新的 |
| 三 | 1 | 更新1个已有Wiki | `update` | 单主题，与已有Wiki相关 |
| 四 | N | M个新 + K个更新 | `split` | 多主题，部分新建部分合并 |
| 五 | 1 | 0（跳过） | — | 内容已被充分覆盖 |

### 6.6 问答流程

```
用户提问 → AI Service 接收问题
       ↓
QA Retrieval 模块判断检索策略：
  ├─ ai 模式    → AI 直接浏览 Wiki 目录，自主选择相关页面
  └─ auto 模式  → 页面少时全量给 AI，多时先关键词预筛再 AI 精选
       ↓
AI 阅读选中的 Wiki 页面 → 生成回答
       ↓
返回答案 + 引用来源（附带 Wiki 页面标题和链接）
```

两种检索模式的设计思路：

- **ai 模式**：AI 直接看到完整的 Wiki 目录（index.md），自主决定读取哪些页面。适合 Wiki 规模较小（<200 页）的场景，AI 的判断比关键词检索更准确
- **auto 模式**：当 Wiki 页面数量超过阈值（默认 200）时，先用关键词搜索预筛相关页面，再把预筛结果交给 AI 精选。兼顾了大规模知识库的检索效率

问答返回示例：

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

### 6.7 设计原则

1. **本地优先**：所有数据存为 `.md` 文件，不依赖外部数据库，`git` 天然可做版本管理
2. **AI 增量融合**：新文档自动判断与已有知识的关系，不做全量重建
3. **配置驱动**：所有开关在 `.env` 中，向量搜索可关闭以节省成本，Git 同步可配置
4. **前后端分离**：后端纯 API + 前端独立项目，可独立部署和扩容
5. **AI 辅助而非 AI 替代**：所有处理结果都可以在 API 层面预览、人工确认后再执行

### 6.8 多 LLM 供应商支持

系统支持四个 LLM 供应商，一行环境变量即可切换：

```bash
LLM_PROVIDER=openai     # 使用 GPT 系列
LLM_PROVIDER=anthropic  # 使用 Claude 系列
LLM_PROVIDER=minimax    # 使用 MiniMax M2 系列
LLM_PROVIDER=deepseek   # 使用 DeepSeek 系列
```

所有 LLM 调用都通过 `call_llm()` 一个入口，各供应商的差异封装在各自的 `_call_*` 方法中。新增供应商只需要添加一个配置段 + 一个方法，对上层业务代码零侵入。

### 6.9 中文搜索优化

重写了关键词评分算法，支持**字符级中文匹配** + **英文单词匹配**双模式：

```python
# 完整查询匹配（标题命中权重最高）
query_lower in title_lower → +15分

# 中文单字符匹配（适合中文模糊查询）
每个字符命中标题 → +0.5分
每个字符命中标签 → +0.3分
每个字符命中内容 → +0.2分

# 英文单词匹配
query_terms = query_lower.split()
每个单词命中标题 → +10分
```

配合可选的向量语义搜索（通过 LLM 的 embedding API），系统提供 keyword / semantic / hybrid 三种搜索模式。

### 6.10 零 LangChain 依赖

本项目**零 LangChain 依赖**，直接通过 `httpx` 调用 LLM 的 REST API：

| 对比维度 | 直接调用 API | 使用 LangChain |
|---------|-------------|---------------|
| 代码透明 | 每一行都可见，prompt 可精确控制 | 框架抽象层多，调试需理解内部机制 |
| 依赖体积 | 仅 httpx | LangChain + 几十个子包 |
| 学习成本 | 新人可立刻上手 | 需要学习 Chain/Agent/Tool 等概念 |
| 版本稳定性 | API 变化改一行 URL | 受框架 breaking changes 影响 |

### 6.11 统一日志

所有模块使用相同格式，每个 LLM 调用都有"开始 → 成功/失败"的三段式日志：

```
2026-05-12 15:27:04 - app.services.ai_service - INFO - [OpenAI] 开始调用 - 模型: gpt-4o-mini, temperature: 0.7
2026-05-12 15:27:06 - app.services.ai_service - INFO - [OpenAI] 调用成功 - 模型: gpt-4o-mini
```

### 6.12 技术栈

- **后端**：Python 3.10+ · FastAPI · httpx · Pydantic · python-frontmatter
- **前端（待开发）**：React 18 · TypeScript · Vite · Tailwind CSS · react-force-graph-2d
- **LLM 供应商**：OpenAI (GPT-4o) / Anthropic (Claude) / MiniMax (M2) / DeepSeek
- **搜索**：关键词 + 向量语义（通过 LLM embedding API，零额外依赖）

### 6.13 快速上手

```bash
git clone https://github.com/zeshawnwang/llm-wiki-service-demo.git
cd llm-wiki-service-demo/backend

pip install -r requirements.txt
cp .env.example .env
# 编辑 .env，配置你的 LLM API Key

uvicorn app.main:app --reload
# 访问 http://localhost:8000/docs 查看 Swagger API 文档
```

然后你就可以：
1. `POST /api/documents` 上传文档
2. `POST /api/pipeline/run` 让 AI 自动归纳
3. `POST /api/ai/ask` 向知识库提问

### 6.14 API 概览

| 类别 | API | 说明 |
|------|-----|------|
| 文档管理 | `POST /api/documents` | 创建文档 |
| | `POST /api/documents/upload` | 上传文件 |
| | `GET /api/documents` | 列出文档 |
| Wiki管理 | `POST /api/wiki/pages` | 创建Wiki页面 |
| | `GET /api/wiki/pages` | 列出Wiki页面 |
| | `GET /api/wiki/graph` | 获取知识图谱 |
| | `POST /api/wiki/backfill-descriptions` | 批量生成页面描述 |
| AI处理 | `POST /api/ai/ask` | 智能问答 |
| | `POST /api/ai/summarize` | 生成摘要 |
| | `POST /api/ai/classify` | 自动分类 |
| 流水线 | `POST /api/pipeline/run` | 执行知识摄入 |
| | `POST /api/pipeline/analyze/{id}` | 预览处理策略 |
| 搜索 | `GET /api/search?q={query}` | 搜索（keyword/semantic/hybrid） |

---

## 七、三方对比：RAG vs llm-wiki Agent vs LLM Wiki Service

### 7.1 综合对比表

| 维度 | RAG | llm-wiki (Agent Skill) | LLM Wiki Service (本项目) |
|------|-----|------------------------|--------------------------|
| **知识形态** | 文档切片 | 结构化 Wiki 页面 | 结构化 Wiki 页面 |
| **知识积累** | 无 | 有（增量编译） | 有（增量编译） |
| **知识关联** | 无 | 有（wikilinks） | 有（wikilinks + 知识图谱 API） |
| **矛盾发现** | 不支持 | 支持（LLM lint） | 支持（AI 分析 + API 可查） |
| **使用方式** | API 调用 | 与 Agent 聊天 | REST API |
| **可集成性** | 高（标准 API） | 低（依赖特定 Agent） | 高（标准 REST API） |
| **过程可解释** | 中（检索结果可见） | 低（Agent 黑盒） | 高（日志 + API 响应 + 处理报告） |
| **可调优** | 中（检索参数） | 低（改 skill 文档） | 高（改代码、改配置、改 prompt） |
| **可扩展** | 高（丰富生态） | 低（受 Agent 能力限制） | 高（添加新 API 端点） |
| **多人协作** | 支持 | 不支持 | 支持（API 天然多客户端） |
| **部署方式** | 需向量数据库 | 本地 Agent | 本地/云端/容器化 |
| **数据库依赖** | 需要向量库 | 无 | 无（文件系统） |
| **Obsidian 集成** | 无 | 天然集成 | 天然集成（data/ 目录即 Vault） |
| **成本模型** | 按查询付费 | 按 Agent 会话付费 | 按 LLM 调用付费（摄入时集中，查询时极少） |
| **适合规模** | 大规模文档库 | 个人知识库（~100 来源） | 个人到小团队知识库 |
| **学习曲线** | 中（需理解 RAG 流程） | 低（和 Agent 聊天即可） | 中（需部署后端服务） |

### 7.2 选择建议

**选 RAG，如果你：**
- 有大量文档需要即时问答（>1000 篇）
- 不需要知识积累和关联
- 已有向量数据库基础设施
- 对实时性要求高

**选 llm-wiki Agent，如果你：**
- 是个人用户，知识库规模适中（<100 来源）
- 日常使用 Claude Code / Codex 等 Agent
- 喜欢在聊天中完成所有操作
- 不需要 API 集成或多人协作

**选 LLM Wiki Service，如果你：**
- 想要 llm-wiki 的核心思想但需要 API 化
- 需要前端集成或多人协作
- 需要过程可解释和可调优
- 想要 Obsidian 集成 + REST API 的组合
- 希望知识库可以部署为服务而非本地工具

### 7.3 演进路径

三种方案不是互斥的，而是可以演进的：

```
个人探索阶段：
  llm-wiki Agent Skill → 快速验证思路，和 Agent 聊天中构建知识库

↓ 当你需要 API 化、可集成、可调优时

平台化阶段：
  LLM Wiki Service → 部署为 API 服务，前端/脚本/其他系统可调用

↓ 当知识库规模增长到需要更强检索时

混合阶段：
  LLM Wiki Service + RAG → Wiki 页面作为高质量语料，RAG 提供大规模检索能力
  （Wiki 是"编译后的知识"，RAG 是"原始文档的索引"，两者互补）
```

---

## 八、一些思考

### 8.1 什么时候该选"轻量方案"

做这个项目的过程中，我反复问自己一个问题：**"真的需要 LangChain 吗？"**

答案是否定的。LangChain 的价值在于快速集成多种数据源、编排复杂 Agent 流程、切换不同 LLM 供应商。但如果你像我一样：
- 场景明确（文档 → 知识库 → 问答）
- 调用模式固定（prompt 结构简单、工具数量少）
- 需要精细控制每一个 prompt 字眼
- 希望代码完全透明、可调试

那么直接调用 API 是更好的选择。**选择"够用的简单方案"而不是"强大的复杂方案"，是我在这次开发中最大的收获。**

### 8.2 AI 的能力边界

在实际测试中，AI 对"新建 vs 合并"的判断准确率令人惊喜——即使是一篇长度适中、主题混合的文档，AI 也能准确识别哪些部分是已有知识的补充、哪些是全新主题。但在以下场景需要人工复核：
- 文档内容过于简短（AI 可能过度判断"新主题"）
- 涉及非常专业的领域术语（AI 可能以为不同术语指向同一概念）
- 知识库中已有大量相似页面（AI 可能选择跳过但实际有差异）

因此，系统设计为**AI 辅助而非 AI 替代**——所有处理结果都可以在 API 层面预览、人工确认后再执行。

### 8.3 从 Memex 到 llm-wiki 到平台

llm-wiki 的思路和 Vannevar Bush 1945 年提出的 Memex 一脉相承——一个个人的、精心策划的知识存储，文档之间的关联和文档本身一样有价值。Bush 无法解决的是"谁来做维护"。LLM 解决了这个问题。

而从 llm-wiki Agent 到 LLM Wiki Service，则是从"个人工具"到"共享平台"的演进。核心思想不变——增量编译、LLM 维护、Markdown 存储——但实现方式从"和 Agent 聊天"变成了"调 API"，从"一个人用"变成了"一个团队用"。

---

## 九、未来迭代方向

### 9.1 前端实现

目前后端 API 已完整可用（可通过 Swagger 文档直接调试），但缺乏直观的图形界面。后续计划使用 React + TypeScript + Vite + Tailwind CSS 构建前端：

- **知识库浏览**：文件树 + Markdown 渲染，支持双向链接跳转
- **知识图谱可视化**：基于 react-force-graph-2d 的力导向图
- **导入页面**：拖拽上传文档、运行流水线、查看处理结果
- **问答页面**：Chat 式交互，附带引用来源展示

### 9.2 云端存储方案

当前所有 Wiki 页面以 Markdown 文件形式存储在本地磁盘。后续计划引入对象存储（S3/MinIO）或轻量级数据库（SQLite/PostgreSQL），将 Wiki 源文件从本地磁盘解耦，支持多实例部署和团队协作。

### 9.3 热点文件本地化缓存

当 Wiki 数据量增长到成百上千篇且存储迁移到远端后，计划实现热点文件本地化缓存策略：冷热分离、本地 LRU 缓存、缓存一致性、预加载，参考 CDN 缓存思路保持毫秒级访问体验。

---

## 十、总结

本文从 RAG 的痛点出发，介绍了 Karpathy 的 llm-wiki 思路，分析了它与 RAG 的本质区别，展示了 llm-wiki 与 Obsidian 的配合方式，论述了从 Agent skill 到 API 服务的平台化演进理由，最后介绍了 LLM Wiki Service 的实现细节。

核心观点：

1. **RAG 是"即时编译"，llm-wiki 是"预编译"**——如果你会反复使用同一批知识，预编译的长期成本更低
2. **知识库的价值在于关联，不在于碎片**——结构化的 Wiki 页面比文档切片更有用
3. **LLM 让知识库维护成本趋近于零**——人类放弃 Wiki 是因为维护负担，LLM 解决了这个问题
4. **从 Agent 到 API 是从工具到平台的演进**——当你需要可集成、可解释、可调优时，平台化是必然选择

如果你对这个项目感兴趣，欢迎来 GitHub 逛逛：

👉 [https://github.com/zeshawnwang/llm-wiki-service-demo](https://github.com/zeshawnwang/llm-wiki-service-demo)

觉得有帮助的话，点个 ⭐ 就是对我最大的鼓励！如果有任何问题或建议，欢迎提 Issue 或 PR，一起交流成长 🚀