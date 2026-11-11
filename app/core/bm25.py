"""BM25 关键索引（纯 Python，无第三方依赖）。

为什么自己实现而不是用 `rank_bm25`：
1. 需要可控分词——基因/等位基因（`CYP2C19*2`、`HLA-B*5701`）必须保持可检索；
2. 需要字段加权——药名、章节名、基因符号是核心信号，拼进索引文本并重复一次即可；
3. 索引要能落盘复用，建一次库多次查询。
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from app.core.text import tokenize


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.doc_ids: list[str] = []
        self.doc_len: list[int] = []
        self.postings: dict[str, list[tuple[int, int]]] = {}
        self.idf: dict[str, float] = {}
        self.avgdl: float = 0.0

    # ---------------------------------------------------------------- 构建
    def build(self, docs: list[tuple[str, str]]) -> "BM25Index":
        """docs: [(chunk_id, index_text)]"""
        self.doc_ids = [cid for cid, _ in docs]
        postings: dict[str, dict[int, int]] = defaultdict(dict)
        self.doc_len = []

        for index, (_cid, text) in enumerate(docs):
            tokens = tokenize(text)
            self.doc_len.append(len(tokens))
            counts: dict[str, int] = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            for token, tf in counts.items():
                postings[token][index] = tf

        self.avgdl = sum(self.doc_len) / max(len(self.doc_len), 1)
        n = len(self.doc_ids)
        self.postings = {term: list(tf.items()) for term, tf in postings.items()}
        self.idf = {
            term: math.log(1 + (n - len(posts) + 0.5) / (len(posts) + 0.5))
            for term, posts in self.postings.items()
        }
        return self

    # ---------------------------------------------------------------- 查询
    def search(self, query: str, top_k: int = 20, allowed: set[str] | None = None) -> list[tuple[str, float]]:
        scores: dict[int, float] = defaultdict(float)
        for term in tokenize(query):
            posts = self.postings.get(term)
            if not posts:
                continue
            idf = self.idf[term]
            for doc_index, tf in posts:
                norm = self.k1 * (1 - self.b + self.b * self.doc_len[doc_index] / (self.avgdl or 1))
                scores[doc_index] += idf * (tf * (self.k1 + 1)) / (tf + norm)

        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        out: list[tuple[str, float]] = []
        for doc_index, score in ranked:
            chunk_id = self.doc_ids[doc_index]
            if allowed is not None and chunk_id not in allowed:
                continue
            out.append((chunk_id, round(score, 4)))
            if len(out) >= top_k:
                break
        return out

    # ---------------------------------------------------------------- 持久化
    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "k1": self.k1, "b": self.b, "doc_ids": self.doc_ids, "doc_len": self.doc_len,
                    "avgdl": self.avgdl, "idf": self.idf, "postings": self.postings,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path) -> "BM25Index":
        payload = json.loads(path.read_text(encoding="utf-8"))
        index = cls(k1=payload["k1"], b=payload["b"])
        index.doc_ids = payload["doc_ids"]
        index.doc_len = payload["doc_len"]
        index.avgdl = payload["avgdl"]
        index.idf = payload["idf"]
        index.postings = {k: [tuple(p) for p in v] for k, v in payload["postings"].items()}
        return index


def build_index_text(chunk) -> str:
    """BM25 索引文本：高价值字段重复一次做轻量加权（不改分数量纲）。"""
    genes = " ".join(chunk.pgx.get("genes", []))
    phenotypes = " ".join(chunk.pgx.get("phenotypes", []))
    return " ".join(
        p for p in [
            chunk.drug, chunk.drug, chunk.section_label, chunk.section_label,
            genes, genes, phenotypes, chunk.heading, chunk.text,
        ] if p
    )
