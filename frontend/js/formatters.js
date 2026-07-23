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

  formatFileSize(bytes) {
    const value = Number(bytes || 0);
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  },
});
