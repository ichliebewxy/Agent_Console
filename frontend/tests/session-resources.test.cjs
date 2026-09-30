const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const methods = {};
const context = {
  window: { NebulaNestApp: { methods } },
  encodeURIComponent,
  console,
};
vm.createContext(context);
for (const filename of ["session-resources.js", "memory.js"]) {
  vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "js", filename), "utf8"), context);
}

function app(fetch) {
  context.fetch = fetch;
  return Object.assign({
    userId: "user", sessionId: "session", memoryScope: "user",
    sessionResources: { project_id: null, skills: null, memory_read_scopes: ["user", "session"], memory_write_scope: "session" },
    sessionSkillSelection: false, sessionResourcesLoading: false,
    memories: [], memoriesLoading: false,
    notify(message) { throw new Error(message); },
  }, methods);
}

const json = (value) => ({ ok: true, json: async () => value });

test("saves a session Skill allowlist and memory policy", async () => {
  let sent;
  const instance = app(async (url, options) => {
    sent = { url, options };
    return json(JSON.parse(options.body));
  });
  instance.sessionResources.project_id = "crm";
  instance.sessionResources.skills = ["pdf"];
  instance.sessionResources.memory_read_scopes = ["project", "session"];
  instance.sessionSkillSelection = true;
  instance.notify = () => {};
  await instance.saveSessionResources();
  assert.equal(sent.url, "/sessions/user/session/resources");
  assert.equal(sent.options.method, "PUT");
  assert.deepEqual(JSON.parse(sent.options.body), {
    project_id: "crm", skills: ["pdf"],
    memory_read_scopes: ["project", "session"], memory_write_scope: "session",
  });
});

test("memory panel reads the selected authorized scope", async () => {
  const calls = [];
  const instance = app(async (url) => {
    calls.push(url);
    if (url.endsWith("/resources")) return json({
      project_id: null, skills: null,
      memory_read_scopes: ["session"], memory_write_scope: "session",
    });
    return json({ memories: [{ id: "one", memory: "fact" }] });
  });
  await instance.loadMemories();
  assert.equal(instance.memoryScope, "session");
  assert.equal(calls[1], "/memory/session/user/session/session");
  assert.equal(instance.memories[0].memory, "fact");
});

test("failed resource loading clears old memories and stops the memory request", async () => {
  const calls = [];
  const notices = [];
  const instance = app(async (url) => {
    calls.push(url);
    return { ok: false, status: 503, json: async () => ({ detail: "unavailable" }) };
  });
  instance.memories = [{ id: "old", memory: "previous session" }];
  instance.notify = (message) => notices.push(message);
  await instance.loadMemories();
  assert.deepEqual(calls, ["/sessions/user/session/resources"]);
  assert.equal(instance.memories.length, 0);
  assert.equal(instance.memoriesLoading, false);
  assert.equal(instance.sessionResourcesLoading, false);
  assert.equal(notices.length, 1);
});

test("a late response from another session cannot replace current memories or resources", async () => {
  let releaseOld;
  const oldResponse = new Promise((resolve) => { releaseOld = resolve; });
  const calls = [];
  const instance = app(async (url) => {
    calls.push(url);
    if (url === "/sessions/user/old/resources") return oldResponse;
    if (url.endsWith("/resources")) return json({
      project_id: null, skills: null, memory_read_scopes: ["session"], memory_write_scope: "session",
    });
    return json({ memories: [{ id: "new", memory: "current" }] });
  });
  instance.sessionId = "old";
  const staleLoad = instance.loadMemories();
  instance.sessionId = "new";
  await instance.loadMemories();
  releaseOld(json({ project_id: null, skills: ["old"], memory_read_scopes: ["user"], memory_write_scope: "user" }));
  await staleLoad;
  assert.deepEqual(calls, [
    "/sessions/user/old/resources",
    "/sessions/user/new/resources",
    "/memory/session/user/new/session",
  ]);
  assert.equal(instance.sessionResources.memory_write_scope, "session");
  assert.equal(instance.memories[0].memory, "current");
  assert.equal(instance.memoriesLoading, false);
});
