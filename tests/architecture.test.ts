import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { describe, expect, it } from "vitest";

async function sources(root: string, extension: string): Promise<string[]> {
  const entries = await readdir(root, { withFileTypes: true });
  const nested = await Promise.all(
    entries
      .filter((entry) => entry.isDirectory() && entry.name !== "__pycache__")
      .map((entry) => sources(path.join(root, entry.name), extension)),
  );
  return [
    ...entries
      .filter((entry) => entry.isFile() && entry.name.endsWith(extension))
      .map((entry) => path.join(root, entry.name)),
    ...nested.flat(),
  ];
}

describe("architecture boundaries", () => {
  it("keeps storage and file services independent of Pi and HTTP", async () => {
    for (const file of [
      ...(await sources("src/services", ".ts")),
      ...(await sources("src/storage", ".ts")),
    ]) {
      const code = await readFile(file, "utf8");
      expect(code, file).not.toMatch(
        /from ["'](?:express|@earendil-works|.*\/http\/|.*\/agent\/)/,
      );
    }
  });
  it("keeps RAG independent of the retired LangChain chat runtime", async () => {
    for (const folder of [
      "api",
      "config",
      "common",
      "knowledge",
      "retrieval",
    ]) {
      for (const file of await sources(`backend/${folder}`, ".py")) {
        expect(await readFile(file, "utf8"), file).not.toMatch(
          /(?:from|import) backend\.legacy/,
        );
      }
    }
  });
});
