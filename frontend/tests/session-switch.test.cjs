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
