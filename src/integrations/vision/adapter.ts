import {
  ModelRegistry,
  type ModelRuntime,
} from "@earendil-works/pi-coding-agent";

type VisionResult =
  | { ok: true; text: string }
  | { ok: false; error: { code: string; message: string } };
type Delegator = {
  config: { defaultReasoningEffort: string };
  delegate(
    params: {
      image_path: string;
      prompt: string;
      compress: boolean;
      reasoning: string;
    },
    signal?: AbortSignal,
  ): Promise<VisionResult>;
};

// The package publishes TS source typed against Pi 0.83. Keep its compatibility
// boundary here instead of weakening type checking throughout the application.
const packageName: string = "@getpipher/vision";
const plugin = (await import(packageName)) as {
  createVisionDelegator(options: {
    modelRegistry: unknown;
    cwd: string;
    agentDir: string;
  }): Delegator;
};

export function createVisionAdapter(
  runtime: ModelRuntime,
  cwd: string,
  agentDir: string,
): Delegator {
  const registry = new ModelRegistry(runtime);
  const compatibleRegistry = {
    find: registry.find.bind(registry),
    getApiKeyAndHeaders: async (
      ...args: Parameters<typeof registry.getApiKeyAndHeaders>
    ) => {
      const auth = await registry.getApiKeyAndHeaders(...args);
      // Pi 0.84 preserves null header-deletion markers; vision 0.5.2 cannot.
      // Fail closed rather than accidentally forwarding an unwanted credential.
      if (
        auth.ok &&
        Object.values(auth.headers ?? {}).some((value) => value === null)
      ) {
        return {
          ok: false,
          error:
            "视觉插件暂不支持此 Provider 的 null 请求头策略，请使用独立视觉 Provider。",
        };
      }
      return auth;
    },
  };
  return plugin.createVisionDelegator({
    modelRegistry: compatibleRegistry,
    cwd,
    agentDir,
  });
}
