import { randomUUID } from "node:crypto";
import {
  Theme,
  type ExtensionUIContext,
} from "@earendil-works/pi-coding-agent";

type Dialog = {
  id: string;
  method: "select" | "input" | "confirm";
  title: string;
  options?: string[];
  placeholder?: string;
};

/** Implements Pi RPC dialog primitives in the Web host; terminal widgets are not rendered. */
export class WebUI {
  private pending = new Map<
    string,
    { dialog: Dialog; finish: (value?: string) => void }
  >();
  constructor(private emit: (event: Record<string, unknown>) => void) {}

  private ask(
    method: Dialog["method"],
    title: string,
    options?: string[],
    placeholder?: string,
    signal?: AbortSignal,
    timeout = 600000,
  ): Promise<string | undefined> {
    if (signal?.aborted) return Promise.resolve(undefined);
    return new Promise((resolve) => {
      const dialog: Dialog = {
        id: randomUUID(),
        method,
        title,
        options,
        placeholder,
      };
      const finish = (value?: string) => {
        clearTimeout(timer);
        signal?.removeEventListener("abort", cancel);
        this.pending.delete(dialog.id);
        this.emit({ type: "ui_closed", id: dialog.id });
        resolve(value);
      };
      const cancel = () => finish();
      const timer = setTimeout(cancel, timeout);
      signal?.addEventListener("abort", cancel, { once: true });
      this.pending.set(dialog.id, { dialog, finish });
      this.emit({ type: "ui_request", ...dialog });
    });
  }

  respond(id: string, value: unknown): boolean {
    const item = this.pending.get(id);
    if (!item) return false;
    if (value !== null && typeof value !== "string")
      throw new Error("回答必须是字符串或取消");
    if (
      typeof value === "string" &&
      item.dialog.options &&
      !item.dialog.options.includes(value)
    )
      throw new Error("请选择有效选项");
    item.finish(value === null ? undefined : String(value));
    return true;
  }

  cancel(): void {
    for (const item of this.pending.values()) item.finish();
  }

  context(): ExtensionUIContext {
    const noop = () => {};
    const foreground = new Proxy({} as ConstructorParameters<typeof Theme>[0], {
      get: () => "#222222",
    });
    const background = new Proxy({} as ConstructorParameters<typeof Theme>[1], {
      get: () => "#ffffff",
    });
    const theme = new Theme(foreground, background, "truecolor");
    theme.fg = (_color, text) => text;
    theme.bg = (_color, text) => text;
    return {
      select: (title, options, opts) =>
        this.ask(
          "select",
          title,
          options,
          undefined,
          opts?.signal,
          opts?.timeout,
        ),
      input: (title, placeholder, opts) =>
        this.ask(
          "input",
          title,
          undefined,
          placeholder,
          opts?.signal,
          opts?.timeout,
        ),
      confirm: async (title, message, opts) =>
        (await this.ask(
          "confirm",
          `${title}\n${message}`,
          ["确认", "取消"],
          undefined,
          opts?.signal,
          opts?.timeout,
        )) === "确认",
      editor: (title, prefill) => this.ask("input", title, undefined, prefill),
      notify: (message, level) =>
        this.emit({ type: "notification", message, level }),
      onTerminalInput: () => noop,
      setStatus: noop,
      setWorkingMessage: noop,
      setWorkingVisible: noop,
      setWorkingIndicator: noop,
      setHiddenThinkingLabel: noop,
      setWidget: noop,
      setFooter: noop,
      setHeader: noop,
      setTitle: noop,
      custom: async <T>() => undefined as T,
      pasteToEditor: noop,
      setEditorText: noop,
      getEditorText: () => "",
      addAutocompleteProvider: noop,
      setEditorComponent: noop,
      getEditorComponent: () => undefined,
      theme,
      getAllThemes: () => [],
      getTheme: () => undefined,
      setTheme: () => ({
        success: false,
        error: "Web host does not render terminal themes",
      }),
      getToolsExpanded: () => false,
      setToolsExpanded: noop,
    };
  }
}
