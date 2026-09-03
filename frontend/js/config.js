Object.assign(window.NebulaNestApp.methods, {
  async loadRuntimeConfig() {
    this.configLoading = true;
    try {
      const response = await fetch("/runtime-config");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      this.runtimeConfig = data.config || null;
    } catch (error) {
      this.notify(`加载运行配置失败：${error.message}`);
    } finally {
      this.configLoading = false;
    }
  },

  async refreshRuntimeCatalog() {
    this.configLoading = true;
    try {
      const response = await fetch("/runtime-config/refresh", { method: "POST" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await this.loadRuntimeConfig();
      this.notify("资源目录已刷新，将在下一条消息中加载");
    } catch (error) {
      this.notify(`刷新失败：${error.message}`);
    } finally {
      this.configLoading = false;
    }
  },

  async addSkill() {
    try {
      const response = await fetch("/runtime-config/skills", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(this.skillForm),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      await this.loadRuntimeConfig();
      this.skillForm = { name: "", description: "", instructions: "", overwrite: false };
      this.notify("Skill 已保存，将在下一条消息中加载");
    } catch (error) {
      this.notify(`保存 Skill 失败：${error.message}`);
    }
  },

  async uploadSkillFile(event) {
    const file = event.target.files && event.target.files[0];
    event.target.value = "";
    if (!file) return;
    try {
      const body = new FormData();
      body.append("skill", file, file.name);
      body.append("overwrite", String(this.skillForm.overwrite));
      const response = await fetch("/runtime-config/skills/upload", { method: "POST", body });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      await this.loadRuntimeConfig();
      this.notify(data.message || "Skill 已上传并加载");
    } catch (error) {
      this.notify(`上传 Skill 失败：${error.message}`);
    }
  },

  async deleteSkill(name) {
    if (!confirm(`删除 Skill「${name}」？`)) return;
    try {
      const response = await fetch(`/runtime-config/skills/${encodeURIComponent(name)}`, { method: "DELETE" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await this.loadRuntimeConfig();
      this.notify("Skill 已删除");
    } catch (error) {
      this.notify(`删除 Skill 失败：${error.message}`);
    }
  },
});
