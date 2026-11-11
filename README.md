# pgx-rag · 药物基因组学证据核对 RAG

给「药物 + 患者基因型/表型 + 临床场景」，返回一张**可核对的证据卡**：

1. **RAG 答案**——通俗、可执行，每句带 `[n]` 引用，可点开核对原文；
2. **CPIC 指南标准答案**——推荐原文、强度（Strong/Moderate/Optional）、检测建议、按临床场景分列；
3. **一致性判定**——两份证据是否一致，不一致时是哪一侧更严。

数据源：美国 FDA 药品说明书（SPL）+ CPIC 基因-药物指南。

> **不是**患者问答机器人，**不是**诊断工具，不替代药师判断。定位是**专业侧的用药证据核验**。

![Demo：左侧选药物/基因/表型，右侧同屏 RAG 答案与 CPIC 标准答案](docs/assets/demo.gif)

---

## 1. 为什么需要「双源对照」

同一个基因-药对，两个权威来源的表述经常对不上：

| 情况 | 例子 |
|---|---|
| 指南有明确处置，说明书根本没写这个基因 | 辛伐他汀 × SLCO1B1：CPIC A 级要求换药或限 20mg/日，FDA 标签中 SLCO1B1 出现 **0** 次 |
| 两边都写，但强度不同 | 氯吡格雷 × CYP2C19：CPIC 在 ACS/PCI 场景为 Strong（避免），说明书表述更保守 |
| 说明书更严 | 少数药物标签直接禁用，而指南给的是"可权衡使用" |

单靠说明书，遇到第一类情况只能回答"说明书未定义"——实测有 **56%** 的表型问题会落到这个兜底。
所以本项目把 **CPIC 推荐原文也放进检索语料**，让答案能同时引用两侧证据，并把"两侧是否一致"直接展示出来。

---

## 2. 功能现状

**已实现**

- 表格感知切片：SPL HTML 的合并单元格、内联脚注、图片占位表都能还原成行列结构
- 混合召回：自研 BM25 + 1024 维向量 + RRF 融合 + 单药过滤 + 章节权威度
- 证据分级 A/B/C/D + 逐句引用回填 + 证据不足时**不调用模型直接拒答**
- 证据卡：CPIC 标准答案（含临床场景）× 说明书原文 × 一致性判定
- 80 题金标准评测 + 留出实验（量化"金标准同源"的循环性）
- Streamlit 演示页；命令行 `card` / `ask` 两个入口

**计划中**

- FastAPI 接口 + SSE 流式输出 + 引用高亮页（当前只有 Streamlit 演示）
- 引用忠实度、数字一致性、禁用词方向三项自动指标
- 药师盲评（当前**没有**任何外部专业评审）
- NMPA 中文说明书（地区访问受限，暂未接入）

### 关键数字

| 指标 | 结果 |
|---|---|
| 语料 | **2722 切片**（FDA 说明书 2416 + CPIC 指南 306），178 张表格 / 1844 行 |
| 检索 | 7 问评测 **R@5 = 1.000、MRR = 0.929**（混合召回） |
| 生成 | 7/7 通过、引用覆盖率 90%、平均 3.3s、拒答 0.24s |
| 评测 | 80 题 **转述一致率 86.5%**；留出实验 42 题 **54.2%**（对照 88.6%） |
| 证据卡巡检 | 50 个基因-药对：一致 9 / 指南更严 1 / 说明书更保守 1 / 说明书未收录基因 2 |

