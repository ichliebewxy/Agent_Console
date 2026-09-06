import { Router } from "express";
import { assertRuntimeId } from "../../shared/runtime-id.js";
import { sendHttpError } from "../errors.js";
import { loadSession } from "../../storage/session-store.js";
import { resolveWorkspaceFile } from "../../services/artifact-service.js";

export function artifactRoutes() {
  const router = Router();
  router.get("/artifacts/:userId/:sessionId", async (request, response) => {
    try {
      const record = await loadSession(
        assertRuntimeId(request.params.userId, "default_user"),
        assertRuntimeId(request.params.sessionId, "default_session"),
      );
      const relative = String(request.query.path || "");
      if (
        !record?.messages.some((message) =>
          message.artifacts?.some((artifact) => artifact.path === relative),
        )
      )
        return response.status(404).json({ detail: "交付物不存在" });
      response.download(await resolveWorkspaceFile(record.workspace, relative));
    } catch (error) {
      sendHttpError(response, error, 400);
    }
  });

  return router;
}
