import { vi } from "vitest";
import type { EventEmitter, StreamEvent } from "../../src/contracts/chat.js";
import type { Runtime } from "../../src/agent/runtime-types.js";

export function fakeRuntime(workspace = "workspace", key = "user\0session") {
  let emit: EventEmitter = () => {};
  const session = {
    isStreaming: false,
    prompt: vi.fn(async (_text: string, _options?: unknown) => {}),
    reload: vi.fn(async () => {}),
    abort: vi.fn(async () => {}),
    dispose: vi.fn(),
  };
  const ui = { cancel: vi.fn(), respond: vi.fn(() => true) };
  // Only the SDK/UI boundary is substituted; application orchestration is real.
  const runtime = {
    key,
    workspace,
    session,
    ui,
    loader: {},
    artifacts: new Map(),
    writtenPaths: new Set(),
    skillsDirty: false,
    getPlan: vi.fn(() => null),
    pausePlan: vi.fn(async () => null),
    beginTurn: vi.fn(() => {
      runtime.artifacts.clear();
      runtime.writtenPaths.clear();
    }),
    emit: (event: StreamEvent) => emit(event),
    setEmitter: (next: EventEmitter) => {
      emit = next;
    },
  } as unknown as Runtime;
  return { runtime, session, ui };
}

export function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((done, fail) => {
    resolve = done;
    reject = fail;
  });
  return { promise, resolve, reject };
}
