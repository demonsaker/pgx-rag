# 核心评测 · RAG 答案 vs CPIC 标准答案

- 题量：80
- 一致 64 · 不一致 10 · 方向不明 6 · 拒答 0
- **方向一致率：86.5%**

## 口径

- 题目由 CPIC 机械生成（药 × 基因 × 表型 × 场景），金标准取自 CPIC 推荐原文；
- RAG 链路不看 CPIC 表，只检索说明书并生成答案；
- 处置方向按关键词归一为三档：避免/禁用(3)、调整/监测(2)、标准剂量(0)；
- 「方向不明」= 答案没有给出可判定的处置语，单独统计、不计入一致率分母。

## 明细

| 药物 | 基因 | 表型 | 场景 | 金标准方向 | 系统方向 | 判定 |
|---|---|---|---|---|---|---|
| abacavir | HLA-B | HLA-B*57:01 negative | general | 0 | 0 | 一致 |
| abacavir | HLA-B | HLA-B*57:01 positive | general | 3 | 3 | 一致 |
| allopurinol | HLA-B | HLA-B*58:01 negative | general | 0 | 0 | 一致 |
| allopurinol | HLA-B | HLA-B*58:01 positive | general | 3 | 3 | 一致 |
| azathioprine | NUDT15 | Intermediate Metabolizer | general | 2 | 2 | 一致 |
| azathioprine | NUDT15 | Normal Metabolizer | general | 0 | 0 | 一致 |
| azathioprine | NUDT15 | Poor Metabolizer | general | 2 | 2 | 一致 |
| azathioprine | NUDT15 | Possible Intermediate Metabolizer | general | 2 | 2 | 一致 |
| azathioprine | TPMT | Intermediate Metabolizer | general | 2 | 2 | 一致 |
| azathioprine | TPMT | Normal Metabolizer | general | 0 | 0 | 一致 |
| azathioprine | TPMT | Poor Metabolizer | general | 2 | 2 | 一致 |
| azathioprine | TPMT | Possible Intermediate Metabolizer | general | 2 | 2 | 一致 |
| capecitabine | DPYD | Intermediate Metabolizer | general | 2 | 2 | 一致 |
| capecitabine | DPYD | Poor Metabolizer | general | 3 | 3 | 一致 |
| carbamazepine | HLA-A | HLA-A*31:01 negative | CBZ naive | 0 | None | 方向不明 |
| carbamazepine | HLA-A | HLA-A*31:01 negative | CBZ-no alternatives | 0 | 0 | 一致 |
| carbamazepine | HLA-A | HLA-A*31:01 negative | CBZ use >3mos | 0 | 0 | 一致 |
| carbamazepine | HLA-A | HLA-A*31:01 positive | CBZ naive | 3 | 3 | 一致 |
| carbamazepine | HLA-A | HLA-A*31:01 positive | CBZ-no alternatives | 2 | 2 | 一致 |
| carbamazepine | HLA-B | HLA-B*15:02 negative | CBZ naive | 0 | 2 | 不一致 |
| carbamazepine | HLA-B | HLA-B*15:02 negative | CBZ-no alternatives | 0 | 0 | 一致 |
| carbamazepine | HLA-B | HLA-B*15:02 negative | CBZ use >3mos | 0 | 0 | 一致 |
| carbamazepine | HLA-B | HLA-B*15:02 positive | CBZ naive | 3 | 3 | 一致 |
| carbamazepine | HLA-B | HLA-B*15:02 positive | CBZ-no alternatives | 3 | 3 | 一致 |
| carbamazepine | HLA-B | HLA-B*15:02 positive | CBZ use >3mos | 2 | None | 方向不明 |
| celecoxib | CYP2C9 | Intermediate Metabolizer | general | 0 | 2 | 不一致 |
| celecoxib | CYP2C9 | Normal Metabolizer | general | 0 | 0 | 一致 |
| celecoxib | CYP2C9 | Poor Metabolizer | general | 0 | 2 | 不一致 |
| clopidogrel | CYP2C19 | Intermediate Metabolizer | CVI ACS PCI | 3 | 2 | 不一致 |
| clopidogrel | CYP2C19 | Intermediate Metabolizer | NVI | 2 | 2 | 一致 |
| clopidogrel | CYP2C19 | Likely Intermediate Metabolizer | CVI ACS PCI | 3 | 3 | 一致 |
| clopidogrel | CYP2C19 | Likely Intermediate Metabolizer | NVI | 2 | 2 | 一致 |
| clopidogrel | CYP2C19 | Likely Poor Metabolizer | CVI ACS PCI | 3 | 3 | 一致 |
| clopidogrel | CYP2C19 | Likely Poor Metabolizer | CVI non-ACS non-PCI | 3 | 3 | 一致 |
| clopidogrel | CYP2C19 | Likely Poor Metabolizer | NVI | 3 | 3 | 一致 |
| clopidogrel | CYP2C19 | Normal Metabolizer | CVI ACS PCI | 0 | 0 | 一致 |
| clopidogrel | CYP2C19 | Normal Metabolizer | CVI non-ACS non-PCI | 0 | 0 | 一致 |
| clopidogrel | CYP2C19 | Normal Metabolizer | NVI | 0 | 0 | 一致 |
| clopidogrel | CYP2C19 | Poor Metabolizer | CVI ACS PCI | 3 | 3 | 一致 |
| clopidogrel | CYP2C19 | Poor Metabolizer | CVI non-ACS non-PCI | 3 | 3 | 一致 |
| clopidogrel | CYP2C19 | Poor Metabolizer | NVI | 3 | 2 | 不一致 |
| clopidogrel | CYP2C19 | Rapid Metabolizer | CVI ACS PCI | 0 | 0 | 一致 |
| clopidogrel | CYP2C19 | Ultrarapid Metabolizer | CVI ACS PCI | 0 | 0 | 一致 |
| codeine | CYP2D6 | Poor Metabolizer | general | 3 | 3 | 一致 |
| codeine | CYP2D6 | Ultrarapid Metabolizer | general | 3 | 3 | 一致 |
| escitalopram | CYP2C19 | Intermediate Metabolizer | general | 0 | 2 | 不一致 |
| escitalopram | CYP2C19 | Likely Intermediate Metabolizer | general | 0 | 2 | 不一致 |
| escitalopram | CYP2C19 | Likely Poor Metabolizer | general | 2 | 2 | 一致 |
| escitalopram | CYP2C19 | Normal Metabolizer | general | 0 | 0 | 一致 |
| escitalopram | CYP2C19 | Poor Metabolizer | general | 2 | 2 | 一致 |
| escitalopram | CYP2C19 | Rapid Metabolizer | general | 0 | 0 | 一致 |
| escitalopram | CYP2C19 | Ultrarapid Metabolizer | general | 2 | 2 | 一致 |
| ondansetron | CYP2D6 | Normal Metabolizer | general | 0 | 0 | 一致 |
| ondansetron | CYP2D6 | Ultrarapid Metabolizer | general | 2 | 2 | 一致 |
| pantoprazole | CYP2C19 | Ultrarapid Metabolizer | general | 2 | 2 | 一致 |
| phenytoin | CYP2C9 | Intermediate Metabolizer | PHT naive | 0 | None | 方向不明 |
| phenytoin | CYP2C9 | Intermediate Metabolizer | PHT use >3mos | 0 | None | 方向不明 |
| phenytoin | CYP2C9 | Normal Metabolizer | PHT naive | 0 | None | 方向不明 |
| phenytoin | CYP2C9 | Normal Metabolizer | PHT use >3mos | 0 | 0 | 一致 |
| phenytoin | HLA-B | HLA-B*15:02 negative | PHT naive | 0 | 0 | 一致 |
| phenytoin | HLA-B | HLA-B*15:02 negative | PHT use >3mos | 0 | 0 | 一致 |
| phenytoin | HLA-B | HLA-B*15:02 positive | PHT naive | 3 | 2 | 不一致 |
| phenytoin | HLA-B | HLA-B*15:02 positive | PHT use >3mos | 2 | None | 方向不明 |
| simvastatin | SLCO1B1 | Decreased Function | general | 2 | 2 | 一致 |
| simvastatin | SLCO1B1 | Increased Function | general | 2 | 0 | 不一致 |
| simvastatin | SLCO1B1 | Normal Function | general | 2 | 0 | 不一致 |
| simvastatin | SLCO1B1 | Poor Function | general | 2 | 2 | 一致 |
| simvastatin | SLCO1B1 | Possible Decreased Function | general | 2 | 2 | 一致 |
| tacrolimus | CYP3A5 | Intermediate Metabolizer | general | 2 | 2 | 一致 |
| tacrolimus | CYP3A5 | Normal Metabolizer | general | 2 | 2 | 一致 |
| tacrolimus | CYP3A5 | Possible Intermediate Metabolizer | general | 2 | 2 | 一致 |
| tramadol | CYP2D6 | Poor Metabolizer | general | 3 | 3 | 一致 |
| tramadol | CYP2D6 | Ultrarapid Metabolizer | general | 3 | 3 | 一致 |
| voriconazole | CYP2C19 | Likely Poor Metabolizer | pediatrics | 2 | 2 | 一致 |
| voriconazole | CYP2C19 | Likely Poor Metabolizer | adults | 2 | 2 | 一致 |
| voriconazole | CYP2C19 | Poor Metabolizer | pediatrics | 2 | 2 | 一致 |
| voriconazole | CYP2C19 | Poor Metabolizer | adults | 2 | 2 | 一致 |
| voriconazole | CYP2C19 | Rapid Metabolizer | adults | 2 | 2 | 一致 |
| voriconazole | CYP2C19 | Ultrarapid Metabolizer | pediatrics | 2 | 2 | 一致 |
| voriconazole | CYP2C19 | Ultrarapid Metabolizer | adults | 2 | 2 | 一致 |

