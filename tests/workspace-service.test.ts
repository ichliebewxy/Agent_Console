import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { tmpRoot } from "../src/config/index.js";
import {
  getWorkspace,
  isChatWorkspace,
  setWorkspace,
  validateWorkspace,
} from "../src/services/workspace-service.js";

const fixture = path.join(tmpRoot, "test-workspace-service");
const userId = `workspace_test_${Date.now()}`;

afterAll(async () => {
  await rm(fixture, { recursive: true, force: true });
});

describe("workspace service", () => {
  it("supports web chat with stable, isolated session directories and switching back", async () => {
    const chatUser = `${userId}_chat`;
    expect(await getWorkspace(chatUser)).toBe("");
    const first = await getWorkspace(chatUser, "first");
    const second = await getWorkspace(chatUser, "second");
    expect(isChatWorkspace(first)).toBe(true);
    expect(second).not.toBe(first);
    expect(await getWorkspace(chatUser, "first")).toBe(first);
    await mkdir(fixture, { recursive: true });
    await setWorkspace(chatUser, fixture);
    expect(await getWorkspace(chatUser, "first")).toBe(fixture);
    expect(await setWorkspace(chatUser, "")).toBe("");
    expect(await getWorkspace(chatUser, "first")).toBe(first);
    await expect(getWorkspace(chatUser, "../escape")).rejects.toThrow("ID");
    await rm(path.dirname(first), { recursive: true, force: true });
  });

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
