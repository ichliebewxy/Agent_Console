import type { Response } from "express";
import multer from "multer";
export const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 50 * 1024 * 1024, files: 8 },
});
export function sendSse(
  response: Response,
  event: Record<string, unknown>,
): void {
  response.write(`data: ${JSON.stringify(event)}\n\n`);
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
