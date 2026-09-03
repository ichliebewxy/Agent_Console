import { readFile } from "node:fs/promises";
import { afterAll, describe, expect, it } from "vitest";
import AdmZip from "adm-zip";
import {
  createSkill,
  deleteSkill,
  listUploadedSkills,
  uploadSkill,
} from "../src/services/skill-service.js";

const createdName = `test-skill-${Date.now()}`;
const uploadedName = `uploaded-skill-${Date.now()}`;

afterAll(async () => {
  await Promise.all([deleteSkill(createdName), deleteSkill(uploadedName)]);
});

describe("skill service", () => {
  it("creates a valid SKILL.md and lists it", async () => {
    const info = await createSkill({
      name: createdName,
      description: "测试创建与热加载前的 catalog 解析。",
      instructions: "# Workflow\n\n1. Do the test task.",
    });
    expect(await readFile(info.path, "utf8")).toContain(`name: ${createdName}`);
    expect(
      (await listUploadedSkills()).some((skill) => skill.name === createdName),
    ).toBe(true);
  });

  it("accepts an uploaded Markdown skill and rejects unsafe names", async () => {
    const body = Buffer.from(
      `---\nname: ${uploadedName}\ndescription: uploaded test\n---\n\n# Workflow\n`,
      "utf8",
    );
    const file = {
      originalname: "SKILL.md",
      buffer: body,
      size: body.length,
    } as Express.Multer.File;
    expect((await uploadSkill(file)).name).toBe(uploadedName);
    await expect(
      createSkill({ name: "../escape", description: "x", instructions: "x" }),
    ).rejects.toThrow("Skill 名称只能包含");
  });

  it("preserves an existing skill when an overwrite ZIP is invalid", async () => {
    const info = (await listUploadedSkills()).find(
      (skill) => skill.name === createdName,
    )!;
    const original = await readFile(info.path, "utf8");
    const zip = new AdmZip();
    zip.addFile("skill/SKILL.md", Buffer.from(original));
    zip.addFile("skill/bad:key.txt", Buffer.from("bad"));
    const buffer = zip.toBuffer();
    await expect(
      uploadSkill(
        {
          originalname: "bad.zip",
          buffer,
          size: buffer.length,
        } as Express.Multer.File,
        true,
      ),
    ).rejects.toThrow("不安全路径");
    expect(await readFile(info.path, "utf8")).toBe(original);
  });

  it("uploads ZIP resources and normalizes the main filename", async () => {
    const zip = new AdmZip();
    zip.addFile(
      "bundle/skill.md",
      Buffer.from(
        `---\nname: ${uploadedName}\ndescription: resources test\n---\n\nRead references/test.txt`,
      ),
    );
    zip.addFile("bundle/references/test.txt", Buffer.from("resource"));
    const buffer = zip.toBuffer();
    const info = await uploadSkill(
      {
        originalname: "valid.zip",
        buffer,
        size: buffer.length,
      } as Express.Multer.File,
      true,
    );
    expect(info.resources).toBe(1);
    expect(await readFile(info.path, "utf8")).toContain("resources test");
  });
});
