"""检索服务：BM25 + 向量双路召回，RRF 融合，实体加权与章节权威度。

这一层只做「编排」，不关心底层是 MySQL 还是 JSONL、是 Qdrant 服务端还是嵌入式，
也不关心 embedding 是 TEI 还是 DashScope —— 那些都在 clients / repositories 里。

三个真正带来增益的设计（都来自阶段 2 的实测，不是拍脑袋）：
1. **RRF 融合**：余弦 0–1 与 BM25 0–∞ 量纲不同，只按名次融合才公平；
2. **章节权威度惩罚**：患者版说明书会复述黑框警告，纯相似度会把它排到前面；
3. **单药自动过滤**：说明书互相引用（泮托拉唑标签里也提氯吡格雷），不过滤会串药。
"""

from __future__ import annotations

from pathlib import Path

from app.clients.embedding import EmbeddingClient, make_embedding_client
from app.clients.vector import VectorClient, make_vector_client
from app.conf.app_config import app_config
from app.core.logger import logger
from app.core.query import QueryPlan, plan_query
from app.entities.schemas import Chunk, SearchHit
from app.repositories.chunk_repository import ChunkRepository, make_chunk_repository
from app.repositories.keyword_repository import KeywordRepository

RRF_K = 60
PRIORITY_PENALTY = 0.01


def rrf_fuse(
    rankings: list[list[tuple[str, float]]],
    weights: list[float] | None = None,
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    weights = weights or [1.0] * len(rankings)
    scores: dict[str, float] = {}
    for ranking, weight in zip(rankings, weights):
        for rank, (chunk_id, _score) in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (k + rank)
    return sorted(scores.items(), key=lambda kv: -kv[1])


class RetrievalService:
    def __init__(
        self,
        *,
        chunk_repository: ChunkRepository | None = None,
        keyword_repository: KeywordRepository | None = None,
        vector_client: VectorClient | None = None,
        embedding_client: EmbeddingClient | None = None,
    ) -> None:
        self.chunks = chunk_repository or make_chunk_repository()
        self.keywords = keyword_repository or KeywordRepository()
        self.keywords.load()
        self._vector_client = vector_client
        self._embedding_client = embedding_client

    # ---------------------------------------------------------------- 惰性初始化
    @property
    def vectors(self) -> VectorClient:
        if self._vector_client is None:
            self._vector_client = make_vector_client()
        return self._vector_client

    @property
    def embedding(self) -> EmbeddingClient:
        if self._embedding_client is None:
            self._embedding_client = make_embedding_client()
        return self._embedding_client

    @property
    def vector_ready(self) -> bool:
        try:
            return self.vectors.count() > 0
        except Exception:  # noqa: BLE001 - 服务未起时视为未就绪
            return False

    # ---------------------------------------------------------------- 检索
    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        mode: str = "hybrid",
        drug: str | None = None,
        kind: str | None = None,
        max_priority: int | None = None,
        candidates: int | None = None,
        exclude: set[str] | None = None,
    ) -> list[SearchHit]:
        cfg = app_config.rag
        top_k = top_k or cfg.top_k
        candidates = candidates or cfg.candidates
        max_priority = cfg.max_priority if max_priority is None else max_priority

        plan = plan_query(query)
        allowed = self.chunks.allowed_ids(drug=drug, kind=kind, max_priority=max_priority)

        # 只点名一个药时，把候选限定在该药（说明书互相引用会串药）
        if not drug and len(plan.drugs) == 1:
            only = self.chunks.allowed_ids(drug=plan.drugs[0])
            allowed = only if allowed is None else (allowed & only)

        # 留出实验用：把指定 id（例如某几个药的 CPIC 切片）从候选里剔除
        if exclude:
            allowed = (set(self.chunks.order()) - exclude) if allowed is None else (allowed - exclude)

        bm25_hits = self.keywords.search(plan.bm25_text, top_k=candidates, allowed=allowed)

        dense_hits: list[tuple[str, float]] = []
        if mode in ("hybrid", "dense") and self.vector_ready:
            vector = self.embedding.embed_query(query)  # 中文原文直接编码（多语言模型）
            dense_hits = self.vectors.search(
                vector, top_k=candidates, drug=plan.drugs[0] if len(plan.drugs) == 1 else None, kind=kind
            )
            if allowed is not None:
                dense_hits = [(cid, s) for cid, s in dense_hits if cid in allowed]

        if mode == "bm25":
            fused = bm25_hits
        elif mode == "dense":
            fused = dense_hits
        else:
            fused = rrf_fuse([bm25_hits, dense_hits]) if dense_hits else bm25_hits

        fused = self._boost(fused, plan)
        fused = self._apply_priority(fused)
        return self._to_hits(fused[:top_k], plan)

    # ---------------------------------------------------------------- 内部
    def _boost(self, fused: list[tuple[str, float]], plan: QueryPlan) -> list[tuple[str, float]]:
        """实体软加权：问题点了基因/表型，就把含该信号的块往前推一点（不做硬过滤）。"""
        if not plan.genes and not plan.phenotypes:
            return fused
        genes = set(plan.genes)
        out: list[tuple[str, float]] = []
        for chunk_id, score in fused:
            chunk = self.chunks.get(chunk_id)
            if chunk is None:
                continue
            bonus = 0.0
            if genes & set(chunk.pgx.get("genes", [])):
                bonus += 0.02
            if plan.phenotypes and chunk.pgx.get("phenotypes"):
                bonus += 0.01
            out.append((chunk_id, score + bonus))
        return sorted(out, key=lambda kv: -kv[1])

    def _apply_priority(self, fused: list[tuple[str, float]]) -> list[tuple[str, float]]:
        """归一化后按章节优先级扣分（RRF 分数只有 0.01 量级，不归一化会被惩罚项淹没）。"""
        if not fused:
            return fused
        scores = [score for _, score in fused]
        lo, hi = min(scores), max(scores)
        span = (hi - lo) or 1.0
        penalized = []
        for chunk_id, score in fused:
            chunk = self.chunks.get(chunk_id)
            if chunk is None:
                continue
            penalized.append((chunk_id, (score - lo) / span - PRIORITY_PENALTY * chunk.section_priority))
        return sorted(penalized, key=lambda kv: -kv[1])

    def _to_hits(self, fused: list[tuple[str, float]], plan: QueryPlan) -> list[SearchHit]:
        hits: list[SearchHit] = []
        for rank, (chunk_id, score) in enumerate(fused, start=1):
            chunk: Chunk | None = self.chunks.get(chunk_id)
            if chunk is None:
                continue
            sources = []
            if chunk.kind == "table":
                sources.append("table")
            if chunk.pgx.get("is_pgx"):
                sources.append("pgx")
            reason = "命中" + "/".join(sources) if sources else "语义或关键词匹配"
            if plan.genes and set(plan.genes) & set(chunk.pgx.get("genes", [])):
                reason += f"；含查询基因 {'/'.join(plan.genes)}"
            hits.append(SearchHit(chunk=chunk, score=score, rank=rank, sources=tuple(sources), reason=reason))
        logger.debug("检索 '{}' -> {} 条（genes={}）", plan.raw, len(hits), plan.genes)
        return hits
