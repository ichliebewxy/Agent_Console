import { handleHttpError } from "./errors.js";
import { healthRoutes } from "./routes/health.js";
import path from "node:path";
import cors from "cors";
import express from "express";
import type { AgentGateway } from "../contracts/chat.js";
import { frontendDir, projectRoot } from "../config/paths.js";
import { workspaceRoutes } from "./routes/workspace.js";
import { chatRoutes } from "./routes/chat.js";
import { sessionsRoutes } from "./routes/sessions.js";
import { configurationRoutes } from "./routes/configuration.js";
import { sidecarRoutes } from "./routes/sidecar.js";

export function createApplication(agentService: AgentGateway, port: number) {
  const app = express();
  const localOrigins = new Set([
    `http://localhost:${port}`,
    `http://127.0.0.1:${port}`,
  ]);
  app.use((request, response, next) => {
    if (
      !["localhost", "127.0.0.1"].includes(request.hostname) ||
      (request.headers.origin && !localOrigins.has(request.headers.origin))
    ) {
      return response.status(403).json({ detail: "只允许本机工作台访问" });
    }
    next();
  });
  app.use(cors({ origin: [...localOrigins], credentials: true }));
  app.use(express.json({ limit: "2mb" }));

  app.use(healthRoutes());

  app.use(workspaceRoutes(agentService));
  app.use(chatRoutes(agentService));
  app.use(sessionsRoutes());
  app.use(configurationRoutes(agentService));
  app.use(sidecarRoutes());
  app.get("/vendor/purify.min.js", (_request, response) =>
    response.sendFile(
      path.join(
        projectRoot,
        "node_modules",
        "dompurify",
        "dist",
        "purify.min.js",
      ),
    ),
  );
  app.use(express.static(frontendDir, { etag: false, maxAge: 0 }));
  app.use((_request, response) =>
    response.status(404).json({ detail: "接口或资源不存在" }),
  );

  app.use(handleHttpError);
  return app;
}
