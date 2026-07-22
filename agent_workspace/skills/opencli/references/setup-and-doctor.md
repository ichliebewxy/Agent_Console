# Setup and doctor

The authoritative runtime currently requires Node.js >=20. A typical local
setup is:

```bash
npm install -g @jackwener/opencli
opencli --version
opencli doctor
```

`doctor` performs live probes and may start or inspect the daemon, Browser Bridge,
Chrome profile, and version compatibility. It is not a pure read-only check.
Public/local adapters can work while the daemon is stopped; browser and cookie
strategies usually need the extension and an authenticated browser session.
