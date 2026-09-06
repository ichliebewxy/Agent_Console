import path from "node:path";

export const projectRoot = path.resolve(process.cwd());
export const tmpRoot = path.join(projectRoot, "tmp");
export const agentDir = path.join(tmpRoot, "pi-agent");
export const sessionDataDir = path.join(tmpRoot, "sessions");
export const userSkillsDir = path.join(tmpRoot, "user-skills");
export const builtinSkillsDirs = [
  path.join(projectRoot, ".pi", "skills"),
  path.join(projectRoot, "agent_workspace", "skills"),
];
export const uploadDir = path.join(tmpRoot, "uploads");
export const configDir = path.join(tmpRoot, "config");
export const permissionConfigDir = path.join(
  agentDir,
  "extensions",
  "pi-permission-system",
);
export const frontendDir = path.join(projectRoot, "frontend");
