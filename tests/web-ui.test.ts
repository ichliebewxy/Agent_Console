import { describe, expect, it } from "vitest";
import { WebUI } from "../src/agent/web-ui.js";

describe("Web extension dialogs", () => {
  it("accepts only offered selections and resolves the waiting plugin", async () => {
    const events: any[] = [];
    const ui = new WebUI((event) => events.push(event));
    const answer = ui.context().select("Choose", ["A", "B"]);
    const request = events[0];
    expect(request.type).toBe("ui_request");
    expect(() => ui.respond(request.id, "invalid")).toThrow("有效选项");
    expect(ui.respond(request.id, "B")).toBe(true);
    expect(await answer).toBe("B");
    expect(ui.respond(request.id, "B")).toBe(false);
  });

  it("cancels outstanding dialogs when the connection is stopped", async () => {
    const ui = new WebUI(() => {});
    const answer = ui.context().input("Your answer");
    ui.cancel();
    expect(await answer).toBeUndefined();
  });
});
