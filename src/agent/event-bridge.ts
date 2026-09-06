import path from "node:path";
import type { AgentSessionEvent } from "@earendil-works/pi-coding-agent";
import type { EventEmitter } from "../contracts/chat.js";

function extractToolResult(result: unknown): string {
  const content = (
    result as { content?: Array<{ type?: string; text?: string }> } | undefined
  )?.content;
  if (!Array.isArray(content)) return String(result ?? "");
  return content
    .filter((item) => item.type === "text")
    .map((item) => item.text || "")
    .join("\n");
}

/** Translate SDK events once; consumers receive the existing Web SSE payloads. */
export function createEventBridge(
  workspace: string,
  emitter: EventEmitter,
  writtenPaths: Set<string>,
  pendingWrites: Map<string, string>,
) {
  let pendingModelError: string | null = null;
  return (event: AgentSessionEvent): void => {
    try {
      if (event.type === "message_update") {
        const delta = event.assistantMessageEvent;
        if (delta?.type === "text_delta" && delta.delta)
          emitter({ type: "content", content: delta.delta });
      } else if (event.type === "tool_execution_start") {
        if (
          ["write", "edit"].includes(event.toolName) &&
          typeof event.args?.path === "string"
        )
          pendingWrites.set(event.toolCallId, event.args.path);
        emitter({
          type: "tool_step",
          step: {
            phase: "call",
            call_id: event.toolCallId,
            tool_name: event.toolName,
            label: `调用 ${event.toolName}`,
            detail: `参数: ${JSON.stringify(event.args ?? {})}`,
          },
        });
      } else if (event.type === "tool_execution_end") {
        const written = pendingWrites.get(event.toolCallId);
        if (written && !event.isError)
          writtenPaths.add(
            path.isAbsolute(written)
              ? path.relative(workspace, written)
              : written,
          );
        pendingWrites.delete(event.toolCallId);
        emitter({
          type: "tool_step",
          step: {
            phase: event.isError ? "error" : "result",
            call_id: event.toolCallId,
            tool_name: event.toolName,
            label: event.isError
              ? `${event.toolName} 失败`
              : `${event.toolName} 已完成`,
            result: extractToolResult(event.result),
          },
        });
      } else if (
        event.type === "message_end" &&
        event.message?.role === "assistant"
      ) {
        if (event.message.stopReason === "error") {
          pendingModelError =
            event.message.errorMessage || "模型请求失败，未返回错误详情";
        } else pendingModelError = null;
      } else if (event.type === "agent_end") {
        if (!event.willRetry && pendingModelError) {
          emitter({ type: "error", content: pendingModelError });
          pendingModelError = null;
        }
      } else if (event.type === "auto_retry_start") {
        emitter({
          type: "retry",
          source: "model",
          status: "waiting",
          attempt: event.attempt,
          max_attempts: event.maxAttempts,
          delay_ms: event.delayMs,
          error: event.errorMessage,
        });
      } else if (event.type === "auto_retry_end") {
        emitter({
          type: "retry",
          source: "model",
          status: event.success ? "success" : "failed",
          attempt: event.attempt,
          max_attempts: 4,
          error: event.finalError,
        });
        if (event.success) pendingModelError = null;
      }
    } catch (error) {
      console.error("pi event bridge failed", error);
    }
  };
}
