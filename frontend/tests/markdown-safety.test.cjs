// Run with jsdom, marked@4.3.0, dompurify@3.4.14 and highlight.js@11.7.0
// available on NODE_PATH.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const { JSDOM } = require("jsdom");
const { marked } = require("marked");
const createDOMPurify = require("dompurify");
const hljs = require("highlight.js");

const frontend = path.resolve(__dirname, "..");
const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost:8765/",
});
const purifier = createDOMPurify(dom.window);
const context = vm.createContext({
  window: dom.window,
  document: dom.window.document,
  URL: dom.window.URL,
  Vue: { createApp() {} },
  marked,
  DOMPurify: purifier,
  hljs,
});
dom.window.DOMPurify = purifier;
vm.runInContext(fs.readFileSync(path.join(frontend, "js/app-core.js"), "utf8"), context);
const methods = dom.window.NebulaNestApp.methods;
methods.configureMarked();
const instance = { escapeHtml: methods.escapeHtml };
const render = (markdown) => methods.parseMarkdown.call(instance, markdown);

test("production page loads sanitizer before the application", () => {
  const html = fs.readFileSync(path.join(frontend, "index.html"), "utf8");
  const sanitizer = html.indexOf("dompurify@3.4.14/dist/purify.min.js");
  const application = html.indexOf("js/app-core.js");
  assert.ok(sanitizer > 0 && application > sanitizer);
});

test("normal Markdown, tables, code blocks and safe links render", () => {
  const result = render("**bold**\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n```js\nconst x = 1;\n```\n\n[site](https://example.com) [local](/doc)");
  assert.match(result, /<strong>bold<\/strong>/);
  assert.match(result, /<table>/);
  assert.match(result, /<code class="hljs language-js">/);
  assert.match(result, /href="https:\/\/example.com"/);
  assert.match(result, /href="\/doc"/);
});

test("script-bearing HTML, SVG and unsafe links are removed", () => {
  const result = render(
    '<img src="data:image/svg+xml,invalid" onerror="alert(1)">' +
    '<svg onload="alert(1)"><circle /></svg>' +
    '[bad](javascript:alert(1))' +
    '<a href="vbscript:alert(1)" target="_blank">bad</a>' +
    '<span style="position:fixed">text</span>'
  );
  assert.doesNotMatch(result, /onerror|onload|<svg|javascript:|vbscript:|data:|target=|style=/i);
  const container = dom.window.document.createElement("div");
  container.innerHTML = result;
  assert.equal(container.querySelector("svg, script, [onerror], [onload], [style]"), null);
  assert.equal(container.querySelector("a[href^='javascript:'], a[href^='vbscript:']"), null);
});

test("sanitizer failure escapes rather than inserts raw HTML", () => {
  delete dom.window.DOMPurify;
  try {
    assert.equal(render('<img src=x onerror="alert(1)">'), '&lt;img src=x onerror="alert(1)"&gt;');
  } finally {
    dom.window.DOMPurify = purifier;
  }
});
