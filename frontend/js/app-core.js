const { createApp } = Vue;

window.NebulaNestApp = {
  data() {
    return {
      messages: [],
      userInput: "",
      isLoading: false,
      activeView: "chat",
      abortController: null,
      userId: "user_" + Math.random().toString(36).slice(2, 11),
      sessionId: "session_" + Date.now(),
      sessions: [],
      runtimeConfig: null,
      configLoading: false,
      mcpForm: {
        name: "",
        transport: "streamable_http",
        url: "",
        command: "",
        args: "",
        headers: "{}",
        env: "{}",
        enabled: true,
      },
      skillForm: {
        name: "",
        description: "",
        instructions: "",
        overwrite: false,
      },
      documents: [],
      documentsLoading: false,
      selectedFile: null,
      isUploading: false,
      uploadProgress: "",
      memories: [],
      memoriesLoading: false,
      memoriesAdding: false,
      memoryForm: {
        memory: "",
        infer: false,
      },
      showHistorySidebar: false,
      isComposing: false,
      toast: "",
    };
  },

  computed: {
    stateKey() {
      return `nebulanest-state-${this.userId}`;
    },
    viewTitle() {
      const titles = {
        chat: { eyebrow: "主 Agent 协调检索、工具与执行计划", title: "研究与分析" },
        knowledge: { eyebrow: "管理本地文档与混合检索索引", title: "知识库" },
        config: { eyebrow: "管理 MCP、Skills 与命令权限", title: "配置中心" },
        memory: { eyebrow: "查看和维护跨会话的用户上下文", title: "长期记忆" },
      };
      return titles[this.activeView] || titles.chat;
    },
    latestAgentMessage() {
      for (let index = this.messages.length - 1; index >= 0; index -= 1) {
        if (!this.messages[index].isUser) return this.messages[index];
      }
      return null;
    },
    contextPlanSteps() {
      const msg = this.latestAgentMessage;
      if (!msg) return [];

      const planned = this.planSteps(msg);
      if (planned.length) return planned;

      return this.agentFlowSteps(msg).slice(-5).map((step, index, steps) => {
        let status = "done";
        if (step.phase === "error" || step.status === "failed") status = "failed";
        else if (this.isLoading && index === steps.length - 1) status = "in_progress";
        return {
          id: step.call_id || `activity-${index}`,
          title: step.label || step.tool_name || "执行步骤",
          detail: step.result || step.detail || "",
          status,
        };
      });
    },
    contextSources() {
      return this.latestAgentMessage ? this.sourceChunks(this.latestAgentMessage).slice(0, 3) : [];
    },
    contextToolCount() {
      return this.latestAgentMessage ? this.toolCallGroups(this.latestAgentMessage).length : 0;
    },
    contextProgressPercent() {
      const steps = this.contextPlanSteps;
      if (!this.latestAgentMessage) return 0;
      if (!steps.length) return this.isLoading ? 28 : 100;
      const complete = steps.filter((step) => ["done", "skipped"].includes(step.status)).length;
      const active = steps.some((step) => step.status === "in_progress") ? 0.45 : 0;
      return Math.min(100, Math.round(((complete + active) / steps.length) * 100));
    },
    contextProgressText() {
      if (!this.latestAgentMessage) return "等待任务";
      if (!this.contextPlanSteps.length) return this.isLoading ? "正在分析" : "已完成";
      const complete = this.contextPlanSteps.filter((step) => ["done", "skipped"].includes(step.status)).length;
      return `${complete} / ${this.contextPlanSteps.length}`;
    },
    contextStatusText() {
      if (this.isLoading) return "执行中";
      const workflowStatus = this.latestAgentMessage && this.latestAgentMessage.workflow
        ? this.latestAgentMessage.workflow.run_status
        : "";
      if (workflowStatus) return this.workflowStatusLabel(workflowStatus);
      if (this.contextPlanSteps.some((step) => step.status === "failed")) return "需处理";
      if (this.contextPlanSteps.some((step) => ["pending", "in_progress"].includes(step.status))) return "待继续";
      return this.latestAgentMessage ? "已完成" : "就绪";
    },
  },

  mounted() {
    this.configureMarked();
    this.restoreIdentity();
    this.restoreState();
    this.syncShellContext();
    this.$nextTick(() => this.scrollToBottom());
  },

  methods: {
    configureMarked() {
      marked.setOptions({
        highlight(code, lang) {
          const language = hljs.getLanguage(lang) ? lang : "plaintext";
          return hljs.highlight(code, { language }).value;
        },
        langPrefix: "hljs language-",
        breaks: true,
        gfm: true,
      });
    },

    restoreIdentity() {
      const savedUserId = localStorage.getItem("nebulanest-user-id");
      if (savedUserId) {
        this.userId = savedUserId;
      } else {
        localStorage.setItem("nebulanest-user-id", this.userId);
      }
    },

    restoreState() {
      const raw = localStorage.getItem(this.stateKey);
      if (!raw) return;
      try {
        const saved = JSON.parse(raw);
        this.sessionId = saved.sessionId || this.sessionId;
        const restoredView = saved.activeView || "chat";
        this.activeView = ["chat", "knowledge", "config", "memory"].includes(restoredView)
          ? restoredView
          : "chat";
        this.userInput = saved.userInput || "";
        this.messages = Array.isArray(saved.messages) ? saved.messages : [];
      } catch (error) {
        console.warn("State restore failed", error);
      }
    },

    persistState() {
      const state = {
        sessionId: this.sessionId,
        activeView: this.activeView,
        userInput: this.userInput,
        messages: this.messages.slice(-80),
      };
      localStorage.setItem(this.stateKey, JSON.stringify(state));
    },

    notify(message, duration = 2400) {
      this.toast = message;
      window.clearTimeout(this._toastTimer);
      this._toastTimer = window.setTimeout(() => {
        this.toast = "";
      }, duration);
    },

    syncShellContext() {
      const shell = document.getElementById("app");
      if (shell) shell.classList.toggle("has-context", this.activeView === "chat");
    },

    switchView(view) {
      this.activeView = view;
      this.showHistorySidebar = false;
      if (view === "knowledge") this.loadDocuments();
      if (view === "config") this.loadRuntimeConfig();
      if (view === "memory") this.loadMemories();
      this.persistState();
    },

    parseMarkdown(text) {
      return marked.parse(text || "");
    },

    createId() {
      if (window.crypto && typeof window.crypto.randomUUID === "function") {
        return window.crypto.randomUUID();
      }
      return `id_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
    },

    escapeHtml(text) {
      const div = document.createElement("div");
      div.textContent = text || "";
      return div.innerHTML;
    },

    activeThinkingLabel(msg) {
      const steps = this.agentFlowSteps(msg);
      if (steps.length) {
        return steps[steps.length - 1].label;
      }
      return msg.thinkingText || "正在规划与检索...";
    },

    agentFlowSteps(msg) {
      if (!msg) return [];
      if (Array.isArray(msg.flowSteps) && msg.flowSteps.length) return msg.flowSteps;
      return [
        ...(Array.isArray(msg.ragSteps) ? msg.ragSteps : []),
        ...(Array.isArray(msg.toolSteps) ? msg.toolSteps : []),
      ];
    },

    autoResize(event) {
      const textarea = event.target;
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
      this.persistState();
    },

    resetTextareaHeight() {
      if (this.$refs.textarea) this.$refs.textarea.style.height = "auto";
    },

    scrollToBottom() {
      if (this.$refs.chatContainer) {
        this.$refs.chatContainer.scrollTop = this.$refs.chatContainer.scrollHeight;
      }
    },

    handleNewChat() {
      this.messages = [];
      this.userInput = "";
      this.sessionId = "session_" + Date.now();
      this.activeView = "chat";
      this.showHistorySidebar = false;
      this.persistState();
    },

    handleClearChat() {
      if (!confirm("确定清空当前会话吗？")) return;
      this.messages = [];
      this.persistState();
    },

    useSuggestion(text) {
      this.userInput = text;
      this.$nextTick(() => {
        const el = this.$refs.textarea;
        if (!el) return;
        el.focus();
        el.style.height = "auto";
        el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
      });
    },
  },

  watch: {
    messages: {
      deep: true,
      handler() {
        this.persistState();
        this.$nextTick(() => this.scrollToBottom());
      },
    },
    userInput() {
      this.persistState();
    },
    activeView() {
      this.persistState();
      this.syncShellContext();
    },
  },
};
