"""CPIC 入库：抓取 → 落原始快照 → 写 MySQL。

    uv run python -m app.scripts.ingest_cpic            # 走本地快照（没有就抓）
    uv run python -m app.scripts.ingest_cpic --refresh  # 强制重抓

只保留我们 17 个药相关的数据：CPIC 全量有 635 个基因-药对，本项目用不到那么多；
保留原始快照是为了可复现、可离线重建。
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import delete, func, select

from app.clients.cpic import CpicClient, filter_for_drugs
from app.clients.mysql import make_engine, make_session_factory
from app.conf.app_config import get_abs_path
from app.core.logger import logger
from app.entities.drugs import DRUGS
from app.models.orm import Base, CpicDiplotype, CpicGeneResult, CpicPair, CpicRecommendation

RAW_DIR = Path("data/raw/cpic")
DRUG_NAMES = [d["drug"] for d in DRUGS]


def _load_or_fetch(name: str, fetcher, refresh: bool) -> list[dict]:
    """本地快照优先，避免每次重建都打网络（CPIC 是公共接口，别滥用）。"""
    path = get_abs_path(str(RAW_DIR / f"{name}.json"))
    if path.exists() and not refresh:
        logger.info("使用本地快照 {}.json（{} 条）", name, len(json.loads(path.read_text(encoding="utf-8"))))
        return json.loads(path.read_text(encoding="utf-8"))
    rows = fetcher()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    logger.info("已抓取 {}.json（{} 条）", name, len(rows))
    return rows


async def main_async(refresh: bool) -> int:
    client = CpicClient()
    try:
        drugs = _load_or_fetch("drugs", client.drugs, refresh)
        pairs = _load_or_fetch("pairs", client.pairs, refresh)
        recommendations = _load_or_fetch("recommendations", client.recommendations, refresh)
    finally:
        client.close()

    my_pairs, my_recs, genes = filter_for_drugs(
        pairs=pairs, recommendations=recommendations, drugs=drugs, drug_names=DRUG_NAMES
    )

    client = CpicClient()
    try:
        diplotypes = _load_or_fetch("diplotypes", lambda: client.diplotypes(genes), refresh)
        alleles = _load_or_fetch("alleles", lambda: client.alleles(genes), refresh)
        gene_results = _load_or_fetch("gene_results", lambda: client.gene_results(genes), refresh)
    finally:
        client.close()

    engine = make_engine()
    # 这三张是 CPIC 的派生表，每次整体重建：避免表结构演进时（例如列宽不足）
    # 出现"建表语句没变、旧表还是窄列"的坑。
    cpic_tables = [
        CpicPair.__table__, CpicRecommendation.__table__,
        CpicDiplotype.__table__, CpicGeneResult.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(lambda c: Base.metadata.drop_all(c, tables=cpic_tables, checkfirst=True))
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=cpic_tables))

    factory = make_session_factory(engine)
    async with factory() as session:
        for model in (CpicPair, CpicRecommendation, CpicDiplotype, CpicGeneResult):
            await session.execute(delete(model))

        session.add_all([
            CpicPair(
                pairid=int(p["pairid"]),
                genesymbol=p.get("genesymbol"),
                drugid=p.get("drugid"),
                guidelineid=p.get("guidelineid"),
                cpiclevel=p.get("cpiclevel"),
                pgxtesting=p.get("pgxtesting"),
                usedforrecommendation=int(bool(p.get("usedforrecommendation"))),
            )
            for p in my_pairs
        ])
        session.add_all([
            CpicRecommendation(
                id=int(r["id"]),
                guidelineid=r.get("guidelineid"),
                drugid=r.get("drugid"),
                classification=(r.get("classification") or "").strip() or None,
                phenotypes=r.get("phenotypes"),
                allelestatus=r.get("allelestatus"),
                implications=r.get("implications"),
                drugrecommendation=r.get("drugrecommendation"),
                activityscore=r.get("activityscore"),
                population=(r.get("population") or "").strip() or None,
                comments=r.get("comments"),
            )
            for r in my_recs
        ])
        session.add_all([
            CpicDiplotype(
                genesymbol=d.get("genesymbol"),
                diplotype=d.get("diplotype"),
                generesult=d.get("generesult"),
                totalactivityscore=str(d.get("totalactivityscore")) if d.get("totalactivityscore") is not None else None,
                ehrpriority=d.get("ehrpriority"),
                consultationtext=d.get("consultationtext"),
                description=d.get("description"),
            )
            for d in diplotypes
        ])
        session.add_all([
            CpicGeneResult(
                id=int(g["id"]),
                genesymbol=g.get("genesymbol"),
                result=g.get("result"),
                activityscore=str(g.get("activityscore")) if g.get("activityscore") is not None else None,
                ehrpriority=g.get("ehrpriority"),
                consultationtext=g.get("consultationtext"),
            )
            for g in gene_results
        ])
        await session.commit()

    async with factory() as session:
        counts = {
            "cpic_pair": (await session.scalar(select(func.count()).select_from(CpicPair))) or 0,
            "cpic_recommendation": (await session.scalar(select(func.count()).select_from(CpicRecommendation))) or 0,
            "cpic_diplotype": (await session.scalar(select(func.count()).select_from(CpicDiplotype))) or 0,
            "cpic_gene_result": (await session.scalar(select(func.count()).select_from(CpicGeneResult))) or 0,
        }
        by_gene = (await session.execute(
            select(CpicPair.genesymbol, func.count()).group_by(CpicPair.genesymbol).order_by(func.count().desc())
        )).all()
        by_class = (await session.execute(
            select(CpicRecommendation.classification, func.count()).group_by(CpicRecommendation.classification)
        )).all()

    logger.info("CPIC 入库校验：{}", counts)
    logger.info("按基因分布（前 8）：{}", by_gene[:8])
    logger.info("推荐强度分布：{}", by_class)
    logger.info("allele 快照 {} 条（用于功能状态查询，暂不入库）", len(alleles))
    await engine.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取并入库 CPIC 结构化数据")
    parser.add_argument("--refresh", action="store_true", help="忽略本地快照，重新抓取")
    args = parser.parse_args()
    return asyncio.run(main_async(args.refresh))


if __name__ == "__main__":
    raise SystemExit(main())
