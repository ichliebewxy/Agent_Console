Object.assign(window.NebulaNestApp.methods, {
  sessionResourcesUrl() {
    return `/sessions/${encodeURIComponent(this.userId)}/${encodeURIComponent(this.sessionId)}/resources`;
  },

  async loadSessionResources() {
    this.sessionResourcesLoading = true;
    try {
      const response = await fetch(this.sessionResourcesUrl());
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      this.sessionResources = data;
      this.sessionSkillSelection = data.skills !== null;
    } catch (error) {
      this.notify(`加载会话资源失败：${error.message}`);
    } finally {
      this.sessionResourcesLoading = false;
    }
  },

  async saveSessionResources() {
    const resources = this.sessionResources;
    const body = {
      project_id: (resources.project_id || "").trim() || null,
      skills: this.sessionSkillSelection ? (resources.skills || []) : null,
      memory_read_scopes: resources.memory_read_scopes,
      memory_write_scope: resources.memory_write_scope,
    };
    try {
      const response = await fetch(this.sessionResourcesUrl(), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      this.sessionResources = data;
      this.notify("当前会话资源配置已保存");
    } catch (error) {
      this.notify(`保存会话资源失败：${error.message}`);
    }
  },

  onSessionSkillModeChange() {
    if (this.sessionSkillSelection && !Array.isArray(this.sessionResources.skills)) {
      this.sessionResources.skills = [];
    }
  },
});
