import path from "node:path";
import { describe, expect, it, vi } from "vitest";
import type { AgentSessionEvent } from "@earendil-works/pi-coding-agent";
import { createEventBridge } from "../src/agent/event-bridge.js";
import { restoredMessages } from "../src/agent/restore-messages.js";

describe("SDK event and history adapters", () => {
  it("preserves text deltas and tool payloads and records only successful writes", () => {
    const emit = vi.fn();
    const written = new Set<string>();
    const pending = new Map<string, string>();
    const workspace = path.resolve("tmp/event-fixture");
    const bridge = createEventBridge(workspace, emit, written, pending);
    bridge({
      type: "message_update",
      assistantMessageEvent: { type: "text_delta", delta: "中文" },
    } as AgentSessionEvent);
    expect(emit).toHaveBeenLastCalledWith({ type: "content", content: "中文" });
    bridge({
      type: "tool_execution_start",
      toolName: "write",
      toolCallId: "write-1",
      args: { path: path.join(workspace, "result.txt") },
    });
    bridge({
      type: "tool_execution_end",
      toolName: "write",
      toolCallId: "write-1",
      isError: false,
      result: {
        content: [
          { type: "text", text: "saved" },
          { type: "image", data: "unused" },
        ],
      },
    });
    expect(written).toEqual(new Set(["result.txt"]));
    expect(emit).toHaveBeenLastCalledWith({
      type: "tool_step",
      step: {
        phase: "result",
        call_id: "write-1",
        tool_name: "write",
        label: "write 已完成",
        result: "saved",
      },
    });
    bridge({
      type: "tool_execution_start",
      toolName: "edit",
      toolCallId: "edit-1",
      args: { path: "failed.txt" },
    });
    bridge({
      type: "tool_execution_end",
      toolName: "edit",
      toolCallId: "edit-1",
      isError: true,
      result: "failed",
    });
    expect(written).toEqual(new Set(["result.txt"]));
    expect(pending.size).toBe(0);
    expect(emit).toHaveBeenLastCalledWith(
      expect.objectContaining({
        step: expect.objectContaining({ phase: "error", result: "failed" }),
      }),
    );
  });

  it("restores historical image references and assistant metadata without inventing usage", () => {
    const messages = restoredMessages([
      {
        type: "human",
        content: "picture",
        timestamp: "2026-09-03T00:00:00Z",
        images: [
          { name: "one.png", path: "uploads/one.png", mimeType: "image/png" },
        ],
      },
      { type: "ai", content: "answer", timestamp: "2026-09-03T00:01:00Z" },
    ]);
    expect(messages[0]).toMatchObject({
      role: "user",
      timestamp: 1788393600000,
      content: [
        { type: "text", text: expect.stringContaining("uploads/one.png") },
      ],
    });
    expect(messages[1]).toMatchObject({
      role: "assistant",
      stopReason: "stop",
      usage: { totalTokens: 0 },
      content: [{ type: "text", text: "answer" }],
    });
  });

  it("hides recoverable model errors, reports retry state and surfaces only the final failure", () => {
    const emit = vi.fn();
    const bridge = createEventBridge("workspace", emit, new Set(), new Map());
    bridge({
      type: "message_end",
      message: {
        ...restoredMessages([{ type: "ai", content: "", timestamp: "" }])[0],
        role: "assistant",
        stopReason: "error",
        errorMessage: "provider offline",
      },
    } as AgentSessionEvent);
    expect(emit).not.toHaveBeenCalledWith({
      type: "error",
      content: "provider offline",
    });
    bridge({
      type: "agent_end",
      messages: [],
      willRetry: true,
    } as unknown as AgentSessionEvent);
    expect(emit).not.toHaveBeenCalledWith(
      expect.objectContaining({ type: "error" }),
    );
    bridge({
      type: "auto_retry_start",
      attempt: 2,
      maxAttempts: 4,
      delayMs: 2500,
      errorMessage: "provider offline",
    } as AgentSessionEvent);
    expect(emit).toHaveBeenLastCalledWith({
      type: "retry",
      source: "model",
      status: "waiting",
      attempt: 2,
      max_attempts: 4,
      delay_ms: 2500,
      error: "provider offline",
    });
    bridge({
      type: "agent_end",
      messages: [],
      willRetry: false,
    } as unknown as AgentSessionEvent);
    expect(emit).toHaveBeenLastCalledWith({
      type: "error",
      content: "provider offline",
    });
  });
});
