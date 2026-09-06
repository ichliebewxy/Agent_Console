import type { ErrorRequestHandler, Response } from "express";
import { errorMessage, errorStatus } from "../shared/errors.js";

export function sendHttpError(
  response: Response,
  error: unknown,
  fallback = 500,
): void {
  response
    .status(errorStatus(error, fallback))
    .json({ detail: errorMessage(error) });
}

/** Includes parser, upload and asynchronous route failures that precede SSE. */
export const handleHttpError: ErrorRequestHandler = (
  error: unknown,
  _request,
  response,
  next,
) => {
  if (response.headersSent) return next(error);
  const status =
    error && typeof error === "object" && "status" in error
      ? error.status
      : undefined;
  sendHttpError(
    response,
    error,
    typeof status === "number" && status >= 400 && status < 600 ? status : 500,
  );
};
