import { readFile } from "node:fs/promises";
import path from "node:path";
import {
  createAgentSession,
  DefaultResourceLoader,
  ModelRuntime,
  SessionManager,
  SettingsManager,
} from "@earendil-works/pi-coding-agent";
import {
  agentDir,
  builtinSkillsDirs,
  chatModel,
  chatProvider,
  chatSupportsImages,
  userSkillsDir,
} from "../config/index.js";
import { createKnowledgeTool, type RagTrace } from "../tools/knowledge-tool.js";
import { resolvePluginResources } from "../integrations/pi/plugin-resources.js";
import {
  appendMessages,
  loadSession,
  type StoredMessage,
} from "../storage/session-store.js";
import { buildSystemPrompt } from "./system-prompt.js";
import { createWebVisionTool } from "../tools/vision-tool.js";
import { WebUI } from "./web-ui.js";
import { resolveShellPath } from "../integrations/pi/shell-config.js";
import {
  describeArtifact,
  type Artifact,
} from "../services/artifact-service.js";

import { createDeliveryTool } from "../tools/delivery-tool.js";

export type StreamEvent = Record<string, unknown>;
export type ChatImage = { path: string; name: string; mimeType: string };

type Runtime = {
  key: string;
  workspace: string;
  session: Awaited<ReturnType<typeof createAgentSession>>["session"];
  loader: DefaultResourceLoader;
  ui: WebUI;
  artifacts: Map<string, Artifact>;
  writtenPaths: Set<string>;
  skillsDirty: boolean;
  beginTurn: () => void;
  emit: (event: StreamEvent) => void;
  setEmitter: (emitter: (event: StreamEvent) => void) => void;
};

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

function restoredMessages(messages: StoredMessage[]): any[] {
  return messages.map((message) => {
    const timestamp = Date.parse(message.timestamp) || Date.now();
    if (message.type === "human") {
      const attachments = message.images?.length
        ? `\n\n[历史图片附件，如需重新查看请调用 describe_image]\n${message.images.map((image) => `- ${image.path}`).join("\n")}`
        : "";
      return {
        role: "user",
        content: [{ type: "text", text: message.content + attachments }],
        timestamp,
      };
    }
    return {
      role: "assistant",
      content: [{ type: "text", text: message.content }],
      api: "openai-completions",
      provider: chatProvider,
      model: chatModel,
      usage: {
        input: 0,
        output: 0,
        cacheRead: 0,
        cacheWrite: 0,
        totalTokens: 0,
        cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
      },
      stopReason: "stop",
      timestamp,
    };
  });
}

export class AgentService {
  private runtimes = new Map<string, Runtime>();
  private activeRequests = new Set<string>();

  isUserBusy(userId: string): boolean {
    return [...this.activeRequests].some((key) =>
      key.startsWith(`${userId}\0`),
    );
  }

  private key(userId: string, sessionId: string): string {
    return `${userId}\0${sessionId}`;
  }

  async disposeUserSessions(userId: string): Promise<void> {
    for (const [key, runtime] of this.runtimes) {
      if (!key.startsWith(`${userId}\0`)) continue;
      runtime.ui.cancel();
      await runtime.session.abort();
      runtime.session.dispose();
      this.runtimes.delete(key);
    }
  }

  async reloadSkills(): Promise<void> {
    // Reload at the next turn boundary so uploading cannot interrupt an active task.
    for (const runtime of this.runtimes.values()) runtime.skillsDirty = true;
  }

