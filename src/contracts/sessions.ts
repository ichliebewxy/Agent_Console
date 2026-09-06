import type { Artifact } from "./artifacts.js";
import type { ChatImage } from "./chat.js";

export type PlanStepStatus =
  | "pending"
  | "in_progress"
  | "done"
  | "failed"
  | "skipped";

export type PlanStatus = "active" | "paused" | "completed" | "failed";

export type PlanStep = {
  id: string;
  title: string;
  detail?: string;
  status: PlanStepStatus;
  result?: string;
};

/** Durable plan snapshot shared by the agent, session API and web client. */
export type TaskPlan = {
  objective: string;
  status: PlanStatus;
  steps: PlanStep[];
  updated_at: string;
};

export type StoredMessage = {
  type: "human" | "ai";
  content: string;
  timestamp: string;
  workspace?: string;
  artifacts?: Artifact[];
  rag_trace?: Record<string, unknown> | null;
  images?: ChatImage[];
  plan?: TaskPlan | null;
};

export type SessionRecord = {
  workspace: string;
  updated_at: string;
  messages: StoredMessage[];
  plan?: TaskPlan | null;
};
