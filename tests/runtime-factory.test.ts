import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  session: {
    agent: { state: { messages: [] } },
    subscribe: vi.fn(),
    bindExtensions: vi.fn(async () => {}),
    dispose: vi.fn(),
    abort: vi.fn(),
  },
  pluginErrors: [] as Array<{ package: string; error: string }>,
  extensionErrors: [] as Array<{ path: string; error: string }>,
  createSession: vi.fn(),
  settingsInMemory: vi.fn(() => ({})),
  beginTurn: vi.fn(),
  installFailureRecovery: vi.fn(),
}));
vi.mock("@earendil-works/pi-coding-agent", () => ({
  createAgentSession: state.createSession,
  DefaultResourceLoader: class {
    async reload() {}
    getExtensions() {
      return { errors: state.extensionErrors };
    }
  },
  ModelRuntime: { create: async () => ({ getModel: () => ({ id: "fake" }) }) },
  SessionManager: { inMemory: vi.fn() },
  SettingsManager: { inMemory: state.settingsInMemory },
}));
vi.mock("../src/agent/retry-policy.js", () => ({
  installFailureRecovery: state.installFailureRecovery,
}));
vi.mock("../src/agent/web-ui.js", () => ({
  WebUI: class {
    cancel() {}
    context() {
      return {};
    }
  },
}));
vi.mock("../src/integrations/pi/plugin-resources.js", () => ({
  resolvePluginResources: async () => ({
    errors: state.pluginErrors,
    extensionPaths: [],
    skillPaths: [],
    promptPaths: [],
  }),
}));
vi.mock("../src/integrations/pi/shell-config.js", () => ({
  resolveShellPath: () => undefined,
}));
vi.mock("../src/tools/knowledge-tool.js", () => ({
  createKnowledgeTool: () => ({
    tool: { name: "search_knowledge_base" },
    beginTurn() {},
  }),
}));
vi.mock("../src/tools/vision-tool.js", () => ({
  createWebVisionTool: () => ({ name: "describe_image" }),
}));
vi.mock("../src/tools/delivery-tool.js", () => ({
  createDeliveryTool: () => ({ name: "deliver_files" }),
}));
vi.mock("../src/tools/plan-tool.js", () => ({
  createPlanTool: () => ({
    tool: { name: "update_plan" },
    getPlan: () => null,
    pause: async () => null,
  }),
}));
vi.mock("../src/storage/session-store.js", () => ({
  savePlan: async () => {},
  loadSession: async () => ({
    messages: [
      { type: "human", content: "previous", timestamp: "2026-01-01T00:00:00Z" },
    ],
  }),
}));

import { createRuntime } from "../src/agent/runtime-factory.js";

beforeEach(() => {
  vi.clearAllMocks();
  state.pluginErrors = [];
  state.extensionErrors = [];
  state.createSession.mockResolvedValue({ session: state.session });
  state.installFailureRecovery.mockReturnValue({ beginTurn: state.beginTurn });
  state.session.agent.state.messages = [];
});

const options = {
  key: "user\0session",
  userId: "user",
  sessionId: "session",
  workspace: "workspace",
  initialEmit: () => {},
};
describe("SDK runtime factory", () => {
  it("retains custom tools, history and RPC binding", async () => {
    const runtime = await createRuntime(options);
    expect(state.createSession).toHaveBeenCalledWith(
      expect.objectContaining({
        cwd: "workspace",
        thinkingLevel: "medium",
        customTools: [
          { name: "search_knowledge_base" },
          { name: "describe_image" },
          { name: "deliver_files" },
          { name: "update_plan" },
        ],
        excludeTools: [],
      }),
    );
    expect(runtime.session.agent.state.messages).toMatchObject([
      { role: "user", content: [{ type: "text", text: "previous" }] },
    ]);
    expect(state.session.bindExtensions).toHaveBeenCalledWith(
      expect.objectContaining({ mode: "rpc" }),
    );
    expect(state.settingsInMemory).toHaveBeenCalledWith(
      expect.objectContaining({
        retry: {
          enabled: true,
          maxRetries: 4,
          baseDelayMs: 1000,
          provider: { maxRetries: 0, maxRetryDelayMs: 9000 },
        },
      }),
      { projectTrusted: true },
    );
    expect(state.installFailureRecovery).toHaveBeenCalledWith(
      state.session,
      expect.any(Function),
    );
    expect(state.session.subscribe).toHaveBeenCalledOnce();
  });

  it("disposes a session if extension binding fails", async () => {
    state.session.bindExtensions.mockRejectedValueOnce(
      new Error("bind failed"),
    );
    await expect(createRuntime(options)).rejects.toThrow("bind failed");
    expect(state.session.dispose).toHaveBeenCalledOnce();
  });

  it("rejects unavailable resources before constructing a model session", async () => {
    state.pluginErrors = [{ package: "test-plugin", error: "missing" }];
    await expect(createRuntime(options)).rejects.toThrow(
      "test-plugin: missing",
    );
    expect(state.createSession).not.toHaveBeenCalled();
    state.pluginErrors = [];
    state.extensionErrors = [{ path: "extension.ts", error: "bad module" }];
    await expect(createRuntime(options)).rejects.toThrow(
      "extension.ts: bad module",
    );
    expect(state.createSession).not.toHaveBeenCalled();
  });
});
