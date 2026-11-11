# HANDOFF · pgx-rag（药物基因组学证据核对 RAG）

> 把这份文件路径发给模型，就能在不依赖聊天记忆的情况下恢复上下文。
> 最近更新：2026-11-10（阶段 0–3 完成，双源证据卡 + Demo + 核心评测已通）

---

## 1. 一句话定位

**面向专业侧（药师/医生）的证据核对工具**：输入「药物 + 基因型/表型（+ 临床场景）」，
输出「RAG 答案（通俗、逐句引用）+ CPIC 指南标准答案 + 两者一致性判定」。

- **RAG 是主体**；CPIC 结构化查表是「标准答案栏」，用于同屏对照与自动打分。
- **不是**患者问答机器人，**不是**诊断工具。
- 目标是跑通「专业侧证据核验」这一条完整链路，并给出可复现的评测。

## 2. 数据源（实测结论）

| 源 | 状态 | 说明 |
|---|---|---|
| OpenFDA `drug/label.json` | ✅ | FDA 说明书（SPL→HTML），17 药 → **2416 切片**、**178 张表** |
| DailyMed SPL | ✅ | 交叉核对 setid（17 中 15 一致） |
| **CPIC `api.cpicpgx.org/v1`** | ✅ | **结构化**：50 药-基因对 / 247 条按表型推荐 / 70 条表型解读 / 6271 星型映射 |
| **NMPA `nmpa.gov.cn`** | ❌ | 412 + JS 挑战（阿里云 WAF）+ 地区访问受限；后续用上传 PDF 的方式补齐 |
| CPIC PDF（Wiley） | ❌ 403 | 用不到，已有结构化 API |

## 3. 当前进度

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | 场景 / 数据源 / 技术底座 | ✅ |
| 1 | 数据准备（抓取 + 表格抽取 + 切片） | ✅ |
| 2 | 检索层（BM25 + 向量 + RRF） | ✅ |
| 3 | 生成层（引用 + 分级 + 拒答） | ✅ |
| — | 双源证据卡 + CPIC 数据层 | ✅（缺人工抽验） |
| — | Streamlit Demo | ✅ |
| — | 核心评测（RAG vs CPIC 80 题） | ✅ 86.5% |
| 4 | FastAPI + SSE + 引用高亮页 | 🔄 40% |
| 5 | 三项自动指标 + 药师盲评 | 🔄 55% |
| 6 | 发布与文档 | ✅ |

**可核对数字**：2722 切片 / R@5=1.000 / MRR=0.929 / 生成 7-7 通过、引用覆盖 90% /
80 题方向一致率 **86.5%** / 证据卡 50 对巡检（一致 9、说明书未收录基因 2）。

## 4. 代码结构

```
app/
  agent/graph.py        LangGraph：retrieve → assess →(refuse|generate)→ finalize
  api/streamlit_app.py  Demo（左右对照）
  clients/              cpic / embedding（TEI+DashScope 双后端）/ vector（Qdrant 服务端+嵌入式）/ mysql
  conf/app_config.py    YAML + dataclass + OmegaConf
  core/                 text / pgx / query（术语桥+表型同义词）/ bm25 / evidence（A-D 分级）/ logger
  entities/             schemas（Chunk/SearchHit/Citation）/ drugs（17 药清单）
  models/orm.py         SQLAlchemy 模型（chunks / label_tables / cpic_*）
  prompt/loader.py      提示词加载（prompts/answer_system.md）
  repositories/         chunk（JSONL+CPIC 语料）/ keyword（BM25）
  scripts/              init_meta_db / ingest_cpic / build_cpic_chunks / build_index /
                        card / ask / eval_retrieval / eval_generation / eval_gold / eval_card / check_services
  services/             retrieval（混合召回）/ generation（引用+拒答）/ evidence_card（一致性）/ answer_judge（LLM 盲判）
conf/app_config.yaml    服务地址、模型、检索参数
docker/                 MySQL(3307) / Qdrant(6333) / ES / Kibana / TEI 编排 + MySQL 初始化 SQL
data/                   corpus（说明书+指南切片）/ raw（抓取快照）/ index（bm25+qdrant+embed cache）/ eval（金标准集）
docs/                   项目计划书、DEMO 演示脚本、assets（截图/GIF）
prompts/                提示词
reports/                各阶段报告
legacy/                 旧实现归档（迁移参考，可删）
```

## 5. 关键决策（不要重复踩坑）

