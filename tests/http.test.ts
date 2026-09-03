import { once } from "node:events";
import type { Server } from "node:http";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createApplication } from "../src/http/app.js";
import type { AgentService } from "../src/agent/agent-service.js";

let server: Server | undefined;
afterEach(async () => {
  if (server)
    await new Promise<void>((resolve) => server!.close(() => resolve()));
});
async function start() {
  const chat = vi.fn(async (options) =>
    options.emit({ type: "content", content: "mock response" }),
  );
  const agent = {
    chat,
    abort: vi.fn(),
    respond: vi.fn(),
    isUserBusy: () => false,
  } as unknown as AgentService;
  server = createApplication(agent, 0).listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address() as { port: number };
  return { base: `http://127.0.0.1:${address.port}`, chat };
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
});
