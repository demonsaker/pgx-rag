"""证据分级与拒答判定（确定性逻辑，不依赖模型是否"听话"）。

分级不看模型自我评价，只看**检索结果的客观属性**：

    A 强证据：命中黑框警告 / 剂量 / 禁忌章节，且证据里出现查询基因或表型
    B 中等  ：命中临床药理 / 药物相互作用 / 警告章节，且出现查询基因
    C 弱    ：只有患者版说明书，或只是泛化提及
    D 不足  ：没有任何一条证据包含查询基因 —— 直接拒答

为什么要有 D：辛伐他汀的说明书里 **SLCO1B1 出现 0 次**（50 个候选标签都查过）。
检索仍会返回"相关"段落，但那些段落不含该基因，拿它们回答等于编造。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.query import QueryPlan
from app.entities.schemas import SearchHit

# 章节优先级里 1–2 视为「决策核心」：黑框警告、剂量、禁忌、临床药理
STRONG_PRIORITY = 2
# 优先级 ≥ 9 是患者版说明书（通俗改写），只能算弱证据
WEAK_PRIORITY = 9


@dataclass
class EvidenceAssessment:
    level: str            # A / B / C / D
    label: str            # 中文说明
    should_refuse: bool
    reason: str
    gene_hits: int = 0
    has_dose: bool = False
    table_hits: int = 0

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "label": self.label,
            "should_refuse": self.should_refuse,
            "reason": self.reason,
            "gene_hits": self.gene_hits,
            "has_dose": self.has_dose,
            "table_hits": self.table_hits,
        }


_LEVEL_LABEL = {
    "A": "A · 强证据（黑框警告 / 剂量 / 禁忌，含基因型信息）",
    "B": "B · 中等证据（临床药理或相互作用，含基因型信息）",
    "C": "C · 弱证据（仅患者版说明或泛化提及）",
    "D": "D · 证据不足（未检索到含目标基因的说明书内容）",
}

# 剂量信息的最小判定：出现 mg / mcg / unit 之类剂量单位
_DOSE_MARKERS = (" mg", "mcg", " mg/kg", "mg/m2", "units", "iu")


def assess(hits: list[SearchHit], plan: QueryPlan) -> EvidenceAssessment:
    if not hits:
        return EvidenceAssessment("D", _LEVEL_LABEL["D"], True, "未检索到任何相关说明书段落")

    genes = set(plan.genes)
    gene_hits = 0
    strong_hits = 0
    table_hits = 0
    has_dose = False

    for hit in hits:
        chunk = hit.chunk
        hit_genes = set(chunk.pgx.get("genes", []))
        # 没有查询基因时（如泛化问题），只要提到任何 PGx 基因也算命中
        matched = bool(hit_genes & genes) if genes else bool(hit_genes)
        if matched:
            gene_hits += 1
            if chunk.section_priority <= STRONG_PRIORITY:
                strong_hits += 1
        if chunk.kind == "table":
            table_hits += 1
        if not has_dose and any(marker in chunk.text.lower() for marker in _DOSE_MARKERS):
            has_dose = True

    if genes and gene_hits == 0:
        return EvidenceAssessment(
            "D",
            _LEVEL_LABEL["D"],
            True,
            f"检索到的 {len(hits)} 条段落都没有出现 {'/'.join(sorted(genes))}，"
            "说明书未收录该基因的相关内容（该药的基因证据可能只存在于 CPIC 指南）",
            gene_hits=0,
            has_dose=has_dose,
            table_hits=table_hits,
        )

    if any(h.chunk.section_priority >= WEAK_PRIORITY for h in hits) and strong_hits == 0:
        return EvidenceAssessment(
            "C", _LEVEL_LABEL["C"], False,
            "只命中患者版说明书或泛化段落，未命中权威章节",
            gene_hits=gene_hits, has_dose=has_dose, table_hits=table_hits,
        )

    if strong_hits:
        return EvidenceAssessment(
            "A", _LEVEL_LABEL["A"], False,
            f"{strong_hits} 条证据来自黑框警告/剂量/禁忌等核心章节，且包含目标基因信息",
            gene_hits=gene_hits, has_dose=has_dose, table_hits=table_hits,
        )

    return EvidenceAssessment(
        "B", _LEVEL_LABEL["B"], False,
        "命中临床药理或相互作用章节，包含目标基因信息，但未触及黑框警告/剂量",
        gene_hits=gene_hits, has_dose=has_dose, table_hits=table_hits,
    )
