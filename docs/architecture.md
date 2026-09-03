# 项目架构与实现分析

使用步骤见根目录 [README](../README.md)，参数默认值见 [配置说明](configuration.md)。本文解释当前模块为什么保留、数据如何流动，以及二次开发应在哪一层修改。

## 1. 职责划分

项目有三个运行边界：浏览器展示、Node Agent 宿主、Python 文档知识库。Pi 插件属于 Node 运行时；Milvus 是知识库的数据服务。

| 层 | 负责 | 关键入口 |
| --- | --- | --- |
| 前端 | 输入、消息、工具活动、来源、交付文件、工作区与配置页面 | `frontend/index.html`、`frontend/js/` |
| Node 协议层 | HTTP 校验、SSE、文件上传下载、文档代理 | `src/http/app.ts`、`src/http/routes/` |
| Agent 层 | Pi Runtime、模型和资源初始化、会话恢复、事件订阅 | `src/agent/agent-service.ts` |
| 工具与集成层 | 将业务能力注册为 Pi 工具，适配社区包 | `src/tools/`、`src/integrations/` |
| 服务与存储层 | 工作区、Skills、附件、交付物、JSON 持久化 | `src/services/`、`src/storage/` |
| Python 知识库 | 文档解析、三级分块、向量入库、检索与重排 | `backend/rag_app.py` |
| 长期记忆 | Markdown 记忆、日记、待办、qmd 搜索 | `pi-memory` 插件，`tmp/pi-memory/` |

**Python 不承担聊天、文件任务调度或记忆管理。** LangGraph 在这里描述有限的检索流程，终点返回来源片段；最终回答由 Pi 主模型生成。

## 2. 依赖方向

```text
frontend
   └─ HTTP routes
        ├─ AgentService
        │    ├─ Pi SDK / resource loader / community extensions
        │    └─ tools → services / integrations
        ├─ services → storage
        └─ document proxy → Python API

knowledge tool → Python API → retrieval / knowledge
pi-memory extension → tmp/pi-memory（不经过 Python）
```

- 路由处理协议和入口校验，通过注入的 AgentService 调用会话，不直接构造模型。
- AgentService 编排生命周期，不接收 Express 请求 / 响应对象。
- 文件、Skill 和存储服务不依赖 Pi 或 Express，可以独立测试。
- 视觉插件的版本兼容集中在 `src/integrations/vision/adapter.ts`，不修改 `node_modules`。
- Python 使用 `backend.*` 全限定导入，避免同一模块重复初始化不同的 embedding 单例。
- 前端各 JS 模块将方法装配到同一个 Vue 应用，没有额外的前端路由服务。页面由 Express 静态服务提供；未知资源 / API 返回 404。

`tests/architecture.test.ts` 检查部分静态边界，HTTP 测试通过注入假 Agent 验证路由，不需要真实模型账户。

## 3. Node 启动和会话生命周期

`main.ts` 必须先于 SDK 初始化：一些插件在导入时读取目录和环境变量。这里配置 `HTTP(S)_PROXY`、本机代理例外、缓存根目录、Pi 记忆目录和插件环境。随后 `server.ts` 调用 `ensureRuntimeLayout()` 写入运行配置并监听回环地址。

Runtime 以用户 ID 和会话 ID 为键缓存，内部持有 Pi session、资源加载器、WebUI、交付物记录和事件出口。首次使用某会话时才加载插件和模型，Web 首页不依赖 Python 成功启动。

Pi session 使用 `SessionManager.inMemory(workspace)`。消息由宿主的 JSON 存储持久化，重新启动后通过已保存的用户 / 助手文本重建上下文。保存内容包括图片附件引用、RAG 来源和交付物元信息；并不保存完整底层工具执行消息链或插件内部状态。

资源加载器额外加载三类 Skill 路径：项目 `.pi/skills`、沿用的 `agent_workspace/skills`、网页上传的 `tmp/user-skills`，以及插件 manifest 声明的资源。上传或删除 Skill 只标记 Runtime 需要重载，在下一轮开始时调用 `session.reload()`。

