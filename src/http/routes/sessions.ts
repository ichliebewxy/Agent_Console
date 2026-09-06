import { artifactRoutes } from "./artifacts.js";
import { sendHttpError } from "../errors.js";
import { Router } from "express";
import { assertRuntimeId } from "../../shared/runtime-id.js";
import {
  loadSession,
  listSessions,
  deleteSession,
} from "../../storage/session-store.js";

export function sessionsRoutes() {
  const router = Router();
  router.use(artifactRoutes());
  router.get("/sessions/:userId", async (request, response) => {
    try {
      response.json({
        sessions: await listSessions(
          assertRuntimeId(request.params.userId, "default_user"),
        ),
      });
    } catch (error) {
      sendHttpError(response, error, 400);
    }
  });

  router.get("/sessions/:userId/:sessionId", async (request, response) => {
    try {
      const record = await loadSession(
        assertRuntimeId(request.params.userId, "default_user"),
        assertRuntimeId(request.params.sessionId, "default_session"),
      );
      if (!record) return response.status(404).json({ detail: "会话不存在" });
      response.json({
        messages: record.messages,
        workspace: record.workspace,
        plan: record.plan || null,
      });
    } catch (error) {
      sendHttpError(response, error, 400);
    }
  });

  router.delete("/sessions/:userId/:sessionId", async (request, response) => {
    const userId = assertRuntimeId(request.params.userId, "default_user");
    const sessionId = assertRuntimeId(
      request.params.sessionId,
      "default_session",
    );
    const deleted = await deleteSession(userId, sessionId);
    response.status(deleted ? 200 : 404).json({
      session_id: sessionId,
      message: deleted ? "会话已删除" : "会话不存在",
    });
  });

  return router;
}
