Object.assign(window.NebulaNestApp.methods, {
  async loadDocuments() {
    this.documentsLoading = true;
    try {
      const response = await fetch("/documents");
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || "知识库服务暂不可用");
      }
      const data = await response.json();
      this.documents = data.documents || [];
    } catch (error) {
      this.notify(`文档列表加载失败：${error.message}`);
    } finally {
      this.documentsLoading = false;
    }
  },

  handleFileSelect(event) {
    if (this.isUploading) return;
    const [file] = event.target.files || [];
    if (!file) return;
    const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    const allowed = [
      ".pdf",
      ".docx",
      ".doc",
      ".pptx",
      ".xlsx",
      ".xls",
      ".csv",
      ".txt",
    ];
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
    this.uploadStatus = "idle";
  },

  async uploadDocument() {
    if (!this.selectedFile || this.isUploading) return;
    const file = this.selectedFile;
    this.isUploading = true;
    this.uploadStatus = "running";
    this.uploadStage = "uploading";
    this.uploadFilename = file.name;
    this.uploadProgress = "正在上传文件，随后将自动解析并建立检索索引…";
    this.uploadChunksProcessed = 0;
    this.uploadChunksTotal = 0;
    this.uploadParentChunks = 0;
    this.uploadElapsed = 0;
    const startedAt = Date.now();
    const updateElapsed = () => {
      this.uploadElapsed = Math.floor((Date.now() - startedAt) / 1000);
    };
    const timer = window.setInterval(updateElapsed, 1000);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch("/documents/upload", {
        method: "POST",
        headers: { Accept: "text/event-stream" },
        body: formData,
      });
      let payload;
      if (
        response.ok &&
        response.headers.get("content-type")?.includes("text/event-stream")
      ) {
        payload = await this.readUploadProgress(response.body);
      } else {
        payload = await response.json().catch(() => ({}));
        if (!response.ok)
          throw new Error(payload.detail || "知识库服务暂不可用");
        if (!payload.filename || !Number.isFinite(payload.chunks_processed)) {
          throw new Error("未收到入库结果，请刷新文档列表确认后重试");
        }
      }
      this.uploadStatus = "success";
      this.uploadStage = "complete";
      this.uploadChunksProcessed = payload.chunks_processed;
      this.uploadChunksTotal = payload.chunks_processed;
      this.uploadParentChunks = payload.parent_chunks_processed || 0;
      this.uploadProgress = payload.message || `${file.name} 入库完成`;
      this.selectedFile = null;
      if (this.$refs.fileInput) this.$refs.fileInput.value = "";
      this.notify(`${file.name} 入库完成，可以开始提问了`);
      await this.loadDocuments();
    } catch (error) {
      this.uploadStatus = "error";
      this.uploadProgress = `入库未完成：${error.message}`;
      this.notify(`${file.name} 入库未完成，请查看处理结果`);
    } finally {
      window.clearInterval(timer);
      updateElapsed();
      this.isUploading = false;
    }
  },

  async readUploadProgress(body) {
    if (!body) throw new Error("未收到入库进度，请刷新文档列表确认后重试");
    const reader = body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    try {
      while (true) {
        const { done, value } = await reader.read();
        buffer += decoder.decode(value, { stream: !done });
        let boundary;
        while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
          const frame = buffer.slice(0, boundary.index);
          buffer = buffer.slice(boundary.index + boundary[0].length);
          const data = frame
            .split(/\r?\n/)
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trimStart())
            .join("\n");
          if (!data) continue;
          const event = JSON.parse(data);
          if (event.type === "error")
            throw new Error(event.message || "文档处理失败");
          if (event.type === "complete") {
            if (!event.filename || !Number.isFinite(event.chunks_processed)) {
              throw new Error("入库结果不完整，请刷新文档列表确认后重试");
            }
            return event;
          }
          if (event.type === "progress") {
            this.uploadStage = event.stage;
            this.uploadProgress = event.message;
            this.uploadChunksProcessed =
              event.processed ?? this.uploadChunksProcessed;
            this.uploadChunksTotal = event.total ?? this.uploadChunksTotal;
            this.uploadParentChunks =
              event.parent_chunks ?? this.uploadParentChunks;
          }
        }
        if (done)
          throw new Error("进度连接中断，请刷新文档列表确认入库结果后重试");
      }
    } finally {
      await reader.cancel().catch(() => {});
      reader.releaseLock();
    }
  },

  uploadStepState(stage) {
    if (this.uploadStatus === "success") return "done";
    const current = this.uploadStages.findIndex(
      (step) => step.id === this.uploadStage,
    );
    const index = this.uploadStages.findIndex((step) => step.id === stage);
    if (index < current) return "done";
    if (index === current)
      return this.uploadStatus === "error" ? "error" : "active";
    return "pending";
  },

  async deleteDocument(filename) {
    if (!confirm(`确定删除 ${filename} 的向量数据吗？`)) return;
    try {
      const response = await fetch(
        `/documents/${encodeURIComponent(filename)}`,
        { method: "DELETE" },
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Delete failed");
      this.notify(payload.message || "删除完成");
      await this.loadDocuments();
    } catch (error) {
      this.notify(`删除失败：${error.message}`);
    }
  },
});
