Object.assign(window.NebulaNestApp.methods, {
  async loadDocuments() {
    this.documentsLoading = true;
    try {
      const response = await fetch("/documents");
      if (!response.ok) throw new Error("Failed to load documents");
      const data = await response.json();
      this.documents = data.documents || [];
    } catch (error) {
      this.notify(`文档列表加载失败：${error.message}`);
    } finally {
      this.documentsLoading = false;
    }
  },

  handleFileSelect(event) {
    const [file] = event.target.files || [];
    if (!file) return;
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    const allowed = [".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".csv", ".txt"];
    if (!allowed.includes(ext)) {
      this.notify(`不支持的文件类型：${ext}`);
      event.target.value = "";
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      this.notify("文件大小不能超过 50MB");
      event.target.value = "";
      return;
    }
    this.selectedFile = file;
    this.uploadProgress = "";
  },

  async uploadDocument() {
    if (!this.selectedFile) return;
    this.isUploading = true;
    this.uploadProgress = "正在上传、解析并写入知识库...";
    try {
      const formData = new FormData();
      formData.append("file", this.selectedFile);
      const response = await fetch("/documents/upload", { method: "POST", body: formData });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Upload failed");
      this.uploadProgress = payload.message || "处理完成";
      this.selectedFile = null;
      if (this.$refs.fileInput) this.$refs.fileInput.value = "";
      await this.loadDocuments();
    } catch (error) {
      this.uploadProgress = `上传失败：${error.message}`;
    } finally {
      this.isUploading = false;
    }
  },

  async deleteDocument(filename) {
    if (!confirm(`确定删除 ${filename} 的向量数据吗？`)) return;
    try {
      const response = await fetch(`/documents/${encodeURIComponent(filename)}`, { method: "DELETE" });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Delete failed");
      this.notify(payload.message || "删除完成");
      await this.loadDocuments();
    } catch (error) {
      this.notify(`删除失败：${error.message}`);
    }
  },
});
