# Agent execution sandbox

Build once before enabling program execution:

```powershell
docker build -t agent-console-sandbox:py312 sandbox
```

Every tool execution starts a new ephemeral container with no network, a
read-only root filesystem, no Linux capabilities, `no-new-privileges`, and
CPU/memory/PID/time limits. Only the current chat session's artifact directory
is mounted read-write at `/workspace`. The backend also enforces total workspace,
file-count, and per-file quotas while the command runs. On native Linux, the
container UID/GID defaults to the non-root backend process UID/GID so the bind
mount remains writable without granting root inside the container.