工作区切换会取消交互并销毁该用户已有 Runtime。路由先检查是否有正在执行的任务；前端随后创建新的会话 ID。历史恢复也会先恢复记录中的工作区。

## 4. 工具、交互与交付

### 工具事件

Pi 的文本增量被转换为 `content` 事件，工具开始 / 结束转换为 `tool_step` 等事件；知识库工具另外产生 `trace`，交付产生 `artifacts`。SSE 通过 `POST /chat/stream` 返回，终止时发送 `[DONE]`；连接关闭会触发取消。

Python 检索过程的中间日志写到标准 Python logging，检索轨迹随一次工具结果返回。Python 不维护聊天 SSE 队列或跨请求的全局事件收集器。

### 人机交互

`WebUI` 将插件的选择、确认、输入请求转成 `ui_request`。前端通过 `/chat/ui-response` 提交结果；无效选项会被拒绝，过期请求返回 410，停止任务会取消挂起的交互。

### 文件成果

真实文件保存在用户工作区。`artifact-service` 校验实际路径、工作区边界、敏感扩展和文件类型。成功的 `write/edit` 会记录候选路径，任务结束时再次检查；Shell 生成的文件通过 `deliver_files` 登记。

下载时既检查路径，也检查文件是否曾登记在对应会话中。浏览器展示一段 Markdown 不等于文件已经写入，历史中的下载条目也不是独立备份。

## 5. backend 各文件为什么保留

### 入口和配置

| 文件 | 职责与调用方 |
| --- | --- |
| `rag_app.py` | 组装文档 / 检索路由，启动时 warm-up BGE 并校验维度 |
| `preload_embedding_model.py` | 运维入口：提前下载 / 检查模型，不是启动时自动执行的脚本 |
| `config/settings.py` | 知识库使用的模型、向量库、embedding、auto-merge、rerank 参数 |
| `config/runtime_data.py` | 将缓存归拢到项目 tmp，非覆盖式复制旧知识库数据 |
| `common/schemas.py` | 文档列表、上传、删除的响应模型 |
| `common/encoding_utils.py` | 避免 Windows 控制台编码导致文档处理中的打印崩溃 |

包目录中的 `__init__.py` 是 Python 包标识；`tests/` 用于回归检查，不能仅因它们不由业务路由调用就视为无用文件。

### 文档入库

| 文件 | 职责 |
| --- | --- |
| `api/routes_documents.py` | 文件名 / 大小校验、暂存、解析、同名替换、列表和索引删除 |
| `knowledge/document_loader.py` | 分派 TXT / PDF / PPTX / Word / 表格解析，构建三级父子块 |
| `knowledge/word_document_reader.py` | DOCX 段落与表格；旧 DOC 的 Word / LibreOffice / antiword 回退 |
| `knowledge/embedding.py` | BGE dense 向量、中文单字 / 英文单词分词、BM25 稀疏向量及统计持久化 |
| `knowledge/milvus_writer.py` | 分批生成向量并写入叶子块，批次失败时回退 BM25 统计 |
| `knowledge/milvus_client.py` | 懒连接、集合维度检查、CRUD、RRF 混合搜索、失效连接重建 |
| `knowledge/parent_chunk_store.py` | JSON 保存 L1/L2 父块，支持 auto-merge 向上读取 |

默认三层分块大小 / 重叠为 `1200/240 → 600/120 → 300/60` 字符。父子 ID、根 ID、页码、块级别保存在元数据中。只有 L3 进入 Milvus；L1/L2 进入父块 JSON。

上传并非跨 Milvus / JSON / 源文件的完整事务：解析失败保护旧源文件；向量写入失败有清理与统计回退，但不能保证原索引原子恢复。同名文件是替换边界，大规模或并发写入需要进一步设计文档 ID、锁及事务策略。

### 检索流程

