import type {
  AgentGateway,
  ChatOptions,
  EventEmitter,
} from "../contracts/chat.js";
import { runChatTurn } from "./chat-turn.js";
import { RuntimeRegistry, runtimeKey } from "./runtime-registry.js";
import type { Runtime, RuntimeFactory } from "./runtime-types.js";

export type { StreamEvent, ChatImage } from "../contracts/chat.js";

const defaultFactory: RuntimeFactory = async (options) => {
  const { createRuntime } = await import("./runtime-factory.js");
  return createRuntime(options);
};

/** Application facade: request ownership and cancellation, independent of HTTP. */
export class AgentService implements AgentGateway {
  private registry: RuntimeRegistry;
  private activeRequests = new Set<string>();

  constructor(
    createRuntime: RuntimeFactory = defaultFactory,
    private runTurn: (
      runtime: Runtime,
      options: ChatOptions,
    ) => Promise<void> = runChatTurn,
  ) {
    this.registry = new RuntimeRegistry(createRuntime);
  }

  isUserBusy(userId: string): boolean {
    return [...this.activeRequests].some((key) =>
      key.startsWith(`${userId}\0`),
    );
  }

  disposeUserSessions(userId: string): Promise<void> {
    return this.registry.disposeUser(userId);
  }

  async reloadSkills(): Promise<void> {
    this.registry.markSkillsDirty();
  }

  getRuntime(
    userId: string,
    sessionId: string,
    workspace: string,
    initialEmit?: EventEmitter,
    signal?: AbortSignal,
  ): Promise<Runtime> {
    return this.registry.get(userId, sessionId, workspace, initialEmit, signal);
  }

  async chat(options: ChatOptions): Promise<void> {
    const key = runtimeKey(options.userId, options.sessionId);
    if (this.activeRequests.has(key))
      throw new Error("当前会话仍在执行，请先停止或等待完成");
    this.activeRequests.add(key);
    let runtime: Runtime | undefined;
    const cancel = () => {
      const active =
        runtime ?? this.registry.find(options.userId, options.sessionId);
      active?.ui.cancel();
      void active?.session.abort();
    };
    options.signal?.addEventListener("abort", cancel, { once: true });
    try {
      runtime = await this.getRuntime(
        options.userId,
        options.sessionId,
        options.workspace,
        options.emit,
        options.signal,
      );
      if (options.signal?.aborted) {
        runtime.ui.cancel();
        runtime.setEmitter(() => {});
        return;
      }
      if (runtime.session.isStreaming)
        throw new Error("当前会话仍在执行，请先停止或等待完成");
      await this.runTurn(runtime, options);
    } finally {
      options.signal?.removeEventListener("abort", cancel);
      this.activeRequests.delete(key);
    }
  }

  abort(userId: string, sessionId: string): void {
    const runtime = this.registry.find(userId, sessionId);
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
      this.registry.find(userId, sessionId)?.ui.respond(id, value) ?? false
    );
  }
}
