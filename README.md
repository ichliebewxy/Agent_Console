# 二狗子助手

这是一个基于 [`earendil-works/pi`](https://github.com/earendil-works/pi) SDK 二次开发的本地 Web Agent。网页不是文件交付区：用户先选择一个本机文件夹作为工作区，Pi 的 `read/write/edit/bash` 等工具都以该目录为真实 `cwd`，生成文件直接留在工作区内。

项目保留了原来的本地知识库能力：上传文档后进行父子层级切分，使用 BGE-M3 稠密向量与 BM25 稀疏向量写入 Milvus，查询时混合召回、auto-merge 和可选 rerank。Python 现在只承担知识库/记忆侧车，Agent 会话、工具、插件、Skills 与流式输出由 Pi SDK 驱动。

## 已实现

- 完整自定义系统提示词：`二狗子助手`。
- 工作区选择：输入绝对路径或调用 Windows 原生文件夹选择器。
- 文件交付：Pi 在选定工作区内直接读写，不把网页消息冒充交付物。
- 知识库工具：`search_knowledge_base` 调用原有 Milvus + BGE/BM25 检索逻辑；每轮最多查询一次。
- 文档上传与分块：PDF、Word、PPT、Excel、CSV、TXT。
- 图片输入：网页可附加最多 5 张 PNG/JPEG/WebP/GIF；主模型不支持图片时由视觉插件委派。
- 用户 Skills：支持网页创建，也支持上传 `SKILL.md` 或 ZIP，保存后热加载。
- SSE：文本增量、工具开始/完成/失败事件实时显示。
- 外部会话历史：Web 使用 `SessionManager.inMemory()`，历史单独保存在 `tmp/sessions`。
- 权限策略：文件工具工作区外默认拒绝；上传附件、内置和用户 Skill 资源允许只读；`.env`、`.pem`、`.key` 等敏感文件拒绝；审计写入 `tmp/permission-logs`。这不是操作系统沙箱，Shell 和第三方插件仍以本机用户权限运行，只适合受信任的本地单用户使用。
- 运行数据：Pi 配置、上传暂存、会话、用户 Skills、知识库源文件、模型和插件缓存默认放在项目的 `tmp/`。Docker 数据卷和 npm/uv 的安装缓存由各自工具管理。

## Pi Packages

版本在 `package.json` 中锁定：

| 功能 | Package |
| --- | --- |
| 上下文压缩 | `@hypabolic/pi-hypa` |
| 网页与外部资料 | `pi-web-access` |
| 子 Agent | `pi-subagents` |
| 人机确认 | `@juicesharp/rpiv-ask-user-question` |
| 代码质量回环 | `pi-lens` |
| 权限与审计 | `@gotgenes/pi-permission-system` |
| 记忆持久化 | `pi-memory` |
| 图片识别 | `@getpipher/vision` |

社区包做了 Web 适配：人机确认使用 RPC 对话框；视觉能力调用插件的公开委派 API；Pi Lens 保留诊断，但关闭自动安装检查器、自动格式化和自动修复，避免写文件时意外联网安装或改写成果。已安装的检查器仍可使用。pi-memory 的文件读写可直接使用，语义检索需要额外安装 `qmd`；未安装时不影响普通对话。网页搜索默认使用 Exa / DuckDuckGo，取决于网络可达性。

核心 SDK 已按用户确认升级并锁定为 `@earendil-works/pi-coding-agent@0.84.4`（2026-09-03 核对的最新稳定版）。以用户提供的 `dg-piagent` Skill 为起点，并对照新版类型与变更记录完成适配；差异见 [升级记录](docs/pi-upgrade.md)。

## 架构

项目按职责分层，详见 [目录、依赖边界与扩展方式](docs/architecture.md)。HTTP 路由只负责协议转换；Agent 负责会话编排；文件服务不依赖 Pi SDK；第三方插件兼容代码集中在 integrations。Python 只保留当前知识库与记忆侧车，停用的旧聊天 Agent 及专属测试已经移除。

```text
浏览器 :3000
  ├─ 选择本机工作区 / 上传图片 / 上传 Skill
  ├─ Express + Pi SDK
  │    ├─ 自定义系统提示词
  │    ├─ Pi 内置 coding tools + packages
  │    ├─ search_knowledge_base 自定义工具
  │    └─ SSE 事件桥
  └─ Python RAG sidecar :8091
       ├─ 文档解析与父子分块
       ├─ BGE-M3 + BM25 + rerank
       ├─ Milvus :19530（Docker）
       └─ mem0 REST API
```

## 启动

环境要求：Node.js 22.19+（推荐 24 LTS）、Python 3.12+、`uv`、Docker Desktop。

```powershell
# 仅首次配置且不存在 .env 时执行，勿覆盖已有密钥。
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# 填写 .env 中的 CHAT_API_KEY，并按实际模型调整 CHAT_MODEL

npm ci --ignore-scripts
uv sync
docker compose up -d
npm run dev
```

打开 [http://127.0.0.1:3000](http://127.0.0.1:3000)。Docker 中 Attu / MinIO 的端口保持现有 Compose 配置，与 Web 的 `3000` 分开。

`.env.example` 仅保留最常用配置；服务地址、视觉模型、重排和其他进阶选项见 [配置说明](docs/configuration.md)。不需要把默认值全部复制到 `.env`。

首次启动知识库侧车会加载或下载 BGE 模型，可能需要数分钟。若已预下载模型，可设置：

```dotenv
EMBEDDING_LOCAL_FILES_ONLY=true
```

只启动某一部分：

```powershell
npm start       # Pi Web :3000
npm run start:rag  # RAG sidecar :8091
```

## 工作区模式

1. 在页面顶部点击“选择文件夹”，或输入存在的绝对路径后点击“应用”。
2. 切换工作区会销毁该用户已有的内存 Runtime，并开启新会话，避免旧 `cwd` 泄漏。
3. 后续任务的文件工具都在该工作区执行，用户可直接用文件管理器、IDE 或 Git 查看结果。
4. `tmp/` 只保存本应用运行数据；它不是用户成果的默认交付位置，除非用户主动把它选作工作区。

工作区记录按浏览器用户 ID 保存于 `tmp/config/workspaces.json`。
成功的 write/edit 会自动登记成果；通过 Shell 创建的文件可由 Agent 调用 `deliver_files` 登记。下载接口只提供该会话已登记、仍存在于原工作区内的文件，拒绝路径穿越和敏感文件。历史会话会恢复其工作区。运行中的任务须先停止或完成，才能切换工作区。

## 用户 Skill 格式

上传一个 `SKILL.md`，或上传包含一个 Skill 目录及其资源的 ZIP（每次一个 Skill）。Skill 必须包含 YAML frontmatter：

```markdown
---
name: my-skill
description: 说明这个 Skill 的功能和何时使用。
---

# Workflow

1. 按步骤执行任务。
2. 在工作区内验证交付物。
```

名称只允许小写字母、数字和连字符。ZIP 会先校验全部路径、符号链接、重复文件和解压大小，再替换已有 Skill；失败时保留原内容。上传文件限 10MB，解压限 30MB / 200 文件。内容保存在 `tmp/user-skills/<name>/`，在下一条消息开始前调用 Pi 的 `session.reload()` 热加载，不打断正在执行的任务。Skill 文件和引用资料可跨工作区只读加载；不要让 Skill 修改自己的安装目录。只上传你信任的 Skills，因为其中脚本可能以本机权限执行。

## 运行数据

```text
tmp/
├─ config/                    # 工作区选择等 Web 状态
├─ sessions/                  # 外部会话历史
├─ user-skills/               # 用户上传 Skills
├─ uploads/                   # 图片暂存
├─ knowledge/                 # 文档源文件、提取图片、父块和 BM25 状态
├─ pi-agent/                  # models.json、视觉和权限运行配置
├─ pi-lens/                   # 代码诊断缓存和插件配置
├─ pi-memory/                 # Pi 记忆插件的 Markdown 文件
├─ cache/                     # 子进程和临时文件
├─ permission-logs/           # 权限审计
├─ huggingface/               # Hugging Face 缓存
└─ mem0/                      # 可选长期记忆
```

`tmp/` 已被 Git 忽略，仅保留 `tmp/.gitkeep`。
`.env*`（模板除外）、依赖、构建产物、测试缓存、Docker 数据和日志也已忽略；`package-lock.json`、`uv.lock` 和 `.env.example` 应提交。忽略规则不会自动移除 Git 已跟踪的文件，提交前仍需检查暂存区。
原有 Skill 资源仍保存在 `agent_workspace/skills`，与新增的 `.pi/skills` 一同加载；用户上传内容独立保存在 `tmp/user-skills`。
知识库侧车首次运行会把 `data/` 中的 BM25 状态、父块和源文档复制到 `tmp/knowledge`，不删除原文件。已有用户的 Hugging Face / mem0 缓存需要迁移后再改目录；本次本机迁移已完成并保留原缓存。`BM25_STATE_PATH` 等显式环境变量会覆盖默认目录。

Windows 推荐安装 Git for Windows。宿主会通过 git.exe 位置寻找 Git Bash；可用 `PI_SHELL_PATH` 指定其他 bash.exe。
宿主自动遵循已有 `HTTP_PROXY` / `HTTPS_PROXY`，本地服务地址不走代理。无需为了模型请求关闭系统代理或修改全局设置。

## 验证

```powershell
npm run typecheck
npm test
npm run test:rag
uv run python -m compileall -q backend
```

健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:3000/health
```

返回值中的 `rag` 表示 `8091` 的知识库侧车是否已就绪。
Milvus 还需 Docker 引擎和 `docker compose` 服务正常运行。模型、网络或社区插件失败会在工具活动或回答中显示，不会虚报成功。

本机已验证：工作区切换、真实写文件 / Git Bash cwd、人机选择回传、图片识别、Skills 上传与跨工作区实际执行、原有混合检索以及新文档父子切分。`npm run check` 覆盖工作区校验、Skill 安全覆盖、对话框取消和交付文件路径校验。

2026-09-03 升级 Pi 和上传/ZIP/YAML/测试依赖后，npm audit 返回 0 vulnerabilities。这仅代表该次 npm 依赖审计没有已知告警，不代表整个应用经过安全认证；不要将本机服务暴露到公网。

## 主要入口

- `src/main.ts` / `src/server.ts`：环境初始化与应用组装，不混入业务路由。
- `src/http/routes/`：按聊天、工作区、会话交付、配置、侧车分组的 API。
- `src/agent/`：Pi Runtime、系统提示词、扩展 UI 适配。
- `src/tools/`：知识库、视觉、文件交付的 Pi 工具协议。
- `src/services/`：工作区、上传、Skills、交付文件的业务规则。
- `src/storage/`：JSON 原子写、会话持久化。
- `src/integrations/`：Pi 包资源与第三方视觉兼容层。
- `backend/rag_app.py`：保留原有知识库与 mem0 API 的 Python 侧车。
- `backend/knowledge/` / `backend/retrieval/`：文档解析入库 / 检索与重排。
- `frontend/`：Vue Web 工作台。
