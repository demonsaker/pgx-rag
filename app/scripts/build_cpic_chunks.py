"""把 CPIC 推荐文本转成「可检索的语料」，与说明书切片放在同一套索引里。

为什么需要这一步
----------------
实测：只用说明书做 RAG，对「患者是 Intermediate Metabolizer 能不能用某药」这类问题，
有 56% 会回答"说明书未定义该表型"——因为 FDA 标签不使用 CPIC 的表型命名。
同义词扩展只能把方向一致率从 56.2% 提到 60.0%，治标不治本。

真正的解法是让 RAG 也能检索到**指南原文**：这样答案可以同时引用
「CPIC 说 Avoid」和「说明书黑框警告说 diminished」，而不是被困在标签措辞里。

产物：data/corpus/cpic_chunks.jsonl（schema 与 chunks.jsonl 一致，
`source=cpic`、`section_priority=1`，便于检索时权重最高）。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.clients.mysql import make_engine, make_session_factory
from app.conf.app_config import get_abs_path
from app.core.logger import logger
from app.core.text import est_tokens, slug
from app.models.orm import CpicRecommendation

OUT_PATH = Path("data/corpus/cpic_chunks.jsonl")


def _chunk_text(drug: str, gene: str, phenotype: str, rec) -> str:
    parts = [
        f"CPIC guideline recommendation for {drug} in {gene} {phenotype}.",
        f"Population: {rec.population or 'general'}.",
        f"Recommendation strength: {rec.classification or 'unspecified'}.",
        f"Recommendation: {rec.drugrecommendation}",
    ]
    implication = (rec.implications or {}).get(gene)
    if implication:
        parts.append(f"Clinical implication: {implication}")
    activity = (rec.activityscore or {}).get(gene)
    if activity:
        parts.append(f"Activity score: {activity}.")
    return " ".join(p for p in parts if p and "None" not in p)


async def build() -> list[dict]:
    engine = make_engine()
    factory = make_session_factory(engine)
    try:
        async with factory() as session:
            recs = (await session.execute(select(CpicRecommendation))).scalars().all()
    finally:
        await engine.dispose()

    drugs = {d["drugid"]: str(d.get("name", "")).lower()
             for d in json.loads(get_abs_path("data/raw/cpic/drugs.json").read_text(encoding="utf-8"))}

    chunks: list[dict] = []
    counter: dict[str, int] = {}
    for rec in recs:
        drug = drugs.get(rec.drugid, "")
        if not drug:
            continue
        phenotypes = rec.phenotypes or {}
        alleles = rec.allelestatus or {}
        genes = [g for g in phenotypes if phenotypes[g]] or [g for g in alleles if alleles[g]]
        if not genes:
            continue
        for gene in genes:
            phenotype = phenotypes.get(gene) or alleles.get(gene) or ""
            if not phenotype:
                continue
            key = f"{drug}-{gene}"
            counter[key] = counter.get(key, 0) + 1
            chunk_id = f"cpic-{drug}-{slug(gene)}-{slug(phenotype)[:24]}-{counter[key]:02d}"
            text = _chunk_text(drug, gene, phenotype, rec)
            chunks.append({
                "chunk_id": chunk_id,
                "source": "cpic",
                "drug": drug,
                "drug_class": "",
                "set_id": None,
                "section": "cpic_recommendation",
                "section_label": "CPIC 指南推荐",
                "section_priority": 1,
                "kind": "text",
                "heading": f"{drug} — CPIC {gene} {phenotype}",
                "text": text,
                "pgx": {
                    "genes": [gene],
                    "phenotypes": [phenotype.lower()] if "metabolizer" in phenotype.lower() else [],
                    "alleles": [],
                    "score": 5,
                    "is_pgx": True,
                },
                "chars": len(text),
                "est_tokens": est_tokens(text),
                "evidence": {
                    "source": "cpic",
                    "guideline_id": rec.guidelineid,
                    "classification": rec.classification,
                    "population": (rec.population or "").strip() or "general",
                    "phenotype": phenotype,
                    "gene": gene,
                    "url": "https://cpicpgx.org/genes-drugs/",
                },
            })
    return chunks


def main() -> int:
    chunks = asyncio.run(build())
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    logger.info("CPIC 语料已生成：{} 条 -> {}", len(chunks), OUT_PATH)

    by_drug: dict[str, int] = {}
    for chunk in chunks:
        by_drug[chunk["drug"]] = by_drug.get(chunk["drug"], 0) + 1
    logger.info("按药物：{}", sorted(by_drug.items(), key=lambda kv: -kv[1])[:8])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
