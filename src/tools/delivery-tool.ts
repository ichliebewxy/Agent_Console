import { Type } from "typebox";
import { defineTool } from "@earendil-works/pi-coding-agent";
import type { Artifact } from "../services/artifact-service.js";

export function createDeliveryTool(
  register: (paths: string[]) => Promise<Artifact[]>,
) {
  return defineTool({
    name: "deliver_files",
    label: "交付工作区文件",
    description:
      "登记已经写入工作区的交付文件，并在网页显示下载入口。只接受实际存在的相对文件路径。仅登记用户需要的最终成果，不要将中间文件、辅助脚本、日志或全部工作区文件一并交付。",
    parameters: Type.Object({
      paths: Type.Array(Type.String(), { minItems: 1, maxItems: 30 }),
    }),
    async execute(_id, params) {
      const artifacts = await register(params.paths);
      return {
        content: [{ type: "text", text: JSON.stringify(artifacts) }],
        details: { artifacts },
      };
    },
  });
}
