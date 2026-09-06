import { beforeEach, describe, expect, it, vi } from "vitest";
import { runChatTurn } from "../src/agent/chat-turn.js";
import { appendMessages } from "../src/storage/session-store.js";
import { describeArtifact } from "../src/services/artifact-service.js";
import { fakeRuntime, deferred } from "./helpers/runtime.js";
import type { ChatOptions } from "../src/contracts/chat.js";

vi.mock("../src/storage/session-store.js", () => ({
  appendMessages: vi.fn(async () => {}),
}));
vi.mock("../src/services/artifact-service.js", () => ({
  describeArtifact: vi.fn(),
}));
beforeEach(() => vi.clearAllMocks());
const options = (): ChatOptions => ({
  userId: "user",
  sessionId: "session",
  workspace: "workspace",
  message: "hello",
  images: [],
  emit: vi.fn(),
});

describe("chat turn persistence and cleanup", () => {
  it("saves user text, assistant deltas, sources and deliverable files in the original schema", async () => {
    const { runtime, session } = fakeRuntime();
    const artifact = {
      name: "result.txt",
      path: "result.txt",
      size: 3,
      download_url: "/download",
    };
    vi.mocked(describeArtifact).mockResolvedValue(artifact);
    const trace = { retrieved_chunks: [{ filename: "manual.txt" }] };
    session.prompt.mockImplementation(async () => {
      runtime.emit({ type: "content", content: " hello" });
      runtime.emit({ type: "content", content: " world " });
      runtime.emit({ type: "trace", rag_trace: trace });
      runtime.writtenPaths.add("result.txt");
    });
    const request = options();
    await runChatTurn(runtime, request);
    expect(appendMessages).toHaveBeenNthCalledWith(
      1,
      "user",
      "session",
      "workspace",
      [
        expect.objectContaining({
          type: "human",
          content: "hello",
          images: [],
        }),
      ],
    );
    expect(appendMessages).toHaveBeenNthCalledWith(
      2,
      "user",
      "session",
      "workspace",
      [
        expect.objectContaining({
          type: "ai",
          content: "hello world",
          rag_trace: trace,
          artifacts: [artifact],
        }),
      ],
    );
    expect(request.emit).toHaveBeenLastCalledWith({
      type: "artifacts",
      artifacts: [artifact],
    });
    const count = vi.mocked(request.emit).mock.calls.length;
    runtime.emit({ type: "content", content: "late" });
    expect(request.emit).toHaveBeenCalledTimes(count);
  });

  it("persists a partial reply before rethrowing a failed prompt", async () => {
    const { runtime, session } = fakeRuntime();
    session.prompt.mockImplementation(async () => {
      runtime.emit({ type: "content", content: "partial" });
      throw new Error("provider failed");
    });
    await expect(runChatTurn(runtime, options())).rejects.toThrow(
      "provider failed",
    );
    expect(appendMessages).toHaveBeenLastCalledWith(
      "user",
      "session",
      "workspace",
      [expect.objectContaining({ type: "ai", content: "partial" })],
    );
  });

  it("restores an unfinished plan into the prompt and saves a paused checkpoint", async () => {
    const { runtime, session } = fakeRuntime();
    const activePlan = {
      objective: "完成续做功能",
      status: "active" as const,
      updated_at: "2026-09-04T00:00:00.000Z",
      steps: [
        { id: "done", title: "已完成", status: "done" as const },
        { id: "next", title: "继续实现", status: "pending" as const },
      ],
    };
    const pausedPlan = { ...activePlan, status: "paused" as const };
    vi.mocked(runtime.getPlan).mockReturnValue(activePlan);
    vi.mocked(runtime.pausePlan).mockResolvedValue(pausedPlan);
    const request = options();

    await runChatTurn(runtime, request);

    expect(session.prompt).toHaveBeenCalledWith(
      expect.stringContaining("宿主恢复的未完成执行计划"),
      expect.any(Object),
    );
    expect(session.prompt.mock.calls[0][0]).toContain("(next) 继续实现");
    expect(request.emit).toHaveBeenCalledWith(
      expect.objectContaining({ type: "plan", plan: activePlan }),
    );
    expect(appendMessages).toHaveBeenLastCalledWith(
      "user",
      "session",
      "workspace",
      [expect.objectContaining({ type: "ai", plan: pausedPlan })],
    );
  });

  it("retries failed skill reloads next turn and detaches the failed request emitter", async () => {
    const { runtime, session } = fakeRuntime();
    runtime.skillsDirty = true;
    session.reload.mockRejectedValueOnce(new Error("reload failed"));
    const request = options();
    await expect(runChatTurn(runtime, request)).rejects.toThrow(
      "reload failed",
    );
    expect(runtime.skillsDirty).toBe(true);
    runtime.emit({ type: "content", content: "late" });
    expect(request.emit).not.toHaveBeenCalled();
    expect(session.prompt).not.toHaveBeenCalled();
    await runChatTurn(runtime, options());
    expect(session.reload).toHaveBeenCalledTimes(2);
    expect(runtime.skillsDirty).toBe(false);
    expect(session.prompt).toHaveBeenCalledOnce();
  });

  it("does not start a prompt after cancellation while reloading", async () => {
    const { runtime, session } = fakeRuntime();
    const reloading = deferred<void>();
    runtime.skillsDirty = true;
    session.reload.mockReturnValue(reloading.promise);
    const controller = new AbortController();
    const request = runChatTurn(runtime, {
      ...options(),
      signal: controller.signal,
    });
    controller.abort();
    reloading.resolve();
    await request;
    expect(session.prompt).not.toHaveBeenCalled();
    expect(appendMessages).not.toHaveBeenCalled();
  });

  it("releases the emitter when saving the user message fails", async () => {
    const { runtime, session } = fakeRuntime();
    vi.mocked(appendMessages).mockRejectedValueOnce(new Error("disk full"));
    const request = options();
    await expect(runChatTurn(runtime, request)).rejects.toThrow("disk full");
    runtime.emit({ type: "content", content: "late" });
    expect(request.emit).not.toHaveBeenCalled();
    expect(session.prompt).not.toHaveBeenCalled();
  });
});
