/** A stable status replaces comparisons against user-facing error messages. */
export class AppError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "AppError";
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function errorStatus(error: unknown, fallback: number): number {
  return error instanceof AppError ? error.status : fallback;
}
