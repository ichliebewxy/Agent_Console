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
      hasEntered: false,
      showEntry: true,
      entryLeaving: false,
      entryTouchStartY: 0,
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

    enterWorkspace() {
      if (this.entryLeaving) return;
      this.hasEntered = true;
      this.entryLeaving = true;
      this.loadReviews();
      this.loadFailures();
      window.setTimeout(() => {
        this.showEntry = false;
        this.entryLeaving = false;
        this.$nextTick(() => this.scrollToBottom());
      }, 720);
    },

    returnToEntry() {
      this.showHistorySidebar = false;
      this.hasEntered = false;
      this.showEntry = true;
      this.entryLeaving = false;
    },

    handleEntryWheel(event) {
      if (event.deltaY > 28) this.enterWorkspace();
    },

    handleEntryTouchStart(event) {
      this.entryTouchStartY = event.changedTouches?.[0]?.clientY || 0;
    },

    handleEntryTouchEnd(event) {
      const endY = event.changedTouches?.[0]?.clientY || 0;
      if (this.entryTouchStartY - endY > 36) this.enterWorkspace();
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
      if (msg.ragSteps && msg.ragSteps.length) {
        return msg.ragSteps[msg.ragSteps.length - 1].label;
      }
      return msg.thinkingText || "正在规划与检索...";
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
