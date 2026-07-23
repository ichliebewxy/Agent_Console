Object.assign(window.NebulaNestApp.methods, {
  sourceChunks(msg) {
    const trace = msg.ragTrace || {};
    for (const key of ["expanded_retrieved_chunks", "initial_retrieved_chunks", "retrieved_chunks"]) {
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
    if (type.includes("doc") || type.includes("word")) return "fas fa-file-word file-word";
    if (type.includes("ppt")) return "fas fa-file-powerpoint file-ppt";
    if (type.includes("xls") || type.includes("csv") || type.includes("excel")) return "fas fa-file-excel file-excel";
    if (type.includes("txt") || type.includes("text")) return "fas fa-file-lines file-text";
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
    return this.sourceChunks(msg).length > 0;
  },

  toolCallGroups(msg) {
    const groups = new Map();
    for (const [index, step] of (msg && Array.isArray(msg.toolSteps) ? msg.toolSteps : []).entries()) {
      const callId = step.call_id || `${step.tool_name || "tool"}-${index}`;
      if (!groups.has(callId)) {
        groups.set(callId, {
          callId,
          toolName: step.tool_name || "未知工具",
          detail: "",
          result: "",
          status: "running",
          statusLabel: "执行中",
          statusIcon: "fas fa-spinner fa-spin",
        });
      }
      const group = groups.get(callId);
      if (step.detail) group.detail = step.detail;
      if (step.result) group.result = step.result;
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
});
