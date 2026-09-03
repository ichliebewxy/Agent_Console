import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
import { expect, it } from "vitest";

it("restores an old memory-page visit into chat without losing messages or drafts", async () => {
  const saved = {
    activeView: "memory",
    sessionId: "existing_session",
    userInput: "尚未发送的草稿",
    messages: [{ text: "保留历史回复", isUser: false }],
  };
  const context = {
    Vue: { createApp() {} },
    window: {} as any,
    localStorage: { getItem: () => JSON.stringify(saved) },
  };
  runInNewContext(await readFile("frontend/js/app-core.js", "utf8"), context);
  const app = context.window.NebulaNestApp;
  const state = app.data();
  app.methods.restoreState.call(state);
  expect(state.activeView).toBe("chat");
  expect(state.sessionId).toBe(saved.sessionId);
  expect(state.userInput).toBe(saved.userInput);
  expect(state.messages).toEqual(saved.messages);
});
