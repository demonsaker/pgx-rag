"""证据卡：把「药 + 基因型/表型 + 临床场景」变成一张可核对的卡片。

三层结构（专业侧的核心产出）：

    ① 指南侧（CPIC）   推荐原文 + 强度(Strong/Moderate/Optional) + 检测建议 + 表型风险
    ② 说明书侧（FDA）  相关段落原文 + 章节 + 生效日期 + set_id（可回溯）
    ③ 一致性判定       一致 / 指南更严格 / 说明书更保守 / 冲突 / 说明书未收录该基因

为什么要有第③层：药师审方最怕的不是"没依据"，而是"两份依据说法不一样"。
把差异显式标出来，比给一句看似权威的结论有用得多。

一致性判定是**确定性规则**（关键词 → 行动等级），不经过大模型——
这样结论可复核，也不会因为模型措辞变化而漂移。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select

from app.clients.mysql import make_engine, make_session_factory
from app.conf.app_config import get_abs_path
from app.core.logger import logger
from app.entities.drugs import DRUG_INDEX
from app.models.orm import CpicGeneResult, CpicPair, CpicRecommendation
from app.services.retrieval_service import RetrievalService

# 行动等级：数字越大越"不建议用"
ACTION_NONE, ACTION_OK, ACTION_CAUTION, ACTION_AVOID = None, 0, 2, 3

_CPIC_AVOID = ("avoid", "do not use", "contraindicated", "not recommended")
_CPIC_CAUTION = ("alternative", "reduce", "decrease", "increase", "limit", "monitor",
                 "titrate", "adjust", "consider")
# CPIC 表达"标准剂量"的写法很杂：standard dose / standard dosing guidelines /
# recommended starting dose / no dosage adjustment necessary …
# 只认一种写法会把大量"标准剂量"错判成"需要调整"（实测占不一致的 17/21）。
_CPIC_OK = (
    "standard dose", "standard dosing", "standard starting dose", "standard initial dose",
    "standard dosing guidelines", "usual dose", "typical dose", "recommended starting dose",
    "no dosage adjustment", "no dose adjustment", "no adjustment", "per standard", "use as usual",
)
_NO_ADJUST = ("no dosage adjustment", "no dose adjustment", "no adjustment")


def _first_sentence(text: str) -> str:
    """CPIC 推荐的主处置通常在第一句；后面的句子多是条件补充。"""
    match = re.match(r"(.+?[.!?])\s", text.strip() + " ")
    return match.group(1) if match else text.strip()


def classify_cpic_action(text: str) -> tuple[int | None, str]:
    """把 CPIC 推荐原文归一成行动等级。

    判定顺序（踩过两轮坑后定的）：
    1. "no dosage adjustment" 这类显式否定优先 → 标准剂量；
    2. 明确的避免/禁用 → 避免；
    3. 第一句里出现**词边界**的调整词（reduced/alternative/titrate…）→ 调整；
       用词边界是为了避免 `considering` 被当成 `consider`、
       以及 `reduced ... (30-80% of standard starting dose)` 里的 standard 抢走判定；
    4. 最后才认标准剂量表述。
    """
    if not text:
        return ACTION_NONE, "无推荐文本"
    lower = text.lower()
    if "no recommendation" in lower:
        return ACTION_NONE, "CPIC 未给出推荐"

    no_adjust = _first_hit(lower, _NO_ADJUST)
    if no_adjust:
        return ACTION_OK, f"无需调整（命中「{no_adjust}」）"

    lead = _first_sentence(text)
    lead_lower = lead.lower()

    def has(patterns: tuple[str, ...], target: str) -> str | None:
        for word in patterns:
            if re.search(rf"\b{re.escape(word)}", target):
                return word
        return None

    # "considering" 不是"考虑调整"（如 "If considering clopidogrel, use at standard dose"），
    # 用负向前瞻把它排除掉；reduc/decreas/increas 则保留词干匹配（reduced/dose reduction 都算）。
    _CAUTION_RE = re.compile(
        r"\b(alternativ|reduc|decreas|increas|titrat|adjust|monitor|limit|consider(?!ing))"
    )

    avoid_hit = has(_CPIC_AVOID, lead_lower)
    if avoid_hit:
        return ACTION_AVOID, f"避免/禁用（命中「{avoid_hit}」）"

    caution_match = _CAUTION_RE.search(lead_lower)
    if caution_match:
        return ACTION_CAUTION, f"考虑替代/调整剂量/监测（命中「{caution_match.group(1)}」）"

    ok_hit = _first_hit(lead_lower, _CPIC_OK) or _first_hit(lower, _CPIC_OK)
    if ok_hit:
        return ACTION_OK, f"标准剂量（命中「{ok_hit}」）"
    return ACTION_NONE, "无法判定行动等级"

_LABEL_AVOID = ("contraindicated", "should not be", "must not be", "do not administer", "avoid")
_LABEL_CAUTION = ("consider an alternative", "dose reduction", "reduce the dose", "reduced dose",
                  "decrease the dose", "monitor", "diminished", "reduced antiplatelet", "reduced response",
                  "decreased efficacy", "lower exposure", "reduced exposure", "discontinue")
_LABEL_OK = ("no dosage adjustment", "no dose adjustment", "standard dose", "usual dose")

# 基因不在说明书里时，用「该药已知的风险词」去取通用剂量/警告段，
# 至少让药师看到"这个药本身怎么警告的"，而不是拿无关段落硬凑。
RISK_HINTS = {
    "SLCO1B1": "myopathy rhabdomyolysis muscle",
    "CYP2C9": "bleeding INR anticoagulation dose",
    "VKORC1": "INR dose initiation",
    "CYP2C19": "reduced efficacy diminished response",
    "CYP2D6": "ultrarapid metabolism respiratory depression",
    "TPMT": "myelosuppression bone marrow",
    "NUDT15": "myelosuppression bone marrow",
    "DPYD": "toxicity deficiency",
    "HLA-B": "rash hypersensitivity Stevens-Johnson",
    "HLA-A": "rash hypersensitivity",
    "CYP3A5": "dose trough concentration",
    "CYP4F2": "dose INR",
}


def _first_hit(text: str, phrases: tuple[str, ...]) -> str | None:
    lower = text.lower()
    for phrase in phrases:
        if phrase in lower:
            return phrase
    return None


_ALLELE_RE = re.compile(r"\*\s?[\d:]+")


def allele_matches(user_input: str, cpic_label: str) -> bool:
    """把用户给的 HLA 结论和 CPIC 的 `allelestatus` 对齐。

    两边的写法都不统一：
      用户可能写 `*57:01 positive` / `HLA-B*5701 阳性` / `Positive`
      CPIC 写 `HLA-B*57:01 positive`
    所以按「等位基因编号（忽略冒号）+ 阴阳性」两个维度比对。
    """
    user = (user_input or "").lower().strip()
    label = (cpic_label or "").lower().strip()
    if not user or not label:
        return False
    if user == label:
        return True

    def polarity(text: str) -> str | None:
        if "positive" in text or "阳性" in text:
            return "positive"
        if "negative" in text or "阴性" in text:
            return "negative"
        return None

    user_polarity, label_polarity = polarity(user), polarity(label)
    if user_polarity and label_polarity and user_polarity != label_polarity:
        return False

    user_allele = _ALLELE_RE.search(user)
    label_allele = _ALLELE_RE.search(label)
    if user_allele and label_allele:
        normalize = lambda s: s.replace(" ", "").replace(":", "")  # noqa: E731
        if normalize(user_allele.group(0)) != normalize(label_allele.group(0)):
            return False
        return True

    # 只给了阴阳性（没给等位基因）时，按阴阳性判断
    if user in ("positive", "negative", "阳性", "阴性"):
        return user_polarity == label_polarity
    return False


def classify_label_action(text: str, gene: str) -> tuple[int | None, str]:
    if gene and gene.lower() not in text.lower():
        return ACTION_NONE, f"说明书段落未出现 {gene}"
    for level, phrases, label in (
        (ACTION_AVOID, _LABEL_AVOID, "禁忌"),
        (ACTION_CAUTION, _LABEL_CAUTION, "警告/调整/监测"),
        (ACTION_OK, _LABEL_OK, "无需调整"),
    ):
        hit = _first_hit(text, phrases)
        if hit:
            return level, f"{label}（命中「{hit}」）"
    return ACTION_NONE, "说明书段落未给出明确行动"


@dataclass
class EvidenceCard:
    drug: str
    gene: str
    phenotype: str
    context: str | None = None

    cpic_level: str | None = None
    pgx_testing: str | None = None
    phenotype_risk: str | None = None
    phenotype_note: str | None = None
    recommendations: list[dict] = field(default_factory=list)
    label_chunks: list[dict] = field(default_factory=list)
    gene_in_label: bool = True
    label_note: str | None = None
    consistency: dict = field(default_factory=dict)
    detection: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "query": {"drug": self.drug, "gene": self.gene, "phenotype": self.phenotype, "context": self.context},
            "cpic": {
                "level": self.cpic_level,
                "pgx_testing": self.pgx_testing,
                "phenotype_risk": self.phenotype_risk,
                "phenotype_note": self.phenotype_note,
                "recommendations": self.recommendations,
            },
            "label": {"chunks": self.label_chunks, "gene_in_label": self.gene_in_label, "note": self.label_note},
            "consistency": self.consistency,
            "detection": self.detection,
            "sources": self.sources,
        }

    def render(self) -> str:
        lines: list[str] = []
        head = f"【证据卡】{self.drug} · {self.gene} · {self.phenotype}"
        if self.context:
            head += f" · 场景={self.context}"
        lines += ["=" * 98, head, "=" * 98]

        lines.append(f"① 指南侧（CPIC）  证据等级={self.cpic_level or '未收录'}  "
                     f"检测建议={self.pgx_testing or '未标注'}")
        if self.phenotype_risk:
            lines.append(f"   表型风险：{self.phenotype_risk}")
        if self.phenotype_note:
            lines.append(f"   表型解读：{self.phenotype_note[:180]}")
        if not self.recommendations:
            lines.append("   ⚠ 该表型在 CPIC 中没有对应推荐（或该药只有剂量表，无按表型推荐）")
        allele_states = {r.get("allelestatus") for r in self.recommendations if r.get("allelestatus")}
        if allele_states:
            lines.append(f"   等位基因状态：{'; '.join(sorted(allele_states))}")
        for rec in self.recommendations:
            ctx = rec.get("population") or "未标注场景"
            lines.append(f"   [{ctx:<22}] {rec.get('classification'):<9} {rec.get('drugrecommendation')}")
            impact = (rec.get("implications") or {}).get(self.gene)
            if impact:
                lines.append(f"      影响：{impact[:150]}")

        lines.append("")
        lines.append(f"② 说明书侧（FDA SPL）  命中 {len(self.label_chunks)} 段"
                     + ("（降级：通用段落）" if not self.gene_in_label else ""))
        if self.label_note:
            lines.append(f"   ⚠ {self.label_note}")
        for chunk in self.label_chunks[:4]:
            lines.append(f"   · {chunk['section_label']}（{chunk['effective_date']}） {chunk['chunk_id']}")
            lines.append(f"     {chunk['snippet'][:170]}")

        lines.append("")
        verdict = self.consistency.get("verdict", "未判定")
        lines.append(f"③ 一致性：{verdict}")
        lines.append(f"   指南侧：{self.consistency.get('cpic_reason')}")
        lines.append(f"   说明书：{self.consistency.get('label_reason')}")
        if self.consistency.get("note"):
            lines.append(f"   说明：{self.consistency['note']}")

        if self.detection:
            lines.append("")
            lines.append(f"④ 是否建议先做检测：{self.detection.get('verdict')}")
            lines.append(f"   {self.detection.get('reason')}")

        lines.append("=" * 98)
        return "\n".join(lines)


class EvidenceCardService:
    def __init__(self, retrieval: RetrievalService | None = None) -> None:
        self.retrieval = retrieval or RetrievalService()

    # ---------------------------------------------------------------- 主入口
    def build(
        self,
        drug: str,
        phenotype: str,
        *,
        gene: str | None = None,
        context: str | None = None,
        label_top_k: int = 5,
    ) -> EvidenceCard:
        drug = drug.strip().lower()
        gene = (gene or self._default_gene(drug) or "").upper()
        if not gene:
            raise ValueError(f"无法确定 {drug} 的基因；请显式传 gene")

        card = EvidenceCard(drug=drug, gene=gene, phenotype=phenotype.strip(), context=context)
        self._fill_cpic(card)
        self._fill_label(card, label_top_k)
        self._judge(card)
        return card

    # ---------------------------------------------------------------- CPIC
    def _default_gene(self, drug: str) -> str | None:
        entry = DRUG_INDEX.get(drug)
        if entry and entry.get("genes"):
            return entry["genes"][0]
        return None

    def _fill_cpic(self, card: EvidenceCard) -> None:
        drugid = self._drugid(card.drug)
        if not drugid:
            logger.warning("CPIC 未收录药物 {}", card.drug)
            return
        card.sources["cpic_drugid"] = drugid

        async def query():
            engine = make_engine()
            factory = make_session_factory(engine)
            try:
                async with factory() as session:
                    pair = (await session.execute(
                        select(CpicPair).where(CpicPair.drugid == drugid, CpicPair.genesymbol == card.gene)
                    )).scalars().first()
                    recs = (await session.execute(
                        select(CpicRecommendation).where(CpicRecommendation.drugid == drugid)
                    )).scalars().all()
                    results = (await session.execute(
                        select(CpicGeneResult).where(CpicGeneResult.genesymbol == card.gene)
                    )).scalars().all()
                    return pair, recs, results
            finally:
                await engine.dispose()

        import asyncio

        pair, recs, results = asyncio.run(query())
        if pair:
            card.cpic_level = pair.cpiclevel
            card.pgx_testing = (pair.pgxtesting or "").strip() or None

        note = next((r for r in results if (r.result or "").lower() == card.phenotype.lower()), None)
        if note:
            card.phenotype_risk = note.ehrpriority
            card.phenotype_note = note.consultationtext

        matched = []
        for rec in recs:
            phenotype_value = (rec.phenotypes or {}).get(card.gene)
            allele_value = (rec.allelestatus or {}).get(card.gene)
            hit = False
            if phenotype_value and phenotype_value.lower() == card.phenotype.lower():
                hit = True
            elif allele_value and allele_matches(card.phenotype, allele_value):
                # HLA 类药对（阿巴卡韦/卡马西平/别嘌醇）没有 phenotypes，
                # 区分的是 `allelestatus`（如 `HLA-B*57:01 positive`）
                hit = True
            if not hit:
                continue
            matched.append({
                "population": rec.population,
                "classification": rec.classification,
                "drugrecommendation": rec.drugrecommendation,
                "implications": rec.implications or {},
                "activityscore": rec.activityscore or {},
                "phenotype": phenotype_value,
                "allelestatus": allele_value,
            })
        if card.context:
            filtered = [m for m in matched if (m["population"] or "").lower() == card.context.lower()]
            card.recommendations = filtered or matched
        else:
            card.recommendations = matched
        logger.info("CPIC：{} 条推荐（场景过滤前）", len(matched))

    def _drugid(self, drug: str) -> str | None:
        path = get_abs_path("data/raw/cpic/drugs.json")
        if not path.exists():
            return None
        rows = json.loads(path.read_text(encoding="utf-8"))
        for row in rows:
            if str(row.get("name", "")).lower() == drug:
                return row.get("drugid")
        return None

    # ---------------------------------------------------------------- 说明书
    def _gene_in_corpus(self, drug: str, gene: str) -> bool:
        """该药的说明书语料里到底有没有出现这个基因（决定走不走降级策略）。"""
        key = (drug, gene)
        cache = self.__dict__.setdefault("_gene_cache", {})
        if key in cache:
            return cache[key]
        found = False
        for chunk_id in self.retrieval.chunks.order():
            chunk = self.retrieval.chunks.get(chunk_id)
            if chunk and chunk.drug == drug and gene.lower() in chunk.text.lower():
                found = True
                break
        cache[key] = found
        return found

    def _fill_label(self, card: EvidenceCard, top_k: int) -> None:
        card.gene_in_label = self._gene_in_corpus(card.drug, card.gene)
        if card.gene_in_label:
            query = f"{card.drug} {card.gene} {card.phenotype}"
        else:
            # 降级：说明书没有这个基因，就别用"基因+表型"去搜（会召回到无关段落）。
            # 改取该药最权威的通用剂量/警告段，明确标注"说明书未提及该基因"。
            hints = RISK_HINTS.get(card.gene.upper(), "")
            query = f"{card.drug} {hints} dosage warnings contraindications"
            card.label_note = (
                f"该药说明书语料中未出现 {card.gene}；以下为该药的通用剂量/警告段落，"
                "仅作对照，不能作为基因型依据。"
            )
        hits = self.retrieval.search(query, top_k=top_k, drug=card.drug)
        for hit in hits:
            ev = hit.chunk.evidence or {}
            card.label_chunks.append({
                "chunk_id": hit.chunk.chunk_id,
                "section": hit.chunk.section,
                "section_label": hit.chunk.section_label,
                "section_priority": hit.chunk.section_priority,
                "kind": hit.chunk.kind,
                "effective_date": ev.get("effective_date"),
                "set_id": ev.get("set_id"),
                "dailymed_url": ev.get("dailymed_url"),
                "snippet": " ".join(hit.chunk.text.split())[:400],
                "role": "gene_specific" if card.gene_in_label else "general_fallback",
            })
        card.sources["label_corpus"] = f"{len(self.retrieval.chunks.order())} chunks"

    # ---------------------------------------------------------------- 一致性
    def _judge(self, card: EvidenceCard) -> None:
        combined = " ".join(c["snippet"] for c in card.label_chunks)
        drugrec = " ".join(str(r.get("drugrecommendation") or "") for r in card.recommendations)

        cpic_level, cpic_reason = classify_cpic_action(drugrec)
        label_level, label_reason = classify_label_action(combined, card.gene)

        if not card.gene_in_label:
            verdict = "说明书未收录该基因"
            note = "该药的 FDA 标签里没有出现此基因，说明书侧无法提供依据（只能用指南侧）"
        elif cpic_level is None:
            verdict = "指南未给出推荐"
            note = "CPIC 对该表型没有明确推荐（可能是剂量表或仅研究性证据）"
        elif label_level is None:
            verdict = "说明书未给出明确行动"
            note = "说明书提到了相关基因但未给出可执行的调整建议，需人工判断"
        elif cpic_level == label_level:
            verdict = "一致"
            note = "指南与说明书方向一致"
        elif cpic_level > label_level:
            verdict = "指南更严格"
            note = f"指南建议更保守（等级差 {cpic_level - label_level}）"
            if cpic_level - label_level >= 2:
                verdict = "存在明显差异"
                note = "指南与说明书在处置方向上差异较大，建议人工复核后再下医嘱"
        else:
            verdict = "说明书更保守"
            note = f"说明书更谨慎（等级差 {label_level - cpic_level}）"

        card.consistency = {
            "verdict": verdict,
            "cpic_action_level": cpic_level,
            "label_action_level": label_level,
            "cpic_reason": cpic_reason,
            "label_reason": label_reason,
            "note": note,
        }

        # 检测建议：CPIC 的 pgxtesting 为主，说明书里的 "screen/test for" 为辅
        # 说明书里的检测表述：screened/screening/testing/genotyping 都算（"screen for" 会漏掉 "screened for"）
        label_mentions_test = any(
            k in combined.lower() for k in ("screen", "genotyp", "test for", "testing", "allele test")
        )
        card.detection = {
            "verdict": "建议先做基因检测" if (card.pgx_testing or "").lower() == "testing required"
            else ("检测有价值（可指导用药）" if (card.pgx_testing or "").lower() == "actionable pgx"
                  else "未强制要求检测"),
            "reason": f"CPIC pgxtesting={card.pgx_testing or '未标注'}；"
                      f"说明书{'提到' if label_mentions_test else '未提到'}检测要求",
        }
