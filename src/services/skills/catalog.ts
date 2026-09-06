import { mkdir, readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { userSkillsDir } from "../../config/paths.js";
import { parseSkill } from "./metadata.js";
import type { SkillInfo } from "./types.js";

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
