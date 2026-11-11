# 阶段 1 · 数据准备报告

- 生成时间：2026-11-10T09:31:57
- 数据源：OpenFDA 药品说明书（`api.fda.gov/drug/label.json`）+ DailyMed SPL 元数据核对
- 药物数：17（失败 0）
- 语料规模：**2416 个 chunk**（正文 1981 / 表格 435），**178 张表格**、1844 行表格数据
- PGx 相关块：340（占比 14.1%）
- 已丢弃：同义重复块 219 个（OpenFDA 把同一段文字同时放进多个章节）、图片版式表 4 张

## 1 抓取与择优结果

同一通用名在 OpenFDA 下常有多家厂商、多个剂型的标签，选择顺序：**PGx 内容丰富度分档（目标基因命中 ≥3 条 / 1–2 条 / 无）> 单方（非复方）> 口服（非注射）> 命中次数 > 任意 PGx 基因次数 > 表格数 > 生效日期**。

| 药物 | 商品名 | 途径 | 成分数 | 生效日期 | 候选标签 | DailyMed 核对 | chunks | 表格 | set_id |
|---|---|---|---|---|---|---|---|---|---|
| clopidogrel | Clopidogrel | ORAL | 1 | 2026-09-29 | 50 | ✅ | 84 | 7 | bb3b5e96… |
| warfarin | Warfarin Sodium | ORAL | 1 | 2021-07-29 | 50 | ✅ | 110 | 14 | 2c8f47c6… |
| tacrolimus | Envarsus XR | ORAL | 1 | 2025-02-26 | 47 | ✅ | 165 | 17 | de2315b0… |
| codeine | Codeine sulfate | ORAL | 1 | 2025-12-22 | 50 | ✅ | 177 | 3 | 010905f9… |
| tramadol | TRAMADOL HYDROCHLORIDE | ORAL | 1 | 2026-05-13 | 50 | ✅ | 199 | 4 | 43fe10b2… |
| simvastatin | Simvastatin | ORAL | 1 | 2026-05-11 | 50 | ✅ | 144 | 10 | 4724dbb4… |
| azathioprine | AZATHIOPRINE | ORAL | 1 | 2026-06-10 | 22 | ✅ | 52 | 1 | 59f3219f… |
| allopurinol | Allopurinol | ORAL | 1 | 2026-01-19 | 50 | ✅ | 99 | 7 | 47b8c920… |
| carbamazepine | Carbamazepine | ORAL | 1 | 2026-05-13 | 50 | ✅ | 102 | 3 | 2676f950… |
| abacavir | Abacavir Sulfate | ORAL | 1 | 2026-03-05 | 23 | ✅ | 126 | 12 | f7633480… |
| voriconazole | Voriconazole | ORAL | 1 | 2026-06-02 | 43 | ✅ | 310 | 24 | b8de04a0… |
| celecoxib | Celecoxib | ORAL | 1 | 2025-04-01 | 50 | ✅ | 176 | 14 | 05224473… |
| ondansetron | Ondansetron Hydrochloride | ORAL | 1 | 2022-04-01 | 50 | ✗ | 71 | 11 | 381b44e7… |
| pantoprazole | Protonix Delayed-Release | ORAL | 1 | 2026-05-18 | 50 | ✅ | 156 | 16 | 08098cb2… |
| escitalopram | Escitalopram oxalate | ORAL | 1 | 2026-09-16 | 50 | ✅ | 155 | 9 | 5ba20d2d… |
| capecitabine | XELODA | ORAL | 1 | 2026-02-05 | 20 | ✅ | 187 | 20 | e702d84d… |
| phenytoin | Phenytoin | ORAL | 1 | 2025-05-28 | 49 | ✅ | 103 | 6 | 09daf485… |

- 仍为复方的药物：无；仍为注射剂的药物：无（已全部为单方口服）

## 2 切片质量

