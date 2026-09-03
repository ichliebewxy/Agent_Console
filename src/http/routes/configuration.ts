import { Router } from "express";
import { assertRuntimeId } from "../../config/index.js";
import type { AgentService } from "../../agent/agent-service.js";
import { errorMessage, upload } from "../shared.js";
import {
  resolvePluginResources,
  selectedPackages,
} from "../../integrations/pi/plugin-resources.js";
import {
  createSkill,
  deleteSkill,
  listUploadedSkills,
  uploadSkill,
} from "../../services/skill-service.js";

export function configurationRoutes(agentService: AgentService) {
  const router = Router();
  router.get("/runtime-config", async (_request, response) => {
    const plugins = await resolvePluginResources();
    response.json({
      config: {
        runtime: {
          name: "二狗子助手",
          engine: "@earendil-works/pi-coding-agent",
          version: "0.84.4",
        },
        plugins: selectedPackages,
        pluginErrors: plugins.errors,
        skills: await listUploadedSkills(),
        mcpServers: {},
        permissions: {
          mode: "工作区内自动允许；附件与 Skill 资源允许只读；其他工作区外路径拒绝",
          protected: ["*.env", "*.env.*", "*.pem", "*.key"],
          auditPath: "tmp/permission-logs",
        },
        discovery: { updated_at: new Date().toISOString(), skill_errors: [] },
      },
    });
  });

  router.post("/runtime-config/refresh", async (_request, response) => {
    try {
      await agentService.reloadSkills();
      response.json({
        skills: await listUploadedSkills(),
        skill_errors: [],
        mcp_server_count: 0,
        mcp_tool_count: 0,
        mcp_errors: {},
      });
    } catch (error) {
      response.status(500).json({ detail: errorMessage(error) });
    }
  });

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
      response
        .status(errorMessage(error) === "Skill 已存在" ? 409 : 422)
        .json({ detail: errorMessage(error) });
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
        response
          .status(errorMessage(error) === "Skill 已存在" ? 409 : 422)
          .json({ detail: errorMessage(error) });
      }
    },
  );

  router.delete("/runtime-config/skills/:name", async (request, response) => {
    try {
      await deleteSkill(request.params.name);
      await agentService.reloadSkills();
      response.json({ message: `Removed Skill: ${request.params.name}` });
    } catch (error) {
      response.status(422).json({ detail: errorMessage(error) });
    }
  });

  return router;
}
