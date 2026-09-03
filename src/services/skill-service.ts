import {
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import AdmZip from "adm-zip";
import YAML from "yaml";
import { userSkillsDir } from "../config/index.js";

export type SkillInfo = {
  name: string;
  description: string;
  path: string;
  resources: number;
};
type SkillMeta = Pick<SkillInfo, "name" | "description">;
const installing = new Set<string>();

function safeName(value: string): string {
  const name = String(value || "")
    .trim()
    .toLowerCase();
  if (
    !/^[a-z0-9][a-z0-9-]{0,63}$/.test(name) ||
    /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(name)
  )
    throw new Error(
      "Skill 名称只能包含小写字母、数字和连字符，且不能使用系统保留名",
    );
  return name;
}
function parseSkill(text: string, fallbackName = ""): SkillMeta {
  const match = text.match(/^---\s*\r?\n([\s\S]*?)\r?\n---\s*(?:\r?\n|$)/);
  if (!match) throw new Error("SKILL.md 缺少 YAML frontmatter");
  const metadata = YAML.parse(match[1]) || {};
  const name = safeName(String(metadata.name || fallbackName));
  const description = String(metadata.description || "").trim();
  if (!description) throw new Error("SKILL.md frontmatter 缺少 description");
  return { name, description };
}
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
async function install(
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
    if (present && !overwrite) throw new Error("Skill 已存在");
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

export async function createSkill(input: {
  name: string;
  description: string;
  instructions: string;
  overwrite?: boolean;
}): Promise<SkillInfo> {
  const name = safeName(input.name);
  const description = String(input.description || "").trim();
  const instructions = String(input.instructions || "").trim();
  if (!description || !instructions) throw new Error("描述和指令不能为空");
  const text =
    "---\nname: " +
    name +
    "\ndescription: " +
    JSON.stringify(description) +
    "\n---\n\n" +
    instructions +
    "\n";
  return install(
    { name, description },
    new Map([["SKILL.md", Buffer.from(text)]]),
    Boolean(input.overwrite),
  );
}
export async function uploadSkill(
  file: Express.Multer.File,
  overwrite = false,
): Promise<SkillInfo> {
  if (file.buffer.length > 10 * 1024 * 1024)
    throw new Error("Skill 文件不能超过 10MB");
  if (/\.zip$/i.test(file.originalname))
    return uploadZip(file.buffer, overwrite);
  if (!/\.md$/i.test(file.originalname))
    throw new Error("仅支持 SKILL.md 或包含一个 Skill 目录的 ZIP");
  const meta = parseSkill(
    file.buffer.toString("utf8"),
    path.basename(file.originalname, path.extname(file.originalname)),
  );
  return install(meta, new Map([["SKILL.md", file.buffer]]), overwrite);
}
async function uploadZip(
  buffer: Buffer,
  overwrite: boolean,
): Promise<SkillInfo> {
  const entries = new AdmZip(buffer)
    .getEntries()
    .filter((entry) => !entry.isDirectory);
  if (
    entries.length > 200 ||
    entries.reduce((sum, item) => sum + item.header.size, 0) > 30 * 1024 * 1024
  )
    throw new Error("ZIP 解压后不能超过 30MB 或 200 个文件");
  for (const entry of entries) {
    const normalized = entry.entryName.replace(/\\/g, "/");
    if (
      normalized.startsWith("/") ||
      normalized
        .split("/")
        .some(
          (part) =>
            !part ||
            part === ".." ||
            /[<>:"|?*\x00-\x1f]/.test(part) ||
            /[ .]$/.test(part) ||
            /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(part),
        )
    )
      throw new Error("ZIP 包含不安全路径");
    if (((entry.attr >>> 16) & 0xf000) === 0xa000)
      throw new Error("ZIP 不能包含符号链接");
  }
  const skills = entries.filter((entry) =>
    /(^|\/)SKILL\.md$/i.test(entry.entryName.replace(/\\/g, "/")),
  );
  if (skills.length !== 1)
    throw new Error("每个 ZIP 必须且只能包含一个 SKILL.md");
  const skillEntry = skills[0];
  const meta = parseSkill(skillEntry.getData().toString("utf8"));
  const normalizedSkill = skillEntry.entryName.replace(/\\/g, "/");
  const prefix = normalizedSkill.slice(0, -"SKILL.md".length);
  const files = new Map<string, Buffer>();
  for (const entry of entries) {
    const normalized = entry.entryName.replace(/\\/g, "/");
    if (!normalized.startsWith(prefix)) continue;
    const relative =
      entry === skillEntry ? "SKILL.md" : normalized.slice(prefix.length);
    if (
      [...files.keys()].some(
        (key) => key.toLowerCase() === relative.toLowerCase(),
      )
    )
      throw new Error("ZIP 包含重复文件");
    files.set(relative, entry.getData());
  }
  return install(meta, files, overwrite);
}
export async function deleteSkill(name: string): Promise<void> {
  const validated = safeName(name);
  if (installing.has(validated)) throw new Error("该 Skill 正在更新");
  await rm(path.join(userSkillsDir, validated), {
    recursive: true,
    force: true,
  });
}
export async function listUploadedSkills(): Promise<SkillInfo[]> {
  await mkdir(userSkillsDir, { recursive: true });
  const directories = await readdir(userSkillsDir, { withFileTypes: true });
  const results: SkillInfo[] = [];
  for (const entry of directories) {
    if (!entry.isDirectory() || entry.name.startsWith(".")) continue;
    const skillPath = path.join(userSkillsDir, entry.name, "SKILL.md");
    try {
      const meta = parseSkill(await readFile(skillPath, "utf8"), entry.name);
      const resources = (
        await readdir(path.join(userSkillsDir, entry.name), {
          recursive: true,
          withFileTypes: true,
        })
      ).filter(
        (item) => item.isFile() && item.name.toLowerCase() !== "skill.md",
      ).length;
      results.push({ ...meta, path: skillPath, resources });
    } catch {
      /* Invalid directories aren't usable skills. */
    }
  }
  return results.sort((a, b) => a.name.localeCompare(b.name));
}
