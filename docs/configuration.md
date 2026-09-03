# 配置说明

`.env` 只放密钥和需要覆盖的设置。省略变量与设置为空串并不总是等价；不用的设置直接省略。修改后重启 Node 和 Python。`tmp/pi-agent` 中的宿主生成配置会在启动时重写，长期配置应修改 `.env` 或 `src/config/index.ts`。

完整启动与操作步骤见 [README](../README.md)。以下默认值以本仓库实现为准。

## 最小配置

```dotenv
CHAT_API_KEY=填写你的密钥
CHAT_MODEL=deepseek-chat
EMBEDDING_LOCAL_FILES_ONLY=false
```

只使用 Node Agent 时无需配置 embedding、Milvus、rerank。使用知识库时，Python 的评估与扩展复用 `CHAT_API_KEY` 和 `CHAT_BASE_URL`；如果账户不支持默认评估模型，显式设置 `GRADE_MODEL`。

## Node Web 与模型

| 变量 | 默认值 / 用途 |
| --- | --- |
| `CHAT_API_KEY` | 无，主模型认证；生成的 models.json 引用这个环境变量，不写入明文密钥 |
| `CHAT_MODEL` | Node 默认 `deepseek-chat`；Python 的默认值为 `deepseek-v4-flash`，建议在 `.env` 显式设置以保持一致 |
| `CHAT_BASE_URL` | `https://api.deepseek.com` |
| `CHAT_MODEL_SUPPORTS_IMAGES` | `false`，是否把上传图片直接交给主模型 |
| `VISION_MODEL` | DeepSeek 接口默认 `deepseek-v4-flash-vision-exp`；其他接口需显式指定可用视觉模型 |
| `CHAT_CONTEXT_WINDOW` / `VISION_CONTEXT_WINDOW` | `128000` |
| `CHAT_MAX_TOKENS` / `VISION_MAX_TOKENS` | `16384` |
| `PORT` | `3000`，Node 固定监听 `127.0.0.1` |
| `RAG_BASE_URL` | `http://127.0.0.1:8091` |
| `PI_SHELL_PATH` | 自动寻找 Git Bash，仅自动识别失败时指定 `bash.exe` 绝对路径 |
| `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` | Node 遵循已有代理；宿主额外将 localhost、127.0.0.1、::1 排除在代理之外 |

Node 使用 OpenAI 兼容模型协议。Python 的 `build_chat_model` 明确使用 DeepSeek provider；换供应商时，需要检查 Python 相关性评估 / 查询扩展的适配，不能仅以 Node 聊天成功推断全部功能可用。

改变 `RAG_BASE_URL` 不会改变 Python 的监听端口。自定义端口可以分开启动：

```powershell
# .env 中先设置 RAG_BASE_URL=http://127.0.0.1:8092
uv run uvicorn backend.rag_app:app --host 127.0.0.1 --port 8092
# 另开一个终端，在项目根执行
npm start
```

## 知识库与嵌入模型

| 变量 | 默认值 / 用途 |
| --- | --- |
| `GRADE_MODEL` | `deepseek-v4-flash`，初次检索后的相关性评估 |
| `QUERY_EXPANSION_MODEL` | 跟随 Python 的 `CHAT_MODEL`，生成 Step-back / HyDE 文本；策略选择本身使用 `CHAT_MODEL` |
| `MILVUS_HOST` / `MILVUS_PORT` | `127.0.0.1` / `19530` |
| `MILVUS_COLLECTION` | `embeddings_bge_m3` |
| `MILVUS_TIMEOUT` | `8` 秒 |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` |
| `EMBEDDING_DEVICE` | `cpu`；其他设备需要对应可用的 PyTorch 环境 |
| `EMBEDDING_DIM` / `MILVUS_DENSE_DIM` | `1024` / 跟随 `EMBEDDING_DIM`；必须与模型输出和既有集合匹配 |
| `EMBEDDING_BATCH_SIZE` | `16`，至少为 1 |
| `EMBEDDING_LOCAL_FILES_ONLY` | `false`；设为 true 后只读本地模型缓存 |
| `BM25_STATE_PATH` | 默认 `tmp/knowledge/bm25_state.json`；自定义时建议使用绝对路径，相对路径按启动目录解析 |
| `AUTO_MERGE_ENABLED` | `true` |
| `AUTO_MERGE_THRESHOLD` | `2`，至少多少个同父子块命中才尝试向上合并 |
| `LEAF_RETRIEVE_LEVEL` | `3`；当前入库只将 L3 写入 Milvus，不应随意改为 1 或 2 |
| `HF_HOME` | 默认 `tmp/huggingface`，已有环境配置优先 |
| `DASHSCOPE_API_KEY` | 可选，PDF/PPTX 内嵌图片的 Qwen 描述，与聊天视觉插件独立 |

当前 embedding 模块将 Hugging Face 下载端点设为 `https://hf-mirror.com`；环境里的 `HF_ENDPOINT` 会被该实现覆盖。镜像不可达时需调整 `backend/knowledge/embedding.py` 的设置，或准备完整缓存后开启离线模式。