## 失败案例

### 患者 HLA-A 检测结果为「HLA-A*31:01 negative」，能否使用 carbamazepine？（临床场景：CBZ naive）

- CPIC：Use carbamazepine per standard dosing guidelines.
- 系统：LLM 判为未给出明确方向

```
结论：现有证据对 HLA-A*31:01 阴性、CBZ naive 患者的推荐**互相矛盾**，无法据此给出统一的"可用/不可用"结论；需结合是否有替代药物等具体情境判断。

依据：
- 对于 HLA-A*31:01 阴性、CBZ naive 人群，一条 CPIC 推荐为"按标准给药方案使用 carbamazepine（Use carbamazepine per standard dosing guidelines）"，证据强度 Strong，临床含义为卡马西平诱导的 SJS/TEN、DRESS 和 MPE 风险正常[4][6]。
- 同样在 HLA-A*31:01 阴性、CBZ naive 人群，另一条 CPIC 推荐为"若患者未用过卡马西平，不要使用 carbamazepine（do not use carbamazepine）"，证据强度 Strong，临床含义同样为风险正常[1]。
```

### 患者 HLA-B 检测结果为「HLA-B*15:02 negative」，能否使用 carbamazepine？（临床场景：CBZ naive）

- CPIC：Use carbamazepine per standard dosing guidelines.
- 系统：LLM 判定：有替代药时建议不用，属考虑换用其他药，判为2

