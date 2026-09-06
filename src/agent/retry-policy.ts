import type { AgentSession } from "@earendil-works/pi-coding-agent";
import type { StreamEvent } from "../contracts/chat.js";

const RETRY_CONTEXT_PREFIX = "[模型调用恢复说明]";
const MAX_RETRIES = 4;
const JITTER_LIMIT_MS = 1000;

type Delay = (milliseconds: number, signal?: AbortSignal) => Promise<void>;

type RetryOptions = {
  random?: () => number;
  delay?: Delay;
};

type RetryInternals = {
  _retryAttempt: number;
  _retryAbortController?: AbortController;
  _prepareRetry: (message: { errorMessage?: string }) => Promise<boolean>;
  _emit: (event: Record<string, unknown>) => void;
  agent: AgentSession["agent"];
  subscribe: AgentSession["subscribe"];
  settingsManager: {
    getRetrySettings(): {
      enabled: boolean;
      maxRetries: number;
      baseDelayMs: number;
    };
  };
};

function abortError(): Error {
  const error = new Error("Retry cancelled");
  error.name = "AbortError";
  return error;
}

export const abortableDelay: Delay = (milliseconds, signal) =>
  new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError());
    const timer = setTimeout(resolve, milliseconds);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(abortError());
      },
      { once: true },
    );
  });

export function retryDelayMs(
  attempt: number,
  baseDelayMs = 1000,
  random: () => number = Math.random,
): number {
  const jitter = Math.floor(
    Math.min(Math.max(random(), 0), 0.999999) * JITTER_LIMIT_MS,
  );
  return baseDelayMs * 2 ** Math.max(0, attempt - 1) + jitter;
}

function messageText(content: unknown): string {
  if (!Array.isArray(content)) return "";
  return content
    .filter(
      (item): item is { type: "text"; text: string } =>
        !!item &&
        typeof item === "object" &&
        (item as { type?: unknown }).type === "text" &&
        typeof (item as { text?: unknown }).text === "string",
    )
    .map((item) => item.text)
    .join("\n");
}

const NON_TRANSIENT_PATTERN =
  /unauthorized|forbidden|permission|authentication|invalid[_ -]?(?:api[_ -]?key|request|argument|parameter)|validation|syntax|insufficient_quota|quota exceeded|billing|not supported|does not exist/i;
const TRANSIENT_PATTERN =
  /network|fetch failed|connection|ECONNRESET|ECONNREFUSED|EAI_AGAIN|ENOTFOUND|socket|timed?\s*out|timeout|terminated|other side closed|websocket|rate.?limit|too many requests|overloaded|service.?unavailable|server.?error|internal.?error|\b408\b|\b409\b|\b425\b|\b429\b|\b5\d\d\b/i;

