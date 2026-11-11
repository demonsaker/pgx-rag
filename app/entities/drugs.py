"""药物与「基因-药物」清单（CPIC 里证据最硬的那批）。

放在 entities 里作为业务主数据：构建元数据库时写进 MySQL，
检索时用来补全药物类别、阶段 3 用来判断"这个药该看哪个基因"。
"""

from __future__ import annotations

DRUGS: list[dict] = [
    {"drug": "clopidogrel", "drug_class": "antiplatelet", "genes": ["CYP2C19"],
     "topic": "CYP2C19 慢代谢者活性代谢物减少、抗血小板反应减弱"},
    {"drug": "warfarin", "drug_class": "anticoagulant", "genes": ["CYP2C9", "VKORC1", "CYP4F2"],
     "topic": "CYP2C9/VKORC1 影响维持剂量"},
    {"drug": "tacrolimus", "drug_class": "immunosuppressant", "genes": ["CYP3A5"],
     "topic": "CYP3A5 表达型需更高剂量"},
    {"drug": "codeine", "drug_class": "opioid analgesic", "genes": ["CYP2D6"],
     "topic": "CYP2D6 超快代谢者吗啡暴露升高（儿童禁用警示）"},
    {"drug": "tramadol", "drug_class": "opioid analgesic", "genes": ["CYP2D6"],
     "topic": "CYP2D6 超快代谢者疗效/风险改变"},
    {"drug": "simvastatin", "drug_class": "statin", "genes": ["SLCO1B1"],
     "topic": "SLCO1B1 功能降低者肌病风险升高"},
    {"drug": "azathioprine", "drug_class": "thiopurine immunosuppressant", "genes": ["TPMT", "NUDT15"],
     "topic": "TPMT/NUDT15 缺陷者骨髓抑制风险"},
    {"drug": "allopurinol", "drug_class": "xanthine oxidase inhibitor", "genes": ["HLA-B"],
     "topic": "HLA-B*58:01 携带者重症药疹风险"},
    {"drug": "carbamazepine", "drug_class": "antiepileptic", "genes": ["HLA-B", "HLA-A", "CYP3A4"],
     "topic": "HLA-B*15:02 / HLA-A*31:01 与 SJS/TEN、DRESS"},
    {"drug": "abacavir", "drug_class": "antiretroviral", "genes": ["HLA-B"],
     "topic": "HLA-B*57:01 携带者超敏反应，需先筛查"},
    {"drug": "voriconazole", "drug_class": "antifungal", "genes": ["CYP2C19"],
     "topic": "CYP2C19 代谢型决定血药浓度与剂量"},
    {"drug": "celecoxib", "drug_class": "NSAID", "genes": ["CYP2C9"],
     "topic": "CYP2C9 弱代谢者暴露升高，起始减半"},
    {"drug": "ondansetron", "drug_class": "antiemetic", "genes": ["CYP2D6"],
     "topic": "CYP2D6 代谢型影响 5-HT3 拮抗剂疗效"},
    {"drug": "pantoprazole", "drug_class": "proton pump inhibitor", "genes": ["CYP2C19"],
     "topic": "CYP2C19 代谢型影响抑酸暴露"},
    {"drug": "escitalopram", "drug_class": "SSRI", "genes": ["CYP2C19", "CYP2D6"],
     "topic": "CYP2C19 慢代谢者暴露升高，需下调剂量上限"},
    {"drug": "capecitabine", "drug_class": "antimetabolite", "genes": ["DPYD"],
     "topic": "DPYD 缺陷者严重/致死性毒性"},
    {"drug": "phenytoin", "drug_class": "antiepileptic", "genes": ["HLA-B", "CYP2C9"],
     "topic": "HLA-B*15:02 与 SJS/TEN"},
]

DRUG_INDEX: dict[str, dict] = {item["drug"]: item for item in DRUGS}
