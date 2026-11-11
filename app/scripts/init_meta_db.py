"""初始化元数据库：建表 + 灌入药物、说明书、chunk、表格结构。

    uv run python -m app.scripts.init_meta_db            # 幂等：先清后灌
    uv run python -m app.scripts.init_meta_db --wait 60  # 等 MySQL 就绪（首次启动较慢）

数据来源是阶段 1 的产物（data/corpus/*.jsonl），不重复抓网络。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import defaultdict
from datetime import date

from sqlalchemy import delete, func, select

from app.clients.mysql import make_engine, make_session_factory
from app.conf.app_config import get_abs_path
from app.core.logger import logger
from app.entities.drugs import DRUGS
from app.entities.schemas import Chunk
from app.models.orm import Base, ChunkRow, Document, Drug, IndexBuild, LabelTableRow


def _load_chunks() -> list[Chunk]:
    path = get_abs_path("data/corpus/chunks.jsonl")
    return [Chunk.from_dict(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _load_tables() -> list[dict]:
    path = get_abs_path("data/corpus/tables.jsonl")
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _parse_date(value) -> date | None:
    text = str(value or "")
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None
    return None


def _documents(chunks: list[Chunk]) -> list[dict]:
    """从 chunk 的 evidence 聚合出「一份说明书一行」。"""
    docs: dict[str, dict] = {}
    for chunk in chunks:
        ev = chunk.evidence or {}
        set_id = ev.get("set_id") or chunk.set_id
        if not set_id or set_id in docs:
            continue
        docs[set_id] = {
            "set_id": set_id,
            "drug": chunk.drug,
            "label_id": ev.get("label_id"),
            "brand_name": ev.get("brand_name"),
            "manufacturer": ev.get("manufacturer"),
            "route": ev.get("route"),
            "effective_date": _parse_date(ev.get("effective_date")),
            "ingredient_count": ev.get("ingredient_count", 1),
            "api_url": ev.get("api_url"),
            "dailymed_url": ev.get("dailymed_url"),
        }
    return list(docs.values())


async def _wait_for_db(engine, timeout: int) -> None:
    deadline = time.time() + timeout
    while True:
        try:
            async with engine.connect() as conn:
                await conn.exec_driver_sql("SELECT 1")
            return
        except Exception as exc:  # noqa: BLE001 - 首次启动时 MySQL 还在初始化
            if time.time() > deadline:
                raise RuntimeError(f"MySQL 在 {timeout}s 内未就绪: {exc}") from exc
            logger.warning("等待 MySQL 就绪…（{}）", type(exc).__name__)
            await asyncio.sleep(3)


async def main_async(timeout: int) -> int:
    engine = make_engine()
    await _wait_for_db(engine, timeout)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("表结构就绪：{}", ", ".join(sorted(Base.metadata.tables)))

    chunks = _load_chunks()
    tables = _load_tables()
    documents = _documents(chunks)
    logger.info("待入库：{} chunk / {} 表格 / {} 说明书 / {} 药物", len(chunks), len(tables), len(documents), len(DRUGS))

    factory = make_session_factory(engine)
    async with factory() as session:
        # 幂等重建：清空业务表（不动表结构）
        for model in (ChunkRow, LabelTableRow, Document, Drug):
            await session.execute(delete(model))

        session.add_all([
            Drug(drug=d["drug"], drug_class=d["drug_class"], genes=d["genes"], topic=d["topic"]) for d in DRUGS
        ])
        session.add_all([Document(**doc) for doc in documents])
        await session.flush()

        session.add_all([
            ChunkRow(
                chunk_id=c.chunk_id,
                set_id=c.set_id,
                drug=c.drug,
                drug_class=c.drug_class,
                section=c.section,
                section_label=c.section_label,
                section_priority=c.section_priority,
                kind=c.kind,
                heading=c.heading,
                text=c.text,
                chars=c.chars,
                est_tokens=c.est_tokens,
                pgx_genes=c.pgx.get("genes", []),
                pgx_phenotypes=c.pgx.get("phenotypes", []),
                pgx_alleles=c.pgx.get("alleles", []),
                is_pgx=int(bool(c.pgx.get("is_pgx"))),
                table_id=c.table_id,
                row_start=(c.row_range or [None, None])[0],
                row_end=(c.row_range or [None, None])[1],
                evidence=c.evidence,
            )
            for c in chunks
        ])

        session.add_all([
            LabelTableRow(
                table_id=t["table_id"],
                drug=t["drug"],
                section=t["section"],
                caption=t.get("caption"),
                headers=t.get("headers", []),
                rows=json.dumps(t.get("rows", []), ensure_ascii=False),
                n_rows=t.get("n_rows", 0),
                n_cols=t.get("n_cols", 0),
                header_source=t.get("header_source"),
                has_rowspan=int(bool(t.get("has_rowspan"))),
                has_colspan=int(bool(t.get("has_colspan"))),
                footnotes=t.get("footnotes", []),
                html_sha=t.get("html_sha"),
                html=t.get("html"),
            )
            for t in tables
        ])
        session.add(IndexBuild(target="mysql_meta", model="corpus", chunks=len(chunks)))
        await session.commit()

    # 校验：读回计数
    async with factory() as session:
        counts = {
            "drugs": (await session.scalar(select(func.count()).select_from(Drug))) or 0,
            "documents": (await session.scalar(select(func.count()).select_from(Document))) or 0,
            "chunks": (await session.scalar(select(func.count()).select_from(ChunkRow))) or 0,
            "label_tables": (await session.scalar(select(func.count()).select_from(LabelTableRow))) or 0,
        }
        per_drug = (await session.execute(
            select(ChunkRow.drug, func.count()).group_by(ChunkRow.drug).order_by(func.count().desc()).limit(5)
        )).all()

    logger.info("入库校验：{}", counts)
    logger.info("块数最多的 5 个药：{}", per_drug)
    await engine.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="初始化 pgx-rag 元数据库")
    parser.add_argument("--wait", type=int, default=90, help="等待 MySQL 就绪的秒数")
    args = parser.parse_args()
    return asyncio.run(main_async(args.wait))


if __name__ == "__main__":
    raise SystemExit(main())