export function isTransientFailure(error: string): boolean {
  if (!error || NON_TRANSIENT_PATTERN.test(error)) return false;
  return TRANSIENT_PATTERN.test(error);
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, entry]) => `${JSON.stringify(key)}:${canonical(entry)}`)
      .join(",")}}`;
  }
  return JSON.stringify(value) ?? String(value);
}

function toolKey(name: string, args: unknown): string {
  return `${name}\0${canonical(args)}`;
}

function installModelRetry(
  session: AgentSession,
  options: Required<RetryOptions>,
): void {
  const target = session as unknown as RetryInternals;
  if (
    typeof target._prepareRetry !== "function" ||
    typeof target._emit !== "function" ||
    !target.settingsManager
  ) {
    throw new Error("当前 Pi SDK 版本不支持宿主重试策略");
  }

  target._prepareRetry = async (message) => {
    const settings = target.settingsManager.getRetrySettings();
    if (!settings.enabled) return false;
    target._retryAttempt += 1;
    if (target._retryAttempt > settings.maxRetries) {
      target._retryAttempt -= 1;
      return false;
    }

    const attempt = target._retryAttempt;
    const errorMessage = message.errorMessage || "Unknown model error";
    const delayMs = retryDelayMs(attempt, settings.baseDelayMs, options.random);
    target._emit({
      type: "auto_retry_start",
      attempt,
      maxAttempts: settings.maxRetries,
      delayMs,
      errorMessage,
    });

    const messages = target.agent.state.messages;
    const withoutFailure =
      messages.at(-1)?.role === "assistant" ? messages.slice(0, -1) : messages;
    const withoutOldContext = withoutFailure.filter((entry) => {
      if (entry.role !== "user" || !Array.isArray(entry.content)) return true;
      return !messageText(entry.content).startsWith(RETRY_CONTEXT_PREFIX);
    });
    target.agent.state.messages = [
      ...withoutOldContext,
      {
        role: "user",
        content: [
          {
            type: "text",
            text: `${RETRY_CONTEXT_PREFIX}\n上一次模型调用失败：${errorMessage.slice(0, 1200)}\n请先判断错误是否暴露了参数、上下文或指令问题；若需要就调整本轮执行方式。若只是瞬时网络或服务波动，从中断处继续，不要重复已经完成的工具操作。`,
          },
        ],
        timestamp: Date.now(),
      },
    ];

    target._retryAbortController = new AbortController();
    try {
      await options.delay(delayMs, target._retryAbortController.signal);
    } catch {
      const cancelledAttempt = target._retryAttempt;
      target._retryAttempt = 0;
      target._emit({
        type: "auto_retry_end",
        success: false,
        attempt: cancelledAttempt,
        finalError: "Retry cancelled",
      });
      return false;
    } finally {
      target._retryAbortController = undefined;
    }
    return true;
  };

  session.subscribe((event) => {
    if (event.type !== "auto_retry_end") return;
    target.agent.state.messages = target.agent.state.messages.filter(
      (entry) => {
        if (entry.role !== "user" || !Array.isArray(entry.content)) return true;
        return !messageText(entry.content).startsWith(RETRY_CONTEXT_PREFIX);
      },
    );
  });
}

export function installFailureRecovery(
  session: AgentSession,
  emit: (event: StreamEvent) => void,
  retryOptions: RetryOptions = {},
) {
  const options: Required<RetryOptions> = {
    random: retryOptions.random || Math.random,
    delay: retryOptions.delay || abortableDelay,
  };
  installModelRetry(session, options);

  const failures = new Map<
    string,
    { count: number; error: string; toolName: string }
  >();
  const previousBefore = session.agent.beforeToolCall;
  const previousAfter = session.agent.afterToolCall;

  session.agent.beforeToolCall = async (context, signal) => {
    const extensionResult = await previousBefore?.(context, signal);
    if (extensionResult?.block) return extensionResult;
    const key = toolKey(context.toolCall.name, context.args);
    const failure = failures.get(key);
    if (!failure) return extensionResult;
    if (failure.count > MAX_RETRIES) {
      emit({
        type: "retry",
        source: "tool",
        status: "failed",
        tool_name: failure.toolName,
        attempt: MAX_RETRIES,
        max_attempts: MAX_RETRIES,
        error: failure.error,
      });
      return {
        block: true,
        reason:
          "同一工具和参数的网络重试已达到 4 次。请停止原样重试，重新分析原因并修改参数、指令或执行方案。",
      };
    }
    const attempt = failure.count;
    const waitMs = retryDelayMs(attempt, 1000, options.random);
    emit({
      type: "retry",
      source: "tool",
      status: "waiting",
      tool_name: failure.toolName,
      attempt,
      max_attempts: MAX_RETRIES,
      delay_ms: waitMs,
      error: failure.error,
    });
    await options.delay(waitMs, signal);
    return extensionResult;
  };

  session.agent.afterToolCall = async (context, signal) => {
    const extensionResult = await previousAfter?.(context, signal);
    const isError = extensionResult?.isError ?? context.isError;
    const content = extensionResult?.content ?? context.result.content ?? [];
    const key = toolKey(context.toolCall.name, context.args);
    const previousFailure = failures.get(key);
    if (!isError) {
      if (previousFailure) {
        failures.delete(key);
        emit({
          type: "retry",
          source: "tool",
          status: "success",
          tool_name: context.toolCall.name,
          attempt: Math.min(previousFailure.count, MAX_RETRIES),
          max_attempts: MAX_RETRIES,
        });
      }
      return extensionResult;
    }

    const error = messageText(content) || "工具执行失败，未返回错误详情";
    const transient = isTransientFailure(error);
    const failureCount = (previousFailure?.count || 0) + 1;
    const retriesExhausted = transient && failureCount > MAX_RETRIES;
    if (transient) {
      failures.set(key, {
        count: failureCount,
        error,
        toolName: context.toolCall.name,
      });
    } else if (!previousFailure || previousFailure.count <= MAX_RETRIES) {
      failures.delete(key);
    }
    emit({
      type: "retry",
      source: "tool",
      status: retriesExhausted ? "failed" : "review",
      tool_name: context.toolCall.name,
      transient,
      ...(retriesExhausted
        ? { attempt: MAX_RETRIES, max_attempts: MAX_RETRIES }
        : {}),
      error,
    });

    const guidance = retriesExhausted
      ? "相同工具和参数的 4 次瞬时故障重试已经用完。请停止原样重试，修改参数、指令或执行方案。"
      : transient
        ? "宿主判断这可能是瞬时网络或服务波动。请先核对错误；如果参数和指令没有问题，可以再次调用同一工具，宿主会在调用前按 1、2、4、8 秒加随机抖动等待。"
        : "请先分析失败原因。若属于参数、权限、路径或指令问题，请修改调用方式后再试；不要用完全相同的参数盲目重试。";
    return {
      ...extensionResult,
      content: [
        ...content,
        { type: "text" as const, text: `[宿主失败诊断]\n${guidance}` },
      ],
      isError: true,
    };
  };

  return {
    beginTurn() {
      failures.clear();
    },
  };
}