  async getRuntime(
    userId: string,
    sessionId: string,
    workspace: string,
    initialEmit: (event: StreamEvent) => void = () => {},
  ): Promise<Runtime> {
    const key = this.key(userId, sessionId);
    const existing = this.runtimes.get(key);
    if (existing && existing.workspace === workspace) return existing;
    if (existing) {
      existing.ui.cancel();
      await existing.session.abort();
      existing.session.dispose();
      this.runtimes.delete(key);
    }

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
        retry: { enabled: true, maxRetries: 2, baseDelayMs: 1000 },
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
        paths.map((file) =>
          describeArtifact(workspace, file, userId, sessionId),
        ),
      );
      for (const file of files) artifacts.set(file.path, file);
      emitter({ type: "artifacts", artifacts: [...artifacts.values()] });
      return files;
    });
    const knowledge = createKnowledgeTool((trace: RagTrace) =>
      emitter({ type: "trace", rag_trace: trace }),
    );
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
      ],
      excludeTools: [],
    });

    const previous = await loadSession(userId, sessionId);
    if (previous?.messages.length)
      session.agent.state.messages = restoredMessages(previous.messages);

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
        artifacts.clear();
        writtenPaths.clear();
        pendingWrites.clear();
      },
      emit: (event) => emitter(event),
      setEmitter: (next) => {
        emitter = next;
      },
    };
    session.subscribe((event: any) => {
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
            emitter({
              type: "error",
              content:
                event.message.errorMessage || "模型请求失败，未返回错误详情",
            });
          }
        }
      } catch (error) {
        console.error("pi event bridge failed", error);
      }
    });
    this.runtimes.set(key, runtime);
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
    console.log("Pi runtime: ready", sessionId);
    return runtime;
  }

  async chat(options: {
    userId: string;
    sessionId: string;
    workspace: string;
    message: string;
    images: ChatImage[];
    emit: (event: StreamEvent) => void;
    signal?: AbortSignal;
  }): Promise<void> {
    const requestKey = this.key(options.userId, options.sessionId);
    if (this.activeRequests.has(requestKey))
      throw new Error("当前会话仍在执行，请先停止或等待完成");
    this.activeRequests.add(requestKey);
    try {
      const runtime = await this.getRuntime(
        options.userId,
        options.sessionId,
        options.workspace,
        options.emit,
      );
      if (options.signal?.aborted) {
        runtime.ui.cancel();
        runtime.setEmitter(() => {});
        return;
      }
      if (runtime.session.isStreaming)
        throw new Error("当前会话仍在执行，请先停止或等待完成");
      runtime.setEmitter(options.emit);
      if (runtime.skillsDirty) {
        runtime.skillsDirty = false;
        try {
          await runtime.session.reload();
        } catch (error) {
          runtime.skillsDirty = true;
          throw error;
        }
      }
      runtime.beginTurn();
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
      const startedAt = new Date().toISOString();
      let assistantText = "";
      let ragTrace: Record<string, unknown> | null = null;
      const userEmitter = options.emit;
      runtime.setEmitter((event) => {
        if (event.type === "content" && typeof event.content === "string")
          assistantText += event.content;
        if (
          event.type === "trace" &&
          event.rag_trace &&
          typeof event.rag_trace === "object"
        ) {
          ragTrace = event.rag_trace as Record<string, unknown>;
        }
        userEmitter(event);
      });
      await appendMessages(
        options.userId,
        options.sessionId,
        options.workspace,
        [
          {
            type: "human",
            content: options.message,
            timestamp: startedAt,
            workspace: options.workspace,
            images: options.images,
          },
        ],
      );
      let promptError: unknown;
      try {
        await runtime.session.prompt(promptText, {
          images: chatSupportsImages ? imageContent : [],
        });
      } catch (error) {
        promptError = error;
      } finally {
        runtime.setEmitter(() => {});
      }
      for (const relative of runtime.writtenPaths) {
        try {
          const file = await describeArtifact(
            options.workspace,
            relative,
            options.userId,
            options.sessionId,
          );
          runtime.artifacts.set(file.path, file);
        } catch {
          /* Deleted or non-deliverable files are not exposed. */
        }
      }
      await appendMessages(
        options.userId,
        options.sessionId,
        options.workspace,
        [
          {
            type: "ai",
            content: assistantText.trim(),
            timestamp: new Date().toISOString(),
            workspace: options.workspace,
            rag_trace: ragTrace,
            artifacts: [...runtime.artifacts.values()],
          },
        ],
      );
      if (runtime.artifacts.size)
        options.emit({
          type: "artifacts",
          artifacts: [...runtime.artifacts.values()],
        });
      if (promptError) throw promptError;
    } finally {
      this.activeRequests.delete(requestKey);
    }
  }

  abort(userId: string, sessionId: string): void {
    const runtime = this.runtimes.get(this.key(userId, sessionId));
    runtime?.ui.cancel();
    void runtime?.session.abort();
  }

  respond(
    userId: string,
    sessionId: string,
    id: string,
    value: unknown,
  ): boolean {
    return (
      this.runtimes.get(this.key(userId, sessionId))?.ui.respond(id, value) ??
      false
    );
  }
}
