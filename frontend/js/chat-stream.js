Object.assign(window.NebulaNestApp.methods, {
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
      } else if (data.type === "retry") {
        const botMessage = this.activeAssistantMessage(botMsgIdx);
        botMessage.retryState = {
          source: data.source || "model",
          status: data.status || "review",
          toolName: data.tool_name || "",
          attempt: data.attempt || 0,
          maxAttempts: data.max_attempts || 4,
          delayMs: data.delay_ms || 0,
          error: data.error || "",
          transient: Boolean(data.transient),
        };
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
        const incoming = Object.prototype.hasOwnProperty.call(data, "plan")
          ? data.plan
          : {
              objective: data.objective || "",
              status: data.status || "active",
              steps: Array.isArray(data.steps) ? data.steps : [],
              reflections: data.reflections || [],
              updated_at: data.updated_at,
            };
        this.activePlan = incoming
          ? JSON.parse(JSON.stringify(incoming))
          : null;
        botMessage.plan = incoming
          ? JSON.parse(JSON.stringify(incoming))
          : null;
      } else if (data.type === "plan_step") {
        const botMessage = this.activeAssistantMessage(botMsgIdx);
        botMessage.flowSteps = botMessage.flowSteps || [];
        botMessage.flowSteps.push(data.step);
      } else if (data.type === "execute") {
        const botMessage = this.activeAssistantMessage(botMsgIdx);
        if (!botMessage.plan)
          botMessage.plan = { objective: "", steps: [], reflections: [] };
        const target = (botMessage.plan.steps || []).find(
          (s) => s.id === data.step_id,
        );
        if (target) {
          target.status = data.status;
          if (data.result !== undefined) target.result = data.result;
        }
        this.activePlan = JSON.parse(JSON.stringify(botMessage.plan));
      } else if (data.type === "reflect") {
        const botMessage = this.activeAssistantMessage(botMsgIdx);
        if (!botMessage.plan)
          botMessage.plan = { objective: "", steps: [], reflections: [] };
        botMessage.plan.reflections = botMessage.plan.reflections || [];
        botMessage.plan.reflections.push({
          decision: data.decision,
          reason: data.reason,
          adjusted: data.adjusted,
        });
        this.activePlan = JSON.parse(JSON.stringify(botMessage.plan));
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
});
