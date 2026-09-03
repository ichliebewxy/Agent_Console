# 二狗子助手 · Pi 工作台

一个运行在本机的中文 Web Agent。你在网页中选定工作区、提出任务，Pi SDK 负责模型会话、工具调用和插件执行，生成的文件直接保存在所选目录。项目还提供可选的本地文档知识库，适合一边处理项目文件，一边查询自己的资料。

**记忆统一由 `pi-memory` 插件管理。`backend/` 只负责知识库的文档解析、入库和检索，不运行第二套聊天 Agent 或记忆系统。**

## 目录

- [1. 功能与运行方式](#1-功能与运行方式)
- [2. 安装与首次启动](#2-安装与首次启动)
- [3. 网页使用流程](#3-网页使用流程)
- [4. Pi 记忆和插件](#4-pi-记忆和插件)
- [5. 项目架构与执行过程](#5-项目架构与执行过程)
- [6. 目录与源码阅读顺序](#6-目录与源码阅读顺序)
- [7. 数据保存与备份](#7-数据保存与备份)
- [8. 接口与运行命令](#8-接口与运行命令)
- [9. 测试和故障排查](#9-测试和故障排查)
- [10. 当前边界与扩展方式](#10-当前边界与扩展方式)

## 1. 功能与运行方式

| 能力 | 实现 | 是否需要 Python / Milvus |
| --- | --- | --- |
| 读取、修改项目文件，运行命令 | Pi 内置 `read/write/edit/bash` 等工具 | 否 |
| 对话流式输出、停止任务、人机确认 | Node SSE + Pi 扩展 UI 适配 | 否 |
| 文件交付和下载 | 工作区真实文件 + `deliver_files` | 否 |
| 会话历史 | 宿主的 JSON 会话存储 | 否 |
| 长期记忆、日记、待办 | `pi-memory` 插件 | 否 |
| 网页资料、子 Agent、代码诊断、上下文管理 | Pi 社区插件 | 否；部分插件有自己的外部依赖 |
| 图片问答 | 主模型或 `@getpipher/vision` 适配 | 否；需要可用的视觉模型 |
| 上传资料、文档问答和来源查看 | Python 知识库 + Milvus | 是 |
| 创建、上传和加载 Skill | 宿主 Skill 服务 + Pi 资源加载器 | 否 |

有两种启动方式：

- **只使用 Agent**：启动 Node 即可。文件操作、Pi 记忆、Skills 和插件不依赖知识库侧车。
- **使用完整知识库**：额外启动 Python 服务和 Docker 中的 Milvus 组件。只有检索和文档管理需要这部分。

## 2. 安装与首次启动

以下 PowerShell 命令均在项目根目录执行。不要从 `backend/` 或任务工作区内启动宿主：Node 使用启动目录定位前端、配置和 `tmp/`。

### 2.1 环境准备

| 环境 | 用途 |
| --- | --- |
| Node.js 22.19+，可使用 24 LTS | 运行 TypeScript 宿主、Pi SDK 和插件 |
| npm | 根据 `package-lock.json` 安装 Node 依赖 |
| Git for Windows | 提供 Git 和 Pi 内置命令工具使用的 Git Bash |
| 可用的模型 API 密钥 | 主模型对话与工具调用 |
| Python 3.12+、uv（知识库模式） | 安装和运行 Python 侧车；当前本机环境使用 Python 3.12 |
| Docker Desktop + Compose（知识库模式） | 运行 Milvus、etcd、MinIO，Attu 用于可视化管理 |

先确认安装的程序可在终端中找到：

```powershell
node --version
npm --version
git --version
# 使用知识库时再检查下面三项
uv --version
python --version
docker compose version
```

BGE 模型和 Python 向量计算依赖占用较多磁盘及内存。初次使用知识库需要下载模型；下载完成后可以从本地缓存加载。

### 2.2 配置模型

```powershell
# 仅在文件不存在时复制，保留已有密钥和配置。
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

编辑根目录 `.env`：

```dotenv
CHAT_API_KEY=填写你的模型服务密钥
CHAT_MODEL=deepseek-chat
EMBEDDING_LOCAL_FILES_ONLY=false
```

`CHAT_MODEL` 必须填写账户实际可用且支持工具调用的模型 ID。宿主的默认接口为 `https://api.deepseek.com`，可用 `CHAT_BASE_URL` 覆盖。Node 通过 OpenAI 兼容协议访问模型；Python 的相关性评估和查询扩展使用 DeepSeek 适配器，其他供应商的兼容性需要单独验证。

知识库还有 `GRADE_MODEL`（默认 `deepseek-v4-flash`）和 `QUERY_EXPANSION_MODEL`（默认跟随 Python 的 `CHAT_MODEL`）。如果账户没有默认评估模型，请在 `.env` 中显式设置 `GRADE_MODEL`。配置清单及默认值见 [配置说明](docs/configuration.md)。

### 2.3 只启动 Agent

```powershell
npm ci --ignore-scripts
npm start
```

打开 [http://127.0.0.1:3000](http://127.0.0.1:3000)。不需要先运行 Python、下载 BGE 或启动 Docker。

`--ignore-scripts` 跳过依赖的安装生命周期脚本；宿主直接加载已安装的 Pi 包资源。需要 qmd 等可选工具时另行安装，见下文记忆说明。

### 2.4 启动完整知识库

在已安装 Node 依赖并配置 `.env` 的基础上：

```powershell
uv sync --locked
# 先打开 Docker Desktop，等待 Docker 引擎就绪。
docker compose up -d
docker compose ps
# 首次可单独下载并验证嵌入模型。
uv run python -m backend.preload_embedding_model
# 同时启动 Node 和 Python。
npm run dev
```

不要与已经运行的 `npm start` 占用同一个端口。先在原终端按 `Ctrl+C`，再运行 `npm run dev`。

`npm run dev` 同时启动两个进程：Node 使用 `tsx watch`，Python 使用 Uvicorn。**当前 Python 命令没有 `--reload`**，修改 Python 代码后需要重启。关闭这组开发进程可按 `Ctrl+C`。

模型下载完成后，可在 `.env` 中设置 `EMBEDDING_LOCAL_FILES_ONLY=true`，以后启动只从本地缓存加载。不要在首次下载前开启这一选项。

### 2.5 确认服务状态

```powershell
Invoke-RestMethod http://127.0.0.1:3000/health
Invoke-RestMethod http://127.0.0.1:8091/health
docker compose ps
```

- Node 返回 `ok: true` 表示 Web 已运行；`rag: true` 表示 Python 健康接口可访问。
- 只运行 Agent 时，`rag: false` 是预期状态。
- Python 在启动阶段加载 BGE 并检查维度，通过后才开始接收请求。
- `rag: true` **不代表 Milvus 或外部模型接口已通过连接测试**。进入“知识库”读取文档列表可检查数据库连接；上传一个短 TXT 并提问可检查完整链路。

| 默认地址 / 端口 | 服务 |
| --- | --- |
| `127.0.0.1:3000` | Node Web 工作台 |
| `127.0.0.1:8091` | Python 知识库 API；交互式 API 文档位于 `/docs` |
| `127.0.0.1:19530` | Milvus |
| `127.0.0.1:9091` | Milvus 健康检查端口 |
| `127.0.0.1:8083` | Attu 管理页面 |
| `127.0.0.1:9081` / `9008` | MinIO 控制台 / API |

Compose 只管理数据库相关组件，不会启动 Node 或 Python。可用 `docker compose stop` 停止数据库服务并保留数据。

## 3. 网页使用流程

### 3.1 选择工作区并执行任务

1. 打开“对话”，在顶部输入现有文件夹的绝对路径并点击“应用”，或在 Windows 上点击“选择文件夹”。例如 `D:\ts_test`。
2. 核对“当前工作区”。新用户默认目录是项目根；保存的目录失效时也会回退到项目根，因此开始任务前要确认路径。
3. 输入具体任务，例如：

   ```text
   检查这个目录里的 TypeScript 练习，补充 tsconfig.json 和运行脚本，实际运行验证后告诉我结果。
   ```

4. 回复会实时显示文字和工具活动。需要你选择或输入时，在弹出的对话框中完成交互。
5. 任务完成后，在工作区检查修改；已登记的文件也会出现在回复的交付列表中，可下载。

`read/write/edit/bash` 使用选定目录作为实际 `cwd`。切换工作区会销毁该用户已有 Runtime，并在网页开始新会话。运行中的任务必须先完成或停止。

停止任务会取消当前请求和待处理的交互框，**不会撤销已经写入的文件或执行完成的命令**。代码类任务建议在 Git 仓库中进行，便于检查修改。

### 3.2 查看历史和文件成果

- “历史”列出当前浏览器用户 ID 对应的会话。打开历史时会恢复对应的工作区和已保存消息。
- “新会话”创建新的会话 ID；“清空当前”目前只清空网页显示的消息，不等于删除服务端历史，也不会清除 Pi 记忆。
- 历史抽屉的删除按钮删除对应会话记录，不会删除工作区文件。
- `write/edit` 成功后宿主会尝试登记文件。通过 Shell 创建的成果需要 Agent 调用 `deliver_files` 登记。
- 下载只允许该会话登记过、仍存在于原工作区中的文件。文件被移走或删除后，历史下载链接可能失效。

### 3.3 上传资料并进行知识库问答

1. 按完整知识库方式启动服务。
2. 打开“知识库”，选择文档并上传，等待“解析并写入知识库”完成。
3. 返回“对话”，明确提出与上传文件有关的问题，例如：

   ```text
   根据刚上传的项目说明，列出部署步骤，并注明引用的文件和页码。
   ```

4. Agent 调用 `search_knowledge_base`，取得来源片段后组织回答。回复中的来源区域可查看文件名、页码和检索片段。

单文件上限为 **50MB**。文档按文件名识别，同名上传会替换对应的索引。解析使用暂存文件，解析失败不会覆盖原文件；索引写入阶段并非完整数据库事务，失败时应检查状态后重新上传。

| 格式 | 处理方式 / 注意事项 |
| --- | --- |
| `.txt` | 读取 UTF-8 文本 |
| `.pdf` | 提取文字、按页分块；内嵌图片描述需要可选的 `DASHSCOPE_API_KEY` |
| `.docx` | 读取段落和表格；来源页码通常为逻辑页 1，不做 Word 渲染分页 |
| `.doc` | 优先尝试 Microsoft Word，再尝试 LibreOffice、antiword；至少有一种可用，或先转成 `.docx` |
| `.pptx` | 按幻灯片提取文字，可选择识别内嵌图片 |
| `.xlsx` / `.xls` | 读取表格；当前默认读取第一个工作表 |
| `.csv` | 使用 pandas 读取表格文本 |

旧版二进制 `.ppt` 请先另存为 `.pptx`。目前没有可用的 `.ppt` 转换器，因此已移除原来会在解析时失败的上传入口。

知识库删除按钮移除该文件的检索索引并回退相关统计，保存的源文档与提取图片仍可能留在 `tmp/knowledge/`。知识库是项目级共享数据，不会因切换任务工作区自动切换。

### 3.4 图片和 Skills

聊天输入框的图片按钮支持每条消息最多 **5 张 PNG/JPEG/WebP/GIF**。聊天图片属于当前任务附件，不会自动进入知识库。主模型能否直接接收图片由 `CHAT_MODEL_SUPPORTS_IMAGES` 控制；`describe_image` 使用视觉适配器，需要供应商支持的 `VISION_MODEL`。

打开“配置中心”可以查看已选插件、加载错误、权限摘要，以及创建、上传、删除用户 Skill。该页面主要用于资源查看和 Skill 管理；模型密钥与高级参数仍在 `.env` 中配置。

上传一个 `SKILL.md`，或包含一个 Skill 的 ZIP。格式示例：

```markdown
---
name: project-review
description: 检查当前工作区的代码结构并输出审查报告。
---

# Workflow

1. 阅读项目说明与入口文件。
2. 检查模块依赖和错误处理。
3. 将报告写到工作区的 review.md，并登记交付文件。
```

名称只允许小写字母、数字和连字符。上传上限 10MB；ZIP 解压上限 30MB / 200 个文件。覆盖前会校验路径、符号链接、重复文件和内容，校验失败不覆盖旧 Skill。保存后在下一轮任务开始时热加载，不打断正在执行的任务。

## 4. Pi 记忆和插件

### 4.1 如何使用记忆

`pi-memory` 随项目 Node 依赖安装，由资源加载器注册。宿主在启动时将 `PI_MEMORY_DIR` 固定为项目的 `tmp/pi-memory`，不需要 Python、mem0、Qdrant 或 Milvus。

直接在对话中提出记忆需求，例如：

```text
请记住：我希望 TypeScript 项目启用 strict，并优先使用中文解释。保存到长期记忆。
读取当前长期记忆，告诉我已经记录了哪些偏好。
检查记忆服务状态和存储位置。
```

对应的插件工具包括：

| 工具 | 用途 |
| --- | --- |
| `memory_write` | 写入长期记忆或每日日志 |
| `memory_read` | 读取记忆文件、列出每日日志 |
| `memory_status` | 检查路径、配置、qmd 和索引状态 |
| `memory_forget` / `memory_restore` | 删除匹配条目并生成恢复记录 / 按恢复 ID 恢复 |
| `scratchpad` | 管理待办清单 |
| `memory_search` | 通过 qmd 搜索记忆 |

应以工具返回的保存结果为准；普通回复说“记住了”并不等于文件已持久化。插件按自己的策略注入记忆上下文。默认 `stable` 模式在会话开始、长期记忆写入后的下一轮等检查点刷新；每日日志和待办的最新状态可以主动调用 `memory_read` 查看。

`memory_search` 的关键词、语义和深度搜索都依赖 **qmd**。没有 qmd 时，记忆读写、待办和状态查询仍可使用。需要搜索时可根据已安装插件的说明单独安装：

```powershell
npm install -g @tobilu/qmd
qmd --version
```

安装后重启 Node，让插件识别新命令；索引和向量准备状态可通过 `memory_status` 查看。相关插件配置见 [配置说明](docs/configuration.md#pi-memory)。

### 4.2 三种数据不要混淆

| 数据 | 保存位置 | 用途 |
| --- | --- | --- |
| 会话历史 | `tmp/sessions/` | 恢复某次对话的消息、来源、图片引用和交付物 |
| Pi 记忆 | `tmp/pi-memory/` | 跨会话的偏好、事实、日记和待办 |
| 文档知识库 | `tmp/knowledge/` + Milvus 数据卷 | 对用户上传的资料进行检索 |

Pi 记忆目录目前在本项目内共享，不按浏览器用户 ID 或工作区隔离。新会话、切换工作区和删除会话历史都不会自动清空记忆。

旧的 mem0 API、网页管理面板、Python 实现和专属依赖已移除。原有 `tmp/mem0/` 若存在，只是保留的历史数据，不会自动导入 Pi 记忆，也不再被应用使用。

### 4.3 已配置的 Pi 包

实际版本锁定在 `package.json` / `package-lock.json`，加载清单在 `src/integrations/pi/plugin-resources.ts`。

| 功能 | Package | 宿主适配 |
| --- | --- | --- |
| Agent 核心 | `@earendil-works/pi-coding-agent`，当前锁定 `0.84.4` | 创建和恢复模型会话，注册工具，订阅事件 |
| 上下文管理 | `@hypabolic/pi-hypa` | 宿主配置独立缓存；SDK 自身也启用上下文压缩 |
| 网页与外部资料 | `pi-web-access` | 配置 Exa / DuckDuckGo 路由，不自动打开浏览器 |
| 子 Agent | `pi-subagents` | 配置独立的子会话和临时成果目录 |
| 人机确认 | `@juicesharp/rpiv-ask-user-question` | 通过 WebUI 将选择和输入转为网页交互 |
| 代码质量 | `pi-lens` | 保留诊断；关闭自动安装检查器、自动格式化和自动修复 |
| 权限与审计 | `@gotgenes/pi-permission-system` | 工作区、附件、Skill 资源和敏感文件规则 |
| 长期记忆 | `pi-memory` | 独立 Markdown 记忆目录 |
| 图片识别 | `@getpipher/vision` | 使用公开委派 API，避免直接加载不兼容的终端 UI 扩展 |

插件安装成功不代表它依赖的外部模型、网络或命令已经可用。加载错误可在“配置中心”查看，工具执行错误显示在当前对话中。

## 5. 项目架构与执行过程

### 5.1 总体结构

```text
浏览器：Vue 3 工作台
   │ HTTP / SSE（同源请求）
   ▼
Node：Express + Pi SDK                         :3000
   ├─ 工作区、文件交付、上传、Skills、历史
   ├─ AgentService → Pi 模型会话 → 工具 / 插件
   │                              ├─ 项目文件与命令
   │                              ├─ pi-memory → tmp/pi-memory
   │                              └─ 网页 / 视觉 / 诊断等
   └─ search_knowledge_base / 文档代理
                 │ HTTP
                 ▼
Python：FastAPI 知识库侧车                     :8091
   ├─ 文档解析 → 三级分块 → BGE dense + BM25 sparse
   ├─ 父块 JSON / BM25 统计 / 源文档
   └─ LangGraph 检索流程
        ├─ Milvus 混合召回 + RRF               :19530
        ├─ Auto-merge + 可选 rerank
        ├─ 相关性评估 / 必要时扩展查询
        └─ 来源片段与检索轨迹 → Pi 生成最终回答
```

Python 保留 LangChain / LangGraph，是因为它们仍用于文档切分、嵌入模型适配和检索流程。这里的模型调用只做文档相关性评估、查询扩展及可选文档图片描述，最终对话和工具决策由 Pi 完成。

### 5.2 一次普通任务如何执行

1. `src/main.ts` 先配置代理、缓存和插件目录，再导入 SDK 相关模块。
2. `src/server.ts` 写入运行配置，创建 `AgentService`，启动本机 Express 服务。
3. 浏览器向 `/chat/stream` 提交消息、用户 ID、会话 ID及可选图片。
4. 路由读取用户选定的工作区，创建或复用该用户/会话的 Pi Runtime。
5. `DefaultResourceLoader` 加载插件与 Skills，Pi 使用工作区作为工具 `cwd`；恢复会话时宿主重新装配已保存的用户和助手消息。
6. Pi 产生文字、调用工具或请求用户交互。宿主转为 SSE 事件，网页更新回复、工具活动和来源。
7. 工具成功写文件后登记交付；任务消息和相关记录通过 JSON 存储保存。

### 5.3 知识库入库和检索

**入库**：上传文件 → 校验格式和大小 → 暂存解析 → 三级父子分块 → 父级 L1/L2 存 JSON，叶子 L3 生成 dense/sparse 向量并写入 Milvus。默认分块大小为 L1 1200、L2 600、L3 300 字符，对应重叠 240、120、60 字符。

**检索**：问题向量化 → L3 混合召回 → RRF 融合 → 相同父块下命中足够多的子块时向上合并 → 可选外部 rerank → 模型评估相关性。初始结果为空或不相关时，选择 Step-back、HyDE 或组合策略，再检索一次并去重。

每轮 Pi 最多调用一次知识库工具；一次工具调用内部可能执行初始和扩展检索，也可能产生多次辅助模型请求。相关性评估出错时保留已召回片段；重排失败时回退到重排前排序；Milvus / embedding 故障会返回错误，不再被当成“没有相关资料”。

HyDE 和 Step-back 生成的文本用于帮助检索，不应作为文档事实引用。最终引用以真实命中的文件、页码和片段为准。

## 6. 目录与源码阅读顺序

```text
project/
├─ src/                         # TypeScript 宿主
│  ├─ main.ts / server.ts       # 环境初始化、依赖组装、监听
│  ├─ config/                  # 模型、目录、权限和插件运行配置
│  ├─ http/routes/             # 聊天、工作区、会话、配置、文档代理 API
│  ├─ agent/                   # Pi Runtime、提示词、WebUI 事件桥
│  ├─ tools/                   # 知识库、图片描述、文件交付工具
│  ├─ services/                # 工作区、上传、Skill、交付业务规则
│  ├─ storage/                 # JSON 原子写与会话存储
│  └─ integrations/            # Pi 资源发现、Shell、视觉插件适配
├─ backend/                     # 只提供文档知识库服务
│  ├─ rag_app.py               # FastAPI 路由组装、BGE 启动检查
│  ├─ preload_embedding_model.py # 手动预下载/验证 BGE 的有效入口
│  ├─ api/                     # routes_documents、routes_knowledge
│  ├─ config/                  # 环境变量、缓存路径、旧知识库数据迁移
│  ├─ knowledge/               # 文档解析、向量化、Milvus 与父块存储
│  ├─ retrieval/               # 初始检索、评估、改写、合并、重排
│  ├─ common/                  # 文档响应模型、Windows 编码安全输出
│  └─ tests/                   # 文档及知识库回归测试
├─ frontend/                    # Vue 页面；无需单独构建
│  ├─ index.html / script.js   # 页面结构和挂载入口
│  ├─ js/                      # 对话、工作区、知识库、配置、格式化
│  └─ css/                     # 按界面区域拆分样式
├─ .pi/skills/                  # 项目内置 Skills
├─ agent_workspace/skills/      # 沿用的 Skill 资源；不是当前任务工作区
├─ tests/                       # TypeScript / HTTP / 前端状态测试
├─ docs/                        # 详细配置、架构、Pi 升级记录
├─ docker-compose.yml           # Milvus 及相关服务
├─ package.json / package-lock.json
├─ pyproject.toml / uv.lock
└─ tmp/                         # 本地运行数据，Git 忽略
```

阅读代码建议：

1. 从 `src/main.ts`、`src/server.ts` 和 `src/http/app.ts` 理解启动与 HTTP 组装。
2. 看 `src/agent/agent-service.ts` 理解会话、工具、事件和持久化如何衔接。
3. 看 `src/agent/system-prompt.ts` 与 `src/tools/` 理解 Agent 被赋予的能力与边界。
4. 看 `src/services/`、`src/storage/` 理解路径校验、交付和存储规则。
5. 需要理解知识库时，顺着 `routes_documents.py → document_loader.py → milvus_writer.py` 阅读入库，顺着 `routes_knowledge.py → rag_pipeline.py → rag_utils.py / retrieval_steps.py` 阅读检索。
6. 最后结合 `frontend/js/chat.js` 理解 SSE 如何转换为网页状态。

更细的模块职责和依赖约束见 [架构分析](docs/architecture.md)，SDK 适配记录见 [Pi 升级说明](docs/pi-upgrade.md)。

## 7. 数据保存与备份

| 位置 | 内容 |
| --- | --- |
| `tmp/config/workspaces.json` | 浏览器用户 ID 对应的工作区；同目录还有宿主插件配置 |
| `tmp/sessions/` | 历史消息、工作区、图片引用、检索来源和交付物信息 |
| `tmp/pi-memory/MEMORY.md` | Pi 长期记忆 |
| `tmp/pi-memory/daily/`、`SCRATCHPAD.md`、`recovery/` | 每日日志、待办、记忆删除恢复记录 |
| `tmp/user-skills/` | 网页创建或上传的 Skills |
| `tmp/uploads/` | 聊天图片附件 |
| `tmp/knowledge/documents/` | 知识库上传源文档 |
| `tmp/knowledge/extracted_images/` | 文档提取的图片 |
| `tmp/knowledge/parent_chunks.json` / `bm25_state.json` | 父块内容与 BM25 词表统计，必须与向量库保持配套 |
| `tmp/pi-agent/` | 宿主生成的模型、权限、视觉和扩展配置 |
| `tmp/huggingface/`、`tmp/cache/`、`tmp/pi-lens/` | 模型和插件缓存 |
| `tmp/permission-logs/` | 权限审计；视觉审计另存于 `tmp/vision-audit.jsonl` |
| `volumes/` | Compose 默认使用的 Milvus、MinIO、etcd 数据；可由 `DOCKER_VOLUME_DIRECTORY` 覆盖 |
| 用户选择的工作区 | 实际项目文件和成果 |

浏览器还保存用户 ID、当前视图和消息草稿等状态；清理浏览器站点数据可能使当前用户 ID 改变，旧历史文件仍留在磁盘，但不会自动出现在新 ID 的历史列表中。

备份前停止相关服务，至少保存工作区、`tmp/sessions`、`tmp/pi-memory`、`tmp/user-skills`。知识库需要成套备份 `tmp/knowledge` 和数据库数据目录。不要只复制 Milvus 而丢失父块 / BM25 文件，也不要把整个 `tmp/` 当成可随意清空的缓存。

旧项目根目录 `data/` 中的 BM25、父块和源文档会在目标不存在时复制到 `tmp/knowledge/`；迁移不会删除原文件或覆盖已存在的新文件。该迁移能力仍在使用，保留在 `backend/config/runtime_data.py`。

真实 `.env`、模型认证信息、运行数据与清理备份不提交 Git；依赖锁文件和无密钥的 `.env.example` 应提交。

## 8. 接口与运行命令

### 日常命令

| 命令 | 作用 |
| --- | --- |
| `npm start` | 运行 Node Web / Pi Agent |
| `npm run dev:pi` | 仅 Node，监听 TypeScript 修改 |
| `npm run start:rag` / `npm run dev:rag` | 仅 Python 知识库，当前两者都不自动重载 |
| `npm run dev` | 同时启动 Node 和 Python |
| `uv sync --locked` | 按锁文件同步 Python 环境；升级后也用于移除已不再需要的包 |
| `npm run check` | TypeScript 类型检查和测试 |
| `npm run test:rag` | Python 知识库测试 |
| `docker compose logs --tail 100 standalone` | 查看 Milvus 最近日志 |

### Node API（网页统一访问这个端口）

| 方法与路径 | 用途 |
| --- | --- |
| `GET /health` | Web 健康状态和侧车可达性 |
| `GET /workspace/:userId` | 当前工作区 |
| `POST /workspace/:userId` | JSON `{ "path": "绝对路径" }` 切换工作区 |
| `POST /workspace/:userId/pick` | 打开 Windows 文件夹选择器 |
| `POST /chat/stream` | JSON 或 multipart；字段 `message`、`user_id`、`session_id`，图片字段 `images` |
| `POST /chat/ui-response` | 回传交互框的 `id`、`value` 和用户 / 会话 ID |
| `GET /sessions/:userId` | 会话列表 |
| `GET /sessions/:userId/:sessionId` | 会话消息与工作区 |
| `DELETE /sessions/:userId/:sessionId` | 删除历史记录 |
| `GET /artifacts/:userId/:sessionId?path=...` | 下载已登记文件；路径需 URL 编码 |
| `GET /runtime-config` / `POST /runtime-config/refresh` | 查看运行资源 / 请求下一轮重载 |
| `POST /runtime-config/skills` | 创建 Skill |
| `POST /runtime-config/skills/upload` | 上传 Skill，文件字段 `skill` |
| `DELETE /runtime-config/skills/:name` | 删除用户上传的 Skill |
| `GET /documents` / `POST /documents/upload` / `DELETE /documents/:filename` | 代理 Python 文档接口；上传字段 `file` |

### Python API（默认 8091）

| 方法与路径 | 用途 |
| --- | --- |
| `GET /health` | 已完成启动的知识库服务状态 |
| `GET /documents` | 读取 Milvus 文档统计 |
| `POST /documents/upload` | 文档解析与入库 |
| `DELETE /documents/{filename}` | 删除文件索引 |
| `POST /knowledge/search` | JSON `{ "query": "问题" }`，返回 `docs`、`rag_trace` 和检索状态 |

知识库搜索由 Pi 工具直接访问侧车。浏览器的文档请求经过 Node 同源代理，因此 Python 无需单独配置网页跨域来源。旧 `/memory/*` 接口已移除，返回 404。

## 9. 测试和故障排查

```powershell
npm run check
npm run test:rag
uv run python -m compileall -q backend
```

自动测试覆盖工作区和交付路径、Skill 上传与覆盖、文档分块、格式解析、HTTP / SSE、交互取消、旧记忆接口下线及旧页面状态恢复。知识库链路测试用假模型 / 假检索验证成功、扩展查询和故障分支，不需要启动 Docker 或下载 BGE；它们不能替代真实模型与数据库的联调。

| 现象 | 检查方法 |
| --- | --- |
| 网页打不开 / 端口被占用 | 确认 Node 进程和终端日志；避免同时运行 `npm start` 与 `npm run dev` 的 Node 进程 |
| 页面空白、Vue 或 marked 报错 | 前端依赖 CDN 提供 Vue、marked、高亮和图标等资源；检查网络，当前没有完整离线前端包 |
| `rag: false` | 只用 Agent 时可忽略；需要知识库则看 RAG 终端是否仍在下载 / 加载 BGE，确认 `RAG_BASE_URL` 与端口一致 |
| 离线模式提示缓存不完整 | 暂时将 `EMBEDDING_LOCAL_FILES_ONLY=false`，运行预下载命令，成功后再开启离线模式 |
| 文档列表失败、Milvus 连接失败 | 检查 Docker Desktop、`docker compose ps` 和 standalone 日志；确认 `MILVUS_HOST/PORT` |
| 向量维度不匹配 | 检查模型、`EMBEDDING_DIM`、`MILVUS_DENSE_DIM` 与集合；更换模型应使用新集合并重新入库 |
| 模型认证 / 模型不存在 | 检查 `.env` 中账户权限、`CHAT_MODEL`、`GRADE_MODEL`、`VISION_MODEL` 和接口地址，修改后重启 |
| `memory_search` 不可用 | 在对话调用 `memory_status`，检查 qmd 是否存在和索引状态；基础记忆读写不依赖 qmd |
| 旧 `.doc` 解析失败 | 安装可用的 Word / LibreOffice / antiword，或转换成 `.docx` |
| 扫描 PDF 没有文字 | 纯图片文档需要图片描述模型；配置可选 `DASHSCOPE_API_KEY`，它与聊天视觉插件配置不同 |
| 无法运行 Shell | 确认 Git for Windows 已安装，必要时通过 `PI_SHELL_PATH` 指向 `bash.exe` |
| 新 Skill 没生效 | 查看配置中心的加载错误，确认 `SKILL.md` frontmatter，等待当前轮结束后再发新消息 |
| 修改界面后仍显示旧内容 | 刷新，必要时 `Ctrl+F5`；若修改了后端则同时重启对应进程 |

## 10. 当前边界与扩展方式

这是供本机受信任用户使用的工具。Node 监听 `127.0.0.1` 并校验 Host / Origin，但没有多用户登录与租户隔离；知识库和 Pi 记忆共享。文件权限扩展也不是操作系统沙箱，Shell 和第三方插件仍以当前系统用户权限运行。

当前会话恢复重放保存的用户 / 助手文本，不能保证恢复完整的底层工具调用链和每个插件的内部状态。文档管理查询上限为 10000 条，文件名是替换依据；大规模文档管理、并发事务和更严格隔离需要后续设计。

新增功能时：HTTP 协议放 `src/http/routes`，业务规则放 `src/services`，持久化放 `src/storage`，Pi 工具放 `src/tools`，第三方兼容放 `src/integrations`。只有文档解析和检索算法进入 Python；记忆、对话、子 Agent 和工具调度继续通过 Pi 扩展实现。
