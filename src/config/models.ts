import "dotenv/config";

export const ragBaseUrl = (
  process.env.RAG_BASE_URL || "http://127.0.0.1:8091"
).replace(/\/$/, "");

export const chatProvider = "ergouzi";
export const chatModel = process.env.CHAT_MODEL || "deepseek-chat";
export const chatBaseUrl = (
  process.env.CHAT_BASE_URL || "https://api.deepseek.com"
).replace(/\/$/, "");
export const visionModel =
  process.env.VISION_MODEL ||
  (chatBaseUrl.includes("deepseek") ? "deepseek-v4-flash-vision-exp" : "");
export const chatSupportsImages = /^(1|true|yes|on)$/i.test(
  process.env.CHAT_MODEL_SUPPORTS_IMAGES || "",
);
