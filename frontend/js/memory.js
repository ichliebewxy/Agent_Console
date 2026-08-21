Object.assign(window.NebulaNestApp.methods, {
  async loadMemories() {
    this.memoriesLoading = true;
    try {
      const response = await fetch(`/memory/${encodeURIComponent(this.userId)}`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      this.memories = data.memories || [];
    } catch (error) {
      this.notify(`加载记忆失败：${error.message}`);
    } finally {
      this.memoriesLoading = false;
    }
  },

  async addMemory() {
    const text = this.memoryForm.memory.trim();
    if (!text || this.memoriesAdding) return;
    this.memoriesAdding = true;
    try {
      const response = await fetch(`/memory/${encodeURIComponent(this.userId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ memory: text, infer: this.memoryForm.infer }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      this.memoryForm.memory = "";
      this.notify(data.message || "已添加记忆");
      await this.loadMemories();
    } catch (error) {
      this.notify(`添加记忆失败：${error.message}`);
    } finally {
      this.memoriesAdding = false;
    }
  },

  async editMemory(mem) {
    const next = prompt("编辑这条记忆：", mem.memory);
    if (next === null) return;
    const text = next.trim();
    if (!text) return;
    try {
      const response = await fetch(`/memory/${encodeURIComponent(mem.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ memory: text }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      this.notify("记忆已更新");
      await this.loadMemories();
    } catch (error) {
      this.notify(`更新记忆失败：${error.message}`);
    }
  },

  async deleteMemory(memoryId) {
    if (!confirm("确定删除这条记忆吗？")) return;
    try {
      const response = await fetch(`/memory/${encodeURIComponent(memoryId)}`, { method: "DELETE" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      this.notify("记忆已删除");
      await this.loadMemories();
    } catch (error) {
      this.notify(`删除记忆失败：${error.message}`);
    }
  },

  async clearAllMemories() {
    if (!confirm("确定清空当前用户的所有长期记忆吗？此操作不可恢复。")) return;
    try {
      const response = await fetch(`/memory/user/${encodeURIComponent(this.userId)}`, { method: "DELETE" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      this.notify("已清空全部记忆");
      await this.loadMemories();
    } catch (error) {
      this.notify(`清空记忆失败：${error.message}`);
    }
  },
});
