import "dotenv/config";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

export const projectRoot = path.resolve(process.cwd());
export const tmpRoot = path.join(projectRoot, "tmp");
export const agentDir = path.join(tmpRoot, "pi-agent");
export const sessionDataDir = path.join(tmpRoot, "sessions");
export const userSkillsDir = path.join(tmpRoot, "user-skills");
export const builtinSkillsDirs = [
  path.join(projectRoot, ".pi", "skills"),
  path.join(projectRoot, "agent_workspace", "skills"),
];
export const uploadDir = path.join(tmpRoot, "uploads");
export const configDir = path.join(tmpRoot, "config");
export const permissionConfigDir = path.join(
  agentDir,
  "extensions",
  "pi-permission-system",
);
export const frontendDir = path.join(projectRoot, "frontend");
export const ragBaseUrl = (
  process.env.RAG_BASE_URL || "http://127.0.0.1:8091"
).replace(/\/$/, "");

export const chatProvider = "ergouzi";
export const chatModel = process.env.CHAT_MODEL || "deepseek-chat";
export const chatBaseUrl = (
  process.env.CHAT_BASE_URL || "https://api.deepseek.com"
).replace(/\/$/, "");
export const visionModel =
  process.env.VISION_MODEL ||
  (chatBaseUrl.includes("deepseek") ? "deepseek-v4-flash-vision-exp" : "");
export const chatSupportsImages = /^(1|true|yes|on)$/i.test(
  process.env.CHAT_MODEL_SUPPORTS_IMAGES || "",
);

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

  const models = [
    {
      id: chatModel,
      name: `二狗子主模型 (${chatModel})`,
      reasoning: true,
      input: chatSupportsImages ? ["text", "image"] : ["text"],
      contextWindow: Number(process.env.CHAT_CONTEXT_WINDOW || 128000),
      maxTokens: Number(process.env.CHAT_MAX_TOKENS || 16384),
    },
  ];
  if (visionModel && visionModel !== chatModel) {
    models.push({
      id: visionModel,
      name: `二狗子视觉模型 (${visionModel})`,
      reasoning: true,
      input: ["text", "image"],
      contextWindow: Number(process.env.VISION_CONTEXT_WINDOW || 128000),
      maxTokens: Number(process.env.VISION_MAX_TOKENS || 16384),
    });
  }

  await writeFile(
    path.join(agentDir, "models.json"),
    JSON.stringify(
      {
        providers: {
          [chatProvider]: {
            baseUrl: chatBaseUrl,
            api: "openai-completions",
            apiKey: "$CHAT_API_KEY",
            models,
          },
        },
      },
      null,
      2,
    ),
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
    JSON.stringify(
      {
        debugLog: false,
        permissionReviewLog: true,
        yoloMode: false,
        permission: {
          "*": "allow",
          path: {
            "*": "allow",
            "*.env": "deny",
            "*.env.*": "deny",
            "*.env.example": "allow",
            "*.pem": "deny",
            "*.key": "deny",
          },
          read: "allow",
          write: "allow",
          edit: "allow",
          bash: {
            "*": "allow",
            "rm -rf /": "deny",
            "rm -rf ~": "deny",
            "git push --force *": "deny",
          },
          mcp: { "*": "allow" },
          skill: { "*": "allow" },
          external_directory: {
            "*": "deny",
          },
          external_directory_read: Object.fromEntries(
            [uploadDir, userSkillsDir, ...builtinSkillsDirs]
              .flatMap((directory) => [directory, `${directory}/*`])
              .map((directory) => [directory.replace(/\\/g, "/"), "allow"]),
          ),
        },
      },
      null,
      2,
    ),
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

export function assertRuntimeId(value: unknown, fallback: string): string {
  const text = typeof value === "string" ? value.trim() : fallback;
  if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(text)) {
    throw new Error("用户或会话 ID 格式无效");
  }
  return text;
}
