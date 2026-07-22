---
name: opencli
description: Use OpenCLI for live public queries, browser/page inspection and interaction, downloads/exports, network inspection, and supported desktop-app control. Trigger when a task mentions OpenCLI, browser automation, a live website/app query, downloading remote content, or inspecting browser network traffic.
---

# OpenCLI workflow

Use this skill whenever the delegated task needs OpenCLI rather than a generic
web guess. OpenCLI has a live command registry; never hard-code an adapter's
arguments when the registry or command help can answer the question.

## Safety and execution

- Run every OpenCLI command through the reviewed `bash` tool. Keep the current
  session's `backend/tmp/<session-key>/` as the working directory.
- Do not expose cookies, authorization headers, tokens, private network bodies,
  screenshots, or downloaded files unless the user explicitly requests them.
- Treat `access=read` as read-only only for the remote side: download/export,
  screenshot, and save commands still write local files and require a clear
  output path inside the current session directory.
- `access=write`, login/refresh, messaging, posting, follow/like, upload,
  delete/archive, plugin install, external install, arbitrary `eval`, and
  auto-approve are side effects. Execute only when the delegated task explicitly
  requests that exact side effect; otherwise report the missing authorization.
- Never expose the OpenCLI daemon port publicly. Do not bypass CAPTCHA, paywall,
  permissions, browser risk controls, or a site's terms.

## Discovery-first workflow

1. Check the CLI version and live registry when starting an unfamiliar workflow:
   `opencli --version` and `opencli list -f json`.
2. Filter the JSON locally by intent, site/app, `access`, `strategy`, and
   `browser`. Do not inject the whole registry into the model context.
3. Read exact help before execution:
   `opencli <site-or-app> --help -f yaml`, then
   `opencli <site-or-app> <command> --help -f yaml`.
4. Execute with `-f json` when available and verify exit code and result shape.
   When invoking `bash`, pass `opencli_access="read"` only for the exact live
   registry row marked `access=read`; pass `opencli_access="write"` plus
   `user_authorized_side_effect=true` only when the delegated user task asks for
   that exact external write. Leave both values at their defaults when the row
   is unknown. P4 rows remain blocked by the execution layer.
5. Return a concise evidence report to the main Agent, including the selected
   command, access level, verification, and any generated relative files.

## Choose a reference

- Registry, top-level commands, and output formats: `references/cli-surface.md`.
- Browser sessions, page state, forms, screenshots, and network: `references/browser.md`.
- Search/query routing across public sources and logged-in sites: `references/search-routing.md`.
- Downloads and exports to the session directory: `references/downloads.md`.
- Desktop-app and Electron/CDP control: `references/app-control.md`.
- Permission levels and high-risk operations: `references/permissions.md`.
- Installation, doctor, and package API notes: `references/setup-and-doctor.md` and
  `references/library-api.md`.

## Browser invariant

For browser workflows use one named session per concurrent task. Open or bind,
inspect `state`, use returned element refs, perform one interaction, then inspect
state again. Prefer `extract` for page content and `network` only when the task
needs API evidence. Use `network --detail`/`--raw` only for an explicitly scoped
request because response bodies can contain private account data.
