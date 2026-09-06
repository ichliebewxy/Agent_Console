Object.assign(window.NebulaNestApp.methods, {
  sourceChunks(msg) {
    const trace = msg.ragTrace || {};
    for (const key of [
      "expanded_retrieved_chunks",
      "initial_retrieved_chunks",
      "retrieved_chunks",
    ]) {
      if (Array.isArray(trace[key]) && trace[key].length) return trace[key];
    }
    return [];
  },

  formatSourceMeta(source) {
    const meta = [];
    if (source.file_type) meta.push(source.file_type);
    if (source.page_number) meta.push(`页 ${source.page_number}`);
    if (source.rerank_score !== undefined && source.rerank_score !== null) {
      meta.push(`rerank ${Number(source.rerank_score).toFixed(3)}`);
    }
    if (source.retrieval_source) meta.push(source.retrieval_source);
    return meta.join(" / ");
  },

  getFileIcon(fileType) {
    const type = (fileType || "").toLowerCase();
    if (type.includes("pdf")) return "fas fa-file-pdf file-pdf";
    if (type.includes("doc") || type.includes("word"))
      return "fas fa-file-word file-word";
    if (type.includes("ppt")) return "fas fa-file-powerpoint file-ppt";
    if (type.includes("xls") || type.includes("csv") || type.includes("excel"))
      return "fas fa-file-excel file-excel";
    if (type.includes("txt") || type.includes("text"))
      return "fas fa-file-lines file-text";
    return "fas fa-file file-default";
  },

  formatFileSize(bytes) {
    const value = Number(bytes || 0);
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  },

  shouldShowAgentTrace(msg) {
    if (!msg || msg.isUser) return false;
    if (msg.isThinking) return true;
    return (
      !!msg.retryState ||
      (Array.isArray(msg.ragSteps) && msg.ragSteps.length > 0)
    );
  },

  retryStatusTitle(retry) {
    if (!retry) return "";
    if (retry.status === "waiting")
      return retry.source === "tool" ? "工具调用稍后重试" : "模型连接稍后重试";
    if (retry.status === "success") return "重试成功，继续执行";
    if (retry.status === "failed") return "重试次数已用完";
    return retry.transient ? "正在判断瞬时故障" : "正在分析失败原因";
  },

  retryStatusDetail(retry) {
    if (!retry) return "";
    const target = retry.toolName ? ` · ${retry.toolName}` : "";
    if (retry.status === "waiting") {
      const seconds = Math.round(Number(retry.delayMs || 0) / 100) / 10;
      return `第 ${retry.attempt}/${retry.maxAttempts} 次${target} · ${seconds} 秒后继续`;
    }
    if (retry.status === "failed") return `已停止原样重试${target}`;
    if (retry.status === "success") return `连接已恢复${target}`;
    return retry.transient
      ? `错误已返回 Agent 判断${target}`
      : `等待 Agent 修改参数或指令${target}`;
  },

  toolCallGroups(msg) {
    const groups = new Map();
    for (const [index, step] of (msg && Array.isArray(msg.toolSteps)
      ? msg.toolSteps
      : []
    ).entries()) {
      const callId = step.call_id || `${step.tool_name || "tool"}-${index}`;
      if (!groups.has(callId)) {
        groups.set(callId, {
          callId,
          toolName: step.tool_name || "未知工具",
          request: "",
          result: "",
          hasResult: false,
          status: "running",
          statusLabel: "执行中",
          statusIcon: "fas fa-spinner fa-spin",
        });
      }
      const group = groups.get(callId);
      if (step.detail)
        group.request = step.detail.replace(/^参数\s*[:：]\s*/, "");
      if (["result", "error", "limit"].includes(step.phase)) {
        group.hasResult = true;
        group.result = step.result ?? "";
      }
      if (step.phase === "result") {
        group.status = "success";
        group.statusLabel = "已完成";
        group.statusIcon = "fas fa-check";
      } else if (step.phase === "error") {
        group.status = "error";
        group.statusLabel = "失败";
        group.statusIcon = "fas fa-xmark";
      } else if (step.phase === "limit") {
        group.status = "limit";
        group.statusLabel = "达到上限";
        group.statusIcon = "fas fa-ban";
      }
    }
    return Array.from(groups.values());
  },

  hasPlan(msg) {
    return !!(
      msg &&
      msg.plan &&
      Array.isArray(msg.plan.steps) &&
      msg.plan.steps.length
    );
  },

  shouldShowMessagePlan(msg) {
    if (!this.hasPlan(msg)) return false;
    if (!this.activePlan) return true;
    return msg.plan.updated_at !== this.activePlan.updated_at;
  },

  planSteps(msg) {
    return msg && msg.plan && Array.isArray(msg.plan.steps)
      ? msg.plan.steps
      : [];
  },

  planReflections(msg) {
    return msg && msg.plan && Array.isArray(msg.plan.reflections)
      ? msg.plan.reflections
      : [];
  },

  planStepStats(msg) {
    return this.planStepStatsForPlan(msg && msg.plan);
  },

  planStepStatsForPlan(plan) {
    const steps = plan && Array.isArray(plan.steps) ? plan.steps : [];
    const done = steps.filter((s) => s.status === "done").length;
    const skipped = steps.filter((s) => s.status === "skipped").length;
    const failed = steps.filter((s) => s.status === "failed").length;
    return (
      done +
      skipped +
      "/" +
      steps.length +
      " 已完成" +
      (failed ? " · " + failed + " 失败" : "")
    );
  },

  planProgressPercent(plan) {
    const steps = plan && Array.isArray(plan.steps) ? plan.steps : [];
    if (!steps.length) return 0;
    const finished = steps.filter((step) =>
      ["done", "skipped"].includes(step.status),
    ).length;
    return Math.round((finished / steps.length) * 100);
  },

  planIsUnfinished(plan) {
    return !!(
      plan &&
      ["active", "paused"].includes(plan.status) &&
      Array.isArray(plan.steps) &&
      plan.steps.length
    );
  },

  planOverallStatusLabel(status) {
    const map = {
      active: "执行中",
      paused: "可继续",
      completed: "已完成",
      failed: "未完成",
    };
    return map[status] || "已保存";
  },

  planStatusIcon(status, planStatus) {
    if (status === "in_progress" && planStatus === "paused")
      return "fas fa-pause";
    const map = {
      pending: "fas fa-circle",
      in_progress: "fas fa-spinner fa-spin",
      done: "fas fa-check",
      failed: "fas fa-xmark",
      skipped: "fas fa-minus",
    };
    return map[status] || "fas fa-circle";
  },

  planStatusLabel(status) {
    const map = {
      pending: "待执行",
      in_progress: "执行中",
      done: "已完成",
      failed: "失败",
      skipped: "已跳过",
    };
    return map[status] || status;
  },
});
