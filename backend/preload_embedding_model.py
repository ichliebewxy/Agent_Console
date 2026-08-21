"""一次性预下载 BGE 嵌入模型，避免服务器运行/知识库搜索时反复缓慢下载。

背景：BAAI/bge-m3 的权重文件（pytorch_model.bin）约 2.2GB，
如果本地缓存不完整，服务启动或首次检索时会触发 tqdm 下载进度条，
按当前 ~100kB/s 的网速需要数小时，且每次进程重启都会重新开始。

用法（在项目根目录 D:\\project 执行）：
    .venv\\Scripts\\python.exe backend\\preload_embedding_model.py

下载完成后模型会缓存到本地 Hugging Face 缓存目录；
之后可在 .env 中设置 EMBEDDING_LOCAL_FILES_ONLY=true，让服务完全离线加载。
"""
import os
import sys
from pathlib import Path

# 与 embedding.py / app.py 保持一致，优先走镜像。
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from embedding import embedding_service  # noqa: E402


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
