import { Router } from "express";
import type { AgentGateway } from "../../contracts/chat.js";
import { upload } from "../upload.js";
import { sendHttpError } from "../errors.js";
import {
  createSkill,
  deleteSkill,
  listUploadedSkills,
  uploadSkill,
} from "../../services/skill-service.js";

export function skillRoutes(agentService: Pick<AgentGateway, "reloadSkills">) {
  const router = Router();
  router.post("/runtime-config/skills", async (request, response) => {
    try {
      await createSkill(request.body || {});
      await agentService.reloadSkills();
      response.json({
        config: {
          skills: await listUploadedSkills(),
          mcpServers: {},
          discovery: { updated_at: new Date().toISOString() },
        },
      });
    } catch (error) {
      sendHttpError(response, error, 422);
    }
  });

  router.post(
    "/runtime-config/skills/upload",
    upload.single("skill"),
    async (request, response) => {
      try {
        if (!request.file) throw new Error("请选择 SKILL.md 或 ZIP");
        const skill = await uploadSkill(
          request.file,
          String(request.body?.overwrite || "") === "true",
        );
        await agentService.reloadSkills();
        response.json({
          skill,
          message: `Skill ${skill.name} 已上传，将在下一条消息中加载`,
        });
      } catch (error) {
        sendHttpError(response, error, 422);
      }
    },
  );

  router.delete("/runtime-config/skills/:name", async (request, response) => {
    try {
      await deleteSkill(request.params.name);
      await agentService.reloadSkills();
      response.json({ message: `Removed Skill: ${request.params.name}` });
    } catch (error) {
      sendHttpError(response, error, 422);
    }
  });

  return router;
}
