import YAML from "yaml";
import type { SkillMeta } from "./types.js";

export function safeName(value: string): string {
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
export function parseSkill(text: string, fallbackName = ""): SkillMeta {
  const match = text.match(/^---\s*\r?\n([\s\S]*?)\r?\n---\s*(?:\r?\n|$)/);
  if (!match) throw new Error("SKILL.md 缺少 YAML frontmatter");
  const metadata = YAML.parse(match[1]) || {};
  const name = safeName(String(metadata.name || fallbackName));
  const description = String(metadata.description || "").trim();
  if (!description) throw new Error("SKILL.md frontmatter 缺少 description");
  return { name, description };
}
