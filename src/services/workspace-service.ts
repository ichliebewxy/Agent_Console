import { access, stat } from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { configDir, projectRoot } from "../config/index.js";
import { readJson, writeJson, withJsonLock } from "../storage/json-store.js";

type WorkspaceMap = Record<string, string>;
const storeFile = path.join(configDir, "workspaces.json");

export async function validateWorkspace(candidate: string): Promise<string> {
  if (!candidate || typeof candidate !== "string")
    throw new Error("请选择工作区目录");
  if (!path.isAbsolute(candidate.trim()))
    throw new Error("工作区必须使用绝对路径");
  const resolved = path.resolve(candidate.trim());
  await access(resolved);
  if (!(await stat(resolved)).isDirectory())
    throw new Error("工作区必须是文件夹");
  return resolved;
}

export async function getWorkspace(userId: string): Promise<string> {
  const entries = await readJson<WorkspaceMap>(storeFile, {});
  const candidate = Object.hasOwn(entries, userId)
    ? entries[userId]
    : projectRoot;
  try {
    return await validateWorkspace(candidate);
  } catch {
    return projectRoot;
  }
}

export async function setWorkspace(
  userId: string,
  candidate: string,
): Promise<string> {
  const workspace = await validateWorkspace(candidate);
  return withJsonLock(storeFile, async () => {
    const entries = await readJson<WorkspaceMap>(storeFile, {});
    entries[userId] = workspace;
    await writeJson(storeFile, entries);
    return workspace;
  });
}

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
