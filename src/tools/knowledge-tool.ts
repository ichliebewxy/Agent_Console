import { Type } from "typebox";
import { defineTool } from "@earendil-works/pi-coding-agent";
import { requestKnowledge } from "../integrations/rag/client.js";

export type RagTrace = Record<string, unknown>;

type KnowledgeDetails = {
  limited: boolean;
  status: number | null;
  ragTrace: RagTrace | null;
  documents: Array<Record<string, unknown>>;
};

export function createKnowledgeTool(onTrace?: (trace: RagTrace) => void) {
  let used = false;
  const parameters = Type.Object({
    query: Type.String({ description: "用于知识库混合检索的完整问题" }),
  });
  const tool = defineTool<typeof parameters, KnowledgeDetails>({
    name: "search_knowledge_base",
    label: "查询本地知识库",
    description:
      "使用现有 Milvus + BGE/BM25 混合检索查询用户上传的内部文档，并返回带文件名和页码的片段。每轮最多调用一次。",
    promptSnippet: "search_knowledge_base: 查询用户上传的本地知识库",
    promptGuidelines: [
      "涉及上传文档或内部资料时最多调用一次 search_knowledge_base，并在回答中保留来源。",
    ],
    parameters,
    async execute(_toolCallId, params, signal) {
      if (used) {
        return {
          content: [
            {
              type: "text",
              text: "本轮已经查询过知识库，请使用已有结果直接回答。",
            },
          ],
          details: {
            limited: true,
            status: null,
            ragTrace: null,
            documents: [] as Array<Record<string, unknown>>,
          },
          isError: true,
        };
      }
      used = true;
      const response = await requestKnowledge("/knowledge/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: params.query }),
        signal,
      });
      const payload = (await response.json().catch(() => ({}))) as {
        docs?: Array<Record<string, unknown>>;
        rag_trace?: RagTrace;
        detail?: string;
      };
      if (!response.ok) {
        return {
          content: [
            {
              type: "text",
              text: payload.detail || `知识库服务返回 HTTP ${response.status}`,
            },
          ],
          details: {
            limited: false,
            status: response.status,
            ragTrace: null,
            documents: [] as Array<Record<string, unknown>>,
          },
          isError: true,
        };
      }
      const docs = Array.isArray(payload.docs) ? payload.docs : [];
      const trace = payload.rag_trace || {};
      onTrace?.(trace);
      const text = docs.length
        ? docs
            .map((doc, index) => {
              const name = String(doc.filename || "Unknown");
              const page = String(doc.page_number || "N/A");
              return `[${index + 1}] ${name}（页 ${page}）\n${String(doc.text || "")}`;
            })
            .join("\n\n---\n\n")
        : "知识库中没有找到相关文档。";
      return {
        content: [{ type: "text", text }],
        details: {
          limited: false,
          status: null,
          ragTrace: trace,
          documents: docs,
        },
      };
    },
  });
  return {
    tool,
    beginTurn: () => {
      used = false;
    },
  };
}
