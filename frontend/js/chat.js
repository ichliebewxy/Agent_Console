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

  async handleSend() {
    const text = this.userInput.trim();
    if (!text || this.isLoading || this.isComposing) return;

    this.messages.push({ id: this.createId(), text, isUser: true });
    this.userInput = "";
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
      thinkingText: "主 Agent 正在规划并选择小 Agent...",
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
      const response = await fetch("/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, user_id: this.userId, session_id: this.sessionId }),
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
      if (data.type === "content_boundary") {
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
      } else if (data.type === "artifacts") {
        const botMessage = this.activeAssistantMessage(botMsgIdx);
        botMessage.artifacts = data.artifacts || [];
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
    this.sessionId = sessionId;
    this.activeView = "chat";
    this.showHistorySidebar = false;
    try {
      const response = await fetch(`/sessions/${this.userId}/${sessionId}`);
      if (!response.ok) throw new Error("Failed to load session messages");
      const data = await response.json();
      this.messages = (data.messages || []).map((msg) => ({
        id: this.createId(),
        text: msg.content,
        isUser: msg.type === "human",
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
