import type { EventEmitter } from "../contracts/chat.js";
import type { Runtime, RuntimeFactory } from "./runtime-types.js";

export function runtimeKey(userId: string, sessionId: string): string {
  return `${userId}\0${sessionId}`;
}

/** Owns cached sessions; publish only after successful extension binding. */
export class RuntimeRegistry {
  private runtimes = new Map<string, Runtime>();
  private initializing = new Map<string, Runtime>();
  constructor(private createRuntime: RuntimeFactory) {}

  find(userId: string, sessionId: string): Runtime | undefined {
    const key = runtimeKey(userId, sessionId);
    return this.runtimes.get(key) ?? this.initializing.get(key);
  }

  async get(
    userId: string,
    sessionId: string,
    workspace: string,
    initialEmit: EventEmitter = () => {},
    signal?: AbortSignal,
  ): Promise<Runtime> {
    const key = runtimeKey(userId, sessionId);
    const existing = this.runtimes.get(key);
    if (existing?.workspace === workspace) return existing;
    if (existing) await this.dispose(existing);
    try {
      const runtime = await this.createRuntime({
        key,
        userId,
        sessionId,
        workspace,
        initialEmit,
        onCreated: (created) => {
          this.initializing.set(key, created);
          if (signal?.aborted) {
            created.ui.cancel();
            void created.session.abort();
          }
        },
      });
      this.runtimes.set(key, runtime);
      return runtime;
    } finally {
      this.initializing.delete(key);
    }
  }

  markSkillsDirty(): void {
    for (const runtime of [
      ...this.runtimes.values(),
      ...this.initializing.values(),
    ])
      runtime.skillsDirty = true;
  }

  async disposeUser(userId: string): Promise<void> {
    for (const [key, runtime] of this.runtimes) {
      if (key.startsWith(`${userId}\0`)) await this.dispose(runtime);
    }
  }

  private async dispose(runtime: Runtime): Promise<void> {
    runtime.ui.cancel();
    try {
      await runtime.session.abort();
    } finally {
      runtime.setEmitter(() => {});
      runtime.session.dispose();
      this.runtimes.delete(runtime.key);
    }
  }
}
