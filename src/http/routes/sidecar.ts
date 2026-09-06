import { Router, type Request, type Response } from "express";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { errorMessage } from "../../shared/errors.js";
import { upload } from "../upload.js";
import { requestKnowledge } from "../../integrations/rag/client.js";

export function sidecarRoutes() {
  const router = Router();
  async function proxyJson(
    request: Request,
    response: Response,
    targetPath: string,
  ): Promise<void> {
    try {
      const upstream = await requestKnowledge(targetPath, {
        method: request.method,
      });
      response
        .status(upstream.status)
        .type(upstream.headers.get("content-type") || "application/json")
        .send(Buffer.from(await upstream.arrayBuffer()));
    } catch (error) {
      response
        .status(503)
        .json({ detail: `知识库服务不可用：${errorMessage(error)}` });
    }
  }

  router.get("/documents", (req, res) => {
    void proxyJson(req, res, "/documents");
  });
  router.delete("/documents/:filename", (req, res) => {
    void proxyJson(
      req,
      res,
      `/documents/${encodeURIComponent(req.params.filename)}`,
    );
  });
  router.post(
    "/documents/upload",
    upload.single("file"),
    async (request, response) => {
      try {
        if (!request.file) throw new Error("请选择文档");
        const form = new FormData();
        form.append(
          "file",
          new Blob([new Uint8Array(request.file.buffer)], {
            type: request.file.mimetype,
          }),
          request.file.originalname,
        );
        const upstream = await requestKnowledge("/documents/upload", {
          method: "POST",
          body: form,
          headers: { Accept: request.get("accept") || "application/json" },
        });
        if (
          upstream.headers.get("content-type")?.includes("text/event-stream") &&
          upstream.body
        ) {
          response.status(upstream.status).set({
            "Content-Type": "text/event-stream; charset=utf-8",
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
          });
          response.flushHeaders();
          // Forward each event immediately, without buffering the full upload.
          await pipeline(
            Readable.fromWeb(
              upstream.body as import("node:stream/web").ReadableStream,
            ),
            response,
          );
          return;
        }
        response
          .status(upstream.status)
          .type("application/json")
          .send(Buffer.from(await upstream.arrayBuffer()));
      } catch (error) {
        if (response.headersSent) {
          response.destroy(error instanceof Error ? error : undefined);
          return;
        }
        response.status(503).json({ detail: errorMessage(error) });
      }
    },
  );

  return router;
}
