# 完整交付文件树

共 171 个版本管理文件（含新增文件）；不包含第三方安装目录、真实密钥或用户运行数据。由 npm run export:source 生成。

```text
project/
├─ .pi/
│  ├─ skills/
│  │  ├─ knowledge-base/
│  │  │  └─ SKILL.md
│  │  └─ skill-authoring/
│  │     └─ SKILL.md
│  └─ settings.json
├─ agent_workspace/
│  ├─ skills/
│  │  ├─ agent-builder/
│  │  │  ├─ references/
│  │  │  │  ├─ agent-philosophy.md
│  │  │  │  ├─ minimal-agent.py
│  │  │  │  ├─ subagent-pattern.py
│  │  │  │  └─ tool-templates.py
│  │  │  ├─ scripts/
│  │  │  │  └─ init_agent.py
│  │  │  └─ SKILL.md
│  │  ├─ code-review/
│  │  │  └─ SKILL.md
│  │  ├─ mcp-builder/
│  │  │  └─ SKILL.md
│  │  ├─ opencli/
│  │  │  ├─ agents/
│  │  │  │  └─ openai.yaml
│  │  │  ├─ references/
│  │  │  │  ├─ app-control.md
│  │  │  │  ├─ browser.md
│  │  │  │  ├─ cli-surface.md
│  │  │  │  ├─ downloads.md
│  │  │  │  ├─ library-api.md
│  │  │  │  ├─ permissions.md
│  │  │  │  ├─ search-routing.md
│  │  │  │  └─ setup-and-doctor.md
│  │  │  └─ SKILL.md
│  │  └─ pdf/
│  │     └─ SKILL.md
│  └─ README.md
├─ backend/
│  ├─ api/
│  │  ├─ __init__.py
│  │  ├─ routes_documents.py
│  │  └─ routes_knowledge.py
│  ├─ common/
│  │  ├─ __init__.py
│  │  ├─ encoding_utils.py
│  │  └─ schemas.py
│  ├─ config/
│  │  ├─ __init__.py
│  │  ├─ runtime_data.py
│  │  └─ settings.py
│  ├─ knowledge/
│  │  ├─ __init__.py
│  │  ├─ document_loader.py
│  │  ├─ embedding.py
│  │  ├─ milvus_client.py
│  │  ├─ milvus_writer.py
│  │  ├─ parent_chunk_store.py
│  │  └─ word_document_reader.py
│  ├─ retrieval/
│  │  ├─ __init__.py
│  │  ├─ chat_models.py
│  │  ├─ query_expansion.py
│  │  ├─ rag_expanded.py
│  │  ├─ rag_pipeline.py
│  │  ├─ rag_state.py
│  │  ├─ rag_utils.py
│  │  └─ retrieval_steps.py
│  ├─ tests/
│  │  ├─ __init__.py
│  │  ├─ test_document_loader.py
│  │  ├─ test_knowledge_service.py
│  │  └─ test_routes_documents.py
│  ├─ __init__.py
│  ├─ preload_embedding_model.py
│  └─ rag_app.py
├─ docs/
│  ├─ architecture.md
│  ├─ configuration.md
│  ├─ dependencies.mmd
│  ├─ file-tree.md
│  ├─ pi-upgrade.md
│  ├─ refactoring.md
│  └─ source-inventory.md
├─ frontend/
│  ├─ css/
│  │  ├─ base.css
│  │  ├─ chat.css
│  │  ├─ overlays.css
│  │  ├─ panels.css
│  │  ├─ responsive.css
│  │  ├─ trace-composer.css
│  │  └─ workspace.css
│  ├─ js/
│  │  ├─ app-core.js
│  │  ├─ chat-messages.js
│  │  ├─ chat-stream.js
│  │  ├─ chat.js
│  │  ├─ config.js
│  │  ├─ formatters.js
│  │  ├─ history.js
│  │  ├─ knowledge.js
│  │  └─ workspace.js
│  ├─ index.html
│  ├─ script.js
│  └─ style.css
├─ scripts/
│  ├─ export-source.ts
│  ├─ smoke.ts
│  └─ source-graph.ts
├─ src/
│  ├─ agent/
│  │  ├─ agent-service.ts
│  │  ├─ chat-turn.ts
│  │  ├─ collect-artifacts.ts
│  │  ├─ event-bridge.ts
│  │  ├─ prompt-images.ts
│  │  ├─ restore-messages.ts
│  │  ├─ runtime-factory.ts
│  │  ├─ runtime-registry.ts
│  │  ├─ runtime-types.ts
│  │  ├─ system-prompt.ts
│  │  └─ web-ui.ts
│  ├─ bootstrap/
│  │  ├─ environment.ts
│  │  └─ proxy.ts
│  ├─ config/
│  │  ├─ index.ts
│  │  ├─ model-config.ts
│  │  ├─ models.ts
│  │  ├─ paths.ts
│  │  ├─ permission-config.ts
│  │  ├─ plugin-config.ts
│  │  └─ runtime-layout.ts
│  ├─ contracts/
│  │  ├─ artifacts.ts
│  │  ├─ chat.ts
│  │  ├─ sessions.ts
│  │  └─ uploads.ts
│  ├─ http/
│  │  ├─ routes/
│  │  │  ├─ artifacts.ts
│  │  │  ├─ chat.ts
│  │  │  ├─ configuration.ts
│  │  │  ├─ health.ts
│  │  │  ├─ sessions.ts
│  │  │  ├─ sidecar.ts
│  │  │  ├─ skills.ts
│  │  │  └─ workspace.ts
│  │  ├─ app.ts
│  │  ├─ errors.ts
│  │  ├─ shared.ts
│  │  ├─ sse.ts
│  │  └─ upload.ts
│  ├─ integrations/
│  │  ├─ pi/
│  │  │  ├─ plugin-resources.ts
│  │  │  └─ shell-config.ts
│  │  ├─ rag/
│  │  │  └─ client.ts
│  │  ├─ system/
│  │  │  └─ folder-picker.ts
│  │  └─ vision/
│  │     └─ adapter.ts
│  ├─ services/
│  │  ├─ skills/
│  │  │  ├─ archive.ts
│  │  │  ├─ catalog.ts
│  │  │  ├─ installer.ts
│  │  │  ├─ metadata.ts
│  │  │  └─ types.ts
│  │  ├─ artifact-service.ts
│  │  ├─ skill-service.ts
│  │  ├─ upload-service.ts
│  │  └─ workspace-service.ts
│  ├─ shared/
│  │  ├─ errors.ts
│  │  └─ runtime-id.ts
│  ├─ storage/
│  │  ├─ json-store.ts
│  │  └─ session-store.ts
│  ├─ tools/
│  │  ├─ delivery-tool.ts
│  │  ├─ knowledge-tool.ts
│  │  └─ vision-tool.ts
│  ├─ main.ts
│  └─ server.ts
├─ tests/
│  ├─ fixtures/
│  │  └─ runtime-config.json
│  ├─ helpers/
│  │  └─ runtime.ts
│  ├─ agent-service.test.ts
│  ├─ architecture.test.ts
│  ├─ artifact-service.test.ts
│  ├─ chat-turn.test.ts
│  ├─ configuration.test.ts
│  ├─ event-bridge.test.ts
│  ├─ frontend-state.test.ts
│  ├─ frontend-stream.test.ts
│  ├─ http.test.ts
│  ├─ runtime-factory.test.ts
│  ├─ skill-service.test.ts
│  ├─ upload-service.test.ts
│  ├─ web-ui.test.ts
│  └─ workspace-service.test.ts
├─ tmp/
│  └─ .gitkeep
├─ .env.example
├─ .gitignore
├─ .python-version
├─ docker-compose.yml
├─ package-lock.json
├─ package.json
├─ pyproject.toml
├─ README.md
├─ tsconfig.json
├─ uv.lock
└─ vitest.config.ts
```
