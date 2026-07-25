# Node library surface

If a future implementation uses the OpenCLI Node package instead of its CLI,
import only package exports such as `/registry`, `/errors`, `/types`, `/utils`,
`/logger`, `/launcher`, `/browser/cdp`, `/browser/page`, `/browser/utils`,
`/download`, `/download/article-download`, `/download/media-download`,
`/download/progress`, and `/pipeline`.

Registry exports include `cli`, `Strategy`, `getRegistry`, `fullName`,
`registerCommand`, and lifecycle hooks. Prefer the CLI in this project because it
keeps the live adapter registry and output formats in one reviewed execution path.
