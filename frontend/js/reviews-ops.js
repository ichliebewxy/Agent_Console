Object.assign(window.NebulaNestApp.methods, {
  async submitForReview(msg, index) {
    const previousQuestion = this.findPreviousQuestion(index);
    try {
      const response = await fetch("/reviews", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: this.userId,
          session_id: this.sessionId,
          question: previousQuestion,
          answer: msg.text,
          message_index: index,
          rag_trace: msg.ragTrace || null,
        }),
      });
      if (!response.ok) throw new Error("Review submit failed");
      this.notify("已提交人工审核");
      await this.loadReviews();
    } catch (error) {
      this.notify(`提交审核失败：${error.message}`);
    }
  },

  findPreviousQuestion(index) {
    for (let i = index - 1; i >= 0; i -= 1) {
      if (this.messages[i].isUser) return this.messages[i].text;
    }
    return "";
  },

  async loadReviews() {
    try {
      const response = await fetch("/reviews?limit=100");
      if (!response.ok) throw new Error("Failed to load reviews");
      const data = await response.json();
      this.reviews = data.reviews || [];
    } catch (error) {
      console.warn(error);
    }
  },

  async updateReview(review, status) {
    try {
      const response = await fetch(`/reviews/${review.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status,
          reviewer_note: review.reviewer_note || "",
          revised_answer: review.revised_answer || "",
        }),
      });
      if (!response.ok) throw new Error("Review update failed");
      await this.loadReviews();
      this.notify("审核状态已更新");
    } catch (error) {
      this.notify(`审核更新失败：${error.message}`);
    }
  },

  async loadFailures() {
    try {
      const response = await fetch("/tool-failures?limit=100");
      if (!response.ok) throw new Error("Failed to load failures");
      const data = await response.json();
      this.failures = data.failures || [];
    } catch (error) {
      console.warn(error);
    }
  },

  async updateFailure(failure, status) {
    try {
      const response = await fetch(`/tool-failures/${failure.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status, callback_note: failure.callback_note || "" }),
      });
      if (!response.ok) throw new Error("Failure update failed");
      const payload = await response.json();
      await this.loadFailures();
      if (status === "retry_requested") {
        this.notify(payload.status === "resolved" ? "回调重试成功" : "回调重试失败，已写入备注");
      } else {
        this.notify("回调状态已更新");
      }
    } catch (error) {
      this.notify(`回调更新失败：${error.message}`);
    }
  },
});
