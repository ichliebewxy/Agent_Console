import { describe, expect, it, vi } from "vitest";
import { AgentService } from "../src/agent/agent-service.js";
import { RuntimeRegistry } from "../src/agent/runtime-registry.js";
import type { ChatOptions } from "../src/contracts/chat.js";
import type { Runtime } from "../src/agent/runtime-types.js";
import { deferred, fakeRuntime } from "./helpers/runtime.js";

const options = (): ChatOptions => ({
  userId: "user",
  sessionId: "session",
  workspace: "workspace",
  message: "hello",
  images: [],
  emit: vi.fn(),
});

describe("agent request lifecycle", () => {
  it("reserves a session during initialization and releases it after completion", async () => {
    const pending = deferred<Runtime>();
    const run = vi.fn(async () => {});
    const agent = new AgentService(() => pending.promise, run);
    const first = agent.chat(options());
    expect(agent.isUserBusy("user")).toBe(true);
    expect(agent.isUserBusy("use")).toBe(false);
    await expect(agent.chat(options())).rejects.toThrow("仍在执行");
    pending.resolve(fakeRuntime().runtime);
    await first;
    expect(run).toHaveBeenCalledOnce();
    expect(agent.isUserBusy("user")).toBe(false);
  });

  it("does not cache a failed factory and permits a retry", async () => {
    const { runtime } = fakeRuntime();
    const factory = vi
      .fn()
      .mockRejectedValueOnce(new Error("bind failed"))
      .mockResolvedValue(runtime);
    const agent = new AgentService(factory, async () => {});
    await expect(agent.chat(options())).rejects.toThrow("bind failed");
    expect(agent.isUserBusy("user")).toBe(false);
    await agent.chat(options());
    expect(factory).toHaveBeenCalledTimes(2);
  });

  it("does not prompt when the client disconnects during initialization", async () => {
    const pending = deferred<Runtime>();
    const { runtime, ui } = fakeRuntime();
    const run = vi.fn(async () => {});
    const agent = new AgentService(() => pending.promise, run);
    const controller = new AbortController();
    const request = agent.chat({ ...options(), signal: controller.signal });
    controller.abort();
    pending.resolve(runtime);
    await request;
    expect(run).not.toHaveBeenCalled();
    expect(ui.cancel).toHaveBeenCalledOnce();
  });

  it("cancels active dialogs and SDK execution, then removes the signal listener", async () => {
    const { runtime, session, ui } = fakeRuntime();
    const entered = deferred<void>();
    const done = deferred<void>();
    const agent = new AgentService(
      async () => runtime,
      async () => {
        entered.resolve();
        await done.promise;
      },
    );
    const controller = new AbortController();
    const remove = vi.spyOn(controller.signal, "removeEventListener");
    const request = agent.chat({ ...options(), signal: controller.signal });
    await entered.promise;
    controller.abort();
    expect(session.abort).toHaveBeenCalledOnce();
    expect(ui.cancel).toHaveBeenCalledOnce();
    done.resolve();
    await request;
    expect(remove).toHaveBeenCalledWith("abort", expect.any(Function));
    expect(agent.isUserBusy("user")).toBe(false);
  });
});

describe("runtime ownership", () => {
  it("routes startup dialog answers before binding finishes and removes failed initialization", async () => {
    const binding = deferred<Runtime>();
    const { runtime, ui } = fakeRuntime();
    const agent = new AgentService(async ({ onCreated }) => {
      onCreated?.(runtime);
      return binding.promise;
    });
    const request = agent.chat(options());
    expect(agent.respond("user", "session", "startup", "yes")).toBe(true);
    expect(ui.respond).toHaveBeenCalledWith("startup", "yes");
    binding.reject(new Error("binding failed"));
    await expect(request).rejects.toThrow("binding failed");
    expect(agent.respond("user", "session", "startup", "yes")).toBe(false);
  });

  it("reuses a workspace runtime and disposes it before changing workspace", async () => {
    const first = fakeRuntime();
    const next = fakeRuntime("other");
    const factory = vi
      .fn()
      .mockResolvedValueOnce(first.runtime)
      .mockResolvedValueOnce(next.runtime);
    const registry = new RuntimeRegistry(factory);
    expect(await registry.get("user", "session", "workspace")).toBe(
      first.runtime,
    );
    expect(await registry.get("user", "session", "workspace")).toBe(
      first.runtime,
    );
    registry.markSkillsDirty();
    expect(first.runtime.skillsDirty).toBe(true);
    expect(first.session.reload).not.toHaveBeenCalled();
    expect(await registry.get("user", "session", "other")).toBe(next.runtime);
    expect(first.session.abort).toHaveBeenCalledOnce();
    expect(first.session.dispose).toHaveBeenCalledOnce();
    expect(factory).toHaveBeenCalledTimes(2);
  });

  it("disposes only the exact user's sessions", async () => {
    const registry = new RuntimeRegistry(
      async ({ key, workspace }) => fakeRuntime(workspace, key).runtime,
    );
    const mine = await registry.get("user", "session", "workspace");
    const other = await registry.get("user2", "session", "workspace");
    await registry.disposeUser("user");
    expect(mine.session.dispose).toHaveBeenCalledOnce();
    expect(other.session.dispose).not.toHaveBeenCalled();
    expect(registry.find("user", "session")).toBeUndefined();
    expect(registry.find("user2", "session")).toBe(other);
  });
});
