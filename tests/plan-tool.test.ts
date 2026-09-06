import { describe, expect, it, vi } from "vitest";
import {
  createPlanTool,
  normalizePlan,
  unfinishedPlanPrompt,
} from "../src/tools/plan-tool.js";

describe("durable plan tool", () => {
  it("saves full snapshots, pauses unfinished work and clears completed state", async () => {
    const save = vi.fn(async () => {});
    const planner = createPlanTool(null, save);
    await (planner.tool.execute as any)("call", {
      action: "replace",
      objective: "交付功能",
      steps: [
        { id: "inspect", title: "检查项目", status: "done", result: "已检查" },
        { id: "build", title: "实现功能", status: "in_progress" },
      ],
    });

    expect(planner.getPlan()).toMatchObject({
      objective: "交付功能",
      status: "active",
      steps: [{ status: "done" }, { status: "in_progress" }],
    });
    await planner.pause();
    expect(planner.getPlan()?.status).toBe("paused");
    expect(save).toHaveBeenCalledTimes(2);

    await (planner.tool.execute as any)("call", { action: "clear" });
    expect(planner.getPlan()).toBeNull();
    expect(save).toHaveBeenLastCalledWith(null);
  });

  it("rejects ambiguous progress and exposes unfinished state to the next turn", () => {
    expect(() =>
      normalizePlan("目标", [
        { id: "one", title: "一", status: "in_progress" },
        { id: "two", title: "二", status: "in_progress" },
      ]),
    ).toThrow("只能有一个");

    const plan = normalizePlan("继续目标", [
      { id: "one", title: "已完成", status: "done" },
      { id: "two", title: "待继续", status: "pending" },
    ]);
    const prompt = unfinishedPlanPrompt({ ...plan, status: "paused" });
    expect(prompt).toContain("宿主恢复的未完成执行计划");
    expect(prompt).toContain("不要重做已经完成的步骤");
    expect(prompt).toContain("(two) 待继续");
  });
});
