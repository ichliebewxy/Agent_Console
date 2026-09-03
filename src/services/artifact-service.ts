import { realpath, stat } from "node:fs/promises";
import path from "node:path";

export type Artifact = {
  name: string;
  path: string;
  size: number;
  download_url: string;
};

export async function resolveWorkspaceFile(
  workspace: string,
  relative: string,
): Promise<string> {
  if (!relative || path.isAbsolute(relative) || relative.includes(":"))
    throw new Error("请提供工作区内相对路径");
  const root = await realpath(workspace);
  const target = await realpath(path.resolve(root, relative));
  const resolved = path.relative(root, target);
  if (
    !resolved ||
    resolved.startsWith(`..${path.sep}`) ||
    resolved === ".." ||
    path.isAbsolute(resolved)
  )
    throw new Error("文件不在工作区内");
  if (
    resolved
      .split(/[\\/]/)
      .some(
        (part) => /^\.env(?:\.|$)/i.test(part) || /\.(pem|key)$/i.test(part),
      )
  )
    throw new Error("敏感文件不能作为交付物下载");
  if (!(await stat(target)).isFile()) throw new Error("交付物必须是文件");
  return target;
}

export async function describeArtifact(
  workspace: string,
  relative: string,
  userId: string,
  sessionId: string,
): Promise<Artifact> {
  const target = await resolveWorkspaceFile(workspace, relative);
  const normalized = path
    .relative(await realpath(workspace), target)
    .replace(/\\/g, "/");
  return {
    name: path.basename(target),
    path: normalized,
    size: (await stat(target)).size,
    download_url: `/artifacts/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}?path=${encodeURIComponent(normalized)}`,
  };
}
