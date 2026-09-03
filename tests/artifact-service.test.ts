import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { tmpRoot } from "../src/config/index.js";
import {
  describeArtifact,
  resolveWorkspaceFile,
} from "../src/services/artifact-service.js";

const fixture = path.join(tmpRoot, `artifact-test-${Date.now()}`);
beforeAll(async () => {
  await mkdir(path.join(fixture, "nested"), { recursive: true });
  await writeFile(path.join(fixture, "nested", "result.txt"), "delivered");
  await writeFile(path.join(fixture, ".env"), "test-only");
});
afterAll(() => rm(fixture, { recursive: true, force: true }));

describe("workspace artifacts", () => {
  it("resolves a real workspace file and creates its download URL", async () => {
    const result = await describeArtifact(
      fixture,
      "nested/result.txt",
      "test_user",
      "test_session",
    );
    expect(result.path).toBe("nested/result.txt");
    expect(result.size).toBe(9);
    expect(result.download_url).toContain("path=nested%2Fresult.txt");
  });
  it("rejects sensitive, absolute, parent and missing files", async () => {
    await expect(resolveWorkspaceFile(fixture, ".env")).rejects.toThrow(
      "敏感文件",
    );
    await expect(
      resolveWorkspaceFile(fixture, path.join(fixture, ".env")),
    ).rejects.toThrow("相对路径");
    await expect(resolveWorkspaceFile(fixture, "../.gitkeep")).rejects.toThrow(
      "不在工作区",
    );
    await expect(
      resolveWorkspaceFile(fixture, "missing.txt"),
    ).rejects.toThrow();
  });
});
