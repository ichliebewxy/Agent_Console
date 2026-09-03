import { ensureRuntimeLayout } from "./config/index.js";
import { AgentService } from "./agent/agent-service.js";
import { createApplication } from "./http/app.js";

await ensureRuntimeLayout();
const port = Number(process.env.PORT || 3000);
createApplication(new AgentService(), port).listen(port, "127.0.0.1", () => {
  console.log(`二狗子助手已启动：http://127.0.0.1:${port}`);
});
