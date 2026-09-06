Object.assign(window.NebulaNestApp.methods, {
  activeAssistantMessage(botMsgIdx) {
    const root = this.messages[botMsgIdx];
    if (!root || !root.streamGroupId) return root;
    for (let index = this.messages.length - 1; index >= botMsgIdx; index -= 1) {
      if (this.messages[index].streamGroupId === root.streamGroupId)
        return this.messages[index];
    }
    return root;
  },

  async answerDialog(value) {
    if (!this.pendingDialog || this.dialogSubmitting) return;
    this.dialogSubmitting = true;
    try {
      const response = await fetch("/chat/ui-response", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: this.userId,
          session_id: this.sessionId,
          id: this.pendingDialog.id,
          value,
        }),
      });
      if (!response.ok)
        throw new Error((await response.json()).detail || "问题已过期");
    } catch (error) {
      this.notify(error.message);
    } finally {
      this.dialogSubmitting = false;
    }
  },

  scrollToolActivityToEnd(messageId) {
    this.$nextTick(() => {
      if (!this.$refs.chatContainer) return;
      const scroller = Array.from(
        this.$refs.chatContainer.querySelectorAll("[data-tool-message-id]"),
      ).find((element) => element.dataset.toolMessageId === String(messageId));
      if (!scroller) return;
      const reduceMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;
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
      if (message === target || message.streamGroupId !== root.streamGroupId)
        continue;
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
      retryState: null,
      plan: null,
      ragTrace: null,
      ragSteps: [],
      toolSteps: [],
      flowSteps: [],
      artifacts: [],
      streamGroupId: current.streamGroupId,
    });
  },
});
