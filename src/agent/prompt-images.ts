import { readFile } from "node:fs/promises";
import { chatSupportsImages } from "../config/models.js";
import type { ChatOptions } from "../contracts/chat.js";

export async function preparePrompt(
  options: Pick<ChatOptions, "images" | "message">,
) {
  const imageContent = await Promise.all(
    options.images.map(async (image) => ({
      type: "image" as const,
      data: (await readFile(image.path)).toString("base64"),
      mimeType: image.mimeType,
    })),
  );
  const promptText =
    options.images.length && !chatSupportsImages
      ? `${options.message}\n\n[系统附件说明]\n主模型是文本模型。请务必调用 describe_image 分析以下已上传图片，不要声称图片不可见：\n${options.images.map((image) => `- ${image.path}`).join("\n")}`
      : options.message;
  return { imageContent, promptText };
}
