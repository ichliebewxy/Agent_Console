import { Router } from "express";
import { assertRuntimeId } from "../../config/index.js";
import type { AgentService } from "../../agent/agent-service.js";
import { errorMessage } from "../shared.js";
import {
  getWorkspace,
  setWorkspace,
  pickWorkspaceNative,
} from "../../services/workspace-service.js";

export function workspaceRoutes(agentService: AgentService) {
  const router = Router();
  router.get("/workspace/:userId", async (request, response) => {
    try {
      const userId = assertRuntimeId(request.params.userId, "default_user");
      response.json({ workspace: await getWorkspace(userId) });
    } catch (error) {
      response.status(400).json({ detail: errorMessage(error) });
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
      response.status(400).json({ detail: errorMessage(error) });
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
      response.status(500).json({ detail: errorMessage(error) });
    }
  });

  return router;
}
