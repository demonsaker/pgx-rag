"""检索评测：BM25 / 向量 / 混合 三组对比，附证据不足案例检查。

评测集是人工标注的（看真实 chunk 定的标准答案，不是"系统返回什么就标什么"）：

    uv run python -m app.scripts.eval_retrieval
    uv run python -m app.scripts.eval_retrieval --write-report
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.conf.app_config import PROJECT_ROOT
from app.services.retrieval_service import RetrievalService

QUERIES: list[dict] = [
    {
        "id": "q1",
        "query": "CYP2C19 慢代谢型患者用氯吡格雷会怎样？",
        "expect": [
            "ofda-clopidogrel-clinical-pharmacology-10",
            "ofda-clopidogrel-pharmacogenomics-01",
            "ofda-clopidogrel-pharmacogenomics-02",
            "ofda-clopidogrel-clinical-pharmacology-table-t03",
            "ofda-clopidogrel-boxed-warning-01",
        ],
    },
    {
        "id": "q2",
        "query": "TPMT 缺陷的患者能用硫唑嘌呤吗？",
        "expect": [
            "ofda-azathioprine-clinical-pharmacology-02",
            "ofda-azathioprine-clinical-pharmacology-03",
            "ofda-azathioprine-clinical-pharmacology-04",
            "ofda-azathioprine-warnings-05",
            "ofda-azathioprine-dosage-and-administration-04",
            "ofda-azathioprine-adverse-reactions-04",
        ],
    },
    {
        "id": "q3",
        "query": "HLA-B*57:01 阳性的患者可以吃阿巴卡韦吗？",
        "expect": [
            "ofda-abacavir-contraindications-01",
            "ofda-abacavir-dosage-and-administration-01",
            "ofda-abacavir-boxed-warning-01",
            "ofda-abacavir-boxed-warning-03",
        ],
    },
    {
        "id": "q4",
        "query": "CYP2C9 弱代谢者用塞来昔布起始剂量怎么定？",
        "expect": [
            "ofda-celecoxib-dosage-and-administration-05",
            "ofda-celecoxib-dosage-and-administration-02",
            "ofda-celecoxib-use-in-specific-populations-01",
        ],
    },
    {
        "id": "q5",
        "query": "DPYD 缺陷的患者用卡培他滨有什么风险？",
        "expect": [
            "ofda-capecitabine-boxed-warning-01",
            "ofda-capecitabine-boxed-warning-03",
            "ofda-capecitabine-dosage-and-administration-03",
        ],
    },
    {
        "id": "q6",
        "query": "CYP2D6 超快代谢的儿童用可待因有什么风险？",
        "expect": [
            "ofda-codeine-warnings-and-cautions-17",
            "ofda-codeine-boxed-warning-04",
            "ofda-codeine-boxed-warning-03",
        ],
    },
    {
        "id": "q7",
        "query": "CYP2C9 和 VKORC1 如何影响华法林的维持剂量？",
        "expect": [
            "ofda-warfarin-dosage-and-administration-08",
            "ofda-warfarin-dosage-and-administration-09",
            "ofda-warfarin-dosage-and-administration-10",
            "ofda-warfarin-dosage-and-administration-table-t02",
        ],
    },
]

NO_ANSWER_CASE = {
    "id": "q8",
    "query": "SLCO1B1 变异的人吃辛伐他汀会肌痛吗？",
    "note": "说明书未收录 SLCO1B1：理想行为是拒答或标注证据不足",
}

MODES = ["bm25", "dense", "hybrid"]


def first_hit_rank(hit_ids: list[str], expect: list[str]) -> int | None:
    for rank, chunk_id in enumerate(hit_ids, start=1):
        if any(chunk_id.startswith(prefix) for prefix in expect):
            return rank
    return None


def mrr(ranks: list[int | None]) -> float:
    return sum(1.0 / r for r in ranks if r) / max(len(ranks), 1)


def recall_at(ranks: list[int | None], k: int) -> float:
    return sum(1 for r in ranks if r and r <= k) / max(len(ranks), 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="pgx-rag 检索评测")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    service = RetrievalService()
    print(f"语料: {len(service.chunks.order())} chunks | BM25: {'就绪' if service.keywords.ready else '缺失'} "
          f"| 向量: {'就绪' if service.vector_ready else '缺失'}")

    results: dict[str, dict] = {}
    detail: dict[str, dict] = {}
    for mode in MODES:
        ranks: list[int | None] = []
        per_query: dict[str, int | None] = {}
        for item in QUERIES:
            hits = service.search(item["query"], top_k=10, mode=mode)
            rank = first_hit_rank([h.chunk_id for h in hits], item["expect"])
            ranks.append(rank)
            per_query[item["id"]] = rank
        results[mode] = {
            f"R@{args.k}": round(recall_at(ranks, args.k), 3),
            "R@10": round(recall_at(ranks, 10), 3),
            "MRR": round(mrr(ranks), 3),
        }
        detail[mode] = per_query

    header = f"{'问题':<44}" + "".join(f"{m:>10}" for m in results)
    print(header)
    print("-" * len(header))
    for item in QUERIES:
        row = f"{item['id']} {item['query'][:38]:<40}"
        for mode in results:
            rank = detail[mode].get(item["id"])
            row += f"{(f'第{rank}名' if rank else '未命中'):>10}"
        print(row)
    print("-" * len(header))
    for metric in (f"R@{args.k}", "R@10", "MRR"):
        row = f"{metric:<44}"
        for mode in results:
            row += f"{results[mode][metric]:>10.3f}"
        print(row)

    hits = service.search(NO_ANSWER_CASE["query"], top_k=5, mode="hybrid")
    leaks = [h.chunk_id for h in hits if "SLCO1B1" in h.chunk.text]
    print(f"\n证据不足案例：返回 {len(hits)} 条，含 SLCO1B1 的 {len(leaks)} 条")

    if args.write_report:
        _write_report(service, results, detail, args.k, len(hits), len(leaks))
    return 0


def _write_report(service: RetrievalService, results: dict, detail: dict, k: int, n_hits: int, n_leak: int) -> None:
    lines = [
        "# 阶段 2 · 检索层报告（app/ 分层版）",
        "",
        f"- 语料：{len(service.chunks.order())} chunks",
        f"- 向量后端：{'就绪' if service.vector_ready else '缺失'}",
        "",
        "| 问题 | " + " | ".join(results) + " |",
        "|---" * (len(results) + 1) + "|",
    ]
    for item in QUERIES:
        cells = [f"第{detail[m].get(item['id'])}名" if detail[m].get(item["id"]) else "未命中" for m in results]
        lines.append(f"| {item['id']} {item['query']} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("| 指标 | " + " | ".join(results) + " |")
    lines.append("|---" * (len(results) + 1) + "|")
    for metric in (f"R@{k}", "R@10", "MRR"):
        lines.append(f"| {metric} | " + " | ".join(f"{results[m][metric]:.3f}" for m in results) + " |")
    lines.append("")
    lines.append(f"证据不足案例（SLCO1B1 + 辛伐他汀）：返回 {n_hits} 条，其中含该基因 {n_leak} 条 → 交给生成层判断是否拒答。")
    path = PROJECT_ROOT / "reports" / "stage2_retrieval.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n报告: {path}")
    (PROJECT_ROOT / "reports" / "stage2_retrieval.json").write_text(
        json.dumps({"results": results, "detail": detail}, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    raise SystemExit(main())
