Object.assign(window.NebulaNestApp.methods, {
  formatMcpEndpoint(server) {
    if (!server) return "";
    if (server.url) return server.url;
    return [server.command, ...(server.args || [])].filter(Boolean).join(" ");
  },

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
      this.notify("MCP 工具和 Skills catalog 已刷新");
    } catch (error) {
      this.notify(`刷新失败：${error.message}`);
    } finally {
      this.configLoading = false;
    }
  },

  async addMcpServer() {
    try {
      const headers = JSON.parse(this.mcpForm.headers || "{}");
      const env = JSON.parse(this.mcpForm.env || "{}");
      const body = {
        name: this.mcpForm.name.trim(),
        transport: this.mcpForm.transport,
        url: this.mcpForm.url.trim(),
        command: this.mcpForm.command.trim(),
        args: this.mcpForm.args.split(/\s+/).filter(Boolean),
        headers,
        env,
        enabled: this.mcpForm.enabled,
      };
      const response = await fetch("/runtime-config/mcp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
      this.runtimeConfig = data.config || this.runtimeConfig;
      this.mcpForm = {
        name: "", transport: "streamable_http", url: "", command: "",
        args: "", headers: "{}", env: "{}", enabled: true,
      };
      this.notify("MCP server 已保存并完成工具发现");
    } catch (error) {
      this.notify(`保存 MCP 失败：${error.message}`);
    }
  },

  async deleteMcpServer(name) {
    if (!confirm(`删除 MCP server「${name}」并重新加载主 Agent？`)) return;
    try {
      const response = await fetch(`/runtime-config/mcp/${encodeURIComponent(name)}`, { method: "DELETE" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await this.loadRuntimeConfig();
      this.notify("MCP server 已删除");
    } catch (error) {
      this.notify(`删除 MCP 失败：${error.message}`);
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
      this.runtimeConfig = data.config || this.runtimeConfig;
      this.skillForm = { name: "", description: "", instructions: "", overwrite: false };
      this.notify("Skill 已保存并重新加载");
    } catch (error) {
      this.notify(`保存 Skill 失败：${error.message}`);
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
