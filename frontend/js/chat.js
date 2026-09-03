Object.assign(window.NebulaNestApp.methods, {
  handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey && !this.isComposing) {
      event.preventDefault();
      this.handleSend();
    }
  },

  handleStop() {
    if (this.abortController) this.abortController.abort();
  },

  handleChatImageSelect(event) {
    const incoming = Array.from(event.target.files || []);
    const remaining = Math.max(0, 5 - this.chatImages.length);
    this.chatImages.push(...incoming.slice(0, remaining));
    if (incoming.length > remaining) this.notify("每次最多上传 5 张图片");
    event.target.value = "";
  },

  removeChatImage(index) {
    this.chatImages.splice(index, 1);
  },

  async handleSend() {
    const text = this.userInput.trim();
    if ((!text && !this.chatImages.length) || this.isLoading || this.isComposing) return;

    const images = [...this.chatImages];
    const prompt = text || "请描述并分析所附图片。";
    this.messages.push({ id: this.createId(), text: prompt, isUser: true, imageNames: images.map((file) => file.name) });
    this.userInput = "";
    this.chatImages = [];
    this.isLoading = true;
    this.persistState();
    this.$nextTick(() => {
      this.resetTextareaHeight();
      this.scrollToBottom();
    });

    this.messages.push({
      id: this.createId(),
      text: "",
      isUser: false,
      isThinking: true,
      thinkingText: "二狗子正在分析任务并操作工作区…",
      plan: null,
      ragTrace: null,
      ragSteps: [],
      toolSteps: [],
      flowSteps: [],
      artifacts: [],
      streamGroupId: this.createId(),
    });
    const botMsgIdx = this.messages.length - 1;
    this.abortController = new AbortController();

    try {
      const body = new FormData();
      body.append("message", prompt);
      body.append("user_id", this.userId);
      body.append("session_id", this.sessionId);
      images.forEach((file) => body.append("images", file, file.name));
      const response = await fetch("/chat/stream", {
        method: "POST",
        body,
        signal: this.abortController.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      if (!response.body) throw new Error("浏览器不支持流式响应");
      await this.readSseStream(response.body, botMsgIdx);
    } catch (error) {
      const botMessage = this.activeAssistantMessage(botMsgIdx);
      botMessage.isThinking = false;
      botMessage.text = error.name === "AbortError"
        ? (botMessage.text || "已终止本次回答。")
        : `请求失败：${error.message}\n\n已保留当前状态，你可以稍后重试。`;
    } finally {
      this.isLoading = false;
      this.pendingDialog = null;
      this.activeAssistantMessage(botMsgIdx).isThinking = false;
      this.abortController = null;
      this.persistState();
      this.$nextTick(() => this.scrollToBottom());
    }
  },

  async readSseStream(body, botMsgIdx) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let eventEndIndex;
      while ((eventEndIndex = buffer.indexOf("\n\n")) !== -1) {
        const eventStr = buffer.slice(0, eventEndIndex);
        buffer = buffer.slice(eventEndIndex + 2);
        this.consumeSseEvent(eventStr, botMsgIdx);
      }
      this.$nextTick(() => this.scrollToBottom());
    }
  },

  consumeSseEvent(eventStr, botMsgIdx) {
    if (!eventStr.startsWith("data: ")) return;
    const dataStr = eventStr.slice(6);
    if (dataStr === "[DONE]") return;
    try {
      const data = JSON.parse(dataStr);
      if (data.type === "ui_request") {
        this.pendingDialog = data;
        this.dialogAnswer = "";
      } else if (data.type === "ui_closed") {
        if (this.pendingDialog?.id === data.id) this.pendingDialog = null;
      } else if (data.type === "notification") {
        this.notify(data.message);
      } else if (data.type === "content_boundary") {
        this.startNextAssistantSegment(botMsgIdx);
      } else if (data.type === "content") {
        const botMessage = this.activeAssistantMessage(botMsgIdx);
        botMessage.isThinking = false;
        botMessage.text += data.content;
      } else if (data.type === "trace") {
        this.mergeStreamTrace(botMsgIdx, data.rag_trace);
      } else if (data.type === "rag_step") {
        const botMessage = this.activeAssistantMessage(botMsgIdx);
        botMessage.ragSteps.push(data.step);
        botMessage.flowSteps = botMessage.flowSteps || [];
        botMessage.flowSteps.push(data.step);
      } else if (data.type === "tool_step") {
        const botMessage = this.activeAssistantMessage(botMsgIdx);
        botMessage.toolSteps = botMessage.toolSteps || [];
        botMessage.flowSteps = botMessage.flowSteps || [];
        botMessage.toolSteps.push(data.step);
        botMessage.flowSteps.push(data.step);
        this.scrollToolActivityToEnd(botMessage.id);
      } else if (data.type === "artifacts") {
        const botMessage = this.activeAssistantMessage(botMsgIdx);
        botMessage.artifacts = data.artifacts || [];
      } else if (data.type === "plan") {
        const botMessage = this.activeAssistantMessage(botMsgIdx);
        if (!botMessage.plan) botMessage.plan = { objective: "", steps: [], reflections: [] };
        botMessage.plan.objective = data.objective || botMessage.plan.objective;
        if (Array.isArray(data.steps)) botMessage.plan.steps = data.steps;
      } else if (data.type === "plan_step") {
        const botMessage = this.activeAssistantMessage(botMsgIdx);
        botMessage.flowSteps = botMessage.flowSteps || [];
        botMessage.flowSteps.push(data.step);
      } else if (data.type === "execute") {
        const botMessage = this.activeAssistantMessage(botMsgIdx);
        if (!botMessage.plan) botMessage.plan = { objective: "", steps: [], reflections: [] };
        const target = (botMessage.plan.steps || []).find((s) => s.id === data.step_id);
        if (target) {
          target.status = data.status;
          if (data.result !== undefined) target.result = data.result;
        }
      } else if (data.type === "reflect") {
        const botMessage = this.activeAssistantMessage(botMsgIdx);
        if (!botMessage.plan) botMessage.plan = { objective: "", steps: [], reflections: [] };
        botMessage.plan.reflections = botMessage.plan.reflections || [];
        botMessage.plan.reflections.push({
          decision: data.decision,
          reason: data.reason,
          adjusted: data.adjusted,
        });
      } else if (data.type === "error") {
        const botMessage = this.activeAssistantMessage(botMsgIdx);
        botMessage.isThinking = false;
        botMessage.text += `\n\n工具或模型返回错误：${data.content}`;
      }
      this.persistState();
    } catch (error) {
      console.warn("SSE parse error", error);
    }
  },

  activeAssistantMessage(botMsgIdx) {
    const root = this.messages[botMsgIdx];
    if (!root || !root.streamGroupId) return root;
    for (let index = this.messages.length - 1; index >= botMsgIdx; index -= 1) {
      if (this.messages[index].streamGroupId === root.streamGroupId) return this.messages[index];
    }
    return root;
  },

  async answerDialog(value) {
    if (!this.pendingDialog || this.dialogSubmitting) return;
    this.dialogSubmitting = true;
    try {
      const response = await fetch("/chat/ui-response", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: this.userId, session_id: this.sessionId, id: this.pendingDialog.id, value }),
      });
      if (!response.ok) throw new Error((await response.json()).detail || "问题已过期");
    } catch (error) { this.notify(error.message); }
    finally { this.dialogSubmitting = false; }
  },

  scrollToolActivityToEnd(messageId) {
    this.$nextTick(() => {
      if (!this.$refs.chatContainer) return;
      const scroller = Array.from(
        this.$refs.chatContainer.querySelectorAll("[data-tool-message-id]")
      ).find((element) => element.dataset.toolMessageId === String(messageId));
      if (!scroller) return;
      const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      scroller.scrollTo({
        top: scroller.scrollHeight,
        behavior: reduceMotion ? "auto" : "smooth",
      });
    });
  },

  mergeStreamTrace(botMsgIdx, ragTrace) {
    const root = this.messages[botMsgIdx];
    const target = this.activeAssistantMessage(botMsgIdx);
    if (!root || !target || !root.streamGroupId) {
      if (target) target.ragTrace = ragTrace;
      return;
    }
    for (let index = botMsgIdx; index < this.messages.length; index += 1) {
      const message = this.messages[index];
      if (message === target || message.streamGroupId !== root.streamGroupId) continue;
      target.ragSteps.push(...(message.ragSteps || []));
      target.toolSteps.push(...(message.toolSteps || []));
      target.flowSteps.push(...(message.flowSteps || []));
      message.ragSteps = [];
      message.toolSteps = [];
      message.flowSteps = [];
    }
    target.ragTrace = ragTrace;
  },

  startNextAssistantSegment(botMsgIdx) {
    const current = this.activeAssistantMessage(botMsgIdx);
    if (!current || !current.text.trim()) return;
    this.messages.push({
      id: this.createId(),
      text: "",
      isUser: false,
      isThinking: false,
      thinkingText: "",
      plan: null,
      ragTrace: null,
      ragSteps: [],
      toolSteps: [],
      flowSteps: [],
      artifacts: [],
      streamGroupId: current.streamGroupId,
    });
  },

  async handleHistory() {
    this.showHistorySidebar = true;
    try {
      const response = await fetch(`/sessions/${this.userId}`);
      if (!response.ok) throw new Error("Failed to load sessions");
      const data = await response.json();
      this.sessions = data.sessions || [];
    } catch (error) {
      this.notify(`加载历史失败：${error.message}`);
    }
  },

  async loadSession(sessionId) {
    if (this.isLoading) { this.notify("请先停止或等待当前任务"); return; }
    this.sessionId = sessionId;
    this.activeView = "chat";
    this.showHistorySidebar = false;
    try {
      const response = await fetch(`/sessions/${this.userId}/${sessionId}`);
      if (!response.ok) throw new Error("Failed to load session messages");
      const data = await response.json();
      if (data.workspace && data.workspace !== this.workspacePath) {
        const workspaceResponse = await fetch(`/workspace/${this.userId}`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: data.workspace }),
        });
        if (!workspaceResponse.ok) throw new Error("原工作区不可用，请手动重新选择文件夹");
        this.workspacePath = data.workspace;
        this.workspaceDraft = data.workspace;
      }
      this.messages = (data.messages || []).map((msg) => ({
        id: this.createId(),
        text: msg.content,
        isUser: msg.type === "human",
        plan: null,
        ragTrace: msg.rag_trace || null,
        ragSteps: [],
        toolSteps: [],
        flowSteps: [],
        artifacts: msg.artifacts || [],
      }));
      this.persistState();
      this.$nextTick(() => this.scrollToBottom());
    } catch (error) {
      this.notify(`加载会话失败：${error.message}`);
    }
  },
});
