"""PGx 标注：从说明书文本识别基因 / 代谢表型 / 等位基因。

用途：
* 检索时按基因做软加权与过滤（"问题点了 CYP2C19" → 含该基因的块往前排）；
* 生成时判断证据是否充分（答案里要引用的段落，是否真的提到了查询基因）。
"""

from __future__ import annotations

import re

GENES: tuple[str, ...] = (
    "CYP1A2", "CYP2B6", "CYP2C8", "CYP2C9", "CYP2C19", "CYP2D6",
    "CYP3A4", "CYP3A5", "CYP4F2", "VKORC1", "SLCO1B1", "ABCG2", "ABCB1",
    "TPMT", "NUDT15", "DPYD", "G6PD", "UGT1A1", "NAT2", "MTHFR",
    "HLA-A", "HLA-B", "HLA-DRB1", "CFTR", "IFNL3", "CYP2A6", "CYP2E1",
)

_GENE_RE = re.compile(
    r"(?<![A-Za-z0-9])(" + "|".join(re.escape(g) for g in sorted(GENES, key=len, reverse=True)) + r")(?![A-Za-z0-9])"
)

PHENOTYPES: tuple[str, ...] = (
    "ultrarapid metabolizer", "rapid metabolizer", "normal metabolizer", "extensive metabolizer",
    "intermediate metabolizer", "poor metabolizer",
    "ultrarapid metabolizers", "rapid metabolizers", "normal metabolizers", "extensive metabolizers",
    "intermediate metabolizers", "poor metabolizers",
)

_PHENOTYPE_RE = re.compile(
    r"\b(" + "|".join(sorted((re.escape(p) for p in PHENOTYPES), key=len, reverse=True)) + r")\b", re.IGNORECASE
)

_ALLELE_RE = re.compile(r"\*\s?(\d{1,2})(?::\d{1,2})?[A-Z]?")


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def tag_pgx(text: str) -> dict:
    """给一段文本打 PGx 标签；只有出现基因或表型才算「PGx 证据」。"""
    if not text:
        return {"genes": [], "phenotypes": [], "alleles": [], "score": 0, "is_pgx": False}

    genes = _dedupe(_GENE_RE.findall(text))
    phenotypes = _dedupe([m.lower() for m in _PHENOTYPE_RE.findall(text)])
    # 等位基因只在同时出现基因时可信，否则 "*5" 这种编号会误伤
    alleles = _dedupe([f"*{m}" for m in _ALLELE_RE.findall(text)]) if genes else []

    score = len(genes) * 3 + len(phenotypes) * 2 + len(alleles)
    return {
        "genes": genes,
        "phenotypes": phenotypes,
        "alleles": alleles[:12],
        "score": score,
        "is_pgx": bool(genes or phenotypes),
    }
