import { sendHttpError } from "../errors.js";
import { Router } from "express";
import { assertRuntimeId } from "../../shared/runtime-id.js";
import type { AgentGateway } from "../../contracts/chat.js";
import {
  getWorkspace,
  setWorkspace,
  pickWorkspaceNative,
} from "../../services/workspace-service.js";

export function workspaceRoutes(agentService: AgentGateway) {
  const router = Router();
  router.get("/workspace/:userId", async (request, response) => {
    try {
      const userId = assertRuntimeId(request.params.userId, "default_user");
      response.json({ workspace: await getWorkspace(userId) });
    } catch (error) {
      sendHttpError(response, error, 400);
    }
  });

  router.post("/workspace/:userId", async (request, response) => {
    try {
      const userId = assertRuntimeId(request.params.userId, "default_user");
      if (agentService.isUserBusy(userId))
        return response
          .status(409)
          .json({ detail: "请先停止或等待当前任务，再切换工作区" });
      const workspace = await setWorkspace(
        userId,
        String(request.body?.path || ""),
      );
      await agentService.disposeUserSessions(userId);
      response.json({
        workspace,
        message: "工作区已切换，后续文件将在此目录内交付",
      });
    } catch (error) {
      sendHttpError(response, error, 400);
    }
  });

  router.post("/workspace/:userId/pick", async (request, response) => {
    try {
      const userId = assertRuntimeId(request.params.userId, "default_user");
      if (agentService.isUserBusy(userId))
        return response
          .status(409)
          .json({ detail: "请先停止或等待当前任务，再切换工作区" });
      const picked = await pickWorkspaceNative();
      if (!picked) return response.status(409).json({ detail: "未选择工作区" });
      const workspace = await setWorkspace(userId, picked);
      await agentService.disposeUserSessions(userId);
      response.json({ workspace, message: "工作区已切换" });
    } catch (error) {
      sendHttpError(response, error, 500);
    }
  });

  return router;
}
