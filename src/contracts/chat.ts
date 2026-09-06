/** Public host protocol. Keep field names compatible with persisted clients. */
export type StreamEvent = Record<string, unknown>;
export type ChatImage = { path: string; name: string; mimeType: string };
export type EventEmitter = (event: StreamEvent) => void;

export type ChatOptions = {
  userId: string;
  sessionId: string;
  workspace: string;
  message: string;
  images: ChatImage[];
  emit: EventEmitter;
  signal?: AbortSignal;
};

/** HTTP depends on this port, never on the concrete SDK host. */
export interface AgentGateway {
  chat(options: ChatOptions): Promise<void>;
  abort(userId: string, sessionId: string): void;
  respond(
    userId: string,
    sessionId: string,
    id: string,
    value: unknown,
  ): boolean;
  isUserBusy(userId: string): boolean;
  disposeUserSessions(userId: string): Promise<void>;
  reloadSkills(): Promise<void>;
}
