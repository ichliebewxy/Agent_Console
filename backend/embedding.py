"""文本向量化服务 - BGE dense embeddings + BM25 sparse embeddings."""
import json
import math
import re
import threading
from collections import Counter
from pathlib import Path
from typing import Any

from settings import (
    BM25_STATE_PATH,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DEVICE,
    EMBEDDING_MODEL,
)

_DEFAULT_STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "bm25_state.json"


class EmbeddingService:
    """文本向量化服务 - BGE 本地密集向量 + 持久化 BM25 稀疏向量。"""

    def __init__(self, state_path: Path | str | None = None):
        self.model_name = EMBEDDING_MODEL
        self.device = EMBEDDING_DEVICE
        self.batch_size = max(1, EMBEDDING_BATCH_SIZE)
        self._embedder: Any | None = None
        self._embedder_lock = threading.Lock()

        self._state_path = Path(state_path or BM25_STATE_PATH or _DEFAULT_STATE_PATH)
        self._state_lock = threading.Lock()

        self.k1 = 1.5
        self.b = 0.75
        self._vocab: dict[str, int] = {}
        self._vocab_counter = 0
        self._doc_freq: Counter[str] = Counter()
        self._total_docs = 0
        self._sum_token_len = 0
        self._avg_doc_len = 1.0

        self._load_state()

    def _get_embedder(self):
        if self._embedder is not None:
            return self._embedder
        with self._embedder_lock:
            if self._embedder is None:
                from langchain_huggingface import HuggingFaceEmbeddings

                self._embedder = HuggingFaceEmbeddings(
                    model_name=self.model_name,
                    model_kwargs={"device": self.device},
                    encode_kwargs={
                        "normalize_embeddings": True,
                        "batch_size": self.batch_size,
                    },
                )
        return self._embedder

    def _recompute_avg_len(self) -> None:
        self._avg_doc_len = self._sum_token_len / self._total_docs if self._total_docs > 0 else 1.0

    def _load_state(self) -> None:
        path = self._state_path
        if not path.is_file():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if raw.get("version") != 1:
            return
        self._vocab = {str(k): int(v) for k, v in raw.get("vocab", {}).items()}
        self._doc_freq = Counter({str(k): int(v) for k, v in raw.get("doc_freq", {}).items()})
        self._total_docs = int(raw.get("total_docs", 0))
        self._sum_token_len = int(raw.get("sum_token_len", 0))
        self._vocab_counter = max(self._vocab.values()) + 1 if self._vocab else 0
        self._recompute_avg_len()

    def _persist_unlocked(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "total_docs": self._total_docs,
            "sum_token_len": self._sum_token_len,
            "vocab": self._vocab,
            "doc_freq": dict(self._doc_freq),
        }
        tmp = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._state_path)

    def increment_add_documents(self, texts: list[str]) -> None:
        """将每个 chunk 文本作为 BM25 文档，增量更新 N、df 和平均长度。"""
        valid_texts = [text for text in texts if text and text.strip()]
        if not valid_texts:
            return
        with self._state_lock:
            for text in valid_texts:
                tokens = self.tokenize(text)
                self._sum_token_len += len(tokens)
                self._total_docs += 1
                for token in set(tokens):
                    if token not in self._vocab:
                        self._vocab[token] = self._vocab_counter
                        self._vocab_counter += 1
                    self._doc_freq[token] += 1
            self._recompute_avg_len()
            self._persist_unlocked()

    def increment_remove_documents(self, texts: list[str]) -> None:
        """删除文档时回退 BM25 统计；词表索引不回收，避免已写入稀疏向量错位。"""
        valid_texts = [text for text in texts if text and text.strip()]
        if not valid_texts:
            return
        with self._state_lock:
            for text in valid_texts:
                tokens = self.tokenize(text)
                self._sum_token_len = max(0, self._sum_token_len - len(tokens))
                self._total_docs = max(0, self._total_docs - 1)
                for token in set(tokens):
                    if token not in self._doc_freq:
                        continue
                    self._doc_freq[token] -= 1
                    if self._doc_freq[token] <= 0:
                        del self._doc_freq[token]
            self._recompute_avg_len()
            self._persist_unlocked()

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """首次调用时懒加载 BGE 模型并生成 dense embeddings。"""
        valid_texts = [text for text in texts if text and text.strip()]
        if not valid_texts:
            return []
        try:
            return self._get_embedder().embed_documents(valid_texts)
        except Exception as exc:
            raise Exception(f"BGE 嵌入模型调用失败: {exc}") from exc

    def get_query_embeddings(self, texts: list[str]) -> list[list[float]]:
        return self.get_embeddings(texts)

    def warm_up(self) -> dict[str, Any]:
        embedder = self._get_embedder()
        vector = embedder.embed_query("warmup")
        return {
            "model": self.model_name,
            "device": self.device,
            "dim": len(vector),
        }

    def get_passage_embeddings(self, texts: list[str]) -> list[list[float]]:
        return self.get_embeddings(texts)

    def tokenize(self, text: str) -> list[str]:
        text = text.lower()
        tokens = []
        chinese_pattern = re.compile(r"[\u4e00-\u9fff]")
        english_pattern = re.compile(r"[a-zA-Z]+")
        i = 0
        while i < len(text):
            char = text[i]
            if chinese_pattern.match(char):
                tokens.append(char)
                i += 1
            elif english_pattern.match(char):
                match = english_pattern.match(text[i:])
                if match:
                    tokens.append(match.group())
                    i += len(match.group())
            else:
                i += 1
        return tokens

    def _sparse_vector_for_text_unlocked(self, text: str) -> tuple[dict[int, float], bool]:
        tokens = self.tokenize(text)
        doc_len = len(tokens)
        tf = Counter(tokens)
        sparse_vector: dict[int, float] = {}
        vocab_changed = False
        n = max(self._total_docs, 0)
        avg = max(self._avg_doc_len, 1.0)

        for token, freq in tf.items():
            if token not in self._vocab:
                self._vocab[token] = self._vocab_counter
                self._vocab_counter += 1
                vocab_changed = True
            idx = self._vocab[token]
            df = self._doc_freq.get(token, 0)
            idf = math.log((n + 1) / 1) if df == 0 else math.log((n - df + 0.5) / (df + 0.5) + 1)
            numerator = freq * (self.k1 + 1)
            denominator = freq + self.k1 * (1 - self.b + self.b * doc_len / avg)
            score = idf * numerator / denominator
            if score > 0:
                sparse_vector[idx] = float(score)
        return sparse_vector, vocab_changed

    def get_sparse_embedding(self, text: str) -> dict[int, float]:
        with self._state_lock:
            sparse_vector, vocab_changed = self._sparse_vector_for_text_unlocked(text)
            if vocab_changed:
                self._persist_unlocked()
        return sparse_vector

    def get_sparse_embeddings(self, texts: list[str]) -> list[dict[int, float]]:
        if not texts:
            return []
        with self._state_lock:
            embeddings = []
            changed = False
            for text in texts:
                sparse_vector, vocab_changed = self._sparse_vector_for_text_unlocked(text)
                embeddings.append(sparse_vector)
                changed = changed or vocab_changed
            if changed:
                self._persist_unlocked()
        return embeddings

    def get_all_embeddings(self, texts: list[str]) -> tuple[list[list[float]], list[dict[int, float]]]:
        dense_embeddings = self.get_passage_embeddings(texts)
        sparse_embeddings = self.get_sparse_embeddings(texts)
        return dense_embeddings, sparse_embeddings


embedding_service = EmbeddingService()
