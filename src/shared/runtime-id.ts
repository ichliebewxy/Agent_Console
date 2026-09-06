export function assertRuntimeId(value: unknown, fallback: string): string {
  const text = typeof value === "string" ? value.trim() : fallback;
  if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(text)) {
    throw new Error("用户或会话 ID 格式无效");
  }
  return text;
}
