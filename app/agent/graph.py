"""问诊工作流（LangGraph）：检索 → 证据分级 → 拒答/生成 → 引用回填。

为什么用图而不是一条直线：
「证据不足就直接拒答」是一个**条件分支**，而且拒答分支不需要调用大模型——
用图表达能把这个决策显式化，日后加"追问""改写查询""多轮澄清"时不用重构。

    START → retrieve → assess ─┬→ refuse  → finalize → END
                               └→ generate → finalize → END
"""

from __future__ import annotations

import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.evidence import EvidenceAssessment, assess
from app.core.query import plan_query
from app.entities.schemas import SearchHit
from app.services.generation_service import Answer, GenerationService


class AskState(TypedDict, total=False):
    question: str
    top_k: int
    hits: list[SearchHit]
    assessment: EvidenceAssessment
    draft: str
    usage: dict | None
    answer: Answer
    started: float


def build_graph(service: GenerationService):
    def retrieve(state: AskState) -> AskState:
        question = state["question"]
        hits = service.retrieval.search(question, top_k=state.get("top_k"))
        return {"hits": hits}

    def assess_node(state: AskState) -> AskState:
        plan = plan_query(state["question"])
        return {"assessment": assess(state["hits"], plan)}

    def generate(state: AskState) -> AskState:
        context = service._build_context(state["hits"])  # noqa: SLF001 - 同一业务流程内的步骤复用
        messages = [
            {"role": "system", "content": service._system_prompt(context)},  # noqa: SLF001
            {"role": "user", "content": state["question"]},
        ]
        text, usage = service._chat(messages)  # noqa: SLF001
        return {"draft": text, "usage": usage}

    def refuse(state: AskState) -> AskState:
        assessment = state["assessment"]
        plan = plan_query(state["question"])
        genes = "/".join(plan.genes) if plan.genes else "目标基因"
        drugs = "/".join(plan.drugs) if plan.drugs else "该药"
        text = (
            f"结论：现有说明书证据不足以回答该问题（证据等级 {assessment.level}）。\n"
            f"依据：\n"
            f"- 已检索 {len(state['hits'])} 条与 {drugs} 相关的说明书段落，但没有任何一条提及 {genes}。\n"
            f"- 说明书（SPL）未收录该基因的相关内容，因此不能据此推断基因型与用药的关系。\n"
            f"注意：该药的基因-药物证据可能只存在于 CPIC 指南或 PharmGKB 注释中；"
            f"需要时请以 CPIC 指南为准，并由临床药师判断。"
        )
        return {"draft": text}

    def finalize(state: AskState) -> AskState:
        assessment = state["assessment"]
        hits = state["hits"]
        draft = state.get("draft", "")
        refused = assessment.should_refuse
        citations, uncited = ([], []) if refused else service._parse_citations(draft, hits)  # noqa: SLF001
        answer = Answer(
            question=state["question"],
            answer=draft.strip(),
            citations=citations,
            assessment=assessment,
            refused=refused,
            hits=hits,
            uncited_sentences=uncited,
            latency_ms=int((time.perf_counter() - state.get("started", time.perf_counter())) * 1000),
            usage=state.get("usage"),
        )
        return {"answer": answer}

    def route(state: AskState) -> str:
        return "refuse" if state["assessment"].should_refuse else "generate"

    graph = StateGraph(AskState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("assess", assess_node)
    graph.add_node("generate", generate)
    graph.add_node("refuse", refuse)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "assess")
    graph.add_conditional_edges("assess", route, {"refuse": "refuse", "generate": "generate"})
    graph.add_edge("refuse", "finalize")
    graph.add_edge("generate", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


def ask(question: str, *, top_k: int | None = None, service: GenerationService | None = None) -> Answer:
    service = service or GenerationService()
    app = build_graph(service)
    state = app.invoke({"question": question, "top_k": top_k, "started": time.perf_counter()})
    return state["answer"]
