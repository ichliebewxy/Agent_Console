import "dotenv/config";
import { configureProxy } from "./bootstrap/proxy.js";
import { configureEnvironment } from "./bootstrap/environment.js";

configureProxy();
await configureEnvironment();
// Plugins read environment variables during import; keep this import dynamic.
export const { server } = await import("./server.js");
