import type {
  createAgentSession,
  DefaultResourceLoader,
} from "@earendil-works/pi-coding-agent";
import type { WebUI } from "./web-ui.js";
import type { Artifact } from "../contracts/artifacts.js";
import type { EventEmitter, StreamEvent } from "../contracts/chat.js";
import type { TaskPlan } from "../contracts/sessions.js";

export type Runtime = {
  key: string;
  workspace: string;
  session: Awaited<ReturnType<typeof createAgentSession>>["session"];
  loader: DefaultResourceLoader;
  ui: WebUI;
  artifacts: Map<string, Artifact>;
  writtenPaths: Set<string>;
  skillsDirty: boolean;
  beginTurn: () => void;
  getPlan: () => TaskPlan | null;
  pausePlan: () => Promise<TaskPlan | null>;
  emit: (event: StreamEvent) => void;
  setEmitter: (emitter: (event: StreamEvent) => void) => void;
};

export type RuntimeOptions = {
  key: string;
  userId: string;
  sessionId: string;
  workspace: string;
  initialEmit: EventEmitter;
  onCreated?: (runtime: Runtime) => void;
};
export type RuntimeFactory = (options: RuntimeOptions) => Promise<Runtime>;
