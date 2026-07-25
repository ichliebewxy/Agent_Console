# OpenCLI permission levels

| Level | Examples | Automatic handling |
| --- | --- | --- |
| P0 discovery | version, help, list, skills read, validate | Allow |
| P1 read | public query, state, find, get, extract | Allow when in user scope |
| P2 sensitive/local write | auth status, network detail/raw, screenshot, download/export | Review target and output |
| P3 external write | post, send, follow, create, purchase, model change | Require exact user request |
| P4 high risk | delete, archive, upload, eval, auto-approve, install plugin/external CLI | Deny by default |

OpenCLI plugins and external adapters are executable code. `plugin install`,
`external install`, `external register --install`, and global npm installation
can execute package-manager hooks and alter local files. Do not perform them as a
side effect of a search request. The daemon on port 19825 has no built-in auth;
never expose it beyond the local machine.
