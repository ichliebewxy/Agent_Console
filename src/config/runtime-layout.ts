import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import {
  tmpRoot,
  agentDir,
  sessionDataDir,
  userSkillsDir,
  uploadDir,
  configDir,
  permissionConfigDir,
} from "./paths.js";
import { visionModel, chatProvider } from "./models.js";
import { buildModelConfig } from "./model-config.js";
import { buildPermissionConfig } from "./permission-config.js";
import { writePluginConfig } from "./plugin-config.js";

export async function ensureRuntimeLayout(): Promise<void> {
  await Promise.all(
    [
      tmpRoot,
      agentDir,
      sessionDataDir,
      userSkillsDir,
      uploadDir,
      configDir,
      permissionConfigDir,
      path.join(tmpRoot, "pi-lens"),
      path.join(agentDir, "extensions", "subagent"),
    ].map((directory) => mkdir(directory, { recursive: true })),
  );

  await writePluginConfig();

  await writeFile(
    path.join(agentDir, "models.json"),
    JSON.stringify(buildModelConfig(), null, 2),
    "utf8",
  );

  if (visionModel) {
    await writeFile(
      path.join(agentDir, "vision.json"),
      JSON.stringify(
        {
          enabled: true,
          provider: chatProvider,
          model: visionModel,
          textOnlyPasteMode: "auto",
          cacheEnabled: true,
          cachePersist: true,
          auditLog: true,
          auditLogPath: path.join(tmpRoot, "vision-audit.jsonl"),
        },
        null,
        2,
      ),
      "utf8",
    );
  }

  await writeFile(
    path.join(permissionConfigDir, "config.json"),
    JSON.stringify(buildPermissionConfig(), null, 2),
    "utf8",
  );

  process.env.PI_CODING_AGENT_DIR = agentDir;
  process.env.PI_PERMISSION_SYSTEM_LOGS_DIR = path.join(
    tmpRoot,
    "permission-logs",
  );
  process.env.HF_HOME ||= path.join(tmpRoot, "huggingface");
  process.env.TRANSFORMERS_CACHE ||= path.join(
    tmpRoot,
    "huggingface",
    "transformers",
  );
}
