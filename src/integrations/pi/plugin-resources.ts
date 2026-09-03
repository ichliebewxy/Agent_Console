import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

export const selectedPackages = [
  { feature: "上下文压缩", package: "@hypabolic/pi-hypa" },
  { feature: "网页与外部资料", package: "pi-web-access" },
  { feature: "子 Agent", package: "pi-subagents" },
  { feature: "人机确认", package: "@juicesharp/rpiv-ask-user-question" },
  { feature: "代码质量", package: "pi-lens" },
  { feature: "权限与审计", package: "@gotgenes/pi-permission-system" },
  { feature: "长期记忆", package: "pi-memory" },
  { feature: "图片识别", package: "@getpipher/vision" },
] as const;

export type PluginResources = {
  extensionPaths: string[];
  skillPaths: string[];
  promptPaths: string[];
  errors: Array<{ package: string; error: string }>;
};

function entries(value: unknown): string[] {
  if (typeof value === "string") return [value];
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

async function packageManifest(
  packageName: string,
): Promise<{ path: string; manifest: any }> {
  try {
    const manifestPath = require.resolve(`${packageName}/package.json`);
    return {
      path: manifestPath,
      manifest: JSON.parse(await readFile(manifestPath, "utf8")),
    };
  } catch {
    let current = path.dirname(require.resolve(packageName));
    for (let depth = 0; depth < 12; depth += 1) {
      const candidate = path.join(current, "package.json");
      try {
        const manifest = JSON.parse(await readFile(candidate, "utf8"));
        if (manifest.name === packageName) return { path: candidate, manifest };
      } catch {
        /* keep walking to the package root */
      }
      const parent = path.dirname(current);
      if (parent === current) break;
      current = parent;
    }
    throw new Error(`无法定位 ${packageName} 的 package.json`);
  }
}

async function addExisting(
  target: string[],
  candidates: string[],
): Promise<void> {
  for (const candidate of candidates) {
    try {
      await stat(candidate);
      target.push(candidate);
    } catch {
      /* Some community manifests publish optional paths that are not in the tarball. */
    }
  }
}

export async function resolvePluginResources(): Promise<PluginResources> {
  const result: PluginResources = {
    extensionPaths: [],
    skillPaths: [],
    promptPaths: [],
    errors: [],
  };
  for (const item of selectedPackages) {
    try {
      const { path: manifestPath, manifest } = await packageManifest(
        item.package,
      );
      const root = path.dirname(manifestPath);
      const pi = manifest.pi || {};
      // The Web host uses @getpipher/vision's public delegator API directly;
      // its TUI extension expects a different lifecycle/config host.
      if (item.package !== "@getpipher/vision") {
        await addExisting(
          result.extensionPaths,
          entries(pi.extensions).map((entry) => path.resolve(root, entry)),
        );
      }
      await addExisting(
        result.skillPaths,
        entries(pi.skills).map((entry) => path.resolve(root, entry)),
      );
      await addExisting(
        result.promptPaths,
        entries(pi.prompts).map((entry) => path.resolve(root, entry)),
      );
    } catch (error) {
      result.errors.push({
        package: item.package,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }
  return result;
}
