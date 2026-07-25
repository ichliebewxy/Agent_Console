# Agent Workspace

This directory stores the skill packages available to the `skills` specialist.

- `skills/`: skill packages. Each package must contain `SKILL.md` with YAML
  frontmatter (`name` and `description`). Full instructions are loaded only
  after the specialist selects an exact catalog name.
- Runtime working files and downloadable artifacts live separately under
  `backend/tmp/<session-key>/` and are ignored by Git.

The runtime prevents skill resources from escaping their package root and keeps
workspace file tools rooted in the current session directory. Commands run
locally with that temporary directory as their current working directory.

The initial skill packages were migrated from `D:\learn_claude_code\skills`.
