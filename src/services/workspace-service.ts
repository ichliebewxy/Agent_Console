import { access, mkdir, stat } from "node:fs/promises";
import path from "node:path";
import { configDir, tmpRoot } from "../config/paths.js";
import { assertRuntimeId } from "../shared/runtime-id.js";
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

const chatWorkspaceRoot = path.join(tmpRoot, "chat-workspaces");

export function isChatWorkspace(workspace: string): boolean {
  const relative = path.relative(chatWorkspaceRoot, path.resolve(workspace));
  return (
    !!relative &&
    relative !== ".." &&
    !relative.startsWith(`..${path.sep}`) &&
    !path.isAbsolute(relative)
  );
}

// An empty selection represents web chat; actual files belong to one session.
export async function getWorkspace(
  userId: string,
  sessionId?: string,
): Promise<string> {
  const entries = await readJson<WorkspaceMap>(storeFile, {});
  const candidate = Object.hasOwn(entries, userId) ? entries[userId] : "";
  if (candidate) return validateWorkspace(candidate);
  if (sessionId === undefined) return "";
  const workspace = path.join(
    chatWorkspaceRoot,
    assertRuntimeId(userId, "default_user"),
    assertRuntimeId(sessionId, "default_session"),
  );
  await mkdir(workspace, { recursive: true });
  return workspace;
}

export async function setWorkspace(
  userId: string,
  candidate: string,
): Promise<string> {
  const workspace = candidate.trim() ? await validateWorkspace(candidate) : "";
  return withJsonLock(storeFile, async () => {
    const entries = await readJson<WorkspaceMap>(storeFile, {});
    entries[userId] = workspace;
    await writeJson(storeFile, entries);
    return workspace;
  });
}

export { pickWorkspaceNative } from "../integrations/system/folder-picker.js";
