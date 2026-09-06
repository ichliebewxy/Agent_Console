import { readFile } from "node:fs/promises";
import { runInNewContext } from "node:vm";
import { expect, it, vi } from "vitest";

async function setup(response: Response) {
  const request = vi.fn(async () => response);
  const context = {
    window: { setInterval: vi.fn(() => 123), clearInterval: vi.fn() } as any,
    Vue: { createApp: vi.fn() },
    fetch: request,
    TextDecoder,
    FormData,
    console,
  };
  for (const file of ["app-core", "knowledge"]) {
    runInNewContext(await readFile(`frontend/js/${file}.js`, "utf8"), context);
  }
  const app = context.window.NebulaNestApp;
  const state = Object.assign(app.data(), app.methods, {
    $refs: { fileInput: { value: "selected" } },
    notify: vi.fn(),
    loadDocuments: vi.fn(async () => {}),
  });
  state.selectedFile = new File(["资料正文"], "码蹄杯资料.docx");
  return { state, request, context };
}

function stream(events: object[], tail = "") {
  const bytes = new TextEncoder().encode(
    ": keepalive\r\n\r\n" +
      events.map((event) => `data: ${JSON.stringify(event)}\r\n\r\n`).join("") +
      tail,
  );
  return new Response(
    new ReadableStream({
      start(controller) {
        // Split inside Chinese UTF-8 sequences and SSE delimiters.
        for (let i = 0; i < bytes.length; i += 2)
          controller.enqueue(bytes.slice(i, i + 2));
        controller.close();
      },
    }),
    { headers: { "Content-Type": "text/event-stream" } },
  );
}

it("updates visible progress while the request is pending and ignores duplicate clicks", async () => {
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const { state, request, context } = await setup(
    new Response(
      new ReadableStream({
        start(value) {
          controller = value;
        },
      }),
      { headers: { "Content-Type": "text/event-stream" } },
    ),
  );
  const work = state.uploadDocument();
  await state.uploadDocument();
  expect(request).toHaveBeenCalledOnce();
  controller.enqueue(
    new TextEncoder().encode(
      'data: {"type":"progress","stage":"indexing","message":"正在生成索引：10 / 32 个片段","processed":10,"total":32,"parent_chunks":19}\n\n',
    ),
  );
  await vi.waitFor(() => expect(state.uploadChunksProcessed).toBe(10));
  expect(state.isUploading).toBe(true);
  expect(state.uploadStepState("parsing")).toBe("done");
  expect(state.uploadStepState("indexing")).toBe("active");
  controller.enqueue(
    new TextEncoder().encode(
      'data: {"type":"complete","filename":"码蹄杯资料.docx","chunks_processed":32,"parent_chunks_processed":19,"message":"码蹄杯资料.docx 入库完成"}\n\n',
    ),
  );
  controller.close();
  await work;
  expect(state.uploadStatus).toBe("success");
  expect(state.uploadProgress).toBe("码蹄杯资料.docx 入库完成");
  expect(state.selectedFile).toBeNull();
  expect(state.uploadParentChunks).toBe(19);
  expect(state.loadDocuments).toHaveBeenCalledOnce();
  expect(context.window.clearInterval).toHaveBeenCalledWith(123);
});

it("decodes fragmented Chinese filenames and content without mojibake", async () => {
  const { state } = await setup(
    stream([
      { type: "progress", stage: "parsing", message: "正在解析码蹄杯资料" },
      {
        type: "complete",
        filename: "码蹄杯资料.docx",
        chunks_processed: 32,
        message: "码蹄杯资料.docx 入库完成",
      },
    ]),
  );
  await state.uploadDocument();
  expect(state.uploadStatus).toBe("success");
  expect(state.uploadProgress).toBe("码蹄杯资料.docx 入库完成");
});

it.each([
  [
    "server error",
    () => stream([{ type: "error", message: "向量服务不可用" }]),
    "向量服务不可用",
  ],
  [
    "truncated stream",
    () => stream([{ type: "progress", stage: "parsing", message: "解析中" }]),
    "连接中断",
  ],
  [
    "HTTP failure",
    () => Response.json({ detail: "文件大小不能超过 50MB" }, { status: 413 }),
    "50MB",
  ],
] as const)(
  "keeps the file selected and exposes %s without claiming success",
  async (_name, response, message) => {
    const { state, context } = await setup(response());
    await state.uploadDocument();
    expect(state.uploadStatus).toBe("error");
    expect(state.uploadProgress).toContain(message);
    expect(state.selectedFile.name).toBe("码蹄杯资料.docx");
    expect(state.isUploading).toBe(false);
    expect(state.loadDocuments).not.toHaveBeenCalled();
    expect(context.window.clearInterval).toHaveBeenCalledWith(123);
  },
);

it("supports an older sidecar's JSON response during rollout", async () => {
  const { state } = await setup(
    Response.json({
      filename: "码蹄杯资料.docx",
      chunks_processed: 32,
      message: "处理完成",
    }),
  );
  await state.uploadDocument();
  expect(state.uploadStatus).toBe("success");
  expect(state.uploadChunksTotal).toBe(32);
});
