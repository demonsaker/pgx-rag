"""查询预处理：把中文问题变成「能命中英文说明书」的检索请求。

语料是英文 SPL 说明书，用户用中文提问。两条召回路径需要**两种查询表示**：

* BM25 只认字面 → 用术语桥把中文药名/表型/剂量词映射成说明书里的英文说法；
* 向量模型是多语言的 → 直接用中文原文，保留语义与语气。

这里不做机器翻译，只映射本领域可枚举的术语；映射过程可追溯（translations），
出问题能一眼看出是哪个词没桥过去。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.pgx import GENES, tag_pgx
from app.core.text import normalize_text

# 中文药名 -> 通用名
DRUG_ZH: dict[str, str] = {
    "氯吡格雷": "clopidogrel", "华法林": "warfarin", "他克莫司": "tacrolimus",
    "可待因": "codeine", "曲马多": "tramadol", "辛伐他汀": "simvastatin",
    "硫唑嘌呤": "azathioprine", "别嘌醇": "allopurinol", "别嘌呤醇": "allopurinol",
    "卡马西平": "carbamazepine", "阿巴卡韦": "abacavir", "伏立康唑": "voriconazole",
    "塞来昔布": "celecoxib", "昂丹司琼": "ondansetron", "泮托拉唑": "pantoprazole",
    "艾司西酞普兰": "escitalopram", "卡培他滨": "capecitabine", "苯妥英": "phenytoin",
}

# 中文临床表述 -> 说明书英文用词
TERM_ZH: dict[str, tuple[str, ...]] = {
    "慢代谢型": ("poor metabolizer",), "弱代谢型": ("poor metabolizer",),
    "慢代谢者": ("poor metabolizer",), "中间代谢型": ("intermediate metabolizer",),
    "中间代谢者": ("intermediate metabolizer",), "中间型": ("intermediate metabolizer",),
    "超快代谢型": ("ultrarapid metabolizer", "ultra-rapid metabolism"),
    "超快速代谢": ("ultrarapid metabolizer", "ultra-rapid metabolism"),
    "超快代谢": ("ultrarapid metabolizer", "ultra-rapid metabolism"),
    "快代谢型": ("rapid metabolizer",), "正常代谢型": ("normal metabolizer",),
    "代谢型": ("metabolizer",), "代谢者": ("metabolizer",),
    "基因型": ("genotype",), "基因检测": ("genetic testing", "genotype"),
    "基因筛查": ("genetic testing",), "等位基因": ("allele",), "携带者": ("carrier",),
    "纯合": ("homozygous",), "杂合": ("heterozygous",), "变异": ("variant",),
    "多态性": ("polymorphism",), "功能缺失": ("loss-of-function",),
    "功能获得": ("gain-of-function",), "基因": ("gene",),
    "剂量": ("dose", "dosage"), "起始剂量": ("initial dose",),
    "维持剂量": ("maintenance dose",), "最大剂量": ("maximum dose",),
    "减量": ("dose reduction", "reduced dose"), "降低剂量": ("dose reduction",),
    "增加剂量": ("increase dose",), "调整剂量": ("adjust dose", "dose adjustment"),
    "每日": ("daily",), "一天一次": ("once daily",), "一天两次": ("twice daily",),
    "出血": ("bleeding", "hemorrhage"), "骨髓抑制": ("myelosuppression", "bone marrow suppression"),
    "超敏反应": ("hypersensitivity",), "过敏": ("hypersensitivity", "allergic"),
    "药疹": ("rash",), "皮疹": ("rash",), "皮肤反应": ("skin reaction",),
    "肌病": ("myopathy",), "横纹肌溶解": ("rhabdomyolysis",),
    "肝毒性": ("hepatotoxicity",), "肝损伤": ("hepatic injury", "hepatotoxicity"),
    "呼吸抑制": ("respiratory depression",), "血药浓度": ("plasma concentration",),
    "浓度": ("concentration",), "活性代谢物": ("active metabolite",),
    "代谢物": ("metabolite",), "毒性": ("toxicity",), "风险": ("risk",),
    "不良反应": ("adverse reaction",), "禁忌": ("contraindicated", "contraindication"),
    "禁用": ("contraindicated",), "警告": ("warning", "boxed warning"),
    "黑框警告": ("boxed warning",), "慎用": ("caution",),
    "相互作用": ("drug interaction",), "适应症": ("indications",),
    "疗效": ("efficacy", "response"), "不推荐": ("not recommended",),
    "推荐": ("recommended",), "儿童": ("pediatric",), "小儿": ("pediatric",),
    "孕妇": ("pregnancy",), "妊娠": ("pregnancy",), "哺乳": ("nursing",),
    "老年": ("geriatric",), "说明书": ("label",), "监测": ("monitor",),
}

DRUG_NAMES: tuple[str, ...] = tuple(v for v in DRUG_ZH.values())

_CJK = re.compile(r"[\u4e00-\u9fff]")
_ALLELE = re.compile(r"\*[0-9]{1,2}(?::[0-9]{1,2})?[A-Z]?")

# CPIC 的表型命名与说明书措辞并不一致：指南说 "Intermediate Metabolizer"，
# 标签里写的是 "one loss-of-function allele / heterozygous / reduced function"。
# 不做这层映射，RAG 会对 56% 的表型问题回答"说明书未定义该表型"（实测 48/85）。
PHENOTYPE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "poor metabolizer": ("two loss-of-function alleles", "homozygous", "deficient",
                         "no function", "poor metabolizers", "absent activity"),
    "intermediate metabolizer": ("one loss-of-function allele", "heterozygous",
                                 "reduced function", "intermediate metabolizers", "decreased activity"),
    "normal metabolizer": ("normal metabolizer", "extensive metabolizer", "no dosage adjustment",
                           "usual dose", "typical dose"),
    "rapid metabolizer": ("rapid metabolizer", "increased function", "increased activity"),
    "ultrarapid metabolizer": ("ultrarapid metabolizer", "ultra-rapid", "gain-of-function",
                               "increased function", "increased activity"),
    "decreased function": ("decreased function", "reduced function", "decreased activity"),
    "poor function": ("poor function", "decreased function", "reduced function"),
    "possible intermediate metabolizer": ("one loss-of-function allele", "reduced function",
                                          "intermediate metabolizer"),
    "likely poor metabolizer": ("two loss-of-function alleles", "homozygous", "poor metabolizer"),
    "likely intermediate metabolizer": ("one loss-of-function allele", "heterozygous", "intermediate metabolizer"),
}


@dataclass
class QueryPlan:
    """一次查询的两种表示 + 结构化实体。"""

    raw: str
    has_cjk: bool
    bm25_text: str
    dense_text: str
    genes: list[str] = field(default_factory=list)
    drugs: list[str] = field(default_factory=list)
    phenotypes: list[str] = field(default_factory=list)
    alleles: list[str] = field(default_factory=list)
    translations: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "raw": self.raw,
            "bm25_text": self.bm25_text,
            "genes": self.genes,
            "drugs": self.drugs,
            "phenotypes": self.phenotypes,
            "translations": self.translations,
        }


def _translate_cjk(query: str) -> tuple[str, list[str]]:
    """最长匹配替换；返回替换后的串和命中的中文词（便于解释与排查）。"""
    hits: list[str] = []
    out = query
    for zh in sorted(list(TERM_ZH) + list(DRUG_ZH), key=len, reverse=True):
        if zh in out:
            hits.append(zh)
            english = DRUG_ZH.get(zh) or " ".join(TERM_ZH[zh])
            out = out.replace(zh, f" {english} ")
    return re.sub(r"\s+", " ", out).strip(), hits


def plan_query(query: str) -> QueryPlan:
    raw = normalize_text(query)
    has_cjk = bool(_CJK.search(raw))

    english, hits = ("", [])
    if has_cjk:
        english, hits = _translate_cjk(raw)
    latin = " ".join(re.findall(r"[A-Za-z0-9*\-:.]+", raw))

    bm25_text = f"{english} {latin}".strip()
    # 术语桥之后残留的中文（"会怎样""需要注意什么"）不含可检索信息
    bm25_text = re.sub(r"[^\x00-\x7F]+", " ", bm25_text)
    bm25_text = re.sub(r"\s+", " ", bm25_text).strip()

    # 表型 -> 说明书措辞的同义词扩展（只加词，不改原句）
    lower = bm25_text.lower()
    extra: list[str] = []
    for phenotype, synonyms in PHENOTYPE_SYNONYMS.items():
        if phenotype in lower:
            extra.extend(synonyms)
    if extra:
        bm25_text = f"{bm25_text} {' '.join(dict.fromkeys(extra))}".strip()

    pgx = tag_pgx(f"{raw} {bm25_text}")
    lower = f"{raw.lower()} {bm25_text.lower()}"
    return QueryPlan(
        raw=raw,
        has_cjk=has_cjk,
        bm25_text=bm25_text,
        dense_text=raw,
        genes=pgx["genes"] or [g for g in GENES if g.lower() in lower],
        drugs=[d for d in DRUG_NAMES if d in lower],
        phenotypes=pgx["phenotypes"],
        alleles=_ALLELE.findall(raw),
        translations=hits,
    )
