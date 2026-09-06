import { access, stat } from "node:fs/promises";
import path from "node:path";
import { configDir, projectRoot } from "../config/paths.js";
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

export { pickWorkspaceNative } from "../integrations/system/folder-picker.js";
