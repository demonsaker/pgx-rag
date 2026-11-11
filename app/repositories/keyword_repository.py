"""关键词仓储：BM25 索引的建/存/查。

Docker 就绪后会换成 Elasticsearch 实现（`es_repository.py`）：
ES 的优势是在大规模语料上做倒排 + 高亮；当前 2416 条规模下，
纯 Python BM25 已经够快（建索引 < 1s，查询 < 10ms），且零外部依赖。
"""

from __future__ import annotations

from pathlib import Path

from app.core.bm25 import BM25Index, build_index_text
from app.core.logger import logger
from app.entities.schemas import Chunk

DEFAULT_INDEX_PATH = Path("data/index/bm25.json")


class KeywordRepository:
    def __init__(self, index_path: Path | None = None) -> None:
        self.index_path = index_path or DEFAULT_INDEX_PATH
        self.index: BM25Index | None = None

    # ---------------------------------------------------------------- 构建
    def build(self, chunks: list[Chunk]) -> int:
        docs = [(chunk.chunk_id, build_index_text(chunk)) for chunk in chunks]
        self.index = BM25Index().build(docs)
        self.index.save(self.index_path)
        logger.info("BM25 索引已构建：{} 条 -> {}", len(docs), self.index_path)
        return len(docs)

    # ---------------------------------------------------------------- 载入
    def load(self) -> bool:
        if not self.index_path.exists():
            self.index = None
            return False
        self.index = BM25Index.load(self.index_path)
        logger.info("BM25 索引已载入：{} 条", len(self.index.doc_ids))
        return True

    # ---------------------------------------------------------------- 查询
    def search(self, query: str, top_k: int = 40, allowed: set[str] | None = None) -> list[tuple[str, float]]:
        if self.index is None and not self.load():
            return []
        return self.index.search(query, top_k=top_k, allowed=allowed)

    @property
    def ready(self) -> bool:
        return self.index is not None
