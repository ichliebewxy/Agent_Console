const { createApp } = Vue;

window.NebulaNestApp = {
  data() {
    return {
      messages: [],
      userInput: "",
      chatImages: [],
      pendingDialog: null,
      dialogAnswer: "",
      dialogSubmitting: false,
      isLoading: false,
      activeView: "chat",
      activePlan: null,
      planExpanded: true,
      abortController: null,
      userId: "user_" + Math.random().toString(36).slice(2, 11),
      sessionId: "session_" + Date.now(),
      sessions: [],
      runtimeConfig: null,
      configLoading: false,
      skillForm: {
        name: "",
        description: "",
        instructions: "",
        overwrite: false,
      },
      workspacePath: "",
      workspaceDraft: "",
      workspaceLoading: false,
      documents: [],
      documentsLoading: false,
      selectedFile: null,
      isUploading: false,
      uploadProgress: "",
      uploadStatus: "idle",
      uploadStage: "",
      uploadFilename: "",
      uploadElapsed: 0,
      uploadChunksProcessed: 0,
      uploadChunksTotal: 0,
      uploadParentChunks: 0,
      uploadStages: [
        { id: "uploading", label: "上传文件" },
        { id: "parsing", label: "解析分块" },
        { id: "indexing", label: "生成索引" },
        { id: "saving", label: "保存完成" },
      ],
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
        chat: { eyebrow: "Workspace", title: "工作区助手" },
        knowledge: { eyebrow: "Knowledge", title: "知识库" },
        config: { eyebrow: "Settings", title: "运行配置" },
      };
      return titles[this.activeView] || titles.chat;
    },
  },

  mounted() {
    this.configureMarked();
    this.restoreIdentity();
    this.restoreState();
    this.loadWorkspace();
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
        this.activeView = ["chat", "knowledge", "config"].includes(restoredView)
          ? restoredView
          : "chat";
        this.userInput = saved.userInput || "";
        this.messages = Array.isArray(saved.messages) ? saved.messages : [];
        this.activePlan = saved.activePlan || null;
        this.planExpanded = saved.planExpanded !== false;
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
        activePlan: this.activePlan,
        planExpanded: this.planExpanded,
      };
      localStorage.setItem(this.stateKey, JSON.stringify(state));
    },

    notify(message) {
      this.toast = message;
      window.clearTimeout(this._toastTimer);
      this._toastTimer = window.setTimeout(() => {
        this.toast = "";
      }, 2400);
    },

    switchView(view) {
      this.activeView = view;
      this.showHistorySidebar = false;
      if (view === "knowledge") this.loadDocuments();
      if (view === "config") this.loadRuntimeConfig();
      this.persistState();
    },

    parseMarkdown(text) {
      return DOMPurify.sanitize(marked.parse(text || ""));
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
      if (this.messages.length && this.$refs.chatContainer) {
        this.$refs.chatContainer.scrollTop = this.$refs.chatContainer.scrollHeight;
      }
    },

    handleNewChat() {
      if (this.isLoading) { this.notify("请先停止或等待当前任务"); return; }
      this.messages = [];
      this.userInput = "";
      this.chatImages = [];
      this.activePlan = null;
      this.planExpanded = true;
      this.sessionId = "session_" + Date.now();
      this.activeView = "chat";
      this.showHistorySidebar = false;
      this.persistState();
    },

    handleClearChat() {
      if (this.isLoading) { this.notify("请先停止或等待当前任务"); return; }
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
    },
  },
};