```
结论：对于 HLA-B*15:02 阴性且未用过卡马西平（CBZ naive）的患者，可按标准给药方案使用 carbamazepine；但若存在可选替代药物，指南仍强烈建议不使用卡马西平[2][4][5]。

依据：
- HLA-B*15:02 阴性、CBZ naive 人群，CPIC 强烈推荐按标准给药指南使用 carbamazepine，其临床意义为卡马西平诱导的 SJS/TEN 风险正常[4][5]。
- 同一人群若存在可选替代药物，CPIC 强烈建议不使用 carbamazepine，临床意义同样为 SJS/TEN 风险正常[2]。
- 若患者无替代药物可用（CBZ-no alternatives），HLA-B*15:02 阴性者按标准给药指南使用 carbamazepine，SJS/TEN 风险正常[6]。

注意：证据仅覆盖 HLA-B*15:02 阴性/阳性与 CBZ nai
```

### 患者 HLA-B 检测结果为「HLA-B*15:02 positive」，能否使用 carbamazepine？（临床场景：CBZ use >3mos）

- CPIC：The latency period for drug-induced SJS/TEN is short with continuous dosing and adherence to therapy (~4-28 days), and cases usually occur within three months of dosing; therefore, if the patient has previously used carbamazepine consistently for longer than three months without incidence of cutaneous adverse reactions, cautiously consider use of carbamazepine in the future.
- 系统：LLM 判为未给出明确方向

