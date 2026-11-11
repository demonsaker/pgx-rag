"""语料仓储：读 chunk / 表格。

当前阶段（Docker 未就绪）用 JSONL 实现；MySQL 起来后换成 `MysqlChunkRepository`，
上层 `RetrievalService` 不需要改——它只依赖这里的接口。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.conf.app_config import app_config, get_abs_path
from app.core.logger import logger
from app.entities.schemas import Chunk


class ChunkRepository:
    """接口约定：按 id 取、按条件筛、拿全量顺序。"""

    def get(self, chunk_id: str) -> Chunk | None:
        raise NotImplementedError

    def all(self) -> list[Chunk]:
        raise NotImplementedError

    def order(self) -> list[str]:
        raise NotImplementedError

    def allowed_ids(
        self,
        *,
        drug: str | None = None,
        kind: str | None = None,
        max_priority: int | None = None,
    ) -> set[str] | None:
        """把过滤条件翻译成 id 集合；没有任何条件时返回 None（表示不过滤）。"""
        if not drug and not kind and max_priority is None:
            return None
        return {
            chunk.chunk_id
            for chunk in self.all()
            if (not drug or chunk.drug == drug)
            and (not kind or chunk.kind == kind)
            and (max_priority is None or chunk.section_priority <= max_priority)
        }


class JsonlChunkRepository(ChunkRepository):
    def __init__(self, path: Path | None = None, extra_paths: list[Path] | None = None) -> None:
        self.path = path or get_abs_path(app_config.rag.corpus_path)
        self.extra_paths = extra_paths if extra_paths is not None else self._default_extra()
        self._chunks: dict[str, Chunk] = {}
        self._order: list[str] = []
        self.load()

    @staticmethod
    def _default_extra() -> list[Path]:
        """除说明书外，是否把指南原文也纳入检索语料。"""
        if not app_config.rag.include_cpic:
            return []
        extra = get_abs_path(app_config.rag.cpic_corpus_path)
        return [extra] if extra.exists() else []

    def load(self) -> None:
        if not self.path.exists():
            raise FileNotFoundError(f"语料不存在：{self.path}（先跑构建脚本）")
        self._chunks.clear()
        self._order.clear()
        for path in [self.path, *self.extra_paths]:
            count = 0
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                chunk = Chunk.from_dict(json.loads(line))
                self._chunks[chunk.chunk_id] = chunk
                self._order.append(chunk.chunk_id)
                count += 1
            logger.info("已载入 {} 条（{}）", count, path.name)

    def get(self, chunk_id: str) -> Chunk | None:
        return self._chunks.get(chunk_id)

    def all(self) -> list[Chunk]:
        return [self._chunks[cid] for cid in self._order]

    def order(self) -> list[str]:
        return list(self._order)


class TableRepository:
    """表格结构仓储（引用时渲染表格用），当前同样读 JSONL。"""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or get_abs_path(app_config.rag.tables_path)
        self._tables: dict[str, dict] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self._tables[row["table_id"]] = row

    def get(self, table_id: str) -> dict | None:
        return self._tables.get(table_id)

    def __len__(self) -> int:
        return len(self._tables)


def make_chunk_repository() -> ChunkRepository:
    """工厂：Docker 未就绪时返回 JSONL 实现；MySQL 版本在下一阶段接入。"""
    return JsonlChunkRepository()
