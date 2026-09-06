import type { UploadedImage } from "../contracts/uploads.js";
import type { ChatImage } from "../contracts/chat.js";
import { randomUUID } from "node:crypto";
import { mkdir, writeFile, realpath, stat } from "node:fs/promises";
import path from "node:path";
import { uploadDir } from "../config/paths.js";

export async function resolveImagePath(
  workspace: string,
  input: string,
): Promise<string> {
  const target = await realpath(path.resolve(workspace, input));
  const roots = await Promise.all(
    [workspace, uploadDir].map((root) => realpath(root)),
  );
  if (
    !roots.some((root) => {
      const relative = path.relative(root, target);
      return (
        relative &&
        relative !== ".." &&
        !relative.startsWith(`..${path.sep}`) &&
        !path.isAbsolute(relative)
      );
    })
  )
    throw new Error("只能识别工作区或本次应用上传目录内的图片");
  if (!(await stat(target)).isFile()) throw new Error("图片路径必须是文件");
  return target;
}
export async function saveChatImages(
  files: UploadedImage[],
): Promise<ChatImage[]> {
  await mkdir(uploadDir, { recursive: true });
  return Promise.all(
    files.map(async (file) => {
      if (!/^image\/(png|jpeg|webp|gif)$/i.test(file.mimetype))
        throw new Error(`不支持的图片格式：${file.mimetype}`);
      const extension =
        (
          {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
            "image/gif": ".gif",
          } as Record<string, string>
        )[file.mimetype] || ".img";
      const target = path.join(uploadDir, `${randomUUID()}${extension}`);
      await writeFile(target, file.buffer);
      return { path: target, name: file.originalname, mimeType: file.mimetype };
    }),
  );
}
