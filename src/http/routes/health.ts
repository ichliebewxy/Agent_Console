import { Router } from "express";
import { requestKnowledge } from "../../integrations/rag/client.js";

export function healthRoutes() {
  const app = Router();
  app.get("/health", async (_request, response) => {
    let rag = false;
    try {
      rag = (
        await requestKnowledge("/health", {
          signal: AbortSignal.timeout(3000),
        })
      ).ok;
    } catch {
      /* sidecar may still be starting */
    }
    response.json({ ok: true, service: "pi-web", rag });
  });

  return app;
}
