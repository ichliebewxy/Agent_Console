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
      reviews: [],
      failures: [],
      documents: [],
      documentsLoading: false,
      selectedFile: null,
      isUploading: false,
      uploadProgress: "",
      showHistorySidebar: false,
      isComposing: false,
      toast: "",
    };
  },

  computed: {
    stateKey() {
      return `nebulanest-state-${this.userId}`;
    },
    pendingReviewCount() {
      return this.reviews.filter((item) => item.status === "pending").length;
    },
    openFailureCount() {
      return this.activeFailures.length;
    },
    activeFailures() {
      return this.failures.filter((item) => ["open", "retry_requested"].includes(item.status));
    },
    viewTitle() {
      const titles = {
        chat: { eyebrow: "Chat", title: "可追踪的 Agent 对话" },
        knowledge: { eyebrow: "Knowledge", title: "知识库与 RAGFlow 接入" },
        reviews: { eyebrow: "Human Review", title: "人工审核工作台" },
        ops: { eyebrow: "Callbacks", title: "工具失败与补偿回调" },
      };
      return titles[this.activeView] || titles.chat;
    },
  },

  mounted() {
    this.configureMarked();
    this.restoreIdentity();
    this.restoreState();
    this.loadReviews();
    this.loadFailures();
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
        this.activeView = saved.activeView || "chat";
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
      if (view === "reviews") this.loadReviews();
      if (view === "ops") this.loadFailures();
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
