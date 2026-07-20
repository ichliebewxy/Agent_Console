# Agent Workspace

This directory is the sandboxed workspace owned by the `skills` specialist.

- `skills/`: skill packages. Each package must contain `SKILL.md` with YAML
  frontmatter (`name` and `description`). Full instructions are loaded only
  after the specialist selects an exact catalog name.
- `files/<session-key>/`: isolated per-chat working files and downloadable
  artifacts. Runtime contents are ignored by Git.

The runtime prevents skill resources from escaping their package root and
prevents workspace file tools from escaping the current session directory.
Programs run only in an ephemeral Docker container where that directory is
mounted as `/workspace`; the container has no network or host filesystem access.

The initial skill packages were migrated from `D:\learn_claude_code\skills`.