- 全部块：均值 738.1 字符，p50=780，p90=900，最长 1668
- 正文块：p50=798，p90=898，最长 1600（目标 900，硬上限 1600，无越界）
- 表格块：p50=578，p90=996，最长 1668（单行超预算时无法再切，属预期）
- 表格结构：含 rowspan 27 张、含 colspan 83 张、带脚注 80 张、最宽 9 列
- 表头来源：{'thead': 55, 'none': 23, 'span-row': 100}；被截断的超宽单元格 0 个

### 每药 PGx 覆盖核验（期望基因 vs 实际出现基因）

| 药物 | CPIC 期望基因 | 说明书实际出现 | 缺失 | PGx 块 | 占比 |
|---|---|---|---|---|---|
| clopidogrel | CYP2C19 | CYP2C19 | - | 24/84 | 29% |
| warfarin | CYP2C9、CYP4F2、VKORC1 | CYP2C9、VKORC1 | CYP4F2 | 19/110 | 17% |
| tacrolimus | CYP3A5 | CYP3A5 | - | 3/165 | 2% |
| codeine | CYP2D6 | CYP2D6 | - | 29/177 | 16% |
| tramadol | CYP2D6 | CYP2D6 | - | 33/199 | 17% |
| simvastatin | SLCO1B1 | **无** | SLCO1B1 | 19/144 | 13% |
| azathioprine | NUDT15、TPMT | NUDT15、TPMT | - | 11/52 | 21% |
| allopurinol | HLA-B | HLA-B | - | 5/99 | 5% |
| carbamazepine | CYP3A4、HLA-A、HLA-B | CYP3A4、HLA-A、HLA-B | - | 19/102 | 19% |
| abacavir | HLA-B | HLA-B | - | 13/126 | 10% |
| voriconazole | CYP2C19 | CYP2C19 | - | 88/310 | 28% |
| celecoxib | CYP2C9 | CYP2C9 | - | 15/176 | 8% |
| ondansetron | CYP2D6 | CYP2D6 | - | 4/71 | 6% |
| pantoprazole | CYP2C19 | CYP2C19 | - | 9/156 | 6% |
| escitalopram | CYP2C19、CYP2D6 | CYP2C19、CYP2D6 | - | 16/155 | 10% |
| capecitabine | DPYD | DPYD | - | 21/187 | 11% |
| phenytoin | CYP2C9、HLA-B | CYP2C9、HLA-B | - | 12/103 | 12% |

## 3 表格清单（结构保真度）

共 **178** 张表格，其中 **51** 张位于 PGx 相关章节（章节优先级 ≤ 3，即用药决策核心）。下面列前 30 张：

