import { describe, expect, it, vi } from "vitest";
import {
  installFailureRecovery,
  isTransientFailure,
  retryDelayMs,
} from "../src/agent/retry-policy.js";

function fakeSession() {
  const listeners: Array<(event: any) => void> = [];
  const sdkEvents: any[] = [];
  const session: any = {
    _retryAttempt: 0,
    _retryAbortController: undefined,
    _prepareRetry: async () => false,
    _emit: (event: any) => sdkEvents.push(event),
    settingsManager: {
      getRetrySettings: () => ({
        enabled: true,
        maxRetries: 4,
        baseDelayMs: 1000,
      }),
    },
    agent: {
      state: { messages: [] },
      beforeToolCall: vi.fn(async () => undefined),
      afterToolCall: vi.fn(async () => undefined),
    },
    subscribe: vi.fn((listener: (event: any) => void) => {
      listeners.push(listener);
      return () => {};
    }),
  };
  return { session, listeners, sdkEvents };
}

describe("failure recovery policy", () => {
  it("uses 1, 2, 4 and 8 second backoff plus less than one second jitter", () => {
    expect(
      [1, 2, 3, 4].map((attempt) => retryDelayMs(attempt, 1000, () => 0.5)),
    ).toEqual([1500, 2500, 4500, 8500]);
    expect(retryDelayMs(1, 1000, () => 1)).toBe(1999);
  });

  it("retries transient failures but not parameter, permission or quota errors", () => {
    expect(isTransientFailure("fetch failed: ECONNRESET")).toBe(true);
    expect(isTransientFailure("HTTP 503 service unavailable")).toBe(true);
    expect(isTransientFailure("invalid parameter: path")).toBe(false);
    expect(isTransientFailure("permission denied")).toBe(false);
    expect(isTransientFailure("insufficient_quota")).toBe(false);
  });

  it("returns model failures for diagnosis before a jittered retry", async () => {
    const { session, listeners, sdkEvents } = fakeSession();
    session.agent.state.messages = [
      { role: "user", content: [{ type: "text", text: "继续任务" }] },
      {
        role: "assistant",
        content: [],
        stopReason: "error",
        errorMessage: "fetch failed",
      },
    ];
    const delay = vi.fn(
      async (_milliseconds: number, _signal?: AbortSignal) => {},
    );
    installFailureRecovery(session, vi.fn(), { random: () => 0.25, delay });

    await expect(
      session._prepareRetry({ errorMessage: "fetch failed" }),
    ).resolves.toBe(true);
    expect(delay).toHaveBeenCalledWith(1250, expect.any(AbortSignal));
    expect(sdkEvents.at(-1)).toMatchObject({
      type: "auto_retry_start",
      attempt: 1,
      maxAttempts: 4,
      delayMs: 1250,
    });
    expect(session.agent.state.messages.at(-1).content[0].text).toContain(
      "[模型调用恢复说明]",
    );

    listeners[0]({ type: "auto_retry_end", success: true });
    expect(session.agent.state.messages).toHaveLength(1);
  });

  it("lets the model inspect tool errors and delays only an unchanged transient retry", async () => {
    const { session } = fakeSession();
    const emit = vi.fn();
    const delay = vi.fn(async () => {});
    installFailureRecovery(session, emit, { random: () => 0.4, delay });
    const call = {
      toolCall: { name: "fetch", id: "call-1" },
      args: { url: "https://example.test" },
    };

    const override = await session.agent.afterToolCall({
      ...call,
      isError: true,
      result: { content: [{ type: "text", text: "fetch failed" }] },
    });
    expect(override.content.at(-1).text).toContain("[宿主失败诊断]");
    expect(emit).toHaveBeenLastCalledWith(
      expect.objectContaining({
        type: "retry",
        source: "tool",
        status: "review",
        transient: true,
      }),
    );

    await session.agent.beforeToolCall(call, undefined);
    expect(delay).toHaveBeenCalledWith(1400, undefined);

    await session.agent.afterToolCall({
      ...call,
      isError: false,
      result: { content: [{ type: "text", text: "ok" }] },
    });
    expect(emit).toHaveBeenLastCalledWith(
      expect.objectContaining({ status: "success", attempt: 1 }),
    );
  });

  it("stops an unchanged tool call after four retries", async () => {
    const { session } = fakeSession();
    const emit = vi.fn();
    const delay = vi.fn(
      async (_milliseconds: number, _signal?: AbortSignal) => {},
    );
    installFailureRecovery(session, emit, { random: () => 0, delay });
    const call = {
      toolCall: { name: "fetch", id: "call-limit" },
      args: { url: "https://example.test" },
    };
    const failure = {
      ...call,
      isError: true,
      result: { content: [{ type: "text", text: "HTTP 503" }] },
    };

    await session.agent.afterToolCall(failure);
    for (let attempt = 0; attempt < 4; attempt += 1) {
      await session.agent.beforeToolCall(call, undefined);
      await session.agent.afterToolCall(failure);
    }
    expect(delay.mock.calls.map(([milliseconds]) => milliseconds)).toEqual([
      1000, 2000, 4000, 8000,
    ]);
    expect(emit).toHaveBeenLastCalledWith(
      expect.objectContaining({
        status: "failed",
        attempt: 4,
        max_attempts: 4,
      }),
    );

    await expect(
      session.agent.beforeToolCall(call, undefined),
    ).resolves.toMatchObject({ block: true });
    expect(delay).toHaveBeenCalledTimes(4);
  });
});
