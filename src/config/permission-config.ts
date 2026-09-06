import { uploadDir, userSkillsDir, builtinSkillsDirs } from "./paths.js";

export function buildPermissionConfig() {
  return {
    debugLog: false,
    permissionReviewLog: true,
    yoloMode: false,
    permission: {
      "*": "allow",
      path: {
        "*": "allow",
        "*.env": "deny",
        "*.env.*": "deny",
        "*.env.example": "allow",
        "*.pem": "deny",
        "*.key": "deny",
      },
      read: "allow",
      write: "allow",
      edit: "allow",
      bash: {
        "*": "allow",
        "rm -rf /": "deny",
        "rm -rf ~": "deny",
        "git push --force *": "deny",
      },
      mcp: { "*": "allow" },
      skill: { "*": "allow" },
      external_directory: {
        "*": "deny",
      },
      external_directory_read: Object.fromEntries(
        [uploadDir, userSkillsDir, ...builtinSkillsDirs]
          .flatMap((directory) => [directory, `${directory}/*`])
          .map((directory) => [directory.replace(/\\/g, "/"), "allow"]),
      ),
    },
  };
}
