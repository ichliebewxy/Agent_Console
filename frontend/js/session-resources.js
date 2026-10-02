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
      this.activeWorkspaceDir = data.workspace_dir || null;
      this.activePermissionMode = data.permission_mode || "relaxed";
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
    if (this.isLoading || this.sessionResourcesLoading || this.sessionResourcesSaving) return false;
    const userId = this.userId;
    const sessionId = this.sessionId;
    const resources = this.sessionResources;
    const body = {
      project_id: (resources.project_id || "").trim() || null,
      skills: this.sessionSkillSelection ? (resources.skills || []) : null,
      memory_read_scopes: resources.memory_read_scopes,
      memory_write_scope: resources.memory_write_scope,
      workspace_dir: (resources.workspace_dir || "").trim() || null,
      permission_mode: resources.permission_mode || "relaxed",
    };
    return this.persistSessionResources(body, userId, sessionId);
  },

  async persistSessionResources(body, userId = this.userId, sessionId = this.sessionId) {
    const requestId = this._resourceRequestId = (this._resourceRequestId || 0) + 1;
    this.sessionResourcesSaving = true;
    try {
      const response = await fetch(this.sessionResourcesUrl(userId, sessionId), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      if (requestId !== this._resourceRequestId || userId !== this.userId || sessionId !== this.sessionId) return false;
      this.sessionResources = data;
      this.sessionSkillSelection = data.skills !== null;
      this.activeWorkspaceDir = data.workspace_dir || null;
      this.activePermissionMode = data.permission_mode || "relaxed";
      this.notify("当前会话资源配置已保存");
      return true;
    } catch (error) {
      if (userId === this.userId && sessionId === this.sessionId) {
        this.notify(`保存会话资源失败：${error.message}`);
      }
      return false;
    } finally {
      this.sessionResourcesSaving = false;
    }
  },

  async openFolderPicker() {
    if (this.isLoading || this.sessionResourcesLoading || this.sessionResourcesSaving) return;
    this.showFolderPicker = true;
    this.folderListing = null;
    await this.browseFolder(this.activeWorkspaceDir || "");
  },

  async browseFolder(path = this.folderPathInput) {
    const requestId = this._folderRequestId = (this._folderRequestId || 0) + 1;
    this.folderLoading = true;
    this.folderError = "";
    this.folderPathInput = path;
    try {
      const query = path ? `?path=${encodeURIComponent(path)}` : "";
      const response = await fetch(`/workspace/folders${query}`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      if (requestId !== this._folderRequestId || !this.showFolderPicker) return;
      this.folderListing = data;
      this.folderPathInput = data.path;
    } catch (error) {
      if (requestId === this._folderRequestId) this.folderError = error.message;
    } finally {
      if (requestId === this._folderRequestId) this.folderLoading = false;
    }
  },

  async setWorkspaceFolder(path) {
    if (this.isLoading || this.sessionResourcesLoading || this.sessionResourcesSaving) return;
    const userId = this.userId;
    const sessionId = this.sessionId;
    // Keep the saved Skill/memory policy when switching folders from the chat.
    const resources = await this.loadSessionResources();
    if (!resources || userId !== this.userId || sessionId !== this.sessionId || this.isLoading) return;
    const saved = await this.persistSessionResources({ ...resources, workspace_dir: path || null }, userId, sessionId);
    if (saved) this.showFolderPicker = false;
  },

  onSessionSkillModeChange() {
    if (this.sessionSkillSelection && !Array.isArray(this.sessionResources.skills)) {
      this.sessionResources.skills = [];
    }
  },
});