| table_id | 章节 | 行×列 | 表头 | rowspan | colspan | 脚注 | 标题 |
|---|---|---|---|---|---|---|---|
| ofda-clopidogrel-t03 | clinical_pharmacology_table | 12×6 | thead | - | - | 5 | Table 3: Active Metabolite Pharmacokinetics and Antiplatelet Response… |
| ofda-clopidogrel-t04 | pharmacogenomics_table | 12×6 | thead | - | - | 5 | Table 3: Active Metabolite Pharmacokinetics and Antiplatelet Response… |
| ofda-warfarin-t02 | dosage_and_administration_table | 4×7 | thead | 是 | 是 | 1 | Table 1: Three Ranges of Expected Maintenance Warfarin Sodium Daily D… |
| ofda-warfarin-t04 | drug_interactions_table | 3×3 | thead | - | - | 0 | Table 2: Examples of CYP450 Interactions with Warfarin |
| ofda-warfarin-t05 | drug_interactions_table | 4×2 | thead | - | - | 0 | Table 3: Drugs that Can Increase the Risk of Bleeding |
| ofda-tacrolimus-t02 | dosage_and_administration_table | 4×3 | none | - | 是 | 0 | - |
| ofda-tacrolimus-t03 | dosage_and_administration_table | 2×2 | span-row | - | - | 0 | Table 1. Recommended Tacrolimus Whole Blood Trough Concentration Rang… |
| ofda-tacrolimus-t09 | drug_interactions_table | 9×3 | none | - | - | 1 | Table 7. Effects of Other Drugs/Substances on ENVARSUS XRa, d |
| ofda-tacrolimus-t10 | use_in_specific_populations_table | 6×3 | span-row | - | - | 0 | Table 8. TPRI Reported Pregnancy Outcomes in Transplant Recipients wi… |
| ofda-tacrolimus-t12 | clinical_pharmacology_table | 6×7 | span-row | 是 | 是 | 1 | Table 9. Pharmacokinetic Parameters of ENVARSUS XR by Study Day in He… |
| ofda-codeine-t02 | drug_interactions_table | 37×2 | span-row | - | 是 | 0 | Table 1: Clinically Significant Drug Interactions with Codeine Sulfat… |
| ofda-tramadol-t02 | drug_interactions_table | 42×2 | span-row | - | 是 | 0 | - |
| ofda-tramadol-t03 | clinical_pharmacology_table | 7×5 | span-row | - | 是 | 0 | - |
| ofda-simvastatin-t02 | drug_interactions_table | 27×2 | span-row | - | 是 | 0 | Table 2: Drug Interactions that Increase the Risk of Myopathy and Rha… |
| ofda-simvastatin-t03 | drug_interactions_table | 5×2 | span-row | - | 是 | 0 | Table 3: Simvastatin Effects on Other Drugs |
| ofda-simvastatin-t04 | clinical_pharmacology_table | 20×6 | thead | 是 | 是 | 1 | Table 4: Effect of Coadministered Drugs or Grapefruit Juice on Simvas… |
| ofda-allopurinol-t01 | dosage_and_administration_table | 6×2 | none | - | - | 0 | - |
| ofda-allopurinol-t02 | dosage_and_administration_table | 5×2 | none | - | - | 0 | - |
| ofda-allopurinol-t03 | dosage_and_administration_table | 6×2 | none | - | - | 0 | - |
| ofda-allopurinol-t04 | dosage_and_administration_table | 5×2 | none | - | - | 0 | - |
| ofda-allopurinol-t05 | drug_interactions_table | 32×2 | span-row | - | 是 | 0 | - |
| ofda-allopurinol-t06 | drug_interactions_table | 32×2 | span-row | - | 是 | 0 | - |
| ofda-abacavir-t01 | dosage_and_administration_table | 4×5 | span-row | 是 | 是 | 1 | Table 1. Dosing Recommendations for Abacavir Scored Tablets in Pediat… |
| ofda-voriconazole-t02 | dosage_and_administration_table | 5×4 | span-row | 是 | 是 | 0 | - |
| ofda-voriconazole-t03 | dosage_and_administration_table | 5×4 | span-row | 是 | 是 | 0 | - |
| ofda-voriconazole-t04 | dosage_and_administration_table | 5×4 | span-row | - | 是 | 6 | Table 1: Recommended Dosing Regimen (Adults) |
| ofda-voriconazole-t05 | dosage_and_administration_table | 5×4 | span-row | 是 | 是 | 3 | Table 2: Recommended Dosing Regimen for Pediatric Patients 2 to less … |
| ofda-voriconazole-t12 | drug_interactions_table | 15×3 | span-row | - | - | 3 | Table 9: Effect of Other Drugs on Voriconazole Pharmacokinetics [see … |
| ofda-voriconazole-t13 | drug_interactions_table | 44×3 | span-row | 是 | - | 5 | Table 10: Effect of Voriconazole on Pharmacokinetics of Other Drugs [… |
| ofda-voriconazole-t14 | clinical_pharmacology_table | 4×7 | span-row | - | - | 1 | Table 11: Geometric Mean (%CV) Plasma Voriconazole Pharmacokinetic Pa… |

> 全部表格的分行分列明细见 `reports/stage1_stats.json` 的 `tables_detail`，原始 HTML 与 `html_sha` 见 `data/corpus/tables.jsonl`。

## 4 抽样：正文 chunk（人肉可读性）

**`ofda-capecitabine-clinical-pharmacology-10`** · Clinical pharmacology · 845 字符 · PGx=['CYP1A2', 'CYP2A6', 'CYP3A4', 'CYP2C19', 'CYP2D6', 'CYP2E1', 'DPYD']

> In Vitro Studies Cytochrome P450 (CYP) Enzymes : Capecitabine and its metabolites (5'-DFUR, 5'-DFCR, fluorouracil, and FBAL) did not inhibit CYP1A2, CYP2A6, CYP3A4, CYP2C19, CYP2D6, or CYP2E1 in vitro. 12.5 Pharmacogenomics The DPYD gene encodes the enzyme DPD, which is responsible for the catabolism of >80% of fluorouracil. Approximately 3-5% of White populations have partial DPD deficiency and 0.2% of White popula…

**`ofda-phenytoin-clinical-pharmacology-05`** · Clinical pharmacology · 841 字符 · PGx=['CYP2C9', 'CYP2C19', 'poor metabolizer']

> Drug Interaction Studies Phenytoin is primarily metabolized by the hepatic cytochrome P450 enzyme CYP2C9 and to a lesser extent by CYP2C19. Phenytoin is a potent inducer of hepatic drug-metabolizing enzymes [see Drug Interactions (7.1 , 7.2) ] . 12.5 Pharmacogenomics CYP2C9 activity is decreased in individuals with genetic variants such as the CYP2C9*2 and CYP2C9*3 alleles. Carriers of variant alleles, resulting in …

**`ofda-azathioprine-clinical-pharmacology-04`** · Clinical pharmacology · 754 字符 · PGx=['TPMT', 'NUDT15', 'poor metabolizers', 'intermediate metabolizers']

> Approximately 0.3% (1:300) of patients of European or African ancestry have two loss-of-function alleles of the TPMT gene and have little or no TPMT activity (homozygous deficient or poor metabolizers), and approximately 10% of patients have one loss-of-function TPMT allele leading to intermediate TPMT activity (heterozygous deficient or intermediate metabolizers). The TPMT*2, TPMT*3A, and TPMT*3C alleles account fo…

**`ofda-pantoprazole-clinical-pharmacology-17`** · Clinical pharmacology · 715 字符 · PGx=['CYP2C19', 'CYP3A4', 'CYP2D6', 'CYP2C9', 'CYP1A2']

> Drug Interaction Studies Effect of Other Drugs on Pantoprazole Pantoprazole is metabolized mainly by CYP2C19 and to minor extents by CYPs 3A4, 2D6, and 2C9. In in vivo drug-drug interaction studies with CYP2C19 substrates (diazepam [also a CYP3A4 substrate] and phenytoin [also a CYP3A4 inducer] and clopidogrel), nifedipine, midazolam, and clarithromycin (CYP3A4 substrates), metoprolol (a CYP2D6 substrate), diclofena…

## 5 抽样：表格线性化（检索用文本）

**`ofda-clopidogrel-adverse-reactions-table-t01`** · Adverse reactions (table) · 718 字符

```
Table 1: CURE Incidence of Bleeding Complications (% patients)
Event | Clopidogrel (+ aspirin) (n=6,259) | Placebo (+ aspirin) (n=6,303)
Major bleeding [1] | 3.7 | 2.7
Life-threatening bleeding | 2.2 | 1.8
Fatal | 0.2 | 0.2
5 g/dL hemoglobin drop | 0.9 | 0.9
Requiring surgical intervention | 0.7 | 0.7
Hemorrhagic strokes | 0.1 | 0.1
Requiring inotropes | 0.5 | 0.5
Requiring transfusion (≥4 units) | 1.2 | 1.0
Other major bleeding | 1.6 | 1.0
Significantly disabling | 0.4 | 0.3
Intraocular bleeding with significant loss of vision | 0.05 | 0.03
Requiring 2-3 units of blood | 1.3 | 0.9
Minor bleeding [2] | 5.1 | 2.4
Notes: [1] Life-threatening and other major bleeding. [2] Led to interruption of study medication.
```

**`ofda-clopidogrel-adverse-reactions-table-t02`** · Adverse reactions (table) · 573 字符

```
Table 2: Incidence of Bleeding Events in COMMIT (% patients)
Type of Bleeding | Clopidogrel (+ aspirin) (n=22,961) | Placebo (+ aspirin) (n=22,891) | p-value
Major [1] noncerebral or cerebral bleeding | 0.6 | 0.5 | 0.59
Major noncerebral | 0.4 | 0.3 | 0.48
Fatal | 0.2 | 0.2 | 0.90
Hemorrhagic stroke | 0.2 | 0.2 | 0.91
Fatal | 0.2 | 0.2 | 0.81
Other noncerebral bleeding (nonmajor) | 3.6 | 3.1 | 0.005
Any noncerebral bleeding | 3.9 | 3.4 | 0.004
Notes: [1] Major bleeds were cerebral bleeds or noncerebral bleeds thought to have caused death or that required transfusion.
```

**`ofda-clopidogrel-clinical-pharmacology-table-t03-p1`** · Clinical pharmacology (table) · 1000 字符

```
Table 3: Active Metabolite Pharmacokinetics and Antiplatelet Responses by CYP2C19 Metabolizer Status
[rows 1-8 of 12]
 | Dose | Poor (n=10) | Intermediate [1] (n=10) | Normal (n=10) | Ultrarapid [2] (n=10)
Cmax (ng/mL) | 300 mg (24 h) | 11 (4) | 23 (11) | 32 (21) | 24 (10)
Cmax (ng/mL) | 600 mg (24 h) | 17 (6) | 39 (23) | 44 (27) | 36 (13)
Cmax (ng/mL) | 75 mg (Day 5) | 4 (1) | 12 (5) | 13 (7) | 12 (6)
Cmax (ng/mL) | 150 mg (Day 5) | 7 (2) | 18 (7) | 19 (5) | 16 (9)
IPA (%) [3] | 300 mg (24 h) | 24 (26) | 37 (21) | 39 (28) | 40 (21)
IPA (%) [3] | 600 mg (24 h) | 32 (25) | 56 (22) | 49 (23) | 51 (28)
IPA (%) [3] | 75 mg (Day 5) | 37 (23) | 60 (18) | 58 (19) | 56 (13)
IPA (%) [3] | 150 mg (Day 5) | 61 (14) | 74 (14) | 73 (9) | 68 (18)
Notes: [1] Intermediate metabolizers have one but not two nonfunctional alleles. [2] Ultrarapid metabolizers have at least one gain-of-function allele. [3] I
```

**`ofda-clopidogrel-clinical-pharmacology-table-t03-p2`** · Clinical pharmacology (table) · 774 字符

```
Table 3: Active Metabolite Pharmacokinetics and Antiplatelet Responses by CYP2C19 Metabolizer Status
[rows 9-12 of 12]
 | Dose | Poor (n=10) | Intermediate [1] (n=10) | Normal (n=10) | Ultrarapid [2] (n=10)
VASP-PRI (%) [4] | 300 mg (24 h) | 91 (12) | 78 (12) | 68 (16) | 73 (12)
VASP-PRI (%) [4] | 600 mg (24 h) | 85 (14) | 56 (26) | 48 (20) | 51 (20)
VASP-PRI (%) [4] | 75 mg (Day 5) | 83 (13) | 50 (16) | 39 (14) | 40 (9)
VASP-PRI (%) [4] | 150 mg (Day 5) | 61 (18) | 29 (11) | 24 (10) | 20 (10)
Notes: [1] Intermediate metabolizers have one but not two nonfunctional alleles. [2] Ultrarapid metabolizers have at least one gain-of-function allele. [4] Vasodilator-stimulated phosphoprotein – platelet reactivity index; smaller value indicates greater platelet inhibition.
```

## 6 结论与下一步

- 真实说明书已入库，表格按行列还原（表头/脚注/合并单元格都保留了位置信息）。
- PGx 证据按基因/表型打标，可直接用于阶段 2 的过滤与阶段 3 的证据分级。
- 已知边界：CPIC 指南 PDF 与 PharmGKB API 仍不可直连（403 / DNS），阶段 1 先用说明书跑通；后续以手工导入或 PMC 版本替换。
- 下一步（阶段 2）：Qdrant/bge-m3 向量索引 + BM25 混合召回 + bge-reranker 重排，核验问题是「慢代谢型患者用氯吡格雷」能否命中 clinical_pharmacology_table。
