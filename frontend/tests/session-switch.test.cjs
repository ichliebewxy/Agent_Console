const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const context = {
  window: {},
  Vue: { createApp() {} },
  console,
};
vm.createContext(context);
for (const filename of ["app-core.js", "chat.js"]) {
  vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "js", filename), "utf8"), context);
}

test("an active stream prevents replacing its session and message array", async () => {
  const calls = [];
  context.fetch = async (url) => { calls.push(url); return { ok: true, json: async () => ({ messages: [] }) }; };
  const instance = Object.assign(context.window.NebulaNestApp.data(), context.window.NebulaNestApp.methods);
  instance.sessionId = "streaming";
  instance.messages = [{ text: "pending response" }];
  instance.isLoading = true;
  instance.persistState = () => {};
  instance.notify = () => {};

  instance.handleNewChat();
  await instance.loadSession("another");

  assert.equal(instance.sessionId, "streaming");
  assert.equal(instance.messages[0].text, "pending response");
  assert.deepEqual(calls, []);
});

test("late history responses cannot overwrite the selected session", async () => {
  let releaseOld;
  const oldResponse = new Promise((resolve) => { releaseOld = resolve; });
  context.fetch = async (url) => {
    if (url.endsWith("/old")) return oldResponse;
    return { ok: true, json: async () => ({ messages: [{ type: "human", content: "new history" }] }) };
  };
  const instance = Object.assign(context.window.NebulaNestApp.data(), context.window.NebulaNestApp.methods);
  instance.userId = "user";
  instance.persistState = () => {};
  instance.$nextTick = (callback) => callback();
  instance.$refs = {};

  const oldLoad = instance.loadSession("old");
  await instance.loadSession("new");
  releaseOld({ ok: true, json: async () => ({ messages: [{ type: "human", content: "old history" }] }) });
  await oldLoad;

  assert.equal(instance.sessionId, "new");
  assert.equal(instance.messages[0].text, "new history");
});

test("new chat invalidates an in-flight history load", async () => {
  let releaseHistory;
  context.fetch = () => new Promise((resolve) => { releaseHistory = resolve; });
  const instance = Object.assign(context.window.NebulaNestApp.data(), context.window.NebulaNestApp.methods);
  instance.userId = "user";
  instance.persistState = () => {};
  instance.$nextTick = (callback) => callback();
  instance.$refs = {};

  const pending = instance.loadSession("old");
  instance.handleNewChat();
  releaseHistory({ ok: true, json: async () => ({ messages: [{ type: "human", content: "stale" }] }) });
  await pending;

  assert.notEqual(instance.sessionId, "old");
  assert.equal(instance.messages.length, 0);
});
