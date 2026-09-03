import { randomUUID } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

export async function readJson<T>(file: string, fallback: T): Promise<T> {
  try {
    return JSON.parse(await readFile(file, "utf8")) as T;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return fallback;
    throw error; // Never overwrite an unreadable/corrupt store with an empty fallback.
  }
}

const locks = new Map<string, Promise<unknown>>();
export async function withJsonLock<T>(
  file: string,
  operation: () => Promise<T>,
): Promise<T> {
  const previous = locks.get(file) ?? Promise.resolve();
  const current = previous.catch(() => {}).then(operation);
  locks.set(file, current);
  try {
    return await current;
  } finally {
    if (locks.get(file) === current) locks.delete(file);
  }
}

export async function writeJson(file: string, value: unknown): Promise<void> {
  await mkdir(path.dirname(file), { recursive: true });
  const staged = `${file}.${process.pid}.${randomUUID()}.tmp`;
  await writeFile(staged, JSON.stringify(value, null, 2), "utf8");
  await rename(staged, file);
}
