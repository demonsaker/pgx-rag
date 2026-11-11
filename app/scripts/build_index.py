"""构建检索索引：BM25（本地）+ 向量（Qdrant）。

用法：
    uv run python -m app.scripts.build_index              # 嵌入式 Qdrant（Docker 未就绪时）
    uv run python -m app.scripts.build_index --server      # 写进 docker 里的 Qdrant 服务
    uv run python -m app.scripts.build_index --no-dense    # 只建 BM25（秒级）
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from app.clients.embedding import make_embedding_client
from app.clients.vector import make_vector_client
from app.conf.app_config import app_config
from app.core.logger import logger
from app.repositories.chunk_repository import JsonlChunkRepository
from app.repositories.keyword_repository import KeywordRepository

EMBED_CACHE = Path("data/index/embed_cache.jsonl")


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 pgx-rag 检索索引")
    parser.add_argument("--server", action="store_true", help="写入服务端 Qdrant（默认嵌入式）")
    parser.add_argument("--no-dense", action="store_true", help="只建 BM25")
    parser.add_argument("--workers", type=int, default=None, help="并发编码数（dashscope 后端有效）")
    args = parser.parse_args()

    started = time.perf_counter()

    # 1) 语料
    repo = JsonlChunkRepository()
    chunks = repo.all()
    logger.info("语料：{} 条 chunk", len(chunks))

    # 2) BM25
    keyword = KeywordRepository()
    keyword.build(chunks)

    # 3) 向量
    if not args.no_dense:
        embedding = make_embedding_client()
        logger.info("编码后端：{} / {}（dim={}）", embedding.kind, embedding.model_name, embedding.dim)
        vectors = embedding.embed_documents(
            [c.text for c in chunks],
            cache_path=EMBED_CACHE,
            workers=args.workers or app_config.embedding.workers,
        )
        logger.info("向量矩阵：{} x {}", vectors.shape[0], vectors.shape[1])

        vector_client = make_vector_client(server=True if args.server else None)
        vector_client.ensure_collection(recreate=True)
        vector_client.upsert(chunks, vectors)
        logger.info("Qdrant：{} 条（{}）", vector_client.count(), vector_client.mode)
        vector_client.close()

    logger.info("建索引完成，耗时 {:.1f}s", time.perf_counter() - started)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
