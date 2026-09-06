import { sendHttpError } from "../errors.js";
import { Router, type Request, type Response } from "express";
import { assertRuntimeId } from "../../shared/runtime-id.js";
import type { AgentGateway } from "../../contracts/chat.js";
import { errorMessage } from "../../shared/errors.js";
import { upload } from "../upload.js";
import { sendSse } from "../sse.js";
import { getWorkspace } from "../../services/workspace-service.js";
import { saveChatImages } from "../../services/upload-service.js";

export function chatRoutes(agentService: AgentGateway) {
  const router = Router();
  router.post(
    "/chat/stream",
    upload.array("images", 5),
    async (request: Request, response: Response) => {
      response.status(200).set({
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      });
      response.flushHeaders();
      let finished = false;
      const controller = new AbortController();
      response.once("close", () => {
        if (!finished) controller.abort();
      });
      const heartbeat = setInterval(() => {
        if (!response.destroyed) response.write(": keepalive\n\n");
      }, 15000);
      try {
        const isMultipart = request.is("multipart/form-data");
        const source = isMultipart ? request.body : request.body || {};
        const userId = assertRuntimeId(source.user_id, "default_user");
        const sessionId = assertRuntimeId(source.session_id, "default_session");
        const message = String(source.message || "").trim();
        if (
          !message &&
          !(request.files as Express.Multer.File[] | undefined)?.length
        )
          throw new Error("消息不能为空");
        const workspace = await getWorkspace(userId);
        const images = await saveChatImages(
          (request.files as Express.Multer.File[] | undefined) || [],
        );
        await agentService.chat({
          userId,
          sessionId,
          workspace,
          message: message || "请描述并分析所附图片。",
          images,
          signal: controller.signal,
          emit: (event) => sendSse(response, event),
        });
        finished = true;
        response.write("data: [DONE]\n\n");
      } catch (error) {
        sendSse(response, { type: "error", content: errorMessage(error) });
      } finally {
        finished = true;
        clearInterval(heartbeat);
        response.end();
      }
    },
  );

  router.post("/chat/ui-response", (request, response) => {
    try {
      const userId = assertRuntimeId(request.body.user_id, "default_user");
      const sessionId = assertRuntimeId(
        request.body.session_id,
        "default_session",
      );
      const accepted = agentService.respond(
        userId,
        sessionId,
        String(request.body.id),
        request.body.value,
      );
      response.status(accepted ? 200 : 410).json({ accepted });
    } catch (error) {
      sendHttpError(response, error, 400);
    }
  });

  return router;
}
