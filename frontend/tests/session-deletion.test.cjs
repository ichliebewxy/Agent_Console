const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const { JSDOM } = require("jsdom");

const frontend = path.resolve(__dirname, "..");
const context = {
  window: { confirm: () => true },
  Vue: { createApp() {} },
  console,
  encodeURIComponent,
};
vm.createContext(context);
for (const filename of ["app-core.js", "chat.js"]) {
  vm.runInContext(fs.readFileSync(path.join(frontend, "js", filename), "utf8"), context);
}

function app(fetch) {
  context.fetch = fetch;
  const instance = Object.assign(context.window.NebulaNestApp.data(), context.window.NebulaNestApp.methods);
  instance.userId = "user";
  instance.sessionId = "current";
  instance.messages = [{ text: "previous" }];
  instance.sessions = [{ session_id: "current" }, { session_id: "other" }];
  instance.persistState = () => {};
  instance.notify = (message) => { instance.notice = message; };
  return instance;
}

test("clearing the current chat deletes its backend session before starting a new one", async () => {
  const calls = [];
  const instance = app(async (url, options) => {
    calls.push({ url, method: options.method });
    return { ok: true };
  });
  await instance.handleClearChat();
  assert.deepEqual(calls, [{ url: "/sessions/user/current", method: "DELETE" }]);
  assert.notEqual(instance.sessionId, "current");
  assert.equal(instance.messages.length, 0);
  assert.deepEqual(instance.sessions.map((item) => item.session_id), ["other"]);
});

test("deleting a past session keeps the active chat", async () => {
  const instance = app(async () => ({ ok: true }));
  await instance.deleteSession("other");
  assert.equal(instance.sessionId, "current");
  assert.equal(instance.messages.length, 1);
  assert.deepEqual(instance.sessions.map((item) => item.session_id), ["current"]);
});

test("a failed delete preserves the current chat", async () => {
  const instance = app(async () => ({ ok: false, status: 500, json: async () => ({ detail: "failed" }) }));
  await instance.handleClearChat();
  assert.equal(instance.sessionId, "current");
  assert.equal(instance.messages.length, 1);
  assert.match(instance.notice, /failed/);
});

test("history provides separate open and delete actions for resource-only sessions", () => {
  const html = fs.readFileSync(path.join(frontend, "index.html"), "utf8");
  const row = new JSDOM(html).window.document.querySelector(".history-open").parentElement;
  assert.equal(row.querySelectorAll("button.history-open").length, 1);
  assert.equal(row.querySelectorAll("button.history-delete").length, 1);
  assert.equal(row.querySelector("button button"), null);
  assert.match(row.textContent, /尚未对话 · 已保存会话资源/);
});
