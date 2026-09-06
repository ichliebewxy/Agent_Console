import { Type } from "typebox";
import { defineTool } from "@earendil-works/pi-coding-agent";
import type { PlanStatus, PlanStep, TaskPlan } from "../contracts/sessions.js";

const stepSchema = Type.Object({
  id: Type.String({
    minLength: 1,
    maxLength: 80,
    description: "稳定且唯一的步骤 ID；后续更新必须保持不变",
  }),
  title: Type.String({ minLength: 1, maxLength: 240 }),
  detail: Type.Optional(Type.String({ maxLength: 1200 })),
  status: Type.Union([
    Type.Literal("pending"),
    Type.Literal("in_progress"),
    Type.Literal("done"),
    Type.Literal("failed"),
    Type.Literal("skipped"),
  ]),
  result: Type.Optional(Type.String({ maxLength: 4000 })),
});

// Chat-completions providers require the function parameters' root to be an
// object. A root Type.Union serializes to anyOf without type and rejects every
// chat request, even when the model never calls this tool.
const parameters = Type.Object({
  action: Type.Union([Type.Literal("replace"), Type.Literal("clear")]),
  objective: Type.Optional(
    Type.String({
      minLength: 1,
      maxLength: 500,
      description: "replace 时必填：计划目标",
    }),
  ),
  steps: Type.Optional(
    Type.Array(stepSchema, {
      minItems: 1,
      maxItems: 30,
      description: "replace 时必填：完整步骤清单",
    }),
  ),
});

export type PlanChangeHandler = (plan: TaskPlan | null) => Promise<void>;

function text(value: unknown, maxLength: number): string | undefined {
  if (typeof value !== "string") return undefined;
  const normalized = value.trim();
  return normalized ? normalized.slice(0, maxLength) : undefined;
}

function statusFor(steps: PlanStep[]): PlanStatus {
  const terminal = steps.every((step) =>
    ["done", "failed", "skipped"].includes(step.status),
  );
  if (!terminal) return "active";
  return steps.some((step) => step.status === "failed")
    ? "failed"
    : "completed";
}

export function normalizePlan(
  objective: string,
  rawSteps: Array<{
    id: string;
    title: string;
    detail?: string;
    status: PlanStep["status"];
    result?: string;
  }>,
): TaskPlan {
  const ids = new Set<string>();
  let running = 0;
  const steps = rawSteps.map((raw, index): PlanStep => {
    const id = text(raw.id, 80);
    const title = text(raw.title, 240);
    if (!id || !title) throw new Error(`计划第 ${index + 1} 步缺少 ID 或标题`);
    if (ids.has(id)) throw new Error(`计划步骤 ID 重复：${id}`);
    ids.add(id);
    if (raw.status === "in_progress") running += 1;
    return {
      id,
      title,
      status: raw.status,
      ...(text(raw.detail, 1200) ? { detail: text(raw.detail, 1200) } : {}),
      ...(text(raw.result, 4000) ? { result: text(raw.result, 4000) } : {}),
    };
  });
  if (running > 1) throw new Error("同一时间只能有一个计划步骤处于执行中");
  const normalizedObjective = text(objective, 500);
  if (!normalizedObjective) throw new Error("计划目标不能为空");
  return {
    objective: normalizedObjective,
    status: statusFor(steps),
    steps,
    updated_at: new Date().toISOString(),
  };
}

function planSummary(plan: TaskPlan): string {
  const done = plan.steps.filter((step) =>
    ["done", "skipped"].includes(step.status),
  ).length;
  return `计划已保存：${done}/${plan.steps.length} 步完成（${plan.status}）`;
}

export function createPlanTool(
  initialPlan: TaskPlan | null,
  onChange: PlanChangeHandler,
) {
  let current: TaskPlan | null = initialPlan;

  const commit = async (next: TaskPlan | null) => {
    await onChange(next);
    current = next;
    return current;
  };

  const tool = defineTool<typeof parameters, { plan: TaskPlan | null }>({
    name: "update_plan",
    label: "更新执行计划",
    description:
      "创建、替换或清除可恢复的多步骤执行计划。replace 必须每次提交完整计划快照；开始执行前先提交计划，每完成一步后立即更新。简单的一步任务不要创建计划。",
    promptSnippet: "update_plan: 在网页展示并持久保存多步骤任务进度",
    promptGuidelines: [
      "多步骤任务在修改文件前调用 update_plan，提交完整步骤清单。",
      "任一时刻最多一个步骤为 in_progress；完成后马上标记 done 并简述 result，再开始下一步。",
      "计划会跨中断恢复。继续旧计划时保留步骤 ID；目标变更或用户取消时替换或清除旧计划。",
    ],
    parameters,
    async execute(_id, params) {
      if (params.action === "clear") {
        await commit(null);
        return {
          content: [{ type: "text", text: "已清除当前执行计划" }],
          details: { plan: null },
        };
      }
      if (params.action !== "replace")
        throw new Error("计划操作必须是 replace 或 clear");
      if (!params.objective?.trim() || !params.steps?.length) {
        throw new Error(
          "replace 必须提供计划目标 objective 和非空步骤清单 steps",
        );
      }
      const plan = normalizePlan(params.objective, params.steps);
      await commit(plan);
      return {
        content: [{ type: "text", text: planSummary(plan) }],
        details: { plan },
      };
    },
  });

  return {
    tool,
    getPlan: () => current,
    async pause(): Promise<TaskPlan | null> {
      if (!current || current.status !== "active") return current;
      return commit({
        ...current,
        status: "paused",
        updated_at: new Date().toISOString(),
      });
    },
  };
}

export function unfinishedPlanPrompt(plan: TaskPlan | null): string {
  if (!plan || ["completed", "failed"].includes(plan.status)) return "";
  const steps = plan.steps
    .map(
      (step, index) =>
        `${index + 1}. [${step.status}] (${step.id}) ${step.title}${step.result ? ` — ${step.result}` : ""}`,
    )
    .join("\n");
  return `\n\n[宿主恢复的未完成执行计划]\n目标：${plan.objective}\n状态：${plan.status}\n${steps}\n这是服务端持久化的真实进度。结合用户的新消息判断：若用户要继续，则从未完成步骤接着执行并用 update_plan 实时更新；若用户明确改变目标或取消，则替换或清除旧计划。不要重做已经完成的步骤。`;
}
