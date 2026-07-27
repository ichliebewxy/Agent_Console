# Desktop applications and Electron/CDP

Supported app adapters include `antigravity`, `chatgpt-app`, `chatwise`, `codex`,
`cursor`, `discord-app`, `doubao-app`, `qoder`, `trae-cn`, and `trae-solo` in the
researched registry. The list is dynamic; check `opencli list -f json` first.

Use `opencli <app> --help -f yaml`, then the exact command help. Read/history/
projects/status are usually read operations; send/new/rename/pin/archive/model
and approval commands are writes. Electron/CDP adapters generally require the
target app to be running and may need `OPENCLI_CDP_ENDPOINT`.

`trae-cn approve`, `ask --auto-approve`, plugin installation, external install,
and commands that alter messages, files, accounts, or models are high-risk and
must not be guessed from a vague request.
