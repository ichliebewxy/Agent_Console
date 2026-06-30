"""文档向量化并写入 Milvus - 支持密集+稀疏向量"""
from encoding_utils import safe_print
from embedding import EmbeddingService, embedding_service as default_embedding_service
from milvus_client import MilvusManager

class MilvusWriter:
    """Milvus 写入管理（适配 Auto-merging 所需的分块 Schema）"""

    def __init__(self, embedding_service: EmbeddingService = None, milvus_manager: MilvusManager = None):
        self.embedding_service = embedding_service or default_embedding_service
        self.milvus_manager = milvus_manager or MilvusManager()

    def write_documents(self, documents: list[dict], batch_size: int = 50):
        """
        批量写入三级分块的字典列表到 Milvus（同时生成密集和稀疏向量）
        :param documents: 已分好层的文档字典列表
        :param batch_size: 批处理数量
        """
        if not documents:
            return

        self.milvus_manager.init_collection()
        
        # 先增量更新 BM25 语料统计（用于生成和查询稀疏向量）
        all_texts = [doc["text"] for doc in documents]
        self.embedding_service.increment_add_documents(all_texts)

        total = len(documents)
        safe_print(f"\n开始批量写入 Milvus，总计 {total} 个分片...")
        
        for i in range(0, total, batch_size):
            batch = documents[i:i + batch_size]
            texts = [doc["text"] for doc in batch]
            
            # 同时生成密集向量和稀疏向量
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
            
            progress = min(i + batch_size, total)
            safe_print(f"   -> [写入进度]: 已完成 {progress} / {total} ({progress/total:.1%})")
