Object.assign(window.NebulaNestApp.methods, {
  async loadFailures() {
    try {
      const response = await fetch("/tool-failures?limit=100");
      if (!response.ok) throw new Error("Failed to load runtime records");
      const data = await response.json();
      this.failures = data.failures || [];
    } catch (error) {
      console.warn(error);
    }
  },
});
