import path from "node:path";
import type { UploadedFile } from "../contracts/uploads.js";
import type { SkillInfo } from "./skills/types.js";
import { safeName, parseSkill } from "./skills/metadata.js";
import { install } from "./skills/installer.js";
import { unpackSkillZip } from "./skills/archive.js";
export type { SkillInfo } from "./skills/types.js";
export { deleteSkill } from "./skills/installer.js";
export { listUploadedSkills } from "./skills/catalog.js";

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
  file: UploadedFile,
  overwrite = false,
): Promise<SkillInfo> {
  if (file.buffer.length > 10 * 1024 * 1024)
    throw new Error("Skill 文件不能超过 10MB");
  if (/\.zip$/i.test(file.originalname)) {
    const { meta, files } = unpackSkillZip(file.buffer);
    return install(meta, files, overwrite);
  }
  if (!/\.md$/i.test(file.originalname))
    throw new Error("仅支持 SKILL.md 或包含一个 Skill 目录的 ZIP");
  const meta = parseSkill(
    file.buffer.toString("utf8"),
    path.basename(file.originalname, path.extname(file.originalname)),
  );
  return install(meta, new Map([["SKILL.md", file.buffer]]), overwrite);
}
