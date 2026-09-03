"""一次性预下载 BGE 嵌入模型，避免服务器运行/知识库搜索时反复缓慢下载。

用法（在项目根目录执行，首次下载前关闭 EMBEDDING_LOCAL_FILES_ONLY）：
    uv run python -m backend.preload_embedding_model

下载完成后模型会缓存到本地 Hugging Face 缓存目录；
之后可在 .env 中设置 EMBEDDING_LOCAL_FILES_ONLY=true，让服务完全离线加载。
"""
import os

# 与 embedding.py 保持一致，优先走镜像。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

from backend.knowledge.embedding import embedding_service  # noqa: E402


def main() -> int:
    print(f"开始加载/下载嵌入模型: {embedding_service.model_name} "
          f"(device={embedding_service.device})")
    print("若模型未缓存，下方会出现下载进度条；请保持网络直到 100% 完成。")
    info = embedding_service.warm_up()
    print(f"模型就绪: {info['model']} -> {info['dim']} 维")
    print("提示：现在可在 .env 里设置 EMBEDDING_LOCAL_FILES_ONLY=true 以离线加载。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
