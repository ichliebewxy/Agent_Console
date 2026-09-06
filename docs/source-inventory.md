# 逐文件源码阅读记录

基线：`cd2b94029c4b0ffa97bc3ec86e9d05f9ddebc3eb`。本表列出最终工作树的每个交付文件，代码为逐文件阅读，锁文件为完整结构解析。行数含空行；生成文档的行数标记为动态。相对依赖依据源码导入记录；外部调用边界详见架构文档。

| 文件 | 职责 / 入口 | 主要符号 | 导入 / 资源依赖 | 行数 |
| --- | --- | --- | --- | --- |
| [.env.example](../.env.example) | 无真实密钥的常用配置模板。 | — | — | 11 |
| [.gitignore](../.gitignore) | 密钥/依赖/运行数据忽略规则。 | — | — | 64 |
| [.pi/settings.json](../.pi/settings.json) | 与 package.json 对应的 Pi 包资源版本清单。 | — | — | 12 |
| [.pi/skills/knowledge-base/SKILL.md](../.pi/skills/knowledge-base/SKILL.md) | 按需加载的 knowledge-base Skill 说明资源；不作为本次重构执行指令。 | `frontmatter: name / description` | — | 11 |
| [.pi/skills/skill-authoring/SKILL.md](../.pi/skills/skill-authoring/SKILL.md) | 按需加载的 skill-authoring Skill 说明资源；不作为本次重构执行指令。 | `frontmatter: name / description` | — | 12 |
| [.python-version](../.python-version) | uv 本地 Python 3.12 选择。 | — | — | 1 |
| [README.md](../README.md) | 产品功能、安装、操作、运行、数据保存和接口说明。 | — | — | 491 |
| [agent_workspace/README.md](../agent_workspace/README.md) | 沿用的 Skill 资源说明；部分执行路径为旧宿主语境。 | — | — | 15 |
| [agent_workspace/skills/agent-builder/SKILL.md](../agent_workspace/skills/agent-builder/SKILL.md) | 按需加载的 agent-builder Skill 说明资源；不作为本次重构执行指令。 | `frontmatter: name / description` | — | 129 |
| [agent_workspace/skills/agent-builder/references/agent-philosophy.md](../agent_workspace/skills/agent-builder/references/agent-philosophy.md) | 按需读取的 agent-philosophy Skill 参考资源。 | — | — | 154 |
| [agent_workspace/skills/agent-builder/references/minimal-agent.py](../agent_workspace/skills/agent-builder/references/minimal-agent.py) | 可选独立 Agent 循环模板；需要额外 anthropic 包。 | `execute_tool`<br>`agent` | `anthropic`<br>`pathlib`<br>`subprocess`<br>`os` | 149 |
| [agent_workspace/skills/agent-builder/references/subagent-pattern.py](../agent_workspace/skills/agent-builder/references/subagent-pattern.py) | 可选上下文隔离 Task 示例；不是当前 Pi 子 Agent 实现。 | `get_agent_descriptions`<br>`get_tools_for_agent`<br>`run_task` | `time`<br>`sys` | 243 |
| [agent_workspace/skills/agent-builder/references/tool-templates.py](../agent_workspace/skills/agent-builder/references/tool-templates.py) | 可选 Python 工具定义/路径校验/分发示例。 | `safe_path`<br>`run_bash`<br>`run_read_file`<br>`run_write_file`<br>`run_edit_file`<br>`execute_tool` | `pathlib`<br>`subprocess` | 271 |
| [agent_workspace/skills/agent-builder/scripts/init_agent.py](../agent_workspace/skills/agent-builder/scripts/init_agent.py) | 独立 Anthropic Agent 脚手架生成器；不由宿主启动。 | `create_agent`<br>`main` | `argparse`<br>`sys`<br>`pathlib` | 279 |
| [agent_workspace/skills/code-review/SKILL.md](../agent_workspace/skills/code-review/SKILL.md) | 按需加载的 code-review Skill 说明资源；不作为本次重构执行指令。 | `frontmatter: name / description` | — | 157 |
| [agent_workspace/skills/mcp-builder/SKILL.md](../agent_workspace/skills/mcp-builder/SKILL.md) | 按需加载的 mcp-builder Skill 说明资源；不作为本次重构执行指令。 | `frontmatter: name / description` | — | 213 |
| [agent_workspace/skills/opencli/SKILL.md](../agent_workspace/skills/opencli/SKILL.md) | 按需加载的 opencli Skill 说明资源；不作为本次重构执行指令。 | `frontmatter: name / description` | — | 63 |
| [agent_workspace/skills/opencli/agents/openai.yaml](../agent_workspace/skills/opencli/agents/openai.yaml) | OpenCLI Skill 的展示名称及调用提示元数据。 | — | — | 4 |
| [agent_workspace/skills/opencli/references/app-control.md](../agent_workspace/skills/opencli/references/app-control.md) | 按需读取的 app-control Skill 参考资源。 | — | — | 14 |
| [agent_workspace/skills/opencli/references/browser.md](../agent_workspace/skills/opencli/references/browser.md) | 按需读取的 browser Skill 参考资源。 | — | — | 25 |
| [agent_workspace/skills/opencli/references/cli-surface.md](../agent_workspace/skills/opencli/references/cli-surface.md) | 按需读取的 cli-surface Skill 参考资源。 | — | — | 29 |
| [agent_workspace/skills/opencli/references/downloads.md](../agent_workspace/skills/opencli/references/downloads.md) | 按需读取的 downloads Skill 参考资源。 | — | — | 15 |
| [agent_workspace/skills/opencli/references/library-api.md](../agent_workspace/skills/opencli/references/library-api.md) | 按需读取的 library-api Skill 参考资源。 | — | — | 11 |
| [agent_workspace/skills/opencli/references/permissions.md](../agent_workspace/skills/opencli/references/permissions.md) | 按需读取的 permissions Skill 参考资源。 | — | — | 15 |
| [agent_workspace/skills/opencli/references/search-routing.md](../agent_workspace/skills/opencli/references/search-routing.md) | 按需读取的 search-routing Skill 参考资源。 | — | — | 12 |
| [agent_workspace/skills/opencli/references/setup-and-doctor.md](../agent_workspace/skills/opencli/references/setup-and-doctor.md) | 按需读取的 setup-and-doctor Skill 参考资源。 | — | — | 15 |
| [agent_workspace/skills/pdf/SKILL.md](../agent_workspace/skills/pdf/SKILL.md) | 按需加载的 pdf Skill 说明资源；不作为本次重构执行指令。 | `frontmatter: name / description` | — | 112 |
| [backend/__init__.py](../backend/__init__.py) | Python 包标识；不包含业务代码。 | — | — | 0 |
| [backend/api/__init__.py](../backend/api/__init__.py) | Python 包标识；不包含业务代码。 | — | — | 0 |
| [backend/api/routes_documents.py](../backend/api/routes_documents.py) | 文件校验、暂存、解析、同名索引替换、列表/删除协议。 | `list_documents`<br>`upload_document`<br>`delete_document`<br>`_filename_filter`<br>`_delete_existing`<br>`_validated_filename`<br>`_save_upload` | `asyncio`<br>`os`<br>`re`<br>`pathlib`<br>`uuid`<br>`fastapi`<br>`backend.knowledge.document_loader`<br>`backend.knowledge.embedding`<br>`backend.knowledge.milvus_client`<br>`backend.knowledge.milvus_writer`<br>`backend.knowledge.parent_chunk_store`<br>`backend.common.schemas` | 167 |
| [backend/api/routes_knowledge.py](../backend/api/routes_knowledge.py) | 检索请求校验、线程执行与异常响应。 | `KnowledgeSearchRequest`<br>`search_knowledge` | `asyncio`<br>`fastapi`<br>`pydantic`<br>`backend.retrieval.rag_pipeline` | 24 |
| [backend/common/__init__.py](../backend/common/__init__.py) | Python 包标识；不包含业务代码。 | — | — | 0 |
| [backend/common/encoding_utils.py](../backend/common/encoding_utils.py) | Windows 控制台 Unicode 安全打印。 | `safe_print` | `sys` | 15 |
| [backend/common/schemas.py](../backend/common/schemas.py) | 文档列表、上传、删除的 Pydantic 响应契约。 | `DocumentInfo`<br>`DocumentListResponse`<br>`DocumentUploadResponse`<br>`DocumentDeleteResponse` | `pydantic`<br>`typing` | 26 |
| [backend/config/__init__.py](../backend/config/__init__.py) | Python 包标识；不包含业务代码。 | — | — | 0 |
| [backend/config/runtime_data.py](../backend/config/runtime_data.py) | 缓存配置与旧 data 到 tmp 的非覆盖迁移。 | `migrate_file`<br>`configure_caches`<br>`migrate_knowledge` | `os`<br>`shutil`<br>`pathlib` | 37 |
| [backend/config/settings.py](../backend/config/settings.py) | 知识库模型、Milvus、BGE、BM25、合并/重排环境参数。 | `env`<br>`env_bool`<br>`env_int` | `os`<br>`dotenv` | 53 |
| [backend/knowledge/__init__.py](../backend/knowledge/__init__.py) | Python 包标识；不包含业务代码。 | — | — | 0 |
| [backend/knowledge/document_loader.py](../backend/knowledge/document_loader.py) | TXT/PDF/PPTX/Word/表格解析分派、图片描述与三级分块。 | `DocumentLoader` | `os`<br>`pathlib`<br>`uuid`<br>`fitz`<br>`pptx`<br>`pandas`<br>`typing`<br>`langchain_text_splitters`<br>`langchain_community.chat_models.tongyi`<br>`langchain_core.messages`<br>`backend.common.encoding_utils`<br>`backend.config.runtime_data`<br>`backend.knowledge.word_document_reader` | 222 |
| [backend/knowledge/embedding.py](../backend/knowledge/embedding.py) | 懒加载 BGE dense、中文/英文分词和持久化 BM25 sparse。 | `EmbeddingService` | `os`<br>`json`<br>`math`<br>`re`<br>`threading`<br>`collections`<br>`pathlib`<br>`typing`<br>`backend.config.settings`<br>`backend.config.runtime_data`<br>`langchain_huggingface` | 248 |
| [backend/knowledge/milvus_client.py](../backend/knowledge/milvus_client.py) | 连接重建、集合兼容检查、CRUD、dense+sparse RRF 检索。 | `MilvusManager` | `threading`<br>`pymilvus`<br>`backend.config.settings` | 215 |
| [backend/knowledge/milvus_writer.py](../backend/knowledge/milvus_writer.py) | 分批写入叶子向量，并在失败时回退 BM25 统计。 | `MilvusWriter` | `backend.common.encoding_utils`<br>`backend.knowledge.embedding`<br>`backend.knowledge.milvus_client` | 56 |
| [backend/knowledge/parent_chunk_store.py](../backend/knowledge/parent_chunk_store.py) | JSON 存储 L1/L2 父块及按来源删除。 | `ParentChunkStore` | `json`<br>`pathlib`<br>`typing`<br>`backend.config.runtime_data` | 81 |
| [backend/knowledge/word_document_reader.py](../backend/knowledge/word_document_reader.py) | DOCX 文本/表格及 DOC 的 Word/LibreOffice/antiword 回退。 | `WordDocumentReader` | `os`<br>`pathlib`<br>`shutil`<br>`subprocess`<br>`tempfile`<br>`docx`<br>`pythoncom`<br>`win32com.client` | 182 |
| [backend/preload_embedding_model.py](../backend/preload_embedding_model.py) | 手动预下载和验证嵌入模型的命令入口。 | `main` | `os`<br>`backend.knowledge.embedding` | 28 |
| [backend/rag_app.py](../backend/rag_app.py) | FastAPI 入口、缓存/数据迁移及启动 BGE 维度检查。 | `lifespan`<br>`health` | `asyncio`<br>`contextlib`<br>`fastapi`<br>`backend.config.runtime_data`<br>`backend.knowledge.embedding`<br>`backend.api.routes_documents`<br>`backend.api.routes_knowledge`<br>`backend.config.settings` | 36 |
| [backend/retrieval/__init__.py](../backend/retrieval/__init__.py) | Python 包标识；不包含业务代码。 | — | — | 0 |
| [backend/retrieval/chat_models.py](../backend/retrieval/chat_models.py) | 仅用于评分与扩展的 DeepSeek 模型工厂。 | `build_chat_model` | `langchain.chat_models`<br>`backend.config.settings` | 22 |
| [backend/retrieval/query_expansion.py](../backend/retrieval/query_expansion.py) | Step-back、背景答案与 HyDE 生成。 | `_get_stepback_model`<br>`_invoke_prompt`<br>`generate_step_back_question`<br>`answer_step_back_question`<br>`generate_hypothetical_document`<br>`step_back_expand` | `backend.retrieval.chat_models`<br>`backend.config.settings` | 64 |
| [backend/retrieval/rag_expanded.py](../backend/retrieval/rag_expanded.py) | 组合扩展分支、合并轨迹与来源去重。 | `_init_meta`<br>`_merge_meta`<br>`_dedupe`<br>`_retrieve_branch`<br>`retrieve_expanded` | `logging`<br>`typing`<br>`backend.retrieval.query_expansion`<br>`backend.retrieval.rag_state`<br>`backend.retrieval.rag_utils` | 114 |
| [backend/retrieval/rag_pipeline.py](../backend/retrieval/rag_pipeline.py) | 初始召回、相关性评分、策略选择与一次扩展的图编排。 | `_get_grader_model`<br>`_get_router_model`<br>`retrieve_initial`<br>`grade_documents_node`<br>`_grade_update`<br>`_choose_strategy`<br>`rewrite_question_node`<br>`build_rag_graph`<br>`run_rag_graph` | `logging`<br>`langgraph.graph`<br>`backend.retrieval.chat_models`<br>`backend.retrieval.query_expansion`<br>`backend.retrieval.rag_expanded`<br>`backend.retrieval.rag_state`<br>`backend.retrieval.rag_utils`<br>`backend.config.settings` | 184 |
| [backend/retrieval/rag_state.py](../backend/retrieval/rag_state.py) | 图状态、评分提示和来源文本格式化。 | `RewriteStrategy`<br>`RAGState`<br>`format_docs`<br>`empty_rag_state` | `typing`<br>`pydantic` | 56 |
| [backend/retrieval/rag_utils.py](../backend/retrieval/rag_utils.py) | 向量化 → Milvus 混合召回 → 合并/重排编排。 | `_search_local`<br>`_finalize_retrieval`<br>`retrieve_documents` | `typing`<br>`backend.knowledge.embedding`<br>`backend.knowledge.milvus_client`<br>`backend.retrieval.retrieval_steps`<br>`backend.config.settings` | 45 |
| [backend/retrieval/retrieval_steps.py](../backend/retrieval/retrieval_steps.py) | 父块两层合并、去重、外部 rerank 及故障回退。 | `get_rerank_endpoint`<br>`merge_to_parent_level`<br>`auto_merge_documents`<br>`rerank_documents`<br>`dedupe_retrieved_docs` | `collections`<br>`typing`<br>`json`<br>`requests`<br>`backend.knowledge.parent_chunk_store`<br>`backend.config.settings` | 129 |
| [backend/tests/__init__.py](../backend/tests/__init__.py) | Python 包标识；不包含业务代码。 | — | — | 1 |
| [backend/tests/test_document_loader.py](../backend/tests/test_document_loader.py) | 回归测试；验证 document_loader。 | `DocumentLoaderWordTests` | `tempfile`<br>`unittest`<br>`pathlib`<br>`unittest.mock`<br>`backend.config.runtime_data`<br>`backend.knowledge.document_loader`<br>`backend.knowledge.word_document_reader`<br>`openpyxl`<br>`dashscope`<br>`xlrd` | 117 |
| [backend/tests/test_knowledge_service.py](../backend/tests/test_knowledge_service.py) | 回归测试；验证 knowledge_service。 | `KnowledgeServiceTests` | `unittest`<br>`types`<br>`unittest.mock`<br>`fastapi.testclient`<br>`backend.config.settings`<br>`backend.rag_app`<br>`backend.retrieval` | 80 |
| [backend/tests/test_routes_documents.py](../backend/tests/test_routes_documents.py) | 回归测试；验证 routes_documents。 | `DocumentRouteTests` | `io`<br>`tempfile`<br>`unittest`<br>`pathlib`<br>`unittest.mock`<br>`fastapi`<br>`backend.api.routes_documents` | 55 |
| [docker-compose.yml](../docker-compose.yml) | Milvus、etcd、MinIO、Attu 的数据服务编排。 | — | — | 77 |
| [docs/architecture.md](../docs/architecture.md) | 三端职责、数据流、Python 各模块及历史清理记录。 | — | — | 157 |
| [docs/configuration.md](../docs/configuration.md) | 完整环境变量、默认值、模型与插件配置说明。 | — | — | 117 |
| [docs/dependencies.mmd](../docs/dependencies.mmd) | 自动生成的文件级 TypeScript 有向依赖图。 | — | — | 动态 |
| [docs/file-tree.md](../docs/file-tree.md) | 自动生成的完整交付路径树。 | — | — | 动态 |
| [docs/pi-upgrade.md](../docs/pi-upgrade.md) | 此前 Pi 0.84.4 升级兼容记录。 | — | — | 39 |
| [docs/refactoring.md](../docs/refactoring.md) | 本次架构、目录迁移、行为边界和逐项回归结果。 | — | — | 136 |
| [docs/source-inventory.md](../docs/source-inventory.md) | 本文件；逐文件阅读记录和依赖入口。 | — | — | 动态 |
| [frontend/css/base.css](../frontend/css/base.css) | 主题变量、全局排版、侧栏、公共按钮。 | — | — | 326 |
| [frontend/css/chat.css](../frontend/css/chat.css) | 聊天布局、消息/Markdown、计划、活动、交付、对话框样式。 | — | — | 974 |
| [frontend/css/overlays.css](../frontend/css/overlays.css) | 历史抽屉、Toast、滚动条和骨架屏。 | — | — | 191 |
| [frontend/css/panels.css](../frontend/css/panels.css) | 知识库/配置表单、表格、卡片、权限摘要。 | — | — | 432 |
| [frontend/css/responsive.css](../frontend/css/responsive.css) | 减少动画及 1180/900/520 宽度响应式规则。 | — | — | 116 |
| [frontend/css/trace-composer.css](../frontend/css/trace-composer.css) | 来源折叠面板与输入区。 | — | — | 196 |
| [frontend/css/workspace.css](../frontend/css/workspace.css) | 工作台网格、顶栏与状态胶囊。 | — | — | 109 |
| [frontend/index.html](../frontend/index.html) | 单页 Vue 模板、CDN 依赖和本地脚本的明确装配顺序。 | — | `https://cdn.jsdelivr.net/npm/marked/marked.min.js`<br>`https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.7.0/highlight.min.js`<br>`https://unpkg.com/vue@3/dist/vue.global.js`<br>`/vendor/purify.min.js`<br>`js/app-core.js`<br>`js/workspace.js`<br>`js/chat-stream.js`<br>`js/chat-messages.js`<br>`js/history.js`<br>`js/chat.js`<br>`js/knowledge.js`<br>`js/config.js`<br>`js/formatters.js`<br>`script.js` | 421 |
| [frontend/js/app-core.js](../frontend/js/app-core.js) | Vue 数据/计算属性/挂载、浏览器状态、公共页面操作。 | `data`<br>`mounted` | — | 225 |
| [frontend/js/chat-messages.js](../frontend/js/chat-messages.js) | 助手消息分段、交互回答、来源合并和活动滚动。 | `activeAssistantMessage`<br>`answerDialog`<br>`scrollToolActivityToEnd`<br>`mergeStreamTrace`<br>`startNextAssistantSegment` | — | 91 |
| [frontend/js/chat-stream.js](../frontend/js/chat-stream.js) | SSE 增量解码及各事件到页面状态的分派。 | `readSseStream`<br>`consumeSseEvent` | — | 97 |
| [frontend/js/chat.js](../frontend/js/chat.js) | 聊天键盘/图片/提交/停止。 | `handleKeyDown`<br>`handleStop`<br>`handleChatImageSelect`<br>`removeChatImage`<br>`handleSend` | — | 98 |
| [frontend/js/config.js](../frontend/js/config.js) | 运行目录查看与 Skill 管理请求。 | `loadRuntimeConfig`<br>`refreshRuntimeCatalog`<br>`addSkill`<br>`uploadSkillFile`<br>`deleteSkill` | — | 76 |
| [frontend/js/formatters.js](../frontend/js/formatters.js) | 来源、文件、工具活动和旧计划数据的展示格式化。 | `sourceChunks`<br>`formatSourceMeta`<br>`getFileIcon`<br>`formatFileSize`<br>`shouldShowAgentTrace`<br>`toolCallGroups`<br>`hasPlan`<br>`planSteps`<br>`planReflections`<br>`planStepStats`<br>`planStatusIcon`<br>`planStatusLabel` | — | 123 |
| [frontend/js/history.js](../frontend/js/history.js) | 会话列表/加载及历史工作区恢复。 | `handleHistory`<br>`loadSession` | — | 54 |
| [frontend/js/knowledge.js](../frontend/js/knowledge.js) | 文档列表、格式/大小检查、上传与删除。 | `loadDocuments`<br>`handleFileSelect`<br>`uploadDocument`<br>`deleteDocument` | — | 68 |
| [frontend/js/workspace.js](../frontend/js/workspace.js) | 工作区读取、应用及原生选择器请求。 | — | — | 58 |
| [frontend/script.js](../frontend/script.js) | 挂载已组合的 Vue 应用。 | — | — | 1 |
| [frontend/style.css](../frontend/style.css) | 区域样式入口；按既有顺序导入 CSS。 | — | `css/base.css`<br>`css/workspace.css`<br>`css/chat.css`<br>`css/trace-composer.css`<br>`css/panels.css`<br>`css/overlays.css`<br>`css/responsive.css` | 7 |
| [package-lock.json](../package-lock.json) | npm 完整解析锁；结构解析并保留所有版本。 | — | — | 9347 |
| [package.json](../package.json) | 运行/开发/验证/导出脚本与精确 Node 直接依赖。 | — | — | 54 |
| [pyproject.toml](../pyproject.toml) | Python 服务依赖、Python 版本要求与 uv 源。 | — | — | 38 |
| [scripts/export-source.ts](../scripts/export-source.ts) | 生成完整树、源码 ZIP/Markdown/SHA256，并重读 ZIP 验证。 | `const`<br>`let`<br>`for`<br>`return`<br>`if` | `node:child_process`<br>`node:crypto`<br>`node:fs/promises`<br>`node:path`<br>`adm-zip` | 107 |
| [scripts/smoke.ts](../scripts/smoke.ts) | 经真实 main 启动独立端口，检查宿主、资源及插件发现。 | `if`<br>`const`<br>`for`<br>`await` | `node:assert/strict`<br>`node:events`<br>`node:net`<br>`../src/main.js` | 42 |
| [scripts/source-graph.ts](../scripts/source-graph.ts) | 使用 TypeScript AST 提取依赖并检测缺失导入/循环。 | `sourceFiles`<br>`extension`<br>`const`<br>`return`<br>`importSpecifiers`<br>`visit`<br>`dependencyGraph`<br>`for`<br>`dependencyCycles`<br>`function` | `node:fs/promises`<br>`node:path`<br>`typescript` | 86 |
| [src/agent/agent-service.ts](../src/agent/agent-service.ts) | AgentGateway 实现；请求互斥、取消、交互回答与依赖注入。 | `const`<br>`return`<br>`AgentService`<br>`private`<br>`constructor`<br>`isUserBusy`<br>`disposeUserSessions`<br>`reloadSkills`<br>`getRuntime`<br>`chat`<br>`abort`<br>`respond` | `../contracts/chat.js`<br>`./chat-turn.js`<br>`./runtime-registry.js`<br>`./runtime-types.js`<br>`./runtime-factory.js` | 107 |
| [src/agent/chat-turn.ts](../src/agent/chat-turn.ts) | 单轮重载、消息持久化、增量累积、交付收集及失败清理。 | `runChatTurn`<br>`try` | `../config/models.js`<br>`../storage/session-store.js`<br>`./prompt-images.js`<br>`./collect-artifacts.js`<br>`../contracts/chat.js`<br>`./runtime-types.js` | 84 |
| [src/agent/collect-artifacts.ts](../src/agent/collect-artifacts.ts) | 任务结束时复查成功 write/edit 的候选路径。 | `collectArtifacts`<br>`for` | `../services/artifact-service.js`<br>`../contracts/chat.js`<br>`./runtime-types.js` | 22 |
| [src/agent/event-bridge.ts](../src/agent/event-bridge.ts) | SDK 事件转 Web 事件；跟踪成功写入，输出工具结果/错误。 | `const`<br>`if`<br>`return`<br>`createEventBridge` | `node:path`<br>`@earendil-works/pi-coding-agent`<br>`../contracts/chat.js` | 82 |
| [src/agent/prompt-images.ts](../src/agent/prompt-images.ts) | 加载附件内容，根据主模型能力准备提示词与图片。 | `preparePrompt`<br>`const`<br>`return` | `node:fs/promises`<br>`../config/models.js`<br>`../contracts/chat.js` | 20 |
| [src/agent/restore-messages.ts](../src/agent/restore-messages.ts) | 把原 JSON 用户/助手记录映射为 SDK 历史消息。 | `restoredMessages`<br>`return` | `@earendil-works/pi-coding-agent`<br>`../contracts/sessions.js`<br>`../config/models.js` | 38 |
| [src/agent/runtime-factory.ts](../src/agent/runtime-factory.ts) | 装配 Pi Settings/ResourceLoader/ModelRuntime/工具，恢复历史并绑定扩展。 | `type`<br>`createRuntime`<br>`const`<br>`if`<br>`await`<br>`let`<br>`try` | `node:path`<br>`@earendil-works/pi-coding-agent`<br>`../config/paths.js`<br>`../config/models.js`<br>`../tools/knowledge-tool.js`<br>`../integrations/pi/plugin-resources.js`<br>`../storage/session-store.js`<br>`./system-prompt.js`<br>`../tools/vision-tool.js`<br>`./web-ui.js`<br>`../integrations/pi/shell-config.js`<br>`../services/artifact-service.js`<br>`../tools/delivery-tool.js`<br>`../contracts/chat.js`<br>`./runtime-types.js`<br>`./event-bridge.js`<br>`./restore-messages.js` | 178 |
| [src/agent/runtime-registry.ts](../src/agent/runtime-registry.ts) | 用户/会话 Runtime 缓存、初始化交互通道、工作区替换、资源失效。 | `runtimeKey`<br>`return`<br>`RuntimeRegistry`<br>`private`<br>`constructor`<br>`find`<br>`get`<br>`markSkillsDirty`<br>`disposeUser` | `../contracts/chat.js`<br>`./runtime-types.js` | 76 |
| [src/agent/runtime-types.ts](../src/agent/runtime-types.ts) | SDK Runtime 及其创建契约；初始化回调只暴露交互与取消能力。 | `Runtime`<br>`RuntimeOptions`<br>`RuntimeFactory` | `@earendil-works/pi-coding-agent`<br>`./web-ui.js`<br>`../contracts/artifacts.js`<br>`../contracts/chat.js` | 31 |
| [src/agent/system-prompt.ts](../src/agent/system-prompt.ts) | 按工作区构建中文宿主系统提示。 | `buildSystemPrompt`<br>`return` | — | 30 |
| [src/agent/web-ui.ts](../src/agent/web-ui.ts) | Web 对话请求、响应校验、超时/取消及终端 UI 适配。 | `type`<br>`WebUI`<br>`private`<br>`constructor`<br>`respond`<br>`cancel`<br>`context` | `node:crypto`<br>`@earendil-works/pi-coding-agent` | 144 |
| [src/bootstrap/environment.ts](../src/bootstrap/environment.ts) | SDK 导入前设置临时目录、记忆、插件和模型缓存环境。 | `configureEnvironment`<br>`const`<br>`await` | `node:path`<br>`node:fs/promises` | 37 |
| [src/bootstrap/proxy.ts](../src/bootstrap/proxy.ts) | 按已有代理环境安装 undici dispatcher，并排除回环地址。 | `configureProxy`<br>`if` | `undici` | 24 |
| [src/config/index.ts](../src/config/index.ts) | 保留旧配置导出的兼容入口。 | — | `./paths.js`<br>`./models.js`<br>`./runtime-layout.js`<br>`../shared/runtime-id.js` | 5 |
| [src/config/model-config.ts](../src/config/model-config.ts) | 构造 models.json，保留 CHAT_API_KEY 环境变量引用。 | `buildModelConfig`<br>`const`<br>`if`<br>`return` | `./models.js` | 41 |
| [src/config/models.ts](../src/config/models.ts) | 读取模型、视觉与侧车参数；只定义值。 | `ragBaseUrl`<br>`chatProvider`<br>`chatModel`<br>`chatBaseUrl`<br>`visionModel`<br>`chatSupportsImages` | `dotenv/config` | 17 |
| [src/config/paths.ts](../src/config/paths.ts) | 从进程工作目录派生宿主路径。 | `projectRoot`<br>`tmpRoot`<br>`agentDir`<br>`sessionDataDir`<br>`userSkillsDir`<br>`builtinSkillsDirs`<br>`uploadDir`<br>`configDir`<br>`permissionConfigDir`<br>`frontendDir` | `node:path` | 19 |
| [src/config/permission-config.ts](../src/config/permission-config.ts) | 构造原权限策略与附件/Skill 外部只读路径。 | `buildPermissionConfig`<br>`return` | `./paths.js` | 39 |
| [src/config/plugin-config.ts](../src/config/plugin-config.ts) | 写入 pi-lens、subagent 和 web-search 配置。 | `writePluginConfig`<br>`await` | `node:path`<br>`node:fs/promises`<br>`./paths.js` | 56 |
| [src/config/runtime-layout.ts](../src/config/runtime-layout.ts) | 创建目录并组合各配置写入；保留 vision 配置和缓存环境。 | `ensureRuntimeLayout`<br>`await`<br>`if` | `node:fs/promises`<br>`node:path`<br>`./paths.js`<br>`./models.js`<br>`./model-config.js`<br>`./permission-config.js`<br>`./plugin-config.js` | 78 |
| [src/contracts/artifacts.ts](../src/contracts/artifacts.ts) | 文件交付响应 DTO。 | `Artifact` | — | 6 |
| [src/contracts/chat.ts](../src/contracts/chat.ts) | ChatOptions、事件出口、图片和 HTTP 使用的 AgentGateway 接口。 | `StreamEvent`<br>`ChatImage`<br>`EventEmitter`<br>`ChatOptions`<br>`AgentGateway`<br>`chat`<br>`abort`<br>`respond`<br>`isUserBusy`<br>`disposeUserSessions`<br>`reloadSkills` | — | 29 |
| [src/contracts/sessions.ts](../src/contracts/sessions.ts) | 原会话与消息 JSON 格式的类型定义。 | `StoredMessage`<br>`SessionRecord` | `./artifacts.js`<br>`./chat.js` | 18 |
| [src/contracts/uploads.ts](../src/contracts/uploads.ts) | 与 Express 无关的内存上传契约。 | `UploadedFile`<br>`UploadedImage` | — | 3 |
| [src/http/app.ts](../src/http/app.ts) | Host/Origin、JSON、路由、静态文件、404 和异常中间件装配。 | `createApplication`<br>`const`<br>`return` | `./errors.js`<br>`./routes/health.js`<br>`node:path`<br>`cors`<br>`express`<br>`../contracts/chat.js`<br>`../config/paths.js`<br>`./routes/workspace.js`<br>`./routes/chat.js`<br>`./routes/sessions.js`<br>`./routes/configuration.js`<br>`./routes/sidecar.js` | 57 |
| [src/http/errors.ts](../src/http/errors.ts) | 统一 JSON 错误响应；已发送响应交给 Express 处理。 | `sendHttpError`<br>`fallback`<br>`if`<br>`const` | `express`<br>`../shared/errors.js` | 31 |
| [src/http/routes/artifacts.ts](../src/http/routes/artifacts.ts) | 仅允许已在会话中登记的文件下载。 | `artifactRoutes`<br>`const`<br>`return` | `express`<br>`../../shared/runtime-id.js`<br>`../errors.js`<br>`../../storage/session-store.js`<br>`../../services/artifact-service.js` | 29 |
| [src/http/routes/chat.ts](../src/http/routes/chat.ts) | POST SSE 与 UI 回答协议；上传和断连信号。 | `chatRoutes`<br>`const`<br>`return` | `../errors.js`<br>`express`<br>`../../shared/runtime-id.js`<br>`../../contracts/chat.js`<br>`../../shared/errors.js`<br>`../upload.js`<br>`../sse.js`<br>`../../services/workspace-service.js`<br>`../../services/upload-service.js` | 88 |
| [src/http/routes/configuration.ts](../src/http/routes/configuration.ts) | 运行配置展示和资源刷新，并挂载 Skill 路由。 | `configurationRoutes`<br>`const`<br>`return` | `./skills.js`<br>`../errors.js`<br>`express`<br>`../../contracts/chat.js`<br>`../../integrations/pi/plugin-resources.js`<br>`../../services/skill-service.js` | 53 |
| [src/http/routes/health.ts](../src/http/routes/health.ts) | 宿主存活状态及 3 秒侧车探测。 | `healthRoutes`<br>`const`<br>`return` | `express`<br>`../../integrations/rag/client.js` | 21 |
| [src/http/routes/sessions.ts](../src/http/routes/sessions.ts) | 会话列表、消息、删除，并挂载兼容的交付路由。 | `sessionsRoutes`<br>`const`<br>`return` | `./artifacts.js`<br>`../errors.js`<br>`express`<br>`../../shared/runtime-id.js`<br>`../../storage/session-store.js` | 53 |
| [src/http/routes/sidecar.ts](../src/http/routes/sidecar.ts) | 代理知识库文档列表、上传、删除，保留上游状态和正文。 | `sidecarRoutes`<br>`const`<br>`function`<br>`return` | `express`<br>`../../shared/errors.js`<br>`../upload.js`<br>`../../integrations/rag/client.js` | 67 |
| [src/http/routes/skills.ts](../src/http/routes/skills.ts) | Skill 创建/上传/删除与既有 HTTP 状态映射。 | `skillRoutes`<br>`const`<br>`return` | `express`<br>`../../contracts/chat.js`<br>`../upload.js`<br>`../errors.js`<br>`../../services/skill-service.js` | 62 |
| [src/http/routes/workspace.ts](../src/http/routes/workspace.ts) | 工作区读取/切换/选择器协议与忙碌检查。 | `workspaceRoutes`<br>`const`<br>`return` | `../errors.js`<br>`express`<br>`../../shared/runtime-id.js`<br>`../../contracts/chat.js`<br>`../../services/workspace-service.js` | 61 |
| [src/http/shared.ts](../src/http/shared.ts) | 旧 upload/sendSse/errorMessage 导出的兼容入口。 | — | `./upload.js`<br>`./sse.js`<br>`../shared/errors.js` | 4 |
| [src/http/sse.ts](../src/http/sse.ts) | 将事件编码为原 SSE data 帧。 | `sendSse` | `express` | 7 |
| [src/http/upload.ts](../src/http/upload.ts) | Multer 内存上传中间件与原大小/数量上限。 | `upload` | `multer` | 5 |
| [src/integrations/pi/plugin-resources.ts](../src/integrations/pi/plugin-resources.ts) | 逐包查找 manifest 和已发布扩展/Skill/提示模板资源。 | `selectedPackages`<br>`PluginResources`<br>`if`<br>`return`<br>`try`<br>`for`<br>`resolvePluginResources`<br>`const` | `node:fs/promises`<br>`node:path`<br>`node:module` | 116 |
| [src/integrations/pi/shell-config.ts](../src/integrations/pi/shell-config.ts) | 优先显式 PI_SHELL_PATH，再探测 Windows Git Bash。 | `resolveShellPath`<br>`if`<br>`try`<br>`return` | `node:fs`<br>`node:path`<br>`node:child_process` | 21 |
| [src/integrations/rag/client.ts](../src/integrations/rag/client.ts) | 统一 Python 侧车 HTTP 访问地址，原样交还 Response。 | `requestKnowledge`<br>`return` | `../../config/models.js` | 9 |
| [src/integrations/system/folder-picker.ts](../src/integrations/system/folder-picker.ts) | Windows PowerShell/COM 文件夹选择器；独立系统集成。 | `pickWorkspaceNative`<br>`if`<br>`const`<br>`return` | `node:child_process` | 34 |
| [src/integrations/vision/adapter.ts](../src/integrations/vision/adapter.ts) | 视觉旧包与 Pi SDK 的窄适配，拒绝不兼容 null 请求头。 | `type`<br>`delegate`<br>`createVisionDelegator`<br>`createVisionAdapter`<br>`const`<br>`return` | `@earendil-works/pi-coding-agent`<br>`@getpipher/vision（变量动态导入）` | 65 |
| [src/main.ts](../src/main.ts) | Node 入口；dotenv、代理与插件环境就绪后动态导入服务器。 | — | `dotenv/config`<br>`./bootstrap/proxy.js`<br>`./bootstrap/environment.js`<br>`./server.js` | 8 |
| [src/server.ts](../src/server.ts) | 组合配置、Agent 和 Express；监听本机，导出自身 Server 供冒烟脚本关闭。 | `server` | `./config/runtime-layout.js`<br>`./agent/agent-service.js`<br>`./http/app.js` | 13 |
| [src/services/artifact-service.ts](../src/services/artifact-service.ts) | 真实路径、目录边界与敏感文件检查；构造文件下载描述。 | `resolveWorkspaceFile`<br>`if`<br>`const`<br>`return`<br>`describeArtifact` | `node:fs/promises`<br>`node:path`<br>`../contracts/artifacts.js` | 51 |
| [src/services/skill-service.ts](../src/services/skill-service.ts) | 保留 Skill CRUD 入口，组合创建/上传业务。 | `createSkill`<br>`const`<br>`if`<br>`return`<br>`uploadSkill`<br>`overwrite` | `node:path`<br>`../contracts/uploads.js`<br>`./skills/types.js`<br>`./skills/metadata.js`<br>`./skills/installer.js`<br>`./skills/archive.js`<br>`./skills/catalog.js` | 52 |
| [src/services/skills/archive.ts](../src/services/skills/archive.ts) | ZIP 数量/大小/路径/符号链接/重名校验与内存解包。 | `unpackSkillZip`<br>`const`<br>`if`<br>`for`<br>`return` | `adm-zip`<br>`./metadata.js`<br>`./types.js` | 60 |
| [src/services/skills/catalog.ts](../src/services/skills/catalog.ts) | 用户 Skill 目录扫描、资源计数与排序。 | `listUploadedSkills`<br>`await`<br>`const`<br>`for`<br>`return` | `node:fs/promises`<br>`node:path`<br>`../../config/paths.js`<br>`./metadata.js`<br>`./types.js` | 30 |
| [src/services/skills/installer.ts](../src/services/skills/installer.ts) | 同名安装互斥、暂存、替换/回滚和删除。 | `try`<br>`install`<br>`if`<br>`let`<br>`deleteSkill`<br>`const`<br>`await` | `node:fs/promises`<br>`node:path`<br>`../../config/paths.js`<br>`../../shared/errors.js`<br>`./metadata.js`<br>`./types.js` | 78 |
| [src/services/skills/metadata.ts](../src/services/skills/metadata.ts) | Skill 名称和 YAML frontmatter 校验。 | `safeName`<br>`const`<br>`if`<br>`return`<br>`parseSkill` | `yaml`<br>`./types.js` | 25 |
| [src/services/skills/types.ts](../src/services/skills/types.ts) | Skill 目录信息与 frontmatter 元数据契约。 | `SkillInfo`<br>`SkillMeta` | — | 7 |
| [src/services/upload-service.ts](../src/services/upload-service.ts) | 聊天图片保存与视觉可访问路径校验。 | `resolveImagePath`<br>`const`<br>`if`<br>`return`<br>`saveChatImages`<br>`await` | `../contracts/uploads.js`<br>`../contracts/chat.js`<br>`node:crypto`<br>`node:fs/promises`<br>`node:path`<br>`../config/paths.js` | 53 |
| [src/services/workspace-service.ts](../src/services/workspace-service.ts) | 工作区合法性及用户选择持久化；兼容导出原生选择器。 | `validateWorkspace`<br>`if`<br>`const`<br>`await`<br>`return`<br>`getWorkspace`<br>`try`<br>`setWorkspace` | `node:fs/promises`<br>`node:path`<br>`../config/paths.js`<br>`../storage/json-store.js`<br>`../integrations/system/folder-picker.js` | 46 |
| [src/shared/errors.ts](../src/shared/errors.ts) | AppError 状态与 unknown 错误的统一消息提取。 | `AppError`<br>`constructor`<br>`errorMessage`<br>`return`<br>`errorStatus` | — | 18 |
| [src/shared/runtime-id.ts](../src/shared/runtime-id.ts) | 用户/会话 ID 规范化及校验。 | `assertRuntimeId`<br>`const`<br>`if`<br>`return` | — | 7 |
| [src/storage/json-store.ts](../src/storage/json-store.ts) | JSON 原子替换、按文件串行锁及损坏文件错误传播。 | `readJson`<br>`try`<br>`withJsonLock`<br>`const`<br>`writeJson`<br>`await` | `node:crypto`<br>`node:fs/promises`<br>`node:path` | 34 |
| [src/storage/session-store.ts](../src/storage/session-store.ts) | 按用户保存会话；消息追加、列表、读取与删除。 | `return`<br>`loadSession`<br>`const`<br>`appendMessages`<br>`listSessions`<br>`Array`<br>`deleteSession` | `node:path`<br>`../config/paths.js`<br>`./json-store.js`<br>`../contracts/sessions.js` | 75 |
| [src/tools/delivery-tool.ts](../src/tools/delivery-tool.ts) | deliver_files 参数及交付注册回调。 | `createDeliveryTool`<br>`return` | `typebox`<br>`@earendil-works/pi-coding-agent`<br>`../services/artifact-service.js` | 24 |
| [src/tools/knowledge-tool.ts](../src/tools/knowledge-tool.ts) | 每轮最多一次知识库工具；来源格式化、检索轨迹与错误。 | `RagTrace`<br>`createKnowledgeTool`<br>`let`<br>`const`<br>`return` | `typebox`<br>`@earendil-works/pi-coding-agent`<br>`../integrations/rag/client.js` | 105 |
| [src/tools/vision-tool.ts](../src/tools/vision-tool.ts) | describe_image 参数、图片路径校验与视觉委派。 | `createWebVisionTool`<br>`const`<br>`return` | `@earendil-works/pi-coding-agent`<br>`../integrations/vision/adapter.js`<br>`typebox`<br>`../config/paths.js`<br>`../services/upload-service.js` | 92 |
| [tests/agent-service.test.ts](../tests/agent-service.test.ts) | 回归测试；验证 agent service。 | `it` | `vitest`<br>`../src/agent/agent-service.js`<br>`../src/agent/runtime-registry.js`<br>`../src/contracts/chat.js`<br>`../src/agent/runtime-types.js`<br>`./helpers/runtime.js` | 135 |
| [tests/architecture.test.ts](../tests/architecture.test.ts) | 回归测试；验证 architecture。 | `const`<br>`return`<br>`it` | `node:fs/promises`<br>`node:path`<br>`vitest`<br>`../scripts/source-graph.js` | 89 |
| [tests/artifact-service.test.ts](../tests/artifact-service.test.ts) | 回归测试；验证 artifact service。 | `await`<br>`it` | `node:fs/promises`<br>`node:path`<br>`vitest`<br>`../src/config/index.js`<br>`../src/services/artifact-service.js` | 44 |
| [tests/chat-turn.test.ts](../tests/chat-turn.test.ts) | 回归测试；验证 chat turn。 | `it` | `vitest`<br>`../src/agent/chat-turn.js`<br>`../src/storage/session-store.js`<br>`../src/services/artifact-service.js`<br>`./helpers/runtime.js`<br>`../src/contracts/chat.js` | 140 |
| [tests/configuration.test.ts](../tests/configuration.test.ts) | 回归测试；验证 configuration。 | `if`<br>`return`<br>`it` | `node:path`<br>`vitest`<br>`./fixtures/runtime-config.json`<br>`../src/config/runtime-layout.js` | 56 |
| [tests/event-bridge.test.ts](../tests/event-bridge.test.ts) | 回归测试；验证 event bridge。 | `it` | `node:path`<br>`vitest`<br>`@earendil-works/pi-coding-agent`<br>`../src/agent/event-bridge.js`<br>`../src/agent/restore-messages.js` | 114 |
| [tests/fixtures/runtime-config.json](../tests/fixtures/runtime-config.json) | 从基线实现捕获的三组无密钥配置契约。 | — | — | 376 |
| [tests/frontend-state.test.ts](../tests/frontend-state.test.ts) | 回归测试；验证 frontend state。 | `const`<br>`runInNewContext`<br>`expect` | `node:fs/promises`<br>`node:vm`<br>`vitest` | 25 |
| [tests/frontend-stream.test.ts](../tests/frontend-stream.test.ts) | 回归测试；验证 frontend stream。 | `const`<br>`for`<br>`expect`<br>`await` | `node:fs/promises`<br>`node:vm`<br>`vitest` | 94 |
| [tests/helpers/runtime.ts](../tests/helpers/runtime.ts) | 只替换 SDK/UI 的可控 Runtime 和异步屏障。 | `fakeRuntime`<br>`let`<br>`const`<br>`return`<br>`deferred` | `vitest`<br>`../../src/contracts/chat.js`<br>`../../src/agent/runtime-types.js` | 45 |
| [tests/http.test.ts](../tests/http.test.ts) | 回归测试；验证 http。 | `if`<br>`const`<br>`server`<br>`await`<br>`return`<br>`it` | `node:events`<br>`node:http`<br>`vitest`<br>`../src/http/app.js`<br>`../src/contracts/chat.js` | 127 |
| [tests/runtime-factory.test.ts](../tests/runtime-factory.test.ts) | 回归测试；验证 runtime factory。 | `it` | `vitest`<br>`../src/agent/runtime-factory.js` | 128 |
| [tests/skill-service.test.ts](../tests/skill-service.test.ts) | 回归测试；验证 skill service。 | `await`<br>`it` | `node:fs/promises`<br>`vitest`<br>`adm-zip`<br>`../src/services/skill-service.js` | 90 |
| [tests/upload-service.test.ts](../tests/upload-service.test.ts) | 回归测试；验证 upload service。 | `if`<br>`await`<br>`it` | `node:fs/promises`<br>`node:path`<br>`vitest`<br>`../src/config/index.js`<br>`../src/services/upload-service.js` | 29 |
| [tests/web-ui.test.ts](../tests/web-ui.test.ts) | 回归测试；验证 web ui。 | `it` | `vitest`<br>`../src/agent/web-ui.js` | 23 |
| [tests/workspace-service.test.ts](../tests/workspace-service.test.ts) | 回归测试；验证 workspace service。 | `await`<br>`it` | `node:fs/promises`<br>`node:path`<br>`vitest`<br>`../src/config/index.js`<br>`../src/services/workspace-service.js` | 34 |
| [tmp/.gitkeep](../tmp/.gitkeep) | 只保留运行数据目录的版本控制占位。 | — | — | 1 |
| [tsconfig.json](../tsconfig.json) | NodeNext、strict、无 emit；包含源码、测试和维护脚本。 | — | — | 16 |
| [uv.lock](../uv.lock) | Python 解析锁；结构解析并保持版本。 | — | — | 3239 |
| [vitest.config.ts](../vitest.config.ts) | Node 测试发现配置，不加载模型/数据库。 | — | `vitest/config` | 9 |

## 锁文件核对

npm lockfileVersion=3，packages 条目数 650；uv package 条目数 138。两份锁文件未改变，直接依赖经 `npm ls --depth=0` 核对。

## 拆分边界

Node 聊天由 HTTP 端口、请求协调、Runtime 装配、事件转换、单轮执行和存储组成；Python 保持文档解析与混合检索服务；前端保持无构建 Vue 页面。项目携带的 Skill 文档和 Python 示例是可选资源。完整功能与真实验证范围见 [重构记录](refactoring.md)。
