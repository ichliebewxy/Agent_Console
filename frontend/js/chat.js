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

  continueActivePlan() {
    if (!this.planIsUnfinished(this.activePlan) || this.isLoading) return;
    this.userInput =
      "继续执行上次未完成的计划，从当前进度接着做，不要重做已完成步骤。";
    this.$nextTick(() => this.handleSend());
  },

  async handleSend() {
    const text = this.userInput.trim();
    if (
      (!text && !this.chatImages.length) ||
      this.isLoading ||
      this.isComposing
    )
      return;

    const images = [...this.chatImages];
    const prompt = text || "请描述并分析所附图片。";
    this.messages.push({
      id: this.createId(),
      text: prompt,
      isUser: true,
      imageNames: images.map((file) => file.name),
    });
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
      retryState: null,
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
      if (this.activePlan?.status === "active") {
        this.activePlan = {
          ...this.activePlan,
          status: "paused",
          updated_at: new Date().toISOString(),
        };
        if (botMessage.plan?.status === "active")
          botMessage.plan = JSON.parse(JSON.stringify(this.activePlan));
      }
      botMessage.text =
        error.name === "AbortError"
          ? botMessage.text || "已终止本次回答。"
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
});
