Object.assign(window.NebulaNestApp.methods, {
  async loadFailures() {
    try {
      const [failureResponse, auditResponse] = await Promise.all([
        fetch("/tool-failures?limit=100"),
        fetch("/bash-audit?limit=100"),
      ]);
      if (!failureResponse.ok || !auditResponse.ok) throw new Error("Failed to load runtime records");
      const [failureData, auditData] = await Promise.all([
        failureResponse.json(),
        auditResponse.json(),
      ]);
      this.failures = failureData.failures || [];
      this.bashAudits = auditData.audits || [];
    } catch (error) {
      console.warn(error);
    }
  },
});
