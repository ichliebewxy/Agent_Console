import path from "node:path";
import { afterEach, expect, it, vi } from "vitest";
import scenarios from "./fixtures/runtime-config.json" with { type: "json" };

const outputs = vi.hoisted(() => new Map<string, unknown>());
vi.mock("dotenv/config", () => ({}));
vi.mock("node:fs/promises", () => ({
  mkdir: vi.fn(async () => {}),
  writeFile: vi.fn(async (file: string, value: string) => {
    outputs.set(file, JSON.parse(value));
  }),
}));
afterEach(() => vi.unstubAllEnvs());

function normalize(value: unknown): unknown {
  if (typeof value === "string")
    return value
      .replaceAll(path.resolve(process.cwd()), "<project>")
      .replaceAll("\\", "/");
  if (Array.isArray(value)) return value.map(normalize);
  if (value && typeof value === "object")
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        normalize(key),
        normalize(item),
      ]),
    );
  return value;
}

for (const scenario of scenarios) {
  it(`preserves every generated configuration file: ${scenario.name}`, async () => {
    vi.resetModules();
    outputs.clear();
    for (const name of [
      "CHAT_MODEL",
      "CHAT_BASE_URL",
      "CHAT_MODEL_SUPPORTS_IMAGES",
      "CHAT_CONTEXT_WINDOW",
      "CHAT_MAX_TOKENS",
      "VISION_MODEL",
      "VISION_CONTEXT_WINDOW",
      "VISION_MAX_TOKENS",
      "RAG_BASE_URL",
      "PI_CODING_AGENT_DIR",
      "PI_PERMISSION_SYSTEM_LOGS_DIR",
      "HF_HOME",
      "TRANSFORMERS_CACHE",
    ])
      vi.stubEnv(name, (scenario.env as Record<string, string>)[name] || "");
    const { ensureRuntimeLayout } =
      await import("../src/config/runtime-layout.js");
    await ensureRuntimeLayout();
    expect(normalize(Object.fromEntries(outputs))).toEqual(scenario.outputs);
  });
}
