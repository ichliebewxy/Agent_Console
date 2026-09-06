import { chatSupportsImages } from "../config/models.js";
import { appendMessages } from "../storage/session-store.js";
import { preparePrompt } from "./prompt-images.js";
import { collectArtifacts } from "./collect-artifacts.js";
import { unfinishedPlanPrompt } from "../tools/plan-tool.js";
import type { ChatOptions } from "../contracts/chat.js";
import type { TaskPlan } from "../contracts/sessions.js";
import type { Runtime } from "./runtime-types.js";

/** One turn owns its emitter and releases it on every preparation/prompt failure. */
export async function runChatTurn(
  runtime: Runtime,
  options: ChatOptions,
): Promise<void> {
  runtime.setEmitter(options.emit);
  try {
    if (runtime.skillsDirty) {
      runtime.skillsDirty = false;
      try {
        await runtime.session.reload();
      } catch (error) {
        runtime.skillsDirty = true;
        throw error;
      }
    }
    if (options.signal?.aborted) return;
    runtime.beginTurn();
    const { imageContent, promptText } = await preparePrompt(options);
    if (options.signal?.aborted) return;
    const startedAt = new Date().toISOString();
    let assistantText = "";
    let ragTrace: Record<string, unknown> | null = null;
    let turnPlan: TaskPlan | null = runtime.getPlan();
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
      if (event.type === "plan") {
        turnPlan =
          event.plan && typeof event.plan === "object"
            ? (event.plan as TaskPlan)
            : null;
      }
      userEmitter(event);
    });
    if (turnPlan)
      runtime.emit({ type: "plan", plan: turnPlan, ...turnPlan });
    await appendMessages(options.userId, options.sessionId, options.workspace, [
      {
        type: "human",
        content: options.message,
        timestamp: startedAt,
        workspace: options.workspace,
        images: options.images,
      },
    ]);
    let promptError: unknown;
    try {
      if (!options.signal?.aborted)
        await runtime.session.prompt(
          promptText + unfinishedPlanPrompt(turnPlan),
          {
            images: chatSupportsImages ? imageContent : [],
          },
        );
    } catch (error) {
      promptError = error;
    }
    try {
      await collectArtifacts(runtime, options);
    } finally {
      // Save a resumable checkpoint even when collection or the request fails.
      try {
        turnPlan = await runtime.pausePlan();
      } finally {
        runtime.setEmitter(() => {});
      }
    }
    await appendMessages(options.userId, options.sessionId, options.workspace, [
      {
        type: "ai",
        content: assistantText.trim(),
        timestamp: new Date().toISOString(),
        workspace: options.workspace,
        rag_trace: ragTrace,
        artifacts: [...runtime.artifacts.values()],
        plan: turnPlan,
      },
    ]);
    if (runtime.artifacts.size)
      options.emit({
        type: "artifacts",
        artifacts: [...runtime.artifacts.values()],
      });
    if (promptError) throw promptError;
  } finally {
    runtime.setEmitter(() => {});
  }
}
