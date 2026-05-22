Object.assign(window.NebulaNestApp.methods, {
  sourceChunks(msg) {
    const trace = msg.ragTrace || {};
    return trace.expanded_retrieved_chunks || trace.initial_retrieved_chunks || trace.retrieved_chunks || [];
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

  reviewStatusLabel(status) {
    return {
      pending: "待审核",
      approved: "已批准",
      rejected: "已驳回",
      needs_revision: "需修订",
    }[status] || status;
  },

  failureStatusLabel(status) {
    return {
      open: "待回调",
      retry_requested: "请求重试",
      resolved: "已处理",
      ignored: "已忽略",
    }[status] || status;
  },
});