```
结论：现有说明书证据不足以回答该问题——证据只覆盖「CBZ naive（未用过卡马西平）」人群，未提供「已使用 carbamazepine 超过 3 个月（CBZ use >3mos）」这一人群的推荐。

依据：
- 证据中 HLA-B*15:02 阳性、CBZ naive 人群的推荐为：若患者为 carbamazepine-naïve，不要使用 carbamazepine，推荐强度为 Strong，临床意义为卡马西平诱导的 SJS/TEN 风险更高[1][2][3]。
- 证据中另有一组 HLA-B*15:02 阳性、标注为「CBZ-no alternatives」的人群，其推荐同样表述为「若患者为 carbamazepine-naïve，不要使用 carbamazepine」，强度 Strong，临床意义为 SJS/TEN 风险更高[4][5][6]。

注意：所有证据块的适用人群均限
```

### 患者 CYP2C9 检测结果为「Intermediate Metabolizer」，能否使用 celecoxib？

- CPIC：Initiate therapy with recommended starting dose. In accordance with the prescribing information, use the lowest effective dosage for shortest duration consistent with individual patient treatment goals.
- 系统：LLM 判定：需调整起始剂量并监测，属改动方案后使用

```
结论：可以使用，但需按中间代谢者（Intermediate Metabolizer, IM）的推荐调整起始剂量，并在治疗中谨慎滴定与监测[1][2]。

依据：
- 对 CYP2C9 中间代谢者，CPIC 推荐可起始 celecoxib 治疗，推荐强度为 Moderate[1][2]。
- 活动评分为 1.0 的中间代谢者，应以最低推荐起始剂量（lowest recommended starting dose）开始治疗，再谨慎向上滴定至临床疗效或最大推荐剂量[1]。
- 活动评分为 1.5 的中间代谢者，可按推荐起始剂量（recommended starting dose）开始治疗[2]。
- 中间代谢者代谢中度至轻度降低，血浆浓度可能升高，从而增加毒性发生的可能性[1][2]。
- 应按说明书使用最低有效剂量、最短疗程，以符合个体治疗目标[1][2]。
- 治疗过程中应仔细监测血压、肾功
```

### 患者 CYP2C9 检测结果为「Poor Metabolizer」，能否使用 celecoxib？

- CPIC：Initiate therapy with 25-50% of the lowest recommended starting dose. Titrate dose upward to clinical effect or 25-50% of the maximum recommended dose with caution. In accordance with the prescribing information, use the lowest effective dosage for shortest duration consistent with individual patient treatment goals. Upward dose titration should not occur until after steady state is reached (at least 8 days for celecoxib after first dose in PMs). Carefully monitor adverse events such as blood pressure and kidney function during course of therapy. Alternatively, consider an alternate therapy not metabolized by CYP2C9 or not significantly impacted by CYP2C9 genetic variants in vivo.
- 系统：LLM 判定：结论为可用但需减量起始并监测，属调整方案后使用

```
结论：可以使用，但需按弱代谢者（Poor Metabolizer, PM）调整给药：成人以最低推荐起始剂量的一半起始[4][6]，或按 CPIC 建议以最低推荐起始剂量的 25–50% 起始[1][2]；幼年特发性关节炎（JRA）患者应考虑改用替代治疗[3][4][6]。

依据：
- 对已知或疑似 CYP2C9 弱代谢者的成人患者（依据基因型，或既往使用其他 CYP2C9 底物如华法林、苯妥英的经验），celecoxib 应以最低推荐起始剂量的一半开始给药[4][6]。
- CPIC 对 CYP2C9 弱代谢者的推荐为：以最低推荐起始剂量的 25–50% 起始治疗，谨慎向上滴定至临床疗效或最大推荐剂量的 25–50%[1][2]。
- 向上滴定不应在达到稳态前进行；celecoxib 在弱代谢者中首次给药后至少需 8 天达到稳态[1][2]。
- 治疗期间应仔细监测血压、肾功能等不良事件
```

