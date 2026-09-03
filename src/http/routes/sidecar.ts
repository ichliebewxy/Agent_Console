import { Router, type Request, type Response } from "express";
import { errorMessage, upload } from "../shared.js";
import { ragBaseUrl } from "../../config/index.js";

export function sidecarRoutes() {
  const router = Router();
  async function proxyJson(
    request: Request,
    response: Response,
    targetPath: string,
  ): Promise<void> {
    try {
      const upstream = await fetch(`${ragBaseUrl}${targetPath}`, {
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
        const upstream = await fetch(`${ragBaseUrl}/documents/upload`, {
          method: "POST",
          body: form,
        });
        response
          .status(upstream.status)
          .type("application/json")
          .send(Buffer.from(await upstream.arrayBuffer()));
      } catch (error) {
        response.status(503).json({ detail: errorMessage(error) });
      }
    },
  );

  return router;
}
