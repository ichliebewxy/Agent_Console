"""Milvus 客户端 - 支持密集向量+稀疏向量混合检索"""
from threading import Lock
from pymilvus import MilvusClient, DataType, AnnSearchRequest, RRFRanker
from settings import MILVUS_COLLECTION, MILVUS_HOST, MILVUS_PORT

class MilvusManager:
    """Milvus 连接和集合管理 - 支持混合检索"""

    def __init__(self):
        self.host = MILVUS_HOST
        self.port = MILVUS_PORT
        self.collection_name = MILVUS_COLLECTION
        self._uri = f"http://{self.host}:{self.port}"
        self._client_lock = Lock()
        self.client = self._new_client()

    def _new_client(self):
        return MilvusClient(uri=self._uri)

    def _reset_client(self):
        with self._client_lock:
            self.client = self._new_client()
            return self.client

    @staticmethod
    def _is_closed_channel_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "closed channel" in message
            or "channel closed" in message
            or ("nonetype" in message and "has no attribute" in message)
        )

    def _call(self, operation):
        try:
            return operation(self.client)
        except Exception as exc:
            if not self._is_closed_channel_error(exc):
                raise
            client = self._reset_client()
            return operation(client)

    def init_collection(self, dense_dim: int = 1024):
        """
        初始化 Milvus 集合 - 同时支持密集向量和稀疏向量以及三级分块索引字段
        """
        if not self._call(lambda client: client.has_collection(self.collection_name)):
            schema = self.client.create_schema(auto_id=True, enable_dynamic_field=True)
            
            # 主键
            schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)
            # 密集向量
            schema.add_field("dense_embedding", DataType.FLOAT_VECTOR, dim=dense_dim)
            # 稀疏向量（BM25）
            schema.add_field("sparse_embedding", DataType.SPARSE_FLOAT_VECTOR)
            
            # 文本和基础元数据字段
            schema.add_field("text", DataType.VARCHAR, max_length=65535) # 加大以兼容图片描述文本
            schema.add_field("filename", DataType.VARCHAR, max_length=255)
            schema.add_field("file_type", DataType.VARCHAR, max_length=50)
            schema.add_field("file_path", DataType.VARCHAR, max_length=1024)
            schema.add_field("page_number", DataType.INT64)
            schema.add_field("chunk_idx", DataType.INT64)

            # Auto-merging 所需层级字段
            schema.add_field("chunk_id", DataType.VARCHAR, max_length=512)
            schema.add_field("parent_chunk_id", DataType.VARCHAR, max_length=512)
            schema.add_field("root_chunk_id", DataType.VARCHAR, max_length=512)
            schema.add_field("chunk_level", DataType.INT64)

            # 创建索引
            index_params = self.client.prepare_index_params()
            index_params.add_index(
                field_name="dense_embedding",
                index_type="HNSW",
                metric_type="IP",
                params={"M": 16, "efConstruction": 256}
            )
            index_params.add_index(
                field_name="sparse_embedding",
                index_type="SPARSE_INVERTED_INDEX",
                metric_type="IP",
                params={"drop_ratio_build": 0.2}
            )

            self._call(
                lambda client: client.create_collection(
                    collection_name=self.collection_name,
                    schema=schema,
                    index_params=index_params
                )
            )

    def insert(self, data: list[dict]):
        return self._call(lambda client: client.insert(self.collection_name, data))

    def query(self, filter_expr: str = "", output_fields: list[str] = None, limit: int = 10000):
        return self._call(
            lambda client: client.query(
                collection_name=self.collection_name,
                filter=filter_expr,
                output_fields=output_fields or ["filename", "file_type"],
                limit=limit
            )
        )

    def delete(self, filter_expr: str):
        return self._call(
            lambda client: client.delete(
                collection_name=self.collection_name,
                filter=filter_expr,
            )
        )

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[dict]:
        """根据 chunk_id 批量查询分块（用于检索后 Auto-merging 向上拉取父块）"""
        ids = [item for item in chunk_ids if item]
        if not ids:
            return []
        quoted_ids = ", ".join([f'"{item}"' for item in ids])
        filter_expr = f"chunk_id in [{quoted_ids}]"
        return self.query(
            filter_expr=filter_expr,
            output_fields=[
                "text", "filename", "file_type", "page_number", 
                "chunk_id", "parent_chunk_id", "root_chunk_id", "chunk_level", "chunk_idx"
            ],
            limit=len(ids),
        )

    def hybrid_retrieve(self, dense_embedding: list[float], sparse_embedding: dict, top_k: int = 5, rrf_k: int = 60, filter_expr: str = "") -> list[dict]:
        """混合检索 - 使用 RRF 融合密集和稀疏向量的检索结果"""
        output_fields = [
            "text", "filename", "file_type", "page_number",
            "chunk_id", "parent_chunk_id", "root_chunk_id", "chunk_level", "chunk_idx"
        ]
        
        dense_search = AnnSearchRequest(
            data=[dense_embedding],
            anns_field="dense_embedding",
            param={"metric_type": "IP", "params": {"ef": 64}},
            limit=top_k * 2,
            expr=filter_expr,
        )
        
        sparse_search = AnnSearchRequest(
            data=[sparse_embedding],
            anns_field="sparse_embedding",
            param={"metric_type": "IP", "params": {"drop_ratio_search": 0.2}},
            limit=top_k * 2,
            expr=filter_expr,
        )
        
        reranker = RRFRanker(k=rrf_k)
        results = self._call(
            lambda client: client.hybrid_search(
                collection_name=self.collection_name,
                reqs=[dense_search, sparse_search],
                ranker=reranker,
                limit=top_k,
                output_fields=output_fields
            )
        )

        return self._format_search_results(results)

    def dense_retrieve(self, dense_embedding: list[float], top_k: int = 5, filter_expr: str = "") -> list[dict]:
        """Dense vector fallback retrieval."""
        output_fields = [
            "text", "filename", "file_type", "page_number",
            "chunk_id", "parent_chunk_id", "root_chunk_id", "chunk_level", "chunk_idx"
        ]
        results = self._call(
            lambda client: client.search(
                collection_name=self.collection_name,
                data=[dense_embedding],
                anns_field="dense_embedding",
                search_params={"metric_type": "IP", "params": {"ef": 64}},
                limit=top_k,
                filter=filter_expr,
                output_fields=output_fields,
            )
        )

        return self._format_search_results(results)

    @staticmethod
    def _format_search_results(results) -> list[dict]:
        formatted_results = []
        for hits in results:
            for hit in hits:
                formatted_results.append({
                    "id": hit.get("id"),
                    "text": hit.get("text", ""),
                    "filename": hit.get("filename", ""),
                    "file_type": hit.get("file_type", ""),
                    "page_number": hit.get("page_number", 0),
                    "chunk_id": hit.get("chunk_id", ""),
                    "parent_chunk_id": hit.get("parent_chunk_id", ""),
                    "root_chunk_id": hit.get("root_chunk_id", ""),
                    "chunk_level": hit.get("chunk_level", 0),
                    "chunk_idx": hit.get("chunk_idx", 0),
                    "score": hit.get("distance", 0.0)
                })
        
        return formatted_results
