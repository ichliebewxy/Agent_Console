import { Router } from "express";
import { assertRuntimeId } from "../../config/index.js";
import { errorMessage } from "../shared.js";
import {
  loadSession,
  listSessions,
  deleteSession,
} from "../../storage/session-store.js";
import { resolveWorkspaceFile } from "../../services/artifact-service.js";

export function sessionsRoutes() {
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
      response.status(400).json({ detail: errorMessage(error) });
    }
  });

  router.get("/sessions/:userId", async (request, response) => {
    try {
      response.json({
        sessions: await listSessions(
          assertRuntimeId(request.params.userId, "default_user"),
        ),
      });
    } catch (error) {
      response.status(400).json({ detail: errorMessage(error) });
    }
  });

  router.get("/sessions/:userId/:sessionId", async (request, response) => {
    try {
      const record = await loadSession(
        assertRuntimeId(request.params.userId, "default_user"),
        assertRuntimeId(request.params.sessionId, "default_session"),
      );
      if (!record) return response.status(404).json({ detail: "会话不存在" });
      response.json({ messages: record.messages, workspace: record.workspace });
    } catch (error) {
      response.status(400).json({ detail: errorMessage(error) });
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
