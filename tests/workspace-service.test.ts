import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { tmpRoot } from "../src/config/index.js";
import {
  getWorkspace,
  setWorkspace,
  validateWorkspace,
} from "../src/services/workspace-service.js";

const fixture = path.join(tmpRoot, "test-workspace-service");
const userId = `workspace_test_${Date.now()}`;

afterAll(async () => {
  await rm(fixture, { recursive: true, force: true });
});

describe("workspace service", () => {
  it("rejects relative workspace paths", async () => {
    await expect(validateWorkspace("tmp")).rejects.toThrow("绝对路径");
  });
  it("persists an absolute directory as the selected workspace", async () => {
    await mkdir(fixture, { recursive: true });
    expect(await setWorkspace(userId, fixture)).toBe(path.resolve(fixture));
    expect(await getWorkspace(userId)).toBe(path.resolve(fixture));
  });

  it("rejects a file as workspace", async () => {
    await mkdir(fixture, { recursive: true });
    const file = path.join(fixture, "not-a-directory.txt");
    await writeFile(file, "fixture", "utf8");
    await expect(validateWorkspace(file)).rejects.toThrow("工作区必须是文件夹");
  });
});
