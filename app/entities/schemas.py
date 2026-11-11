"""业务实体：检索与生成共用的数据结构。

分两层：
* `Chunk` / `LabelTable` 是「语料侧」实体，来自 SPL 解析结果；
* `SearchHit` / `Citation` 是「问答侧」实体，检索与生成层用它传递证据和出处。

两者都提供 `from_row` / `to_payload`，方便在 JSONL、MySQL、Qdrant payload 之间转换，
避免每层各写一套字段映射。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    chunk_id: str
    drug: str
    section: str
    text: str
    source: str = "openfda"
    kind: str = "text"
    drug_class: str = ""
    set_id: str | None = None
    section_label: str = ""
    section_priority: int = 5
    heading: str = ""
    table_id: str | None = None
    row_range: list[int] | None = None
    pgx: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    chars: int = 0
    est_tokens: int = 0

    @classmethod
    def from_dict(cls, row: dict) -> "Chunk":
        return cls(
            chunk_id=row["chunk_id"],
            drug=row.get("drug", ""),
            section=row.get("section", ""),
            text=row.get("text", ""),
            source=row.get("source", "openfda"),
            kind=row.get("kind", "text"),
            drug_class=row.get("drug_class", ""),
            set_id=row.get("set_id"),
            section_label=row.get("section_label", ""),
            section_priority=int(row.get("section_priority", 5)),
            heading=row.get("heading", ""),
            table_id=row.get("table_id"),
            row_range=row.get("row_range"),
            pgx=row.get("pgx") or {},
            evidence=row.get("evidence") or {},
            chars=int(row.get("chars", 0)),
            est_tokens=int(row.get("est_tokens", 0)),
        )

    # ------------------------------------------------------------ 向量库 payload
    def to_payload(self) -> dict:
        """写进 Qdrant 的元数据（够过滤、够展示引用，不重复存全文）。"""
        return {
            "chunk_id": self.chunk_id,
            "drug": self.drug,
            "section": self.section,
            "kind": self.kind,
            "section_priority": self.section_priority,
            "is_pgx": bool(self.pgx.get("is_pgx")),
            "genes": self.pgx.get("genes", []),
            "set_id": self.set_id,
        }

    # ------------------------------------------------------------ DB row
    def to_row(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "set_id": self.set_id,
            "drug": self.drug,
            "drug_class": self.drug_class,
            "section": self.section,
            "section_label": self.section_label,
            "section_priority": self.section_priority,
            "kind": self.kind,
            "heading": self.heading,
            "text": self.text,
            "chars": self.chars,
            "est_tokens": self.est_tokens,
            "pgx_genes": json.dumps(self.pgx.get("genes", []), ensure_ascii=False),
            "pgx_phenotypes": json.dumps(self.pgx.get("phenotypes", []), ensure_ascii=False),
            "pgx_alleles": json.dumps(self.pgx.get("alleles", []), ensure_ascii=False),
            "is_pgx": int(bool(self.pgx.get("is_pgx"))),
            "table_id": self.table_id,
            "row_start": (self.row_range or [None, None])[0],
            "row_end": (self.row_range or [None, None])[1],
            "evidence": json.dumps(self.evidence, ensure_ascii=False),
        }


@dataclass
class SearchHit:
    """检索结果：实体 + 分数 + 命中原因（原因用于调试与"为什么引这段"）。"""

    chunk: Chunk
    score: float
    rank: int = 0
    sources: tuple[str, ...] = ()      # ("bm25", "dense") 之类
    reason: str = ""

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk.chunk_id,
            "score": round(self.score, 6),
            "drug": self.chunk.drug,
            "section": self.chunk.section,
            "section_label": self.chunk.section_label,
            "kind": self.chunk.kind,
            "genes": self.chunk.pgx.get("genes", []),
            "sources": list(self.sources),
            "reason": self.reason,
            "text": self.chunk.text,
        }


@dataclass
class Citation:
    """答案里的一句话引用：回填到具体说明书段落。"""

    index: int
    chunk_id: str
    drug: str
    section_label: str
    effective_date: str | None = None
    set_id: str | None = None
    dailymed_url: str | None = None
    table_id: str | None = None

    @classmethod
    def from_hit(cls, index: int, hit: SearchHit) -> "Citation":
        ev = hit.chunk.evidence or {}
        return cls(
            index=index,
            chunk_id=hit.chunk_id,
            drug=hit.chunk.drug,
            section_label=hit.chunk.section_label,
            effective_date=ev.get("effective_date"),
            set_id=ev.get("set_id"),
            dailymed_url=ev.get("dailymed_url"),
            table_id=hit.chunk.table_id,
        )

    def label(self) -> str:
        date = self.effective_date or "未知生效日"
        return f"[{self.index}] {self.drug} · {self.section_label} · {date}"
