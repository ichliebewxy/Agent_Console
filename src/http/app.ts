import path from "node:path";
import cors from "cors";
import express from "express";
import type { AgentService } from "../agent/agent-service.js";
import { frontendDir, projectRoot, ragBaseUrl } from "../config/index.js";
import { workspaceRoutes } from "./routes/workspace.js";
import { chatRoutes } from "./routes/chat.js";
import { sessionsRoutes } from "./routes/sessions.js";
import { configurationRoutes } from "./routes/configuration.js";
import { sidecarRoutes } from "./routes/sidecar.js";

export function createApplication(agentService: AgentService, port: number) {
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

  app.get("/health", async (_request, response) => {
    let rag = false;
    try {
      rag = (
        await fetch(`${ragBaseUrl}/health`, {
          signal: AbortSignal.timeout(3000),
        })
      ).ok;
    } catch {
      /* sidecar may still be starting */
    }
    response.json({ ok: true, service: "pi-web", rag });
  });

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
    response.sendFile(path.join(frontendDir, "index.html")),
  );

  return app;
}
