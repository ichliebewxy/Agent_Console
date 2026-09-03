# 配置说明

`.env` 只放密钥和需要覆盖的设置。留空不一定等价于删除变量；不使用的选项直接省略。修改后重启 Web 和 Python 侧车。模板不包含真实密钥，不要覆盖已经配置好的 `.env`。

## 最小配置

```dotenv
CHAT_API_KEY=填写你的密钥
CHAT_MODEL=deepseek-chat
EMBEDDING_LOCAL_FILES_ONLY=false
```

`CHAT_MODEL` 应填写实际账户可用的模型 ID，同时供 Pi、查询扩展和 mem0 使用。知识库相关性评估另由 `GRADE_MODEL` 控制。BGE 已下载到 `tmp/huggingface` 时可把离线模式设为 `true`，首次下载则使用 `false`。

可选重排需要同时填写 `RERANK_MODEL`、`RERANK_BINDING_HOST`、`RERANK_API_KEY`；任意一项缺失时不会执行重排。已有重排服务配置无需调整。

## 按需覆盖的默认值

| 设置 | 默认值 / 用途 |
| --- | --- |
| `CHAT_BASE_URL` | `https://api.deepseek.com`，主模型兼容接口 |
| `CHAT_MODEL_SUPPORTS_IMAGES` | `false`，主模型是否直接接收图片 |
| `VISION_MODEL` | DeepSeek 接口默认 `deepseek-v4-flash-vision-exp`；其他接口需显式指定视觉模型 |
| `CHAT_CONTEXT_WINDOW` / `VISION_CONTEXT_WINDOW` | `128000` |
| `CHAT_MAX_TOKENS` / `VISION_MAX_TOKENS` | `16384` |
| `PORT` | Web 监听 `3000` |
| `RAG_BASE_URL` | `http://127.0.0.1:8091`；侧车端口须与启动命令一致 |
| `PI_SHELL_PATH` | 自动寻找 Git Bash，仅自动识别失败时指定 |
| `GRADE_MODEL` | `deepseek-v4-flash`，知识库相关性评估 |
| `QUERY_EXPANSION_MODEL` | 跟随 `CHAT_MODEL` |
| `MILVUS_HOST` / `MILVUS_PORT` | `127.0.0.1` / `19530` |
| `MILVUS_COLLECTION` / `MILVUS_TIMEOUT` | `embeddings_bge_m3` / `8` 秒 |
| `EMBEDDING_MODEL` / `EMBEDDING_DEVICE` | `BAAI/bge-m3` / `cpu` |
| `EMBEDDING_DIM` / `MILVUS_DENSE_DIM` | `1024` / 跟随 `EMBEDDING_DIM`；必须匹配模型与现有集合 |
| `EMBEDDING_BATCH_SIZE` | `16` |
| `BM25_STATE_PATH` | 默认 `tmp/knowledge/bm25_state.json` |
| `AUTO_MERGE_ENABLED` / `AUTO_MERGE_THRESHOLD` | `true` / `2`，父子块自动合并 |
| `LEAF_RETRIEVE_LEVEL` | `3` |
| `MEMORY_ENABLED` | `true`，侧车记忆面板启用状态，不控制 Pi 记忆插件 |
| `MEM0_DIR` / `MEM0_MODEL` | `tmp/mem0` / 跟随 `CHAT_MODEL` |
| `DASHSCOPE_API_KEY` | 可选，知识库 PDF/PPT 内嵌图片的 Qwen 描述；与聊天视觉插件独立 |

模型选择必须匹配供应商支持能力；不要仅修改向量维度来适配新模型，已有集合需要重新建库。修改端口需同步代理与侧车跨域配置。

旧聊天运行时的地图/MCP、OpenCLI 包装器、Plan-and-Execute、`BACKEND_TMP_DIR`、`AGENT_SKILLS_DIR` 等配置不再读取，已从示例与 Python 设置中移除。Pi 的工具、Skills 和插件改由 TypeScript 宿主管理；内置 OpenCLI Skill 资源仍保留，其自身安装说明不受影响。

运行目录固定在项目 `tmp/`；用户选择的工作区仅用于任务读写与文件交付。`.env` 和清理备份中含有密钥，不能提交到 Git 或共享给他人。
