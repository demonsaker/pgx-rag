"""Qdrant 客户端：服务端模式与嵌入式模式共用一套接口。

* 服务端：`QdrantClient(url="http://host:port")`，对应 docker compose 里的 qdrant（生产形态）；
* 嵌入式：`QdrantClient(path=...)`，进程内跑，Docker 未就绪时也能验证整条链路。

payload 只存过滤/展示需要的元数据，正文仍在 MySQL/JSONL 里，避免两处存同一份文本。
"""

from __future__ import annotations

import atexit
import os
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PointStruct, VectorParams

from app.conf.app_config import app_config
from app.core.logger import logger
from app.entities.schemas import Chunk

# 本机容器端口（6333）会被环境的 HTTP 代理/拦截层接走，返回 502 Bad Gateway；
# 显式把 localhost 排除在代理之外，Docker 里的服务才能被正常访问。
for _var in ("NO_PROXY", "no_proxy"):
    _existing = os.environ.get(_var, "")
    _missing = [host for host in ("localhost", "127.0.0.1", "::1") if host not in _existing]
    if _missing:
        os.environ[_var] = ",".join(filter(None, [_existing, *_missing]))


class VectorClient:
    def __init__(self, *, local_path: Path | None = None, collection: str | None = None) -> None:
        cfg = app_config.qdrant
        self.collection = collection or cfg.collection
        self.dim = cfg.embedding_size
        self._local_path = local_path
        self._closed = False
        if local_path is not None:
            local_path.mkdir(parents=True, exist_ok=True)
            self.client = QdrantClient(path=str(local_path))
            self.mode = f"embedded:{local_path}"
        else:
            self.client = QdrantClient(url=f"http://{cfg.host}:{cfg.port}")
            self.mode = f"server:{cfg.host}:{cfg.port}"
        # 嵌入式模式会在进程退出时由 portalocker 解锁文件；
        # 若等到 __del__ 才关，模块已被拆掉会抛 "import of typing halted"。
        # 提前注册 atexit，在模块销毁前正常关闭。
        atexit.register(self.close)

    # ---------------------------------------------------------------- 结构
    def ensure_collection(self, recreate: bool = False) -> None:
        exists = self.client.collection_exists(self.collection)
        if exists and recreate:
            self.client.delete_collection(self.collection)
            exists = False
        if not exists:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE),
            )
            logger.info("已创建 collection {}（dim={}）", self.collection, self.dim)

    def count(self) -> int:
        try:
            return self.client.count(self.collection, exact=True).count
        except Exception:  # noqa: BLE001 - collection 不存在时返回 0
            return 0

    # ---------------------------------------------------------------- 写入
    def upsert(self, chunks: list[Chunk], vectors: np.ndarray, batch_size: int = 256) -> int:
        total = 0
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            points = [
                PointStruct(id=start + offset, vector=vectors[start + offset].tolist(), payload=chunk.to_payload())
                for offset, chunk in enumerate(batch)
            ]
            self.client.upsert(collection_name=self.collection, points=points, wait=True)
            total += len(points)
        logger.info("向量写入完成：{} 条 -> {}", total, self.mode)
        return total

    # ---------------------------------------------------------------- 查询
    def search(
        self,
        vector: np.ndarray,
        top_k: int = 40,
        *,
        drug: str | None = None,
        kind: str | None = None,
        max_priority: int | None = None,
    ) -> list[tuple[str, float]]:
        conditions = []
        if drug:
            conditions.append(FieldCondition(key="drug", match=MatchValue(value=drug)))
        if kind:
            conditions.append(FieldCondition(key="kind", match=MatchValue(value=kind)))
        query_filter = Filter(must=conditions) if conditions else None

        hits = self.client.query_points(
            collection_name=self.collection,
            query=vector.tolist(),
            limit=top_k,
            query_filter=query_filter,
        ).points
        return [(str(hit.payload.get("chunk_id", hit.id)), float(hit.score)) for hit in hits]

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self.client.close()
        except Exception:  # noqa: BLE001 - 关闭告警不影响流程
            pass


def make_vector_client(*, server: bool | None = None) -> VectorClient:
    """按配置选择服务端或嵌入式；`server` 显式覆盖（脚本 --server 用）。"""
    if server is None:
        server = app_config.qdrant.mode.lower() != "embedded"
    return VectorClient(local_path=None if server else Path("data/index/qdrant"))
