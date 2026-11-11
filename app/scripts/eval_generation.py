"""阶段 3 验收：答案质量 + 引用覆盖 + 拒答正确性。

检查项（都是可判定的，不靠"看起来还行"）：
* 该回答的必须回答、该拒答的必须拒答；
* 引用覆盖率 = 带 [n] 的句子 / 总句子，低于阈值要暴露；
* 引用必须能映射回真实 chunk_id（不能出现越界编号）；
* 拒答时不得编造引用。

    uv run python -m app.scripts.eval_generation
    uv run python -m app.scripts.eval_generation --write-report
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from app.conf.app_config import PROJECT_ROOT
from app.core.logger import logger
from app.services.generation_service import GenerationService

CASES: list[dict] = [
    {"id": "g1", "query": "CYP2C19 慢代谢型患者用氯吡格雷会怎样？", "expect": "answer",
     "must_mention": ["活性代谢物"], "check": "CYP2C19 与抗血小板反应"},
    {"id": "g2", "query": "TPMT 缺陷的患者能用硫唑嘌呤吗？", "expect": "answer",
     "must_mention": ["骨髓"], "check": "TPMT 缺陷与骨髓抑制"},
    {"id": "g3", "query": "HLA-B*57:01 阳性的患者可以吃阿巴卡韦吗？", "expect": "answer",
     "must_mention": ["禁忌", "HLA-B"], "check": "HLA-B*5701 携带者禁忌"},
    {"id": "g4", "query": "CYP2D6 超快代谢的儿童用可待因有什么风险？", "expect": "answer",
     "must_mention": ["呼吸"], "check": "超快代谢与儿童呼吸抑制"},
    {"id": "g5", "query": "DPYD 缺陷的患者用卡培他滨有什么风险？", "expect": "answer",
     "must_mention": ["DPD", "风险"], "check": "DPD 缺陷与严重毒性"},
    {"id": "g6", "query": "CYP2C9 弱代谢者用塞来昔布的起始剂量是多少？", "expect": "answer",
     "must_mention": ["剂量"], "check": "CYP2C9 弱代谢者剂量减半"},
    {"id": "g7", "query": "SLCO1B1 变异的人吃辛伐他汀会肌痛吗？", "expect": "refuse",
     "must_mention": [], "check": "说明书未收录 SLCO1B1 → 必须拒答"},
]

_CITATION = re.compile(r"\[(\d{1,2})\]")
_SENTENCE = re.compile(r"[^。！？\n]{6,}[。！？]?")


def _coverage(text: str) -> float:
    sentences = [s for s in _SENTENCE.findall(text) if not s.strip().endswith("：")]
    if not sentences:
        return 0.0
    cited = sum(1 for s in sentences if _CITATION.search(s))
    return cited / len(sentences)


def main() -> int:
    parser = argparse.ArgumentParser(description="阶段 3 生成层验收")
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()

    service = GenerationService()
    rows: list[dict] = []

    for case in CASES:
        answer = service.answer(case["query"])
        refused = answer.refused
        want_refuse = case["expect"] == "refuse"

        coverage = _coverage(answer.answer)
        markers = [int(m) for m in _CITATION.findall(answer.answer)]
        invalid = [m for m in markers if m < 1 or m > len(answer.hits)]
        mentioned = [kw for kw in case["must_mention"] if kw.lower() in answer.answer.lower()]

        verdict = "PASS"
        reasons: list[str] = []
        if refused != want_refuse:
            verdict = "FAIL"
            reasons.append(f"拒答行为不符（期望 {'拒答' if want_refuse else '回答'}）")
        if not refused:
            if not answer.citations:
                verdict = "FAIL"
                reasons.append("没有可回填的引用")
            if invalid:
                verdict = "FAIL"
                reasons.append(f"引用编号越界：{invalid}")
            if coverage < 0.6:
                verdict = "WARN"
                reasons.append(f"引用覆盖率偏低：{coverage:.0%}")
            if case["must_mention"] and not mentioned:
                verdict = "FAIL"
                reasons.append(f"未提及关键内容：{case['must_mention']}")
        else:
            if answer.citations:
                verdict = "FAIL"
                reasons.append("拒答却带了引用")

        rows.append({
            "id": case["id"], "query": case["query"], "expect": case["expect"],
            "refused": refused, "level": answer.assessment.level,
            "coverage": coverage, "citations": len(answer.citations),
            "latency": answer.latency_ms, "verdict": verdict, "reasons": "; ".join(reasons),
            "answer": answer.answer, "check": case["check"],
        })
        logger.info("{} {} | 等级 {} | 引用 {} | 覆盖 {:.0%} | {} {}",
                    case["id"], "拒答" if refused else "回答", answer.assessment.level,
                    len(answer.citations), coverage, verdict, "; ".join(reasons))

    passed = sum(1 for r in rows if r["verdict"] == "PASS")
    warn = sum(1 for r in rows if r["verdict"] == "WARN")
    failed = sum(1 for r in rows if r["verdict"] == "FAIL")
    avg_latency = sum(r["latency"] for r in rows) / len(rows)
    avg_coverage = sum(r["coverage"] for r in rows if not r["refused"]) / max(
        1, sum(1 for r in rows if not r["refused"])
    )

    print("\n" + "=" * 92)
    print(f"{'用例':<5}{'期望':<8}{'实际':<8}{'等级':<5}{'引用':<6}{'覆盖':<8}{'耗时':<9}{'判定'}")
    print("-" * 92)
    for r in rows:
        print(f"{r['id']:<5}{'拒答' if r['expect'] == 'refuse' else '回答':<8}"
              f"{'拒答' if r['refused'] else '回答':<8}{r['level']:<5}{r['citations']:<6}"
              f"{r['coverage']:<8.0%}{r['latency']:<9}{r['verdict']}  {r['reasons']}")
    print("-" * 92)
    print(f"PASS {passed} / WARN {warn} / FAIL {failed} · 平均耗时 {avg_latency:.0f} ms"
          f" · 平均引用覆盖 {avg_coverage:.0%}")

    if args.write_report:
        _write_report(rows, passed, warn, failed, avg_latency, avg_coverage)
    return 0 if failed == 0 else 1


def _write_report(rows: list[dict], passed: int, warn: int, failed: int, latency: float, coverage: float) -> None:
    refuse_count = sum(1 for r in rows if r["expect"] == "refuse")
    lines = [
        "# 阶段 3 · 生成层验收",
        "",
        f"- 用例：{len(rows)} 个（其中 {refuse_count} 个应拒答）",
        f"- 结果：PASS {passed} / WARN {warn} / FAIL {failed}",
        f"- 平均耗时：{latency:.0f} ms；平均引用覆盖率：{coverage:.0%}",
        "",
        "## 判定规则",
        "",
        "- 该拒答的必须拒答（证据等级 D），且拒答不得带引用；",
        "- 该回答的必须有可回填引用，编号不得越界；",
        "- 引用覆盖率 = 带 `[n]` 的句子 / 总句子，低于 60% 记 WARN；",
        "- 必须命中关键内容（如 TPMT 案例必须提到“骨髓”）。",
        "",
        "## 明细",
        "",
        "| 用例 | 期望 | 实际 | 证据等级 | 引用数 | 引用覆盖率 | 耗时(ms) | 判定 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['id']} {r['query']} | {'拒答' if r['expect'] == 'refuse' else '回答'} | "
            f"{'拒答' if r['refused'] else '回答'} | {r['level']} | {r['citations']} | "
            f"{r['coverage']:.0%} | {r['latency']} | {r['verdict']} |"
        )
    lines += ["", "## 抽样答案", ""]
    for r in rows[:3]:
        lines += [f"### {r['id']} · {r['query']}", "", "```", r["answer"], "```", ""]
    path = PROJECT_ROOT / "reports" / "stage3_generation.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告：{path}")


if __name__ == "__main__":
    raise SystemExit(main())
