Object.assign(window.NebulaNestApp.methods, {
  async handleHistory() {
    this.showHistorySidebar = true;
    try {
      const response = await fetch(`/sessions/${this.userId}`);
      if (!response.ok) throw new Error("Failed to load sessions");
      const data = await response.json();
      this.sessions = data.sessions || [];
    } catch (error) {
      this.notify(`加载历史失败：${error.message}`);
    }
  },

  async loadSession(sessionId) {
    if (this.isLoading) {
      this.notify("请先停止或等待当前任务");
      return;
    }
    this.sessionId = sessionId;
    this.activeView = "chat";
    this.showHistorySidebar = false;
    try {
      const response = await fetch(`/sessions/${this.userId}/${sessionId}`);
      if (!response.ok) throw new Error("Failed to load session messages");
      const data = await response.json();
      if (data.workspace && data.workspace !== this.workspacePath) {
        const workspaceResponse = await fetch(`/workspace/${this.userId}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: data.workspace }),
        });
        if (!workspaceResponse.ok)
          throw new Error("原工作区不可用，请手动重新选择文件夹");
        this.workspacePath = data.workspace;
        this.workspaceDraft = data.workspace;
      }
      this.messages = (data.messages || []).map((msg) => ({
        id: this.createId(),
        text: msg.content,
        isUser: msg.type === "human",
        retryState: null,
        plan: msg.plan || null,
        ragTrace: msg.rag_trace || null,
        ragSteps: [],
        toolSteps: [],
        flowSteps: [],
        artifacts: msg.artifacts || [],
      }));
      this.activePlan = data.plan || null;
      this.planExpanded = true;
      this.persistState();
      this.$nextTick(() => this.scrollToBottom());
    } catch (error) {
      this.notify(`加载会话失败：${error.message}`);
    }
  },
});
