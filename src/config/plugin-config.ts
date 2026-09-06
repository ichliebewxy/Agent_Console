import path from "node:path";
import { writeFile } from "node:fs/promises";
import { agentDir, tmpRoot } from "./paths.js";

export async function writePluginConfig(): Promise<void> {
  await writeFile(
    path.join(tmpRoot, "pi-lens", "config.json"),
    JSON.stringify(
      {
        format: { enabled: false },
        autofix: { enabled: false },
        ignore: ["tmp/**", "node_modules/**", ".venv/**"],
      },
      null,
      2,
    ),
  );
  await writeFile(
    path.join(agentDir, "extensions", "subagent", "config.json"),
    JSON.stringify(
      {
        artifactDir: "temp",
        defaultSessionDir: path.join(tmpRoot, "subagent-sessions"),
      },
      null,
      2,
    ),
  );
  await writeFile(
    path.join(agentDir, "web-search.json"),
    JSON.stringify(
      {
        workflow: "none",
        autoOpenBrowser: false,
        allowBrowserCookies: false,
        searchRouting: {
          providers: ["exa", "duckduckgo"],
          fallbackOn: [
            "unsupported",
            "transient",
            "quota",
            "network",
            "invalid-response",
          ],
        },
        githubClone: {
          enabled: true,
          clonePath: path.join(tmpRoot, "web-repos"),
          cloneTimeoutSeconds: 30,
        },
      },
      null,
      2,
    ),
  );
}
