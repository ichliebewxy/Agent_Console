import { describeArtifact } from "../services/artifact-service.js";
import type { ChatOptions } from "../contracts/chat.js";
import type { Runtime } from "./runtime-types.js";

export async function collectArtifacts(
  runtime: Runtime,
  options: Pick<ChatOptions, "workspace" | "userId" | "sessionId">,
): Promise<void> {
  for (const relative of runtime.writtenPaths) {
    try {
      const file = await describeArtifact(
        options.workspace,
        relative,
        options.userId,
        options.sessionId,
      );
      runtime.artifacts.set(file.path, file);
    } catch {
      /* Deleted or non-deliverable files are not exposed. */
    }
  }
}
