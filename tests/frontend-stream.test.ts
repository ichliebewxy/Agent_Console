import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
import { expect, it, vi } from "vitest";

it("assembles every browser module from HTML and consumes a fragmented UTF-8 SSE stream", async () => {
  const html = await readFile("frontend/index.html", "utf8");
  const captured: { app?: any } = {};
  const context = {
    Vue: {
      createApp: (app: unknown) => ({
        mount: () => {
          captured.app = app;
        },
      }),
    },
    window: {} as any,
    localStorage: { getItem: () => null, setItem: vi.fn() },
    console,
    TextDecoder,
  };
  const methods = new Set<string>();
  for (const match of html.matchAll(
    /<script src="((?:js\/|script\.js)[^"]*)"><\/script>/g,
  )) {
    // The same context preserves the script ordering and top-level Vue binding.
    const code = await readFile(`frontend/${match[1]}`, "utf8");
    runInNewContext(code, context);
    if (context.window.NebulaNestApp) {
      for (const name of Object.keys(context.window.NebulaNestApp.methods))
        methods.add(name);
    }
  }
  const app = captured.app;
  expect(app).toBeDefined();
  for (const method of [
    "handleSend",
    "handleStop",
    "readSseStream",
    "answerDialog",
    "continueActivePlan",
    "loadSession",
    "loadWorkspace",
    "uploadDocument",
    "uploadSkillFile",
    "formatSourceMeta",
  ])
    expect(methods.has(method), method).toBe(true);
  const state = Object.assign(app.data(), app.methods, {
    $refs: {},
    $nextTick: (callback: () => void) => callback(),
    persistState: vi.fn(),
    notify: vi.fn(),
  });
  state.messages = [
    {
      id: "bot",
      text: "",
      streamGroupId: "group",
      isThinking: true,
      ragSteps: [],
      toolSteps: [],
      flowSteps: [],
      artifacts: [],
    },
  ];
  const trace = { retrieved_chunks: [{ filename: "说明.txt", text: "资料" }] };
  const events = [
    { type: "content", content: "你好" },
    {
      type: "tool_step",
      step: { phase: "call", tool_name: "write", call_id: "a" },
    },
    { type: "trace", rag_trace: trace },
    { type: "artifacts", artifacts: [{ path: "result.txt" }] },
    {
      type: "plan",
      plan: {
        objective: "完成测试",
        status: "active",
        updated_at: "2026-09-04T00:00:00.000Z",
        steps: [{ id: "test", title: "执行测试", status: "in_progress" }],
      },
    },
    {
      type: "retry",
      source: "model",
      status: "waiting",
      attempt: 2,
      max_attempts: 4,
      delay_ms: 2500,
      error: "fetch failed",
    },
    { type: "ui_request", id: "dialog", method: "input", title: "问题" },
    { type: "ui_closed", id: "dialog" },
  ];
  const bytes = new TextEncoder().encode(
    events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("") +
      ": keepalive\n\ndata: [DONE]\n\n",
  );
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (let index = 0; index < bytes.length; index += 3)
        controller.enqueue(bytes.slice(index, index + 3));
      controller.close();
    },
  });
  await state.readSseStream(body, 0);
  expect(state.messages[0].text).toBe("你好");
  expect(state.messages[0].toolSteps).toHaveLength(1);
  expect(state.messages[0].ragTrace).toEqual(trace);
  expect(state.messages[0].artifacts).toEqual([{ path: "result.txt" }]);
  expect(state.activePlan.objective).toBe("完成测试");
  expect(state.messages[0].plan.steps[0].status).toBe("in_progress");
  expect(state.messages[0].retryState).toEqual({
    source: "model",
    status: "waiting",
    toolName: "",
    attempt: 2,
    maxAttempts: 4,
    delayMs: 2500,
    error: "fetch failed",
    transient: false,
  });
  expect(state.retryStatusTitle(state.messages[0].retryState)).toContain(
    "模型",
  );
  expect(state.pendingDialog).toBeNull();
});
