import { defineTool, type ModelRuntime } from "@earendil-works/pi-coding-agent";
import { createVisionAdapter } from "../integrations/vision/adapter.js";
import { Type } from "typebox";
import { agentDir } from "../config/index.js";
import { resolveImagePath } from "../services/upload-service.js";

type VisionDetails = {
  ok: boolean;
  images: number;
  errors: string[];
};

export function createWebVisionTool(modelRuntime: ModelRuntime, cwd: string) {
  const parameters = Type.Object({
    image_path: Type.Optional(
      Type.String({ description: "单张图片的绝对路径" }),
    ),
    image_paths: Type.Optional(
      Type.Array(Type.String(), {
        maxItems: 5,
        description: "多张图片的绝对路径",
      }),
    ),
    prompt: Type.String({ description: "需要从图片中识别、提取或分析的内容" }),
  });
  const delegator = createVisionAdapter(modelRuntime, cwd, agentDir);

  return defineTool<typeof parameters, VisionDetails>({
    name: "describe_image",
    label: "识别图片",
    description:
      "使用 @getpipher/vision 配置的视觉模型识别一张或多张图片。文本主模型收到图片附件时必须调用此工具。",
    promptSnippet: "describe_image: 使用视觉模型识别上传图片",
    promptGuidelines: [
      "主模型不支持图片时，对附件路径调用 describe_image；不要用 read 工具假装看图。",
    ],
    parameters,
    async execute(_toolCallId, params, signal) {
      const paths = [
        ...(params.image_paths || []),
        ...(params.image_path ? [params.image_path] : []),
      ].filter(
        (value, index, values) =>
          value.trim() && values.indexOf(value) === index,
      );
      if (!paths.length) {
        return {
          content: [
            {
              type: "text",
              text: "describe_image 需要 image_path 或 image_paths。",
            },
          ],
          details: { ok: false, images: 0, errors: ["no_image_path"] },
          isError: true,
        };
      }
      if (paths.length > 5) throw new Error("每次最多识别 5 张图片");
      const allowedPaths = await Promise.all(
        paths.map((file) => resolveImagePath(cwd, file)),
      );
      const results = await Promise.all(
        allowedPaths.map((image_path) =>
          delegator.delegate(
            {
              image_path,
              prompt: params.prompt,
              compress: true,
              reasoning: delegator.config.defaultReasoningEffort,
            },
            signal,
          ),
        ),
      );
      const errors = results
        .filter((item) => !item.ok)
        .map((item) => (item.ok ? "" : item.error.message));
      const text = results
        .map((item, index) =>
          item.ok
            ? `[图片 ${index + 1}] ${paths[index]}\n${item.text}`
            : `[图片 ${index + 1}] ${paths[index]}\n${item.error.message}`,
        )
        .join("\n\n---\n\n");
      return {
        content: [{ type: "text", text }],
        details: { ok: errors.length === 0, images: paths.length, errors },
        isError: errors.length === results.length,
      };
    },
  });
}
