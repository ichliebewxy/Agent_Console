"""RAG 进度日志；Web 工具事件由 Pi 宿主负责转发。

侧车不再拥有聊天 SSE 队列，避免跨请求共享旧 Agent 的全局事件状态。
"""

import logging

logger = logging.getLogger("ergouzi.rag")


def emit_rag_step(icon: str, label: str, detail: str = "") -> None:
    logger.debug("%s %s %s", icon, label, detail)