预下载命令：

```powershell
uv run python -m backend.preload_embedding_model
```

更换向量模型不仅是改维度。旧向量与新模型的空间可能不兼容，应使用新的 `MILVUS_COLLECTION` 并重新入库，同时管理配套的 BM25 / 父块数据。

## 可选外部重排

同时提供以下三项才启用：

```dotenv
RERANK_MODEL=BAAI/bge-reranker-v2-m3
RERANK_BINDING_HOST=https://api.siliconflow.cn/v1/rerank
RERANK_API_KEY=填写你的重排服务密钥
```

缺任一项则使用原有排序。配置接口时使用完整 `/v1/rerank` 地址，或只填写站点根地址；代码会在不以 `/v1/rerank` 结尾时追加该路径。重排请求超时为 15 秒，错误写入检索轨迹，并回退到重排前结果。

## Pi-memory

宿主固定把 `PI_MEMORY_DIR` 设为 `<项目根>/tmp/pi-memory`，所以在 `.env` 里覆盖该变量目前无效。长期记忆、每日记录、待办以及删除恢复记录都保存在这里；qmd 索引由插件和 qmd 管理。

下面这些可选项由已安装的 `pi-memory` 读取，宿主没有覆盖：

| 变量 | 默认值 / 用途 |
| --- | --- |
| `PI_MEMORY_SNAPSHOT` | `stable`，按检查点刷新注入；`per-turn` 每轮重建上下文 |
| `PI_MEMORY_QMD_UPDATE` | `background`，写入后后台更新索引 / 向量；还支持 `manual`、`off` |
| `PI_MEMORY_QMD_SEARCH_TIMEOUT_MS` | `60000`，显式记忆搜索超时，单位毫秒 |
| `PI_MEMORY_NO_SEARCH` | 未设置；设为 `1` 禁用 per-turn 模式的自动搜索注入，不关闭显式工具 |
| `PI_MEMORY_EXIT_SUMMARY` | 默认启用；`0/off/false/no` 禁止插件退出总结 |
| `PI_MEMORY_EXIT_SUMMARY_MODEL` | 未设置，默认跟随会话；可指定插件支持的 `provider/model-id` |
| `PI_MEMORY_EXIT_SUMMARY_TIMEOUT_MS` | `10000`，退出总结超时 |

退出总结还依赖宿主实际触发插件生命周期，不能将其当作每条消息都会持久化的保证。需要保存重要偏好时，应明确让 Agent 调用 `memory_write` 并检查返回结果。

检查记忆状态优先使用对话中的 `memory_status` 工具。`memory_search` 需要 qmd，基础读写不需要。工具清单与操作示例见 [README](../README.md#4-pi-记忆和插件)。

## 已移除设置

`MEMORY_ENABLED`、`MEM0_DIR`、`MEM0_MODEL` 已不再读取，旧 `/memory/*` 接口和网页 mem0 面板也已下线。原 `.env` 若仍有这些变量，可以删除对应行；它们不会控制 Pi 记忆。旧 `tmp/mem0` 数据没有自动迁移至插件。

旧聊天运行时的地图 / MCP 包装器、OpenCLI 包装器、Plan-and-Execute、`BACKEND_TMP_DIR`、`AGENT_SKILLS_DIR` 等设置也不再由宿主读取。沿用的 Skill 资源保留自己的运行说明，不能把 Skill 脚本的独立参数误认为宿主配置。

## 配置与数据位置

宿主默认运行数据位于项目 `tmp/`，文件任务使用用户选定的工作区，二者是不同概念。Docker 默认把数据写入项目 `volumes/`；通过 Compose 的 `DOCKER_VOLUME_DIRECTORY` 可改变挂载根目录。

模型、权限、网页插件和子 Agent 的宿主配置由 `src/config/index.ts` 生成；扩展环境由 `src/main.ts` 初始化。新增高级配置时同步更新实现、`.env.example`（若属于常用项）和本文。
