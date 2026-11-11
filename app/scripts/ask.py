"""命令行问诊：一个问题 → 带引用的循证回答。

    uv run python -m app.scripts.ask "CYP2C19 慢代谢型患者用氯吡格雷会怎样？"
    uv run python -m app.scripts.ask "..." --json       # 给程序用
    uv run python -m app.scripts.ask "..." --top 8 --no-graph   # 直接走服务，不经 LangGraph
"""

from __future__ import annotations

import argparse
import json

from app.agent.graph import ask as ask_with_graph
from app.core.logger import logger
from app.services.generation_service import Answer, GenerationService


def _print(answer: Answer, width: int) -> None:
    a = answer.assessment
    print("=" * 96)
    print(f"问题：{answer.question}")
    print(f"证据等级：{a.level}（{a.reason}）")
    print(f"检索：{len(answer.hits)} 条 · 其中含目标基因 {a.gene_hits} 条 · 表格 {a.table_hits} 条"
          f" · 出现剂量 {a.has_dose} · 耗时 {answer.latency_ms} ms")
    if answer.refused:
        print("状态：⛔ 已拒答（证据不足）")
    print("-" * 96)
    print(answer.answer)
    print("-" * 96)
    if answer.citations:
        print("引用：")
        for c in answer.citations:
            print(f"  {c.label()}  ·  chunk={c.chunk_id}")
            if c.dailymed_url:
                print(f"      {c.dailymed_url}")
    if answer.uncited_sentences:
        print(f"\n⚠ 有 {len(answer.uncited_sentences)} 句没有引用标记：")
        for s in answer.uncited_sentences[:3]:
            print(f"  · {s[:width]}")
    print("=" * 96)


def main() -> int:
    parser = argparse.ArgumentParser(description="pgx-rag 循证问诊")
    parser.add_argument("question")
    parser.add_argument("--top", type=int, default=None)
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--no-graph", action="store_true", help="不经 LangGraph，直接调用生成服务")
    parser.add_argument("--width", type=int, default=80)
    args = parser.parse_args()

    if args.no_graph:
        answer = GenerationService().answer(args.question, top_k=args.top)
    else:
        answer = ask_with_graph(args.question, top_k=args.top)

    if args.json:
        print(json.dumps(answer.as_dict(), ensure_ascii=False, indent=2))
    else:
        _print(answer, args.width)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
