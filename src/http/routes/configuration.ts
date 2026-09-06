import { skillRoutes } from "./skills.js";
import { sendHttpError } from "../errors.js";
import { Router } from "express";
import type { AgentGateway } from "../../contracts/chat.js";
import {
  resolvePluginResources,
  selectedPackages,
} from "../../integrations/pi/plugin-resources.js";
import { listUploadedSkills } from "../../services/skill-service.js";

export function configurationRoutes(agentService: AgentGateway) {
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
      sendHttpError(response, error, 500);
    }
  });

  router.use(skillRoutes(agentService));
  return router;
}
