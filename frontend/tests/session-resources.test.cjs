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
    memoryLimit: 100, memoryListKey: null, memoriesHasMore: false,
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
    workspace_dir: null, permission_mode: "relaxed",
  });
});

test("folder selection preserves saved resources and clearing it returns to folderless mode", async () => {
  let saved = { project_id: "crm", skills: ["pdf"], memory_read_scopes: ["session"], memory_write_scope: "session", permission_mode: "restricted", workspace_dir: null };
  const instance = app(async (_url, options) => {
    if (options) saved = JSON.parse(options.body);
    return json(saved);
  });
  instance.notify = () => {};
  instance.showFolderPicker = true;
  await instance.setWorkspaceFolder("D:\\项目 with spaces");
  assert.equal(instance.activeWorkspaceDir, "D:\\项目 with spaces");
  assert.equal(instance.activePermissionMode, "restricted");
  assert.deepEqual(saved.skills, ["pdf"]);
  assert.equal(saved.project_id, "crm");
  assert.equal(instance.showFolderPicker, false);
  await instance.setWorkspaceFolder(null);
  assert.equal(saved.workspace_dir, null);
  assert.equal(instance.activeWorkspaceDir, null);
});

test("an active chat blocks directory and permission changes", async () => {
  const calls = [];
  const instance = app(async (url) => { calls.push(url); return json({}); });
  instance.isLoading = true;
  await instance.openFolderPicker();
  await instance.setWorkspaceFolder("D:\\other");
  await instance.saveSessionResources();
  assert.deepEqual(calls, []);
});

test("a stale folder listing cannot replace a newer navigation", async () => {
  let releaseOld;
  const instance = app(async (url) => {
    if (url.endsWith("old")) return new Promise((resolve) => { releaseOld = resolve; });
    return json({ path: "new", directories: [], roots: [] });
  });
  instance.showFolderPicker = true;
  const oldLoad = instance.browseFolder("old");
  await instance.browseFolder("new");
  releaseOld(json({ path: "old", directories: [], roots: [] }));
  await oldLoad;
  assert.equal(instance.folderListing.path, "new");
  assert.equal(instance.folderPathInput, "new");
  assert.equal(instance.folderLoading, false);
});

test("a folder save completing after a session switch cannot replace current resources", async () => {
  let releaseSave;
  const instance = app(async () => new Promise((resolve) => { releaseSave = resolve; }));
  const pending = instance.persistSessionResources({ workspace_dir: "D:\\old" });
  instance.sessionId = "new";
  instance.activeWorkspaceDir = null;
  releaseSave(json({ workspace_dir: "D:\\old", skills: null }));
  assert.equal(await pending, false);
  assert.equal(instance.activeWorkspaceDir, null);
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
  assert.equal(calls[1], "/memory/session/user/session/session?limit=100");
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
    "/memory/session/user/new/session?limit=100",
  ]);
  assert.equal(instance.sessionResources.memory_write_scope, "session");
  assert.equal(instance.memories[0].memory, "current");
  assert.equal(instance.memoriesLoading, false);
});

test("memory panel can request the next hundred entries", async () => {
  const calls = [];
  const instance = app(async (url) => {
    calls.push(url);
    if (url.endsWith("/resources")) return json({
      project_id: null, skills: null, memory_read_scopes: ["session"], memory_write_scope: "session",
    });
    return json({ memories: [{ id: "one", memory: "fact" }], has_more: url.endsWith("limit=100") });
  });
  await instance.loadMemories();
  assert.equal(instance.memoriesHasMore, true);
  await instance.loadMoreMemories();
  assert.equal(instance.memoryLimit, 200);
  assert.equal(calls[3], "/memory/session/user/session/session?limit=200");
  assert.equal(instance.memoriesHasMore, false);
});
