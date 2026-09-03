import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import { tmpRoot, uploadDir } from "../src/config/index.js";
import { resolveImagePath } from "../src/services/upload-service.js";

await mkdir(uploadDir, { recursive: true });
const root = await mkdtemp(path.join(tmpRoot, "image-path-test-"));
const workspace = path.join(root, "workspace");
await mkdir(workspace);
await writeFile(path.join(workspace, "inside.png"), "test fixture");
await writeFile(path.join(root, "outside.png"), "test fixture");
afterAll(async () => {
  if (!root.startsWith(tmpRoot + path.sep))
    throw new Error("Unsafe test cleanup");
  await rm(root, { recursive: true, force: true });
});
describe("image path boundary", () => {
  it("accepts a file in the chosen workspace", async () => {
    expect(await resolveImagePath(workspace, "inside.png")).toBe(
      path.join(workspace, "inside.png"),
    );
  });
  it("rejects another directory even when the path exists", async () => {
    await expect(resolveImagePath(workspace, "../outside.png")).rejects.toThrow(
      "只能识别",
    );
  });
});
