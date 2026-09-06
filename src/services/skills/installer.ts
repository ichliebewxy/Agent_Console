import { mkdir, mkdtemp, rename, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { userSkillsDir } from "../../config/paths.js";
import { AppError } from "../../shared/errors.js";
import { safeName } from "./metadata.js";
import type { SkillInfo, SkillMeta } from "./types.js";

const installing = new Set<string>();
async function exists(target: string): Promise<boolean> {
  try {
    await stat(target);
    return true;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return false;
    throw error;
  }
}

/** Validate first, stage beside the destination, then replace with rollback. */
export async function install(
  meta: SkillMeta,
  files: Map<string, Buffer>,
  overwrite: boolean,
): Promise<SkillInfo> {
  if (installing.has(meta.name))
    throw new Error("该 Skill 正在更新，请稍后重试");
  installing.add(meta.name);
  let staging = "";
  let preserveBackup = false;
  try {
    await mkdir(userSkillsDir, { recursive: true });
    const directory = path.join(userSkillsDir, meta.name);
    const present = await exists(directory);
    if (present && !overwrite) throw new AppError("Skill 已存在", 409);
    staging = await mkdtemp(path.join(userSkillsDir, ".upload-"));
    const prepared = path.join(staging, "prepared");
    await mkdir(prepared);
    for (const [relative, content] of files) {
      const target = path.join(prepared, relative);
      await mkdir(path.dirname(target), { recursive: true });
      await writeFile(target, content);
    }
    const backup = path.join(staging, "previous");
    if (present) await rename(directory, backup);
    try {
      await rename(prepared, directory);
    } catch (error) {
      if (present) {
        try {
          await rename(backup, directory);
        } catch {
          preserveBackup = true;
          throw new Error("恢复失败，原 Skill 备份保留于 " + backup);
        }
      }
      throw error;
    }
    return {
      ...meta,
      path: path.join(directory, "SKILL.md"),
      resources: files.size - 1,
    };
  } finally {
    installing.delete(meta.name);
    // Always an immediate child created by mkdtemp under userSkillsDir.
    if (staging && !preserveBackup)
      await rm(staging, { recursive: true, force: true });
  }
}

export async function deleteSkill(name: string): Promise<void> {
  const validated = safeName(name);
  if (installing.has(validated)) throw new Error("该 Skill 正在更新");
  await rm(path.join(userSkillsDir, validated), {
    recursive: true,
    force: true,
  });
}
