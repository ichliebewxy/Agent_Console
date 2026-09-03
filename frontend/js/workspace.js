Object.assign(window.NebulaNestApp.methods, {
    async loadWorkspace() {
      this.workspaceLoading = true;
      try {
        const response = await fetch(`/workspace/${encodeURIComponent(this.userId)}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
        this.workspacePath = data.workspace;
        this.workspaceDraft = data.workspace;
      } catch (error) {
        this.notify(`读取工作区失败：${error.message}`);
      } finally {
        this.workspaceLoading = false;
      }
    },

    async saveWorkspace() {
      const target = this.workspaceDraft.trim();
      if (!target || this.workspaceLoading) return;
      this.workspaceLoading = true;
      try {
        const response = await fetch(`/workspace/${encodeURIComponent(this.userId)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: target }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
        this.workspacePath = data.workspace;
        this.workspaceDraft = data.workspace;
        this.handleNewChat();
        this.notify("工作区已切换，后续文件会交付到该目录");
      } catch (error) {
        this.notify(`切换工作区失败：${error.message}`);
      } finally {
        this.workspaceLoading = false;
      }
    },

    async pickWorkspace() {
      if (this.workspaceLoading) return;
      this.workspaceLoading = true;
      try {
        const response = await fetch(`/workspace/${encodeURIComponent(this.userId)}/pick`, { method: "POST" });
        const data = await response.json();
        if (response.status === 409) return;
        if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
        this.workspacePath = data.workspace;
        this.workspaceDraft = data.workspace;
        this.handleNewChat();
        this.notify("已使用选定文件夹作为工作区");
      } catch (error) {
        this.notify(`选择文件夹失败：${error.message}`);
      } finally {
        this.workspaceLoading = false;
      }
    },
});
