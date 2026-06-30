"""Write document chunks to Milvus with dense and sparse embeddings."""
from encoding_utils import safe_print
from embedding import EmbeddingService, embedding_service as default_embedding_service
from milvus_client import MilvusManager


class MilvusWriter:
    """Batch writer for searchable leaf chunks."""

    def __init__(
        self,
        embedding_service: EmbeddingService = None,
        milvus_manager: MilvusManager = None,
    ):
        self.embedding_service = embedding_service or default_embedding_service
        self.milvus_manager = milvus_manager or MilvusManager()

    def write_documents(self, documents: list[dict], batch_size: int = 50):
        if not documents:
            return

        self.milvus_manager.init_collection()
        total = len(documents)
        safe_print(f"\nStart writing {total} chunks to Milvus...")

        for i in range(0, total, batch_size):
            batch = documents[i:i + batch_size]
            texts = [doc["text"] for doc in batch]

            self.embedding_service.increment_add_documents(texts)
            try:
                dense_embeddings, sparse_embeddings = self.embedding_service.get_all_embeddings(texts)
                insert_data = [
                    {
                        "dense_embedding": dense_emb,
                        "sparse_embedding": sparse_emb,
                        "text": doc["text"],
                        "filename": doc["filename"],
                        "file_type": doc["file_type"],
                        "file_path": doc.get("file_path", ""),
                        "page_number": doc.get("page_number", 0),
                        "chunk_idx": doc.get("chunk_idx", 0),
                        "chunk_id": doc.get("chunk_id", ""),
                        "parent_chunk_id": doc.get("parent_chunk_id", ""),
                        "root_chunk_id": doc.get("root_chunk_id", ""),
                        "chunk_level": doc.get("chunk_level", 0),
                    }
                    for doc, dense_emb, sparse_emb in zip(batch, dense_embeddings, sparse_embeddings)
                ]
                self.milvus_manager.insert(insert_data)
            except Exception:
                self.embedding_service.increment_remove_documents(texts)
                raise

            progress = min(i + batch_size, total)
            safe_print(f"   -> write progress: {progress} / {total} ({progress / total:.1%})")
