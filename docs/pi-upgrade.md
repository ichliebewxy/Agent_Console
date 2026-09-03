# Pi 0.83.0 → 0.84.4 升级记录

2026-09-03，经用户确认升级，随后用户要求使用最新版本。npm registry 返回最新稳定版 0.84.4，项目以精确版本和 lockfile 固定它。

依据：[官方变更记录](https://github.com/earendil-works/pi/blob/v0.84.4/packages/coding-agent/CHANGELOG.md) 与本机已安装的 `dist/core/*.d.ts`，而不是直接假设旧 Skill 的 API 永久不变。

## 本项目适配

| 边界 | 新版差异 | 本项目处理 |
| --- | --- | --- |
| SSE/RPC | 0.84 不再依赖累积 partial message | 继续消费 `text_delta`，宿主自行拼接，未依赖移除字段 |
| Provider headers | `ModelRegistry.getApiKeyAndHeaders()` 保留 null 删除标记 | 视觉 0.5.2 尚未兼容，独立适配器对这种 Provider 明确报错；普通字符串 headers 原样传递，不误发凭据 |
| ModelRegistry refresh | 新增 options/result 类型 | 本项目不调用旧 refresh 签名；初始化与视觉接口已核对新版类型 |
| ModelRuntime credentials | setRuntimeApiKey 的 options 语义变化 | 使用 models.json 的环境变量引用，不调用旧接口 |
| Extension UI | 新增 ui_prompt_start/end | 已有 RPC 选择/输入/取消桥可继续使用，浏览器确认回传通过 |
| Session/storage | 底层 harness 有破坏性变更 | 只通过 coding-agent SDK 的 SessionManager.inMemory 与宿主持久化，不调用被移除的底层仓库 API |

视觉包以已核对的窄接口动态装载，避免将其旧 TS 源码类型混入整个项目；没有关闭项目 strict 检查，也没有改写安装目录。

## 依赖审计

初始审计 9 项；升级上传/ZIP/YAML/开发依赖后剩旧 Pi 的 3 项锁定依赖告警。Pi 包带 npm-shrinkwrap，宿主 overrides 无效，因此在确认后升级 SDK。最新审计返回 0 vulnerabilities。

这不是完整安全认证。本产品只面向受信任本机单用户，第三方插件与 Shell 不是操作系统沙箱。

## dg-piagent Skill 更新清单（未覆盖原文件）

用户提供的 Skill 基线仍标记为 0.83.0。本次已经参考其主文件的升级协议；它链接的 `references/skill-maintenance.md` 返回 404，因此没有伪称完成整套 Skill 维护流程，也没有擅改原附件。

建议后续确认后更新：

- 顶部基线与示例安装版本调整到 0.84.4。
- `sdk_doc/04-events`、E11：强调仅消费流增量，新增 UI 等待事件。
- `sdk_doc/05-auth-model-registry`：ProviderHeaders 的 null 语义，以及 refresh / auth options 新类型。
- `sdk_doc/06-tools`：defaultTools 与可选 PowerShell；本项目仍使用已验证的 Git Bash。
- `sdk_doc/07-extensions-api`：UI prompt 事件、终止工具调用与新增上下文约定。
- 补齐缺失的维护参考文件，并将升级差异记录到 Skill CHANGELOG。

本项目升级和原 Skill 文档维护是两件事：前者已实施，后者保持待确认清单。
