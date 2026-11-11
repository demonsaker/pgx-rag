"""证据卡覆盖度与一致性巡检。

对 50 个 CPIC 基因-药对逐个生成证据卡，统计：
* 有推荐的覆盖率（有多少对能查到该表型的推荐）
* 一致性判定分布（一致 / 指南更严格 / 说明书更保守 / 说明书未收录该基因）
* 「说明书未收录该基因」清单 —— 这不是 bug，而是双源存在的理由

    uv run python -m app.scripts.eval_card
    uv run python -m app.scripts.eval_card --write-report
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from app.clients.mysql import make_engine, make_session_factory
from app.conf.app_config import PROJECT_ROOT, get_abs_path
from app.core.logger import logger
from app.models.orm import CpicGeneResult, CpicPair, CpicRecommendation
from app.services.evidence_card import EvidenceCardService

# 每个基因挑一个有代表性的表型来巡检
PHENOTYPE_PRIORITY = [
    "Poor Metabolizer", "Decreased Function", "Poor Function",
    "*15:02 positive", "*57:01 positive", "*58:01 positive",
    "Intermediate Metabolizer", "Normal Metabolizer",
]


def pick_phenotype(values: set[str]) -> str | None:
    for candidate in PHENOTYPE_PRIORITY:
        if candidate in values:
            return candidate
    return sorted(values)[0] if values else None


async def load_cases() -> list[dict]:
    engine = make_engine()
    factory = make_session_factory(engine)
    try:
        async with factory() as session:
            pairs = (await session.execute(select(CpicPair))).scalars().all()
            recs = (await session.execute(select(CpicRecommendation))).scalars().all()
            results = (await session.execute(select(CpicGeneResult))).scalars().all()
    finally:
        await engine.dispose()

    drugs = json.loads(get_abs_path("data/raw/cpic/drugs.json").read_text(encoding="utf-8"))
    id2name = {d["drugid"]: str(d.get("name", "")).lower() for d in drugs}

    by_pair: dict[tuple[str, str], set[str]] = {}
    for rec in recs:
        for gene, pheno in (rec.phenotypes or {}).items():
            if pheno:
                by_pair.setdefault((id2name.get(rec.drugid, ""), gene), set()).add(pheno)

    # HLA 类药没有 phenotypes，表型要从 gene_result 拿（如 "*57:01 positive"）
    by_gene_result: dict[str, set[str]] = {}
    for row in results:
        if row.result:
            by_gene_result.setdefault(row.genesymbol, set()).add(row.result)

    cases = []
    for pair in pairs:
        drug = id2name.get(pair.drugid, "")
        if not drug:
            continue
        values = by_pair.get((drug, pair.genesymbol), set())
        phenotype = pick_phenotype(values)
        if not phenotype:
            # 从 gene_result 里挑一个阳性结果（HLA 场景）
            candidates = by_gene_result.get(pair.genesymbol, set())
            positives = sorted(p for p in candidates if "positive" in p.lower())
            phenotype = positives[0] if positives else None
        cases.append({
            "drug": drug,
            "gene": pair.genesymbol,
            "cpiclevel": pair.cpiclevel,
            "pgxtesting": pair.pgxtesting,
            "phenotypes": values,
            "phenotype": phenotype,
        })
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description="证据卡巡检")
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    cases = asyncio.run(load_cases())
    if args.limit:
        cases = cases[: args.limit]

    service = EvidenceCardService()
    rows: list[dict] = []
    for case in cases:
        if not case["phenotype"]:
            rows.append({**case, "verdict": "无按表型的推荐", "label_gene": "-", "recs": 0})
            continue
        try:
            card = service.build(case["drug"], case["phenotype"], gene=case["gene"])
        except Exception as exc:  # noqa: BLE001 - 巡检不因单条失败中断
            logger.warning("{} {} 生成失败：{}", case["drug"], case["gene"], exc)
            rows.append({**case, "verdict": f"失败({type(exc).__name__})", "label_gene": "-", "recs": 0})
            continue
        label_has_gene = card.gene_in_label
        rows.append({
            **case,
            "verdict": card.consistency.get("verdict"),
            "label_gene": "有" if label_has_gene else "无",
            "recs": len(card.recommendations),
            "cpic_reason": card.consistency.get("cpic_reason"),
            "label_reason": card.consistency.get("label_reason"),
        })
        logger.info("{:<16} {:<8} {:<16} -> {}（说明书含该基因={}）",
                    case["drug"], case["gene"], case["phenotype"], rows[-1]["verdict"], rows[-1]["label_gene"])

    verdicts = Counter(r["verdict"] for r in rows)
    with_recs = sum(1 for r in rows if r.get("recs"))
    missing_gene = [r for r in rows if r["verdict"] == "说明书未收录该基因"]

    print("\n" + "=" * 92)
    print(f"共 {len(rows)} 个基因-药对；其中 {with_recs} 个能查到该表型的 CPIC 推荐（{with_recs/len(rows):.0%}）")
    print(f"一致性判定分布：{dict(verdicts)}")
    print(f"\n「说明书未收录该基因」{len(missing_gene)} 例（这些只能靠指南侧回答）：")
    for r in missing_gene:
        print(f"   {r['drug']:<16} {r['gene']:<8} CPIC={r['cpiclevel']}  表型={r['phenotype']}")
    print("=" * 92)

    if args.write_report:
        _write_report(rows, verdicts, with_recs)
    return 0


def _write_report(rows: list[dict], verdicts: Counter, with_recs: int) -> None:
    lines = [
        "# 阶段 2 · 证据卡巡检报告",
        "",
        f"- 基因-药对：{len(rows)} 个",
        f"- 能查到对应表型推荐的：{with_recs} 个（{with_recs/len(rows):.0%}）",
        f"- 一致性分布：{dict(verdicts)}",
        "",
        "## 判定口径",
        "",
        "行动等级由确定性规则得出（指南推荐原文 / 说明书原文的关键词 → 0 标准剂量 / 2 调整或监测 / 3 避免或禁用）：",
        "",
        "- 两侧等级相同 → **一致**",
        "- 指南更严 → **指南更严格**；差 ≥2 → **存在明显差异**（建议人工复核）",
        "- 说明书更严 → **说明书更保守**",
        "- 说明书段落里没有该基因 → **说明书未收录该基因**（双源存在的理由）",
        "",
        "## 明细",
        "",
        "| 药物 | 基因 | CPIC | 检测建议 | 巡检表型 | 一致性 | 说明书含该基因 | 推荐条数 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['drug']} | {r['gene']} | {r['cpiclevel'] or '-'} | {r['pgxtesting'] or '-'} | "
            f"{r['phenotype'] or '-'} | {r['verdict']} | {r['label_gene']} | {r.get('recs', 0)} |"
        )
    path = PROJECT_ROOT / "reports" / "stage2_evidence_card.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告：{path}")


if __name__ == "__main__":
    raise SystemExit(main())
