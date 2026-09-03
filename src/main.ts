import path from "node:path";
import { mkdir } from "node:fs/promises";
import "dotenv/config";
import { EnvHttpProxyAgent, setGlobalDispatcher } from "undici";

// Node fetch does not otherwise honor the user's HTTP(S)_PROXY settings.
if (
  process.env.HTTP_PROXY ||
  process.env.HTTPS_PROXY ||
  process.env.http_proxy ||
  process.env.https_proxy
) {
  setGlobalDispatcher(
    new EnvHttpProxyAgent({
      noProxy: [
        process.env.NO_PROXY || process.env.no_proxy,
        "localhost",
        "127.0.0.1",
        "::1",
      ]
        .filter(Boolean)
        .join(","),
    }),
  );
}

// Set Pi's agent directory before importing the SDK or any community extension.
// Several extensions read getAgentDir() during module/session initialization.
const runtimeRoot = path.resolve(process.cwd(), "tmp");
await mkdir(path.join(runtimeRoot, "cache"), { recursive: true });
process.env.TMP =
  process.env.TEMP =
  process.env.TMPDIR =
    path.join(runtimeRoot, "cache");
process.env.XDG_CACHE_HOME = path.join(runtimeRoot, "cache");
process.env.PI_MEMORY_DIR = path.join(runtimeRoot, "pi-memory");
process.env.HYPA_PI_CONFIG = path.join(runtimeRoot, "config", "hypa.json");
process.env.PI_LENS_HOME = path.join(runtimeRoot, "pi-lens");
process.env.PILENS_DATA_DIR = path.join(runtimeRoot, "pi-lens", "projects");
process.env.PI_LENS_CONFIG_PATH = path.join(
  runtimeRoot,
  "pi-lens",
  "config.json",
);
process.env.PI_LENS_DISABLE_LSP_INSTALL = "1";
process.env.PI_LENS_DISABLE_TOOL_INSTALL = "1";
process.env.PI_LENS_STARTUP_MODE = "quick";
process.env.PI_CODING_AGENT_DIR = path.join(runtimeRoot, "pi-agent");
process.env.PI_PERMISSION_SYSTEM_LOGS_DIR = path.join(
  runtimeRoot,
  "permission-logs",
);
process.env.HF_HOME ||= path.join(runtimeRoot, "huggingface");
process.env.TRANSFORMERS_CACHE ||= path.join(
  runtimeRoot,
  "huggingface",
  "transformers",
);

await import("./server.js");
