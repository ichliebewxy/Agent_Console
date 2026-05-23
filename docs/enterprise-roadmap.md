# NebulaNest 企业化路线与压测计划

## 当前已落地

- 上传入口增加文件名路径穿越校验、空文件/大小限制和内容 SHA-256。
- 文档入库增加本地 ingestion manifest，记录版本、状态、chunk 数和重复内容，后续可平滑迁移到 Postgres。
- 新增工具策略引擎雏形，支持 tenant 校验、工具权限、高风险工具人工审批。
- 新增 pytest 用例和 GitHub Actions 质量门禁。

## 近期路线

| 阶段 | 目标 | 验收标准 |
|---|---|---|
| 工程清淤 | 统一 `uvicorn backend.app:app` 启动；把实验脚本迁入 `experiments/`；补 License/安全文档 | CI 全绿，根目录只保留运行与交付必需文件 |
| 平台元数据 | 用 Postgres 替换核心 JSON 状态；文档、chunk、会话、审核、失败事件都带 `tenant_id` | 删除本地 JSON 后核心链路仍可运行 |
| 治理安全 | OIDC/JWT、RBAC、对象级权限、审计日志、工具 policy gate | 跨 tenant 访问被拒绝，高风险工具必须审核 |
| 异步入库 | 上传只创建 job，解析、embedding、Milvus 写入放到 worker | 重复上传不重复入库，失败可重试，队列可回压 |
| 观测评测 | OpenTelemetry、Prometheus/Grafana、golden queries、RAG 回归 | 每次发布有 p50/p95、Recall@k、MRR 和 groundedness 报告 |

## 压测计划

先做三类压测，不要一上来压全链路：

1. `/chat/stream` 流式压测：记录 TTFB、完整回答耗时、错误率、上游模型 429/5xx 比例。
2. `/documents/upload` 入库压测：按 TXT、PDF、CSV 三种文件分别测小文件和大文件，记录解析耗时、embedding 耗时、Milvus 写入耗时。
3. 混合场景压测：50 到 200 并发聊天，同时 10 到 20 并发上传，观察队列回压、Milvus 延迟和工具失败事件。

建议工具组合：

- `k6`：压 SSE 和 HTTP API，生成 p50/p95/p99。
- `locust`：模拟真实用户行为，适合聊天、上传、审核混合场景。
- `pytest-benchmark`：做单函数基准，例如 chunking、RRF fusion、rerank adapter。
- `Prometheus + Grafana`：压测时同步看 CPU、内存、Milvus、请求延迟和错误率。

第一版目标值：

| 指标 | 建议目标 |
|---|---|
| Chat TTFB | p50 < 800ms，p95 < 2s |
| Chat E2E | p50 < 4s，p95 < 8s |
| 上传入库 | 小文档 < 10s，大文档随页数近似线性增长 |
| 工具成功率 | > 99% |
| 重复上传 | 不重复写 Milvus，不重复生成 embedding |
| 混合并发 | 50 并发聊天 + 10 并发上传无明显错误峰值 |

## 评测数据

准备 100 到 300 条 golden queries，覆盖：

- 精确命中文档事实。
- 需要多段上下文合成的问题。
- 需要 Step-back/HyDE 扩展的问题。
- 检索不到时应拒答或说明依据不足的问题。
- 工具调用成功、超时、失败回调三种路径。

每条样本至少包含 `question`、`expected_sources`、`reference_answer`、`tenant_id` 和 `risk_level`。后续把 Recall@k、MRR、citation precision、answer groundedness 都纳入发布前回归。