1. 表格必须单独解析成行列矩阵（合并单元格/脚注/图片占位表都处理过）。
2. SPL 的 `<footnote>` 内联在单元格里，要抽出来编号。
3. 多标签择优：内容丰富度分档 > 单方 > 口服 > 命中次数 > 表格数 > 日期。
4. 表格分块要按字符预算（把表头/脚注占用扣掉）。
5. 首列行组标签要向下补全（否则切分后丢 `VASP-PRI`）。
6. 同药文本指纹去重（OpenFDA 多字段重复，丢了 219 条）。
7. 融合用 RRF，不要加权求和（量纲不同）。
8. 章节权威度惩罚（患者版会挤掉黑框警告）。
9. 单药自动过滤（说明书互相引用）。
10. 重排默认关闭（gte-rerank 实测负收益：0.929→0.707）。
11. 先判证据再调模型（D 级直接拒答，236ms）。
12. 证据卡必须带临床场景（ACS/PCI=Strong vs 非 ACS=Moderate）。
13. **指南原文要进检索语料**（只用说明书时 56% 的表型问题答"说明书未定义该表型"）。
14. HLA 类药对没有 `phenotypes`，用 `allelestatus` 匹配（`HLA-B*57:01 positive`）。
15. 说明书未收录某基因时**降级而非硬凑**（给通用剂量/警告段并明确标注）。

## 6. 环境与运行

```powershell
# 依赖：uv（缓存必须指到项目内，沙箱不允许写 %LOCALAPPDATA%）
$env:UV_CACHE_DIR = "$PWD\.uv-cache"; uv sync

# 基础服务（Docker Desktop 已装；MySQL 映射 3307 避开本机 MySQL80）
docker compose -f docker/docker-compose.yaml up -d mysql qdrant

# 数据 → 索引 → Demo
uv run python -m app.scripts.init_meta_db
uv run python -m app.scripts.ingest_cpic
uv run python -m app.scripts.build_cpic_chunks
uv run python -m app.scripts.build_index
uv run streamlit run app/api/streamlit_app.py     # http://localhost:8501
```

**环境事实**
- Python 3.12.15（uv 管理），`.venv` 在项目内；
- 密钥：项目根 `.env`（`Deepseek_key` / `Qwen_key`），由 `app/conf/app_config.py` 注入；
- 本机 pip 装不了包（沙箱 rmtree 被拒），只能用 `uv`；
- `jieba` 是 sdist，装不上 → 已做成可选依赖，未装时用正则分词；
- 访问本机容器端口的 HTTP 客户端需要 `NO_PROXY=localhost,127.0.0.1`（已在 `app/clients/vector.py` 处理）；
- 沙箱默认只读；改代码前确认策略是 `workspace-write`。

## 7. 评测口径（重要，别写错）

- 题目由 CPIC **机械生成**（80 题）；金标准取自 CPIC 推荐原文；
- RAG 链路不看 CPIC 表，只做检索+生成；方向由 **LLM 盲判**（不提供金标准）；
- **有两个数字，含义不同**：
  - **转述一致率 86.5%**（80 题）：语料含 CPIC 原文时，能否正确检索并转述权威依据；
  - **留出一致率 54.2%**（42 题，把 4 个药的 182 条 CPIC 切片从语料剔除）：泛化能力，对照组 88.6%；
- 循环性问题已被量化（88.6% → 54.2%），见 `reports/eval_holdout.md`。
  对外说明必须分开写这两个数，**不要**写成一个笼统"准确率"。

## 8. 下一步（按优先级）

| 优先级 | 事项 | 验收 |
|---|---|---|
| P0 | 三项自动指标：引用忠实度 / 数字一致 / 禁用词方向 | 新脚本 + 报告，失败案例可列 |
| P0 | 人工抽验 20 题，确认机械金标准未标错 | `reports/gold_review.md` |
| P1 | 药师盲评包（10 条证据卡 + 打分表） | 可直接发给药师的文件 |
| P2 | FastAPI + SSE + 引用高亮页 | 接口可被前端调用 |
| P3 | 增量扩药 3–5 个（如 atorvastatin / fluorouracil） | 验证可扩展性 |
| P4 | NMPA 三方差异（地区访问恢复后，3–5 药） | 对照表 |

## 9. 已知限制

- 只有 17 个药（CPIC 里相关 A 级药 51 个，取代表性子集）；
- 无患者个体信息（年龄/肝肾功能/合并用药）→ 不能判断"能不能吃"；
- 无药师评审（可信度短板）；
- ES/TEI 已编排未启动；
- 图片型图表已丢弃。

## 10. 相关文档

- `README.md`（总览、快速开始、脚本清单）
- `docs/项目计划书.md`（供评审的完整方案 + v2/v3 更新）
- `docs/DEMO.md`（3 分钟演示脚本 + 常见问题）
- `reports/`：stage1_report / stage2_retrieval / stage2_evidence_card / stage3_generation / eval_gold
