import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  dependencyCycles,
  dependencyGraph,
  importSpecifiers,
} from "../scripts/source-graph.js";

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
  it("resolves all relative imports and has no cycles, including type and dynamic imports", async () => {
    expect(dependencyCycles(await dependencyGraph("src"))).toEqual([]);
  });

  it("keeps HTTP independent of Agent implementations and data layers independent of frameworks", async () => {
    for (const [file, dependencies] of await dependencyGraph("src")) {
      const relative = path
        .relative(path.resolve("src"), file)
        .replace(/\\/g, "/");
      const targets = dependencies.map((item) =>
        path.relative(path.resolve("src"), item).replace(/\\/g, "/"),
      );
      if (relative.startsWith("http/"))
        expect(targets, relative).not.toContainEqual(
          expect.stringMatching(/^agent\//),
        );
      if (/^(contracts|shared|storage|services)\//.test(relative)) {
        const code = await readFile(file, "utf8");
        expect(code, relative).not.toMatch(/Express\.|\bany\b/);
        expect(importSpecifiers(file, code), relative).not.toContainEqual(
          expect.stringMatching(/^(express|multer|@earendil-works)/),
        );
        expect(targets, relative).not.toContainEqual(
          expect.stringMatching(/^(agent|http|tools)\//),
        );
      }
      if (relative.startsWith("storage/"))
        expect(targets, relative).not.toContainEqual(
          expect.stringMatching(/^services\//),
        );
      if (/^(contracts|shared)\//.test(relative))
        expect(
          targets.every((item) => /^(contracts|shared)\//.test(item)),
          relative,
        ).toBe(true);
    }
  });
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
