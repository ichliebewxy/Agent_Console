import {
  chatModel,
  chatProvider,
  chatBaseUrl,
  chatSupportsImages,
  visionModel,
} from "./models.js";

export function buildModelConfig() {
  const models = [
    {
      id: chatModel,
      name: `二狗子主模型 (${chatModel})`,
      reasoning: true,
      input: chatSupportsImages ? ["text", "image"] : ["text"],
      contextWindow: Number(process.env.CHAT_CONTEXT_WINDOW || 128000),
      maxTokens: Number(process.env.CHAT_MAX_TOKENS || 16384),
    },
  ];
  if (visionModel && visionModel !== chatModel) {
    models.push({
      id: visionModel,
      name: `二狗子视觉模型 (${visionModel})`,
      reasoning: true,
      input: ["text", "image"],
      contextWindow: Number(process.env.VISION_CONTEXT_WINDOW || 128000),
      maxTokens: Number(process.env.VISION_MAX_TOKENS || 16384),
    });
  }

  return {
    providers: {
      [chatProvider]: {
        baseUrl: chatBaseUrl,
        api: "openai-completions",
        apiKey: "$CHAT_API_KEY",
        models,
      },
    },
  };
}
