import path from "node:path";
import {
  createAgentSession,
  DefaultResourceLoader,
  ModelRuntime,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";
import { agentDir, builtinSkillsDirs, userSkillsDir } from "../config/paths.js";
import { chatModel, chatProvider } from "../config/models.js";
import { createKnowledgeTool, type RagTrace } from "../tools/knowledge-tool.js";
import { resolvePluginResources } from "../integrations/pi/plugin-resources.js";
import { loadSession, savePlan } from "../storage/session-store.js";
import { buildSystemPrompt } from "./system-prompt.js";
import { createWebVisionTool } from "../tools/vision-tool.js";
import { WebUI } from "./web-ui.js";
import { resolveShellPath } from "../integrations/pi/shell-config.js";
import {
  describeArtifact,
  type Artifact,
} from "../services/artifact-service.js";

import { createDeliveryTool } from "../tools/delivery-tool.js";

import type { StreamEvent } from "../contracts/chat.js";
import type { Runtime, RuntimeOptions } from "./runtime-types.js";
import { createEventBridge } from "./event-bridge.js";
import { restoredMessages } from "./restore-messages.js";
import { createPlanTool } from "../tools/plan-tool.js";
import { installFailureRecovery } from "./retry-policy.js";

export async function createRuntime({
  key,
  userId,
  sessionId,
  workspace,
  initialEmit,
  onCreated,
}: RuntimeOptions): Promise<Runtime> {
  const previous = await loadSession(userId, sessionId);
  const pluginResources = await resolvePluginResources();
  if (pluginResources.errors.length) {
    throw new Error(
      `Pi 插件资源不完整：${pluginResources.errors.map((item) => `${item.package}: ${item.error}`).join("; ")}`,
    );
  }
  const settingsManager = SettingsManager.inMemory(
    {
      compaction: {
        enabled: true,
        reserveTokens: 16384,
        keepRecentTokens: 24000,
      },
      retry: {
        enabled: true,
        maxRetries: 4,
        baseDelayMs: 1000,
        // The host owns the visible 1/2/4/8s+jitter schedule. Avoid nested SDK retries.
        provider: { maxRetries: 0, maxRetryDelayMs: 9000 },
      },
      images: { autoResize: true, blockImages: false },
      shellPath: resolveShellPath(),
    },
    { projectTrusted: true },
  );
  const loader = new DefaultResourceLoader({
    cwd: workspace,
    agentDir,
    settingsManager,
    additionalExtensionPaths: pluginResources.extensionPaths,
    additionalSkillPaths: [
      ...builtinSkillsDirs,
      userSkillsDir,
      ...pluginResources.skillPaths,
    ],
    additionalPromptTemplatePaths: pluginResources.promptPaths,
    systemPromptOverride: () => buildSystemPrompt(workspace),
    appendSystemPromptOverride: () => [],
    noContextFiles: true,
  });
  console.log("Pi runtime: loading resources", sessionId);
  await loader.reload({ resolveProjectTrust: async () => true });
  const extensionErrors = loader.getExtensions().errors;
  if (extensionErrors.length) {
    throw new Error(
      `Pi 扩展加载失败：${extensionErrors.map((item) => `${item.path}: ${item.error}`).join("; ")}`,
    );
  }
  console.log("Pi runtime: resources loaded", sessionId);

  const modelRuntime = await ModelRuntime.create({
    authPath: path.join(agentDir, "auth.json"),
    modelsPath: path.join(agentDir, "models.json"),
    allowModelNetwork: false,
  });
  const model = modelRuntime.getModel(chatProvider, chatModel);
  if (!model) throw new Error(`pi 无法加载模型 ${chatProvider}/${chatModel}`);

  let emitter: (event: StreamEvent) => void = initialEmit;
  const ui = new WebUI((event) => emitter(event));
  const artifacts = new Map<string, Artifact>();
  const writtenPaths = new Set<string>();
  const pendingWrites = new Map<string, string>();
  const delivery = createDeliveryTool(async (paths) => {
    const files = await Promise.all(
      paths.map((file) => describeArtifact(workspace, file, userId, sessionId)),
    );
    for (const file of files) artifacts.set(file.path, file);
    emitter({ type: "artifacts", artifacts: [...artifacts.values()] });
    return files;
  });
  const knowledge = createKnowledgeTool((trace: RagTrace) =>
    emitter({ type: "trace", rag_trace: trace }),
  );
  const planner = createPlanTool(previous?.plan || null, async (plan) => {
    await savePlan(userId, sessionId, workspace, plan);
    emitter({
      type: "plan",
      plan,
      ...(plan || {}),
      ...(plan ? {} : { cleared: true }),
    });
  });
  const { session } = await createAgentSession({
    cwd: workspace,
    agentDir,
    modelRuntime,
    model,
    thinkingLevel: "medium",
    resourceLoader: loader,
    sessionManager: SessionManager.inMemory(workspace),
    settingsManager,
    customTools: [
      knowledge.tool,
      createWebVisionTool(modelRuntime, workspace),
      delivery,
      planner.tool,
    ],
    excludeTools: [],
  });

  try {
    if (previous?.messages.length)
      session.agent.state.messages = restoredMessages(previous.messages);

    let recovery: ReturnType<typeof installFailureRecovery> | undefined;
    const runtime: Runtime = {
      key,
      workspace,
      session,
      loader,
      ui,
      artifacts,
      writtenPaths,
      skillsDirty: false,
      beginTurn: () => {
        knowledge.beginTurn();
        recovery?.beginTurn();
        artifacts.clear();
        writtenPaths.clear();
        pendingWrites.clear();
      },
      getPlan: planner.getPlan,
      pausePlan: planner.pause,
      emit: (event) => emitter(event),
      setEmitter: (next) => {
        emitter = next;
      },
    };
    session.subscribe(
      createEventBridge(
        workspace,
        (event) => emitter(event),
        writtenPaths,
        pendingWrites,
      ),
    );
    // Startup extensions may await a Web dialog before bindExtensions completes.
    onCreated?.(runtime);
    console.log("Pi runtime: binding extensions", sessionId);
    await session.bindExtensions({
      mode: "rpc",
      uiContext: ui.context(),
      abortHandler: () => {
        ui.cancel();
        void session.abort();
      },
      onError: (error) => {
        console.error("Pi extension error", error);
        emitter({ type: "notification", level: "error", message: error.error });
      },
    });
    recovery = installFailureRecovery(session, (event) => emitter(event));
    console.log("Pi runtime: ready", sessionId);
    return runtime;
  } catch (error) {
    ui.cancel();
    session.dispose();
    throw error;
  }
}
