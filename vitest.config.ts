import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    exclude: ["tmp/**", "node_modules/**"],
    environment: "node",
  },
});
