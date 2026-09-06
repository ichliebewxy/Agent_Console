import AdmZip from "adm-zip";
import { parseSkill } from "./metadata.js";
import type { SkillMeta } from "./types.js";

export function unpackSkillZip(buffer: Buffer): {
  meta: SkillMeta;
  files: Map<string, Buffer>;
} {
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
  return { meta, files };
}