### 患者 CYP2C19 检测结果为「Intermediate Metabolizer」，能否使用 clopidogrel？（临床场景：CVI ACS PCI）

- CPIC：Avoid standard dose (75 mg) clopidogrel if possible. Use prasugrel or ticagrelor at standard dose if no contraindication.
- 系统：LLM 判定：建议换用其他药，属调整方案后可用，非绝对禁用

```
结论：在 CVI ACS PCI 场景下，CYP2C19 Intermediate Metabolizer 患者应尽可能避免使用标准剂量（75 mg）clopidogrel；若无禁忌，应改用标准剂量的 prasugrel 或 ticagrelor[4]。

依据：
- 针对 CYP2C19 Intermediate Metabolizer、人群为 CVI ACS PCI 的 CPIC 推荐强度为 Strong，推荐尽可能避免使用标准剂量（75 mg）clopidogrel[4]。
- 若患者无禁忌证，应使用标准剂量的 prasugrel 或 ticagrelor[4]。
- 该基因型对应的临床影响为：clopidogrel 活性代谢物生成减少、治疗中血小板反应性升高、不良心脑血管事件风险增加[4]。

注意：上述推荐仅适用于 CVI ACS PCI 人群；证据中 Intermediate 
```

### 患者 CYP2C19 检测结果为「Poor Metabolizer」，能否使用 clopidogrel？（临床场景：NVI）

- CPIC：Avoid clopidogrel if possible. Consider an alternative P2Y12 inhibitor at standard dose if clinically indicated and no contraindication.
- 系统：LLM 判定：结论为考虑换用其他P2Y12抑制剂，属改方案后可用，非绝对禁用

```
结论：不建议使用氯吡格雷（clopidogrel）；如临床需要且无禁忌，应考虑换用其他 P2Y12 抑制剂（标准剂量）[2][3]。说明书黑框警告也明确要求：对已确认为 CYP2C19 慢代谢者的患者，应考虑使用其他血小板 P2Y12 抑制剂[1]。

依据：
- CYP2C19 慢代谢者（poor metabolizer）指 CYP2C19 基因两个功能缺失等位基因的纯合子；此类患者按推荐剂量服用氯吡格雷时，生成的活性代谢物更少，对血小板活性的抑制作用减弱[1][4]。
- 针对 CYP2C19 Poor Metabolizer（人群 NVI）的 CPIC 推荐为：尽可能避免使用氯吡格雷；如临床有指征且无禁忌，可考虑换用其他 P2Y12 抑制剂，并按标准剂量给药；推荐强度为 Moderate[3]。
- 对 CYP2C19 Likely Poor Metabolizer（人群 NVI）的
```

### 患者 CYP2C19 检测结果为「Intermediate Metabolizer」，能否使用 escitalopram？

- CPIC：Initiate therapy with recommended starting dose. Consider a slower titration schedule and lower maintenance dose than normal metabolizers.
- 系统：LLM 判定：结论为可用但需调整滴定节奏和维持剂量，属需改动方案后使用

```
结论：可以使用。CYP2C19 中间代谢者（Intermediate Metabolizer）可按推荐起始剂量启用 escitalopram，但需考虑比正常代谢者更慢的滴定节奏和更低的维持剂量[1]。

依据：
- 对 CYP2C19 中间代谢者，CPIC 推荐以推荐起始剂量开始治疗（Initiate therapy with recommended starting dose），推荐强度为 Moderate[1]。
- 建议考虑比正常代谢者更慢的滴定方案和更低的维持剂量（slower titration schedule and lower maintenance dose than normal metabolizers）[1]。
- 临床含义为：与 CYP2C19 正常代谢者相比代谢减慢，血浆浓度可能升高，从而增加不良反应发生的可能性[1]。

注意：证据未给出具体的起始剂量与维持剂
```

