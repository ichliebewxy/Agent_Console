Object.assign(window.NebulaNestApp.methods, {
  sessionResourcesUrl(userId = this.userId, sessionId = this.sessionId) {
    return `/sessions/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}/resources`;
  },

  async loadSessionResources() {
    const userId = this.userId;
    const sessionId = this.sessionId;
    const requestId = this._resourceRequestId = (this._resourceRequestId || 0) + 1;
    this.sessionResourcesLoading = true;
    try {
      const response = await fetch(this.sessionResourcesUrl(userId, sessionId));
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      if (requestId !== this._resourceRequestId || userId !== this.userId || sessionId !== this.sessionId) return null;
      this.sessionResources = data;
      this.sessionSkillSelection = data.skills !== null;
      return data;
    } catch (error) {
      if (requestId === this._resourceRequestId && userId === this.userId && sessionId === this.sessionId) {
        this.notify(`加载会话资源失败：${error.message}`);
      }
      return null;
    } finally {
      if (requestId === this._resourceRequestId) this.sessionResourcesLoading = false;
    }
  },

  async saveSessionResources() {
    const userId = this.userId;
    const sessionId = this.sessionId;
    const resources = this.sessionResources;
    const body = {
      project_id: (resources.project_id || "").trim() || null,
      skills: this.sessionSkillSelection ? (resources.skills || []) : null,
      memory_read_scopes: resources.memory_read_scopes,
      memory_write_scope: resources.memory_write_scope,
    };
    try {
      const response = await fetch(this.sessionResourcesUrl(userId, sessionId), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      if (userId !== this.userId || sessionId !== this.sessionId) return;
      this.sessionResources = data;
      this.notify("当前会话资源配置已保存");
    } catch (error) {
      if (userId === this.userId && sessionId === this.sessionId) {
        this.notify(`保存会话资源失败：${error.message}`);
      }
    }
  },

  onSessionSkillModeChange() {
    if (this.sessionSkillSelection && !Array.isArray(this.sessionResources.skills)) {
      this.sessionResources.skills = [];
    }
  },
});
