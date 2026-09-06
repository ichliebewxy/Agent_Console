import { spawn } from "node:child_process";

export async function pickWorkspaceNative(): Promise<string | null> {
  if (process.platform !== "win32") return null;
  const script = [
    "$shell = New-Object -ComObject Shell.Application",
    "$folder = $shell.BrowseForFolder(0, '选择二狗子助手工作区', 0, 0)",
    "if ($folder) { [Console]::OutputEncoding = [Text.UTF8Encoding]::new(); $folder.Self.Path }",
  ].join("; ");
  return await new Promise((resolve, reject) => {
    const child = spawn(
      "powershell.exe",
      ["-NoProfile", "-STA", "-Command", script],
      {
        windowsHide: false,
        stdio: ["ignore", "pipe", "pipe"],
      },
    );
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8").on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.setEncoding("utf8").on("data", (chunk) => {
      stderr += chunk;
    });
    child.once("error", reject);
    child.once("close", (code) => {
      if (code !== 0)
        reject(new Error(stderr.trim() || `目录选择器退出码 ${code}`));
      else resolve(stdout.trim() || null);
    });
  });
}
