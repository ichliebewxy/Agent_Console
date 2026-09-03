import { existsSync } from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

export function resolveShellPath(): string | undefined {
  if (process.env.PI_SHELL_PATH) return process.env.PI_SHELL_PATH;
  if (process.platform !== "win32") return undefined;
  try {
    const git = execFileSync("where.exe", ["git.exe"], {
      encoding: "utf8",
      windowsHide: true,
    })
      .trim()
      .split(/\r?\n/)[0];
    const bash = path.resolve(path.dirname(git), "..", "bin", "bash.exe");
    if (existsSync(bash)) return bash;
  } catch {
    /* SDK will use its normal shell resolution. */
  }
  return undefined;
}
