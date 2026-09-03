# 项目结构与依赖边界

## 目录职责

```text
project/
├─ src/                        # 当前生产入口：TypeScript + Pi
│  ├─ main.ts                  # 先配置代理/cache，再导入 SDK
│  ├─ server.ts                # 仅组装与监听端口
│  ├─ config/                  # 环境、模型、运行目录、插件策略
│  ├─ http/                    # Express 与 SSE 协议层
│  │  └─ routes/               # chat/workspace/sessions/configuration/sidecar
│  ├─ agent/                   # 会话生命周期、提示词、事件/UI 桥
│  ├─ tools/                   # Pi 工具定义及输入输出转换
│  ├─ services/                # 工作区/交付物/Skill/上传业务规则
│  ├─ storage/                 # 会话数据与 JSON 原子写/串行锁
│  └─ integrations/            # 外部包适配，不侵入通用业务逻辑
├─ backend/                    # 当前 Python 仅提供知识库与记忆侧车
│  ├─ rag_app.py               # FastAPI 组装与 BGE 生命周期
│  ├─ api/                     # 文档/知识检索/记忆 HTTP API
│  ├─ knowledge/               # 解析、父子分块、embedding、Milvus 写入
│  ├─ retrieval/               # 混合检索、auto-merge、改写、重排
│  ├─ memory/                  # 可选 mem0 集成
│  ├─ config/                  # 环境设置、旧数据迁移、缓存根目录
│  ├─ common/                  # DTO、编码、进度日志与失败审计
│  └─ tests/                   # 当前侧车的回归测试
├─ frontend/                   # 展示层：不执行本机文件操作
│  ├─ js/app-core.js           # 页面状态、生命周期与公共显示方法
│  ├─ js/workspace.js          # 选择/切换工作区
│  ├─ js/chat.js               # 流式会话、历史、工具交互与交付物
│  ├─ js/knowledge.js          # 文档管理
│  ├─ js/config.js             # Pi 配置与用户 Skill
│  ├─ js/memory.js             # 记忆管理
│  └─ css/                    # 按页面区域分类的样式
├─ .pi/skills/                 # 新增内置 Pi Skills
├─ agent_workspace/skills/     # 沿用的原项目 Skill 资源（只读加载）
├─ tests/                      # TypeScript 单测、接口测试、架构边界测试
├─ docs/                       # 架构、升级记录与使用说明
└─ tmp/                        # 所有默认运行数据；不提交 Git
```

## 依赖方向

```text
frontend → HTTP routes → AgentService → tools → services / integrations
                   └───────────────→ services → storage
knowledge tool / sidecar routes → Python HTTP API → knowledge / retrieval
```

- `http` 处理请求、校验入口、状态码和 SSE；通过注入的 AgentService 调用业务，不创建模型会话。
- `agent` 只编排任务和生命周期：资源加载、工具注册、消息恢复、流事件、交付登记。没有 Express 对象。
- `tools` 把 Pi 参数和结果转换为业务调用；文件路径规则在 services，不能复制到多个工具里。
- `services` 和 `storage` 不引用 Pi 或 Express，可独立测试；文件成果与网页下载展示分离。
- `integrations/vision` 集中处理社区插件与 Pi 版本差异。升级插件只改这个边界，不修改 node_modules。
- Python 使用全限定包导入，避免同一个 embedding 模块因两种导入名称被重复初始化。
- 旧 LangChain 聊天运行时及其专属测试已移除。Python 不再维护聊天 SSE 队列、Shell 工具与 Agent 调度配置。
- 前端方法按功能模块装配同一个 Vue 应用；工作区操作已从公共状态模块中拆出。无需引入第二套前端框架。

这些约束由 `tests/architecture.test.ts` 验证。`tests/http.test.ts` 注入假的 Agent，能够在不连接模型的情况下验证 SSE 和跨域拒绝。

## 新增能力放哪里

1. 通用文件/Skill 规则放 `src/services`，持久化细节放 `src/storage`。
2. 外部 API/第三方包写在 `src/integrations`，不要让业务服务直接依赖第三方实现。
3. 新 Pi 工具放 `src/tools`，在 AgentService 中注册；新 HTTP 端点放对应 `http/routes`。
4. 文档格式扩展放 `backend/knowledge`；检索策略放 `backend/retrieval`，维持现有 HTTP 契约。
5. 为边界与失败路径添加测试，再运行 `npm run check`、`npm run test:rag`。

## 保留与迁移

原 `backend/*.py` 中仍在运行的知识库和记忆实现已按上述职责移动；旧 Agent、旧路由及调试入口已清理。当前启动入口是 `npm run dev`，不再提供旧 `backend.app`。

删除前的本地恢复包放在 `tmp/cleanup-backups/<时间>/`，不参与运行与 Git 提交。恢复包包含旧 `.env`，必须按密钥文件保管，不要上传或分享。知识库数据、已有交付物、用户 Skills 和模型缓存不属于无用文件，继续保留。

工作区是用户选择的真实文件夹；`tmp` 属于宿主运行数据。二者可以不同，切换工作区不会搬动或删除之前的交付物。
