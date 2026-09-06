import type { AgentSession } from "@earendil-works/pi-coding-agent";
import type { StoredMessage } from "../contracts/sessions.js";
import { chatModel, chatProvider } from "../config/models.js";

export function restoredMessages(
  messages: StoredMessage[],
): AgentSession["agent"]["state"]["messages"] {
  return messages.map((message) => {
    const timestamp = Date.parse(message.timestamp) || Date.now();
    if (message.type === "human") {
      const attachments = message.images?.length
        ? `\n\n[历史图片附件，如需重新查看请调用 describe_image]\n${message.images.map((image) => `- ${image.path}`).join("\n")}`
        : "";
      return {
        role: "user",
        content: [{ type: "text", text: message.content + attachments }],
        timestamp,
      };
    }
    return {
      role: "assistant",
      content: [{ type: "text", text: message.content }],
      api: "openai-completions",
      provider: chatProvider,
      model: chatModel,
      usage: {
        input: 0,
        output: 0,
        cacheRead: 0,
        cacheWrite: 0,
        totalTokens: 0,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
      },
      stopReason: "stop",
      timestamp,
    };
  });
}
