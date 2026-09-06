import { once } from "node:events";
import type { Server } from "node:http";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createApplication } from "../src/http/app.js";
import type { AgentGateway, ChatOptions } from "../src/contracts/chat.js";

let server: Server | undefined;
afterEach(async () => {
  if (server)
    await new Promise<void>((resolve) => server!.close(() => resolve()));
});
async function start() {
  const chat = vi.fn(async (options: ChatOptions) =>
    options.emit({ type: "content", content: "mock response" }),
  );
  const agent = {
    chat,
    abort: vi.fn(),
    respond: vi.fn(() => false),
    isUserBusy: () => false,
    disposeUserSessions: vi.fn(async () => {}),
    reloadSkills: vi.fn(async () => {}),
  } satisfies AgentGateway;
  server = createApplication(agent, 0).listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address() as { port: number };
  return { base: `http://127.0.0.1:${address.port}`, chat, agent };
}
describe("HTTP routing without a model runtime", () => {
  it("serves the workbench while retired endpoints and assets return 404", async () => {
    const { base } = await start();
    const page = await fetch(base);
    expect(page.status).toBe(200);
    expect(await page.text()).toContain("二狗子助手");
    for (const [method, route] of [
      ["GET", "/memory/status"],
      ["GET", "/memory/test_user"],
      ["POST", "/memory/test_user"],
      ["PUT", "/memory/test_entry"],
      ["DELETE", "/memory/test_entry"],
      ["DELETE", "/memory/user/test_user"],
      ["GET", "/js/memory.js"],
    ]) {
      const response = await fetch(`${base}${route}`, { method });
      expect(response.status, `${method} ${route}`).toBe(404);
      expect(await response.json()).toEqual({ detail: "接口或资源不存在" });
    }
  });

  it("streams application events through an injected agent", async () => {
    const { base, chat } = await start();
    const response = await fetch(`${base}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: "hello",
        user_id: "http_test",
        session_id: "test",
      }),
    });
    const text = await response.text();
    expect(text).toContain("mock response");
    expect(text).toContain("[DONE]");
    expect(chat).toHaveBeenCalledOnce();
  });
  it("rejects cross-origin requests before they reach business services", async () => {
    const { base, chat } = await start();
    const response = await fetch(`${base}/chat/stream`, {
      method: "POST",
      headers: { Origin: "https://untrusted.example" },
    });
    expect(response.status).toBe(403);
    expect(chat).not.toHaveBeenCalled();
  });

  it("keeps invalid chat errors inside SSE and expired dialog responses at 410", async () => {
    const { base } = await start();
    const stream = await fetch(`${base}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    expect(stream.status).toBe(200);
    expect(stream.headers.get("content-type")).toContain("text/event-stream");
    expect(await stream.text()).toContain('"content":"消息不能为空"');
    const dialog = await fetch(`${base}/chat/ui-response`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: "expired", value: null }),
    });
    expect(dialog.status).toBe(410);
    expect(await dialog.json()).toEqual({ accepted: false });
  });

  it("normalizes parser errors to JSON without changing the parser status", async () => {
    const { base, chat } = await start();
    const response = await fetch(`${base}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{",
    });
    expect(response.status).toBe(400);
    expect(await response.json()).toEqual({ detail: expect.any(String) });
    expect(chat).not.toHaveBeenCalled();
  });

  it("retains validation and missing-resource response contracts", async () => {
    const { base } = await start();
    const missing = await fetch(
      `${base}/sessions/http_contract/does-not-exist`,
    );
    expect(missing.status).toBe(404);
    expect(await missing.json()).toEqual({ detail: "会话不存在" });
    const artifact = await fetch(
      `${base}/artifacts/http_contract/does-not-exist?path=README.md`,
    );
    expect(artifact.status).toBe(404);
    expect(await artifact.json()).toEqual({ detail: "交付物不存在" });
    const skill = await fetch(`${base}/runtime-config/skills`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "../bad" }),
    });
    expect(skill.status).toBe(422);
    expect((await skill.json()).detail).toContain("Skill 名称");
  });
});
