import { once } from "node:events";
import type { Server } from "node:http";
import express from "express";
import { afterEach, expect, it, vi } from "vitest";
import { sidecarRoutes } from "../src/http/routes/sidecar.js";
import { requestKnowledge } from "../src/integrations/rag/client.js";

vi.mock("../src/integrations/rag/client.js", () => ({
  requestKnowledge: vi.fn(),
}));
const upstream = vi.mocked(requestKnowledge);
let server: Server;
afterEach(async () => {
  vi.resetAllMocks();
  if (server)
    await new Promise<void>((resolve) => server.close(() => resolve()));
});

async function start() {
  server = express().use(sidecarRoutes()).listen(0, "127.0.0.1");
  await once(server, "listening");
  return `http://127.0.0.1:${(server.address() as { port: number }).port}`;
}

it.each(["码蹄杯资料.docx", "résumé.docx", "报告 📚 2026.docx", "report.docx"])(
  "preserves the browser multipart filename and file bytes: %s",
  async (filename) => {
    const base = await start();
    const bytes = new Uint8Array([0, 128, 255, 80, 75]);
    upstream.mockImplementation(async (_path, options) => {
      const file = (options!.body as FormData).get("file") as File;
      expect(file.name).toBe(filename);
      expect(new Uint8Array(await file.arrayBuffer())).toEqual(bytes);
      return Response.json({
        filename,
        chunks_processed: 32,
        message: `${filename} 入库完成`,
      });
    });
    const form = new FormData();
    form.append("file", new Blob([bytes]), filename);
    const response = await fetch(`${base}/documents/upload`, {
      method: "POST",
      body: form,
    });
    expect(response.status).toBe(200);
    expect((await response.json()).filename).toBe(filename);
  },
);

it("forwards progress before ingestion finishes and preserves the terminal result", async () => {
  const base = await start();
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  upstream.mockResolvedValue(
    new Response(
      new ReadableStream({
        start(value) {
          controller = value;
          controller.enqueue(
            encoder.encode('data: {"type":"progress","stage":"parsing"}\n\n'),
          );
        },
      }),
      { headers: { "Content-Type": "text/event-stream" } },
    ),
  );
  const form = new FormData();
  form.append("file", new Blob(["资料"]), "资料.txt");
  const response = await fetch(`${base}/documents/upload`, {
    method: "POST",
    body: form,
    headers: { Accept: "text/event-stream" },
  });
  expect(upstream.mock.calls[0][1]?.headers).toEqual({
    Accept: "text/event-stream",
  });
  expect(response.headers.get("content-type")).toContain("text/event-stream");
  const reader = response.body!.getReader();
  expect(new TextDecoder().decode((await reader.read()).value)).toContain(
    "parsing",
  );
  controller.enqueue(
    encoder.encode('data: {"type":"complete","filename":"资料.txt"}\n\n'),
  );
  controller.close();
  let remaining = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    remaining += new TextDecoder().decode(value);
  }
  expect(remaining).toContain('"filename":"资料.txt"');
});

it("keeps validation failures as JSON even when streaming was requested", async () => {
  const base = await start();
  upstream.mockResolvedValue(
    Response.json({ detail: "不支持的文件格式" }, { status: 400 }),
  );
  const form = new FormData();
  form.append("file", new Blob(["test"]), "invalid.exe");
  const response = await fetch(`${base}/documents/upload`, {
    method: "POST",
    body: form,
    headers: { Accept: "text/event-stream" },
  });
  expect(response.status).toBe(400);
  expect((await response.json()).detail).toBe("不支持的文件格式");
});
