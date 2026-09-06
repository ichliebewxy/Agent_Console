import assert from "node:assert/strict";
import { once } from "node:events";
import type { AddressInfo } from "node:net";

// Import the real startup path on an OS-assigned port; never stop another server.
process.env.PORT = "0";
const { server } = await import("../src/main.js");
try {
  if (!server.listening) await once(server, "listening");
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  const health = await fetch(`${base}/health`).then((response) =>
    response.json(),
  );
  assert.equal(health.ok, true);
  assert.equal(health.service, "pi-web");
  const config = await fetch(`${base}/runtime-config`).then((response) =>
    response.json(),
  );
  assert.equal(config.config.runtime.version, "0.84.4");
  assert.deepEqual(config.config.pluginErrors, []);
  for (const resource of [
    "/",
    "/js/chat.js",
    "/js/chat-stream.js",
    "/js/chat-messages.js",
    "/js/history.js",
    "/style.css",
    "/vendor/purify.min.js",
  ]) {
    const response = await fetch(`${base}${resource}`);
    assert.equal(response.status, 200, resource);
    assert.ok((await response.text()).length > 0, resource);
  }
  console.log(
    `Smoke passed: real startup, health, ${config.config.plugins.length} plugin manifests and 8 frontend resources. RAG reachable: ${health.rag}.`,
  );
} finally {
  server.closeAllConnections();
  await new Promise<void>((resolve, reject) =>
    server.close((error) => (error ? reject(error) : resolve())),
  );
}
