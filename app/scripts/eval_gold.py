"""核心评测：RAG 答案 vs CPIC 标准答案（方向一致率）。

定位说明
--------
RAG 是主体产出（通俗、指令清晰、逐句引用），CPIC 查表是**标准答案**，用来给医生对照、
也用来给系统打分。所以评测的核心问题是：

    **系统给出的处置方向，与 CPIC 官方推荐是否一致？**

做法：
1. 从 CPIC 机械生成题目（药 × 基因 × 表型，必要时带场景）——**金标准来自公开权威数据，不是我手写**；
2. 把题目交给 RAG 链路（检索 + 生成，不看 CPIC 表）；
3. 把答案里的处置方向抽出来（避免 / 调整或监测 / 标准剂量 / 未提及）；
4. 与 CPIC 推荐的方向比对，统计一致率，并列出**失败案例**。

    uv run python -m app.scripts.eval_gold
    uv run python -m app.scripts.eval_gold --limit 20 --write-report
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from app.clients.mysql import make_engine, make_session_factory
from app.conf.app_config import PROJECT_ROOT, get_abs_path
from app.core.logger import logger
from app.models.orm import CpicGeneResult, CpicPair, CpicRecommendation
from app.services.answer_judge import DirectionJudge
from app.services.evidence_card import ACTION_AVOID, ACTION_CAUTION, ACTION_OK, classify_cpic_action
from app.services.generation_service import GenerationService

GOLD_PATH = Path("data/eval/gold_set.jsonl")

# 从中文/英文答案里抽取处置方向。
# 注意词序与歧义：「考虑替代」「换用」属于"调整"档，不能被 `替代` 这种词抢到"避免"档里
# （第一版就是把「考虑替代治疗」判成了"避免"，导致一致率被严重低估）。
_AVOID_WORDS = ("避免使用", "避免", "禁用", "禁忌", "不应使用", "不推荐使用", "不建议使用",
                "contraindicated", "not recommended", "do not use", "must not")
_CAUTION_WORDS = ("考虑替代", "考虑换用", "考虑其他", "替代", "换用", "更换", "减量", "降低剂量",
                  "调整剂量", "剂量调整", "减半", "监测", "谨慎", "consider", "monitor", "reduce", "titrate")
_OK_WORDS = ("标准剂量", "常规剂量", "按常规", "无需调整", "可以使用", "standard dose", "no adjustment")


@dataclass
class GoldItem:
    drug: str
    gene: str
    phenotype: str
    context: str | None
    gold_action: int | None
    gold_text: str
    gold_class: str | None
    cpic_level: str | None
    pgx_testing: str | None

    @property
    def question(self) -> str:
        ctx = f"（临床场景：{self.context}）" if self.context and self.context.lower() != "general" else ""
        return f"患者 {self.gene} 检测结果为「{self.phenotype}」，能否使用 {self.drug}？{ctx}"

    def to_dict(self) -> dict:
        return {
            "drug": self.drug, "gene": self.gene, "phenotype": self.phenotype,
            "context": self.context, "question": self.question,
            "gold_action": self.gold_action, "gold_text": self.gold_text,
            "gold_class": self.gold_class, "cpic_level": self.cpic_level, "pgx_testing": self.pgx_testing,
        }


def extract_answer_action(text: str) -> tuple[int | None, str]:
    """从 RAG 答案里抽处置方向。

    优先看「结论」那一句：整篇扫描会被"依据"里其他表型（如"纯合缺陷者禁用"）带偏，
    而系统真正给出的处置方向在结论里。
    """
    match = re.search(r"结论[:：]\s*(.+)", text)
    target = match.group(1) if match else text
    for candidate in (target, text):
        lower = candidate.lower()
        for words, level, label in (
            (_AVOID_WORDS, ACTION_AVOID, "避免/禁用"),
            (_CAUTION_WORDS, ACTION_CAUTION, "调整/监测"),
            (_OK_WORDS, ACTION_OK, "标准剂量"),
        ):
            hit = next((w for w in words if w in lower), None)
            if hit:
                return level, f"{label}（命中「{hit}」）"
    return None, "未给出明确处置方向"


async def load_gold_items(limit: int | None = None) -> list[GoldItem]:
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
    level_map = {(id2name.get(p.drugid, ""), p.genesymbol): (p.cpiclevel, p.pgxtesting) for p in pairs}

    items: list[GoldItem] = []
    seen: set[tuple] = set()
    for rec in recs:
        drug = id2name.get(rec.drugid, "")
        if not drug:
            continue
        for gene, value in (rec.phenotypes or {}).items():
            if not value or drug not in {n for n in id2name.values()}:
                continue
            key = (drug, gene, value, rec.population)
            if key in seen:
                continue
            seen.add(key)
            action, _ = classify_cpic_action(rec.drugrecommendation or "")
            level, testing = level_map.get((drug, gene), (None, None))
            items.append(GoldItem(
                drug=drug, gene=gene, phenotype=value, context=rec.population,
                gold_action=action, gold_text=rec.drugrecommendation or "",
                gold_class=rec.classification, cpic_level=level, pgx_testing=testing,
            ))
        # HLA 类：phenotypes 为空，用 allelestatus。
        # 注意：一行 allelestatus 可能同时含多个基因（如卡马西平 HLA-A + HLA-B），
        # 若其它基因是阳性，这一行给出的处置是"因别的基因而禁用"，
        # 不能拿来当本基因阴性的金标准，否则会把"阴性可用"错标成"禁用"。
        for gene, value in (rec.allelestatus or {}).items():
            if not value or "no " in value.lower():
                continue
            others = {
                g: v for g, v in (rec.allelestatus or {}).items()
                if g != gene and v and "positive" in str(v).lower()
            }
            if others:
                continue
            key = (drug, gene, value, rec.population)
            if key in seen:
                continue
            seen.add(key)
            action, _ = classify_cpic_action(rec.drugrecommendation or "")
            level, testing = level_map.get((drug, gene), (None, None))
            items.append(GoldItem(
                drug=drug, gene=gene, phenotype=value, context=rec.population,
                gold_action=action, gold_text=rec.drugrecommendation or "",
                gold_class=rec.classification, cpic_level=level, pgx_testing=testing,
            ))

    # 优先保留有明确方向的（无推荐的不适合做方向比对）；
    # 同时剔除「No Result / Indeterminate」这类没有临床处置意义的表型，
    # 否则金标准会有一半题目在问"没有结果该怎么办"。
    skip_phenotypes = {"no result", "indeterminate", "unknown"}
    usable = [
        i for i in items
        if i.gold_action is not None and i.phenotype.lower().strip() not in skip_phenotypes
    ]
    usable.sort(key=lambda i: (i.drug, i.gene, i.phenotype))
    return usable[:limit] if limit else usable


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG 答案 vs CPIC 标准答案")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--save-gold", action="store_true", help="把金标准集落盘")
    parser.add_argument("--judge", choices=["llm", "rule"], default="llm", help="方向判定方式")
    parser.add_argument(
        "--holdout-drugs", default=None,
        help="留出实验：把这些药的 CPIC 切片从语料里剔除后再考（逗号分隔）",
    )
    parser.add_argument("--no-exclude", action="store_true", help="留出实验的对照组：题目相同但语料不剔除")
    args = parser.parse_args()

    items = asyncio.run(load_gold_items(args.limit))
    if args.save_gold:
        GOLD_PATH.parent.mkdir(parents=True, exist_ok=True)
        with GOLD_PATH.open("w", encoding="utf-8") as fh:
            for item in items:
                fh.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")
        logger.info("金标准集已落盘：{} 条 -> {}", len(items), GOLD_PATH)

    service = GenerationService()
    judge = DirectionJudge() if args.judge == "llm" else None

    # ---- 留出实验：剔除某些药的 CPIC 切片，只考这些药
    excluded: set[str] | None = None
    if args.holdout_drugs:
        holdout = {d.strip().lower() for d in args.holdout_drugs.split(",") if d.strip()}
        items = [item for item in items if item.drug in holdout]
        if not args.no_exclude:
            excluded = {
                chunk.chunk_id for chunk in service.retrieval.chunks.all()
                if chunk.source == "cpic" and chunk.drug in holdout
            }
        print(f"留出实验：药物={sorted(holdout)} 题目={len(items)} 剔除切片={len(excluded or [])}")

    rows: list[dict] = []
    agree = disagree = unclear = refused = 0

    for item in items:
        answer = service.answer(item.question, exclude=excluded)
        if answer.refused:
            refused += 1
            verdict = "拒答（未回答）"
            answer_action, reason = None, "系统拒答"
        else:
            if judge is not None:
                judged_result = judge.judge(item.question, answer.answer)
                answer_action = judged_result["action"]
                reason = (
                    f"LLM 判定：{judged_result.get('rationale', '')}"
                    if answer_action is not None
                    else "LLM 判为未给出明确方向"
                )
            else:
                answer_action, reason = extract_answer_action(answer.answer)
            if answer_action is None:
                unclear += 1
                verdict = "方向不明"
            elif answer_action == item.gold_action:
                agree += 1
                verdict = "一致"
            else:
                disagree += 1
                verdict = "不一致"
        rows.append({
            "question": item.question, "drug": item.drug, "gene": item.gene,
            "phenotype": item.phenotype, "context": item.context,
            "gold_action": item.gold_action, "gold_text": item.gold_text,
            "answer_action": answer_action, "verdict": verdict, "reason": reason,
            "answer": answer.answer[:400], "citations": len(answer.citations),
        })
        logger.info("{:<12} {:<8} {:<24} gold={} answer={} -> {}",
                    item.drug, item.gene, item.phenotype[:22], item.gold_action, answer_action, verdict)

    total = len(rows)
    judged = agree + disagree
    print("\n" + "=" * 100)
    print(f"{'药物':<14}{'基因':<9}{'表型':<30}{'金标准':<8}{'系统':<8}{'判定'}")
    print("-" * 100)
    for row in rows:
        print(f"{row['drug']:<14}{row['gene']:<9}{row['phenotype'][:28]:<30}"
              f"{str(row['gold_action']):<8}{str(row['answer_action']):<8}{row['verdict']}")
    print("-" * 100)
    print(f"金标准题数：{total}（其中 CPIC 有明确方向的 {judged + unclear + refused} 条）")
    print(f"一致 {agree} · 不一致 {disagree} · 方向不明 {unclear} · 拒答 {refused}")
    print(f"**方向一致率（一致 / (一致+不一致)）：{(agree / judged if judged else 0):.1%}**")
    print("=" * 100)

    failures = [r for r in rows if r["verdict"] in ("不一致", "方向不明")]
    if failures:
        print(f"\n失败案例（前 5 条，共 {len(failures)} 条）：")
        for row in failures[:5]:
            print(f"\n  问：{row['question']}")
            print(f"  CPIC：{row['gold_text'][:100]}")
            print(f"  系统：{row['reason']} | 引用 {row['citations']} 条")
            print(f"  答案片段：{row['answer'][:160]}")

    if args.write_report:
        _write_report(rows, agree, disagree, unclear, refused)
    return 0 if disagree == 0 else 1


def _write_report(rows: list[dict], agree: int, disagree: int, unclear: int, refused: int) -> None:
    judged = agree + disagree
    lines = [
        "# 核心评测 · RAG 答案 vs CPIC 标准答案",
        "",
        f"- 题量：{len(rows)}",
        f"- 一致 {agree} · 不一致 {disagree} · 方向不明 {unclear} · 拒答 {refused}",
        f"- **方向一致率：{(agree / judged if judged else 0):.1%}**",
        "",
        "## 口径",
        "",
        "- 题目由 CPIC 机械生成（药 × 基因 × 表型 × 场景），金标准取自 CPIC 推荐原文；",
        "- RAG 链路不看 CPIC 表，只检索说明书并生成答案；",
        "- 处置方向按关键词归一为三档：避免/禁用(3)、调整/监测(2)、标准剂量(0)；",
        "- 「方向不明」= 答案没有给出可判定的处置语，单独统计、不计入一致率分母。",
        "",
        "## 明细",
        "",
        "| 药物 | 基因 | 表型 | 场景 | 金标准方向 | 系统方向 | 判定 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['drug']} | {r['gene']} | {r['phenotype']} | {r['context'] or '-'} | "
            f"{r['gold_action']} | {r['answer_action']} | {r['verdict']} |"
        )
    failures = [r for r in rows if r["verdict"] in ("不一致", "方向不明")]
    if failures:
        lines += ["", "## 失败案例", ""]
        for r in failures[:8]:
            lines += [f"### {r['question']}", "", f"- CPIC：{r['gold_text']}", f"- 系统：{r['reason']}",
                      "", "```", r["answer"], "```", ""]
    path = PROJECT_ROOT / "reports" / "eval_gold.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告：{path}")


if __name__ == "__main__":
    raise SystemExit(main())
