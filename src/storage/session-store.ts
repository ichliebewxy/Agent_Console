import path from "node:path";
import { sessionDataDir } from "../config/paths.js";
import { readJson, writeJson, withJsonLock } from "./json-store.js";

import type {
  StoredMessage,
  SessionRecord,
  TaskPlan,
} from "../contracts/sessions.js";
export type { StoredMessage } from "../contracts/sessions.js";

type UserSessions = Record<string, SessionRecord>;

function userFile(userId: string): string {
  return path.join(sessionDataDir, `${userId}.json`);
}

export async function loadSession(
  userId: string,
  sessionId: string,
): Promise<SessionRecord | null> {
  const sessions = await readJson<UserSessions>(userFile(userId), {});
  return Object.hasOwn(sessions, sessionId) ? sessions[sessionId] : null;
}

export async function appendMessages(
  userId: string,
  sessionId: string,
  workspace: string,
  messages: StoredMessage[],
): Promise<void> {
  return withJsonLock(userFile(userId), async () => {
    const sessions = await readJson<UserSessions>(userFile(userId), {});
    const record = (Object.hasOwn(sessions, sessionId)
      ? sessions[sessionId]
      : null) || {
      workspace,
      updated_at: new Date().toISOString(),
      messages: [],
    };
    record.workspace = workspace;
    record.updated_at = new Date().toISOString();
    record.messages.push(...messages);
    sessions[sessionId] = record;
    await writeJson(userFile(userId), sessions);
  });
}

/** Save plan progress independently of messages so every completed step is resumable. */
export async function savePlan(
  userId: string,
  sessionId: string,
  workspace: string,
  plan: TaskPlan | null,
): Promise<void> {
  return withJsonLock(userFile(userId), async () => {
    const sessions = await readJson<UserSessions>(userFile(userId), {});
    const record = (Object.hasOwn(sessions, sessionId)
      ? sessions[sessionId]
      : null) || {
      workspace,
      updated_at: new Date().toISOString(),
      messages: [],
    };
    record.workspace = workspace;
    record.updated_at = new Date().toISOString();
    record.plan = plan;
    sessions[sessionId] = record;
    await writeJson(userFile(userId), sessions);
  });
}

export async function listSessions(userId: string): Promise<
  Array<{
    session_id: string;
    updated_at: string;
    message_count: number;
    workspace: string;
    plan_status?: TaskPlan["status"];
    plan_objective?: string;
    plan_progress?: { done: number; total: number };
  }>
> {
  const sessions = await readJson<UserSessions>(userFile(userId), {});
  return Object.entries(sessions)
    .map(([session_id, value]) => ({
      session_id,
      updated_at: value.updated_at,
      message_count: value.messages.length,
      workspace: value.workspace,
      ...(value.plan
        ? {
            plan_status: value.plan.status,
            plan_objective: value.plan.objective,
            plan_progress: {
              done: value.plan.steps.filter((step) =>
                ["done", "skipped"].includes(step.status),
              ).length,
              total: value.plan.steps.length,
            },
          }
        : {}),
    }))
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}

export async function deleteSession(
  userId: string,
  sessionId: string,
): Promise<boolean> {
  return withJsonLock(userFile(userId), async () => {
    const sessions = await readJson<UserSessions>(userFile(userId), {});
    if (!Object.hasOwn(sessions, sessionId)) return false;
    delete sessions[sessionId];
    await writeJson(userFile(userId), sessions);
    return true;
  });
}
