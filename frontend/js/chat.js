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
      thinkingText: "正在调用 Agent、检查工具与知识库...",
      ragTrace: null,
      ragSteps: [],
      toolSteps: [],
      flowSteps: [],
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
      this.messages[botMsgIdx].isThinking = false;
      this.messages[botMsgIdx].text = error.name === "AbortError"
        ? (this.messages[botMsgIdx].text || "已终止本次回答。")
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
      const botMessage = this.messages[botMsgIdx];
      if (data.type === "content") {
        botMessage.isThinking = false;
        botMessage.text += data.content;
      } else if (data.type === "trace") {
        botMessage.ragTrace = data.rag_trace;
      } else if (data.type === "rag_step") {
        botMessage.ragSteps.push(data.step);
        botMessage.flowSteps = botMessage.flowSteps || [];
        botMessage.flowSteps.push(data.step);
      } else if (data.type === "tool_step") {
        botMessage.toolSteps = botMessage.toolSteps || [];
        botMessage.flowSteps = botMessage.flowSteps || [];
        botMessage.toolSteps.push(data.step);
        botMessage.flowSteps.push(data.step);
      } else if (data.type === "error") {
        botMessage.isThinking = false;
        botMessage.text += `\n\n工具或模型返回错误：${data.content}`;
        this.loadFailures();
      }
      this.persistState();
    } catch (error) {
      console.warn("SSE parse error", error);
    }
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
      }));
      this.persistState();
      this.$nextTick(() => this.scrollToBottom());
    } catch (error) {
      this.notify(`加载会话失败：${error.message}`);
    }
  },
});
