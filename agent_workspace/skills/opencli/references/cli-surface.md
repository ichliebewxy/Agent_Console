# Live CLI surface

OpenCLI v1.8.6 currently exposes a live registry of roughly 1300 adapter commands
across websites and desktop apps. The registry is authoritative because built-in
adapters, `~/.opencli/clis` overrides, plugins, and external CLI definitions can
change it at runtime.

## Discovery

```bash
opencli --version
opencli list -f json
opencli skills list -f json
opencli plugin list -f json
opencli external list -f json
opencli adapter status -f json
```

Common top-level commands are `list`, `validate`, `verify`, `skills`, `auth`,
`convention-audit`, `browser`, `doctor`, `completion`, `plugin`, `adapter`,
`profile`, `daemon`, and `external`. Always read `--help -f yaml` for the exact
version instead of assuming one exists.

## Common flags and exit codes

Use `-f json|yaml|plain|table|md|csv`, `--trace off|on|retain-on-failure`, and
`-v` when supported. Meaningful exits include 0 success, 1 execution failure,
2 usage error, 66 no data, 69 Browser Bridge unavailable, 75 timeout, 77 not
authenticated, 78 configuration error, and 130 interrupted.