| 文件 | 职责 |
| --- | --- |
| `api/routes_knowledge.py` | 在线程中执行 RAG；正常返回状态，异常返回 HTTP 错误 |
| `retrieval/rag_pipeline.py` | LangGraph 的初始检索 → 相关性评估 → 必要时改写 / 再检索 |
| `retrieval/rag_state.py` | 图状态、相关性提示词、策略枚举、片段格式化 |
| `retrieval/rag_utils.py` | 查询向量化、Milvus 混合召回、合并和重排的串联 |
| `retrieval/retrieval_steps.py` | 父块合并、去重、可选外部 rerank 与失败回退 |
| `retrieval/query_expansion.py` | Step-back 问题 / 背景文本、HyDE 假设文档生成 |
| `retrieval/rag_expanded.py` | 执行扩展分支并合并来源和轨迹 |
| `retrieval/chat_models.py` | 仅供相关性评估、策略选择和扩展使用的 DeepSeek 模型工厂 |

默认每个检索分支取 5 个最终片段，初始候选为 15；dense / sparse 子检索进一步取候选并用 RRF 融合。Auto-merge 最多向上两层；达到阈值且本地父块存在时才合并。未配置完整 rerank 参数时保留原有排序。

图在相关性通过时结束；不通过时最多走一轮扩展。组合策略可分别执行 HyDE 和 Step-back 后去重，因此最终片段数可能超过 5。Pi 的“每轮一次知识库工具”限制不等于只发送一次辅助模型请求。

错误边界：

- 真实零命中仍允许查询扩展。
- Milvus / embedding 故障返回错误，不再记录到一个没有消费方的旧审计 JSON 后伪装零命中。
- 相关性评估调用失败时保留已有片段；外部重排失败回退到重排前结果。
- HyDE 生成文本只用于搜索，不能作为真实引用来源。

## 6. 记忆与知识库的隔离

`src/main.ts` 为 `pi-memory` 指定 `tmp/pi-memory`，`plugin-resources.ts` 加载插件扩展。记忆读写、日记、待办和可恢复删除由插件实现；搜索由可选 qmd 提供。Node / Python 均不再提供独立的 `/memory/*` CRUD API。

记忆目录是项目级共享的，当前不按工作区或浏览器用户隔离。会话历史使用用户 ID 分文件存储；Milvus 知识库则是项目级集合。这些边界来自当前实现，不能把浏览器 ID 当成安全的多租户账户。

## 7. 本次清理范围

- 删除 `backend/memory/`、`api/routes_memory.py`、mem0 DTO 和配置。
- 删除 Node 的记忆代理、前端记忆脚本 / 面板 / 状态 / 专属样式；旧记忆页状态恢复到聊天，保留消息和草稿。
- 删除 `common/ops_store.py` 和未消费的失败 JSON 审计；检索基础设施故障正常返回。
- 将 `common/event_stream.py` 的旧进度包装收回普通日志，删除空壳模块。
- 删除已无调用的 dense-only 搜索、Milvus 父块查询、批量目录加载、过期结构化评分模型、未使用编码初始化等代码。
- 移除没有实现转换能力的二进制 `.ppt` 上传入口，返回转成 `.pptx` 的提示。
- 删除 mem0、Qdrant、PostHog 等专属依赖，使用 uv 重新生成锁文件并同步环境；仍被其他依赖需要的包由 uv 保留。
- Python 的旧网页 CORS 配置已移除：浏览器通过 Node 同源代理访问文档接口。

文档、模型缓存、用户 Skill、已有成果和旧记忆数据不属于无用代码，不在删除范围。知识库数据迁移和预下载脚本仍是有效能力，继续保留。

## 8. 测试与后续扩展

- `npm run check`：类型、服务、HTTP、交互取消、架构边界和旧前端状态恢复。
- `npm run test:rag`：文档格式、三级分块、上传失败保护、旧接口下线、RAG 成功 / 扩展 / 故障路径。
- 真实链路：启动模型与 Milvus，上传短 TXT，再从网页提问并核对来源；单测不会访问真实模型或数据库。

新增文档格式在 `knowledge` 实现并同步前端与 API 的格式白名单；新增检索策略在 `retrieval` 中接入并维持 `docs/rag_trace` 契约。新的聊天能力或记忆行为优先通过 Pi 工具和插件扩展。改变数据存储格式前应设计迁移，不要用删除现有数据来掩盖不兼容。
