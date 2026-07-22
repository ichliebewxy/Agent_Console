# Browser and page workflows

Browser commands use a named session:

```bash
opencli browser <session> <command> [args] -f json
```

Session/navigation commands include `bind`, `unbind`, `close`, `open`, `back`,
and `scroll`. Tab commands include `tab list`, `tab new`, `tab select`, and
`tab close`.

Observe before acting with `state`, `find`, `frames`, `screenshot`, `console`,
or `analyze`. Read values with `get title|url|text|value|html|attributes` and
extract structured content with `extract`.

Interact with refs from the latest state using `click`, `dblclick`, `hover`,
`focus`, `type`, `fill`, `select`, `check`, `uncheck`, `upload`, `drag`, `keys`,
`dialog accept|dismiss`, and `wait`. `eval` accepts arbitrary JavaScript and is
high risk even when a skill description calls it read-only; require an explicit
user request and keep the script minimal.

Use `network` for API evidence. `--detail <key>`, `--raw`, `--all`, `--filter`,
`--since`, `--until`, `--follow`, `--failed`, `--max-body`, and `--ttl` can expose
private response data; use the smallest scope and redact secrets in the report.
