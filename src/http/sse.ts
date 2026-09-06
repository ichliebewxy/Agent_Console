import type { Response } from "express";
export function sendSse(
  response: Response,
  event: Record<string, unknown>,
): void {
  response.write(`data: ${JSON.stringify(event)}\n\n`);
}