复现方式见 [§6 快速开始](#6-快速开始) 与 [§9 评测方法](#9-评测方法)；报告在 [reports/](reports/)。

---

## 3. 架构

```
问题（药 + 基因型/表型 + 场景）
  │
  ├─ 检索路径（RAG 主体）
  │   说明书 2416 + CPIC 306 切片
  │     ├─ BM25（基因符号/等位基因/剂量词精确命中）
  │     └─ 向量（text-embedding-v4，1024 维，中文原文直编）
  │           → RRF 融合 → 单药过滤 → 章节权威度惩罚 → top_k
  │   证据分级 A/B/C/D → DeepSeek 生成（逐句 [n] 引用）→ 引用回填校验
  │
  └─ 对照路径（标准答案）
      MySQL 直查 CPIC：cpic_pair + cpic_recommendation + cpic_gene_result
      → 推荐原文 + 强度(Strong/Moderate/Optional) + 检测建议 + 场景
        ↓
     一致性判定：一致 / 指南更严格 / 说明书更保守 / 说明书未收录该基因
```

LangGraph 编排：

```
retrieve → assess ─┬→ refuse   → finalize
                   └→ generate → finalize
```

`assess` 用确定性规则判定证据是否充分；不足时走 `refuse`，**不经过大模型**。

---

## 4. 技术栈

| 层 | 选型 |
|---|---|
| 环境与依赖 | **uv**（`pyproject.toml` + `uv.lock`），Python 3.12 |
| 分层 | `app/{api,agent,clients,conf,core,entities,models,prompt,repositories,scripts,services}` |
| 配置 | YAML + dataclass + **OmegaConf** + python-dotenv（密钥走 `.env`） |
| 日志 | **loguru**（文件轮转 + 控制台） |
| 元数据库 | **MySQL 8.0**（Docker，宿主 3307）+ SQLAlchemy 2.0 async + asyncmy |
| 向量库 | **Qdrant 1.16**（Docker，6333；也支持嵌入式） |
| 向量化 | **DashScope `text-embedding-v4`**（1024 维，多语言）；目标形态 TEI + bge-large-zh-v1.5 |
| 关键词检索 | 自实现 **BM25**（基因/等位基因友好分词 + 字段加权） |
| 文档解析 | **lxml**（SPL HTML → 行列矩阵） |
| 生成 | **DeepSeek**（OpenAI 兼容），逐句引用 + 证据分级 + 拒答 |
| 编排 | **LangGraph**（条件分支） |
| 演示 | **Streamlit** |

---

## 5. 前置要求

| 依赖 | 说明 |
|---|---|
| Python 3.12 + [uv](https://docs.astral.sh/uv/) | 依赖由 `uv.lock` 固定 |
| Docker Desktop | 跑 MySQL(3307) 与 Qdrant(6333) |
| DeepSeek API Key | 生成模型 |
| 阿里云百炼 DashScope API Key | 向量化模型 |

> 说明书的原始 HTML 与向量索引没有入库（可重建），首次运行需要联网抓取 OpenFDA 与 CPIC 数据。

---

## 6. 快速开始

```bash
# 1) 依赖
uv sync

# 2) 配置密钥（复制模板后填入真实值，.env 不会入库）
cp .env-example .env

# 3) 基础服务
docker compose -f docker/docker-compose.yaml up -d mysql qdrant
docker compose -f docker/docker-compose.yaml ps

# 4) 数据入库（抓取 → MySQL → 检索语料 → 索引）
uv run python -m app.scripts.init_meta_db      # 说明书：17 药 / 2416 切片 / 178 表
uv run python -m app.scripts.ingest_cpic       # CPIC 结构化入库
uv run python -m app.scripts.build_cpic_chunks # 指南原文转检索语料（306 条）
uv run python -m app.scripts.build_index       # BM25 + 向量索引

# 5) 自检
uv run python -m app.scripts.check_services

# 6) 演示页
uv run streamlit run app/api/streamlit_app.py  # http://localhost:8501

# 7) 命令行
uv run python -m app.scripts.card --drug clopidogrel --phenotype "Poor Metabolizer" --context "CVI ACS PCI"
uv run python -m app.scripts.ask "CYP2C19 慢代谢型患者用氯吡格雷会怎样？"
```

---

## 7. 主要脚本

| 脚本 | 作用 |
|---|---|
| `init_meta_db.py` | 建表 + 灌入说明书数据（17 药 / 2416 切片 / 178 表） |
| `ingest_cpic.py` | 抓取并入库 CPIC（50 pair / 247 推荐 / 70 表型解读 / 6271 星型映射） |
| `build_cpic_chunks.py` | CPIC 推荐转成可检索语料（306 条） |
| `build_index.py` | 建 BM25 + 向量索引（`--server` / `--no-dense`） |
| `card.py` | 生成证据卡（JSON / 可读文本） |
| `ask.py` | RAG 问答（走 LangGraph，可 `--no-graph`） |
| `eval_retrieval.py` | 检索评测（BM25 / 向量 / 混合） |
| `eval_generation.py` | 生成验收（拒答正确性 / 引用覆盖 / 越界引用） |
| `eval_gold.py` | RAG 答案 vs CPIC 金标准（含 `--holdout-drugs` 留出实验） |
| `eval_card.py` | 证据卡巡检（50 个基因-药对的一致性分布） |
| `check_services.py` | 服务健康检查 |

---

## 8. 设计决策

每条都对应一个实测问题，不是预设的最佳实践。

1. **表格单独解析成行列矩阵**：CYP2C19 四表型的 Cmax/IPA/VASP-PRI 全在表格里，切碎后既检索不到也无法引用。
2. **`<footnote>` 从单元格抽出编号 `[n]`**：SPL 把脚注正文内联在单元格里，不抽出来会糊进表头。
3. **多标签择优**：内容丰富度分档 > 单方 > 口服 > 命中次数 > 表格数 > 生效日期。否则他克莫司会选中 2017 年、完全不提 CYP3A5 的那份标签。
4. **表格分块按字符预算**（扣掉表头/脚注占用）：只按行数切会产生 6835 字符的超长块。
5. **首列行组标签向下补全**：表格切分后，第二段会丢掉 `VASP-PRI` 这类参数名。
6. **同药文本指纹去重**：OpenFDA 把同一段文字放进多个字段，实测去掉 219 条冗余。
7. **融合用 RRF，不用加权求和**：余弦相似度 0–1、BM25 0–∞，量纲不同。
8. **章节权威度惩罚**：患者版说明书会复述黑框警告，纯相似度会把它排到黑框警告前面。
9. **单药自动过滤**：说明书互相引用（泮托拉唑标签里也提到氯吡格雷）。
10. **重排默认关闭**：gte-rerank 实测把 MRR 从 0.929 拉到 0.707，三档 α 融合都是单调下降。
11. **先判证据、再调模型**：D 级证据直接拒答（236ms），不依赖模型是否听指令。
12. **证据卡必须带临床场景**：同一表型在 ACS/PCI 是 Strong、非 ACS 是 Moderate。
13. **指南原文进检索语料**：否则 56% 的表型问题只能回答"说明书未定义该表型"。

---

## 9. 评测方法

### 题从哪来

题目由 CPIC 推荐**机械生成**（药 × 基因 × 表型 × 场景），金标准即 CPIC 推荐原文，方向按规则归一为三档：
`0 标准剂量 / 2 调整或监测 / 3 避免或禁用`。排除 `No Result`、`Indeterminate` 等无处置意义的表型。

### 判分

RAG 链路不看 CPIC 表结构，只做检索 + 生成；方向由 **LLM 盲判**（判定时不提供金标准）后比对。

### 两个数字，含义不同

| 指标 | 值 | 测什么 | 是否循环 |
|---|---|---|---|
| **转述一致率** | 86.5%（80 题） | 语料含 CPIC 原文时，能否正确检索并转述权威依据 | 部分（已量化） |
| **留出一致率** | 54.2%（42 题） | 剔除金标准来源后的泛化能力（对照 88.6%） | 否 |

留出实验：把 4 个药的 182 条 CPIC 切片从检索候选中剔除，同一批题从 88.6% 掉到 54.2%，
说明 86.5% 衡量的是「检索 + 转述」，**不是独立医学推理正确率**。
详见 [reports/eval_holdout.md](reports/eval_holdout.md)。

> 引用时请分开写这两个数，不要合并成一个"准确率"。

---

## 10. 适用范围与限制

**覆盖 17 个药物**：氯吡格雷、华法林、他克莫司、可待因、曲马多、辛伐他汀、硫唑嘌呤、别嘌醇、
卡马西平、阿巴卡韦、伏立康唑、塞来昔布、昂丹司琼、泮托拉唑、艾司西酞普兰、卡培他滨、苯妥英。

| 限制 | 说明 |
|---|---|
| 药物范围有限 | CPIC 中与相关基因挂钩的 A 级药物共 51 个，这里取代表性子集；架构支持增量扩药 |
| **NMPA 数据暂未接入** | `nmpa.gov.cn` 对非中国大陆网络返回 412（WAF 的 JS 挑战），当前环境无法访问；后续通过上传说明书 PDF 补齐 |
| 无患者个体信息 | 没有年龄/肝肾功能/合并用药，**不能**判断"这个患者能不能吃" |
| 无外部评审 | 尚未经过药师或临床医生评审，不能作为临床依据 |
| ES / TEI 未启用 | 编排已写好但未启动，当前用自研 BM25 + 云端 embedding 替代 |
| 图片型图表已丢弃 | `<rendermultimedia>` 的表格数据在图片里，无法从 HTML 恢复 |

---

## 11. 目录结构

```
pgx-rag/
├── app/                    # 分层源码
│   ├── agent/graph.py          LangGraph 工作流
│   ├── api/streamlit_app.py    Demo 页面
│   ├── clients/                cpic / embedding / vector / mysql
│   ├── conf/app_config.py      YAML + dataclass + OmegaConf
│   ├── core/                   text / pgx / query / bm25 / evidence / logger
│   ├── entities/               schemas / drugs
│   ├── models/orm.py           SQLAlchemy 模型
│   ├── prompt/loader.py        提示词加载
│   ├── repositories/           chunk / keyword
│   ├── scripts/                见 §7
│   └── services/               retrieval / generation / evidence_card / answer_judge
├── conf/app_config.yaml
├── docker/                 # MySQL / Qdrant / ES / Kibana / TEI 编排
├── data/                   # corpus（已提交）/ raw、index（可重建，未提交）
├── docs/                   # 计划书、演示脚本、数据来源与许可
├── prompts/                # 提示词
└── reports/                # 各阶段评测报告
```

---

## 12. 文档

| 文档 | 内容 |
|---|---|
| [docs/项目计划书.md](docs/项目计划书.md) | 场景、数据源、设计取舍、评测与风险 |
| [docs/DEMO.md](docs/DEMO.md) | 3 分钟演示脚本 + 常见问题 |
| [docs/数据来源与许可.md](docs/数据来源与许可.md) | 数据许可、免责声明、不包含的内容 |
| [reports/eval_gold.md](reports/eval_gold.md) | 80 题评测明细与失败案例 |
| [reports/eval_holdout.md](reports/eval_holdout.md) | 留出实验 |
| [reports/stage1_report.md](reports/stage1_report.md) | 数据解析与切片 |
| [reports/stage2_retrieval.md](reports/stage2_retrieval.md) | 检索评测与重排调参记录 |
| [reports/stage2_evidence_card.md](reports/stage2_evidence_card.md) | 证据卡巡检 |
| [reports/stage3_generation.md](reports/stage3_generation.md) | 生成验收 |
| [HANDOFF-pgx-rag.md](HANDOFF-pgx-rag.md) | 代码结构与实现备忘 |

---

## 13. 许可与免责声明

- 代码：[MIT](LICENSE)；
- 数据：FDA 说明书为美国政府作品（公有领域）；CPIC 推荐内容版权归 ASCPT/CPIC，本项目仅引用摘要并注明出处，商用请自行确认授权。细节见 [docs/数据来源与许可.md](docs/数据来源与许可.md)；
- **本项目仅用于技术演示，不构成医疗建议**，不可用于临床决策。
