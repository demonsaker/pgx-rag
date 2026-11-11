"""生成服务：检索 → 证据分级 → （拒答 | 调用大模型）→ 引用回填。

三条不可妥协的规则：
1. **先判证据、再生成**。证据不足（D 级）时不调模型，直接给出结构化拒答——
   让护栏不依赖"模型是否愿意听话"。
2. **引用要可回填**。模型输出里的 `[n]` 必须能映射回具体 chunk；
   解析不到的按"无依据句"标出来，不能装作有引用。
3. **拒答要说清楚缺什么**。只说"无法回答"没有价值，要指出是哪个基因、哪类证据缺失。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import httpx

from app.conf.app_config import app_config
from app.core.evidence import EvidenceAssessment, assess
from app.core.logger import logger
from app.core.query import plan_query
from app.entities.schemas import Citation, SearchHit
from app.prompt.loader import render_prompt
from app.services.retrieval_service import RetrievalService

_CITATION = re.compile(r"\[(\d{1,2})\]")
# 只在句末标点/换行处切句：中文分号常在一句话内部，按分号切会把一句拆成两半，
# 导致"后半句没有引用"的假阳性。
_SENTENCE = re.compile(r"[^。！？\n]+[。！？]?")


@dataclass
class Answer:
    question: str
    answer: str
    citations: list[Citation]
    assessment: EvidenceAssessment
    refused: bool = False
    hits: list[SearchHit] = field(default_factory=list)
    uncited_sentences: list[str] = field(default_factory=list)
    latency_ms: int = 0
    usage: dict | None = None

    def as_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "refused": self.refused,
            "evidence": self.assessment.as_dict(),
            "citations": [
                {
                    "index": c.index,
                    "chunk_id": c.chunk_id,
                    "drug": c.drug,
                    "section": c.section_label,
                    "effective_date": c.effective_date,
                    "set_id": c.set_id,
                    "dailymed_url": c.dailymed_url,
                }
                for c in self.citations
            ],
            "uncited_sentences": self.uncited_sentences,
            "latency_ms": self.latency_ms,
            "usage": self.usage,
        }


class GenerationService:
    def __init__(self, retrieval: RetrievalService | None = None) -> None:
        self.retrieval = retrieval or RetrievalService()
        cfg = app_config.llm
        self.model = cfg.model_name
        self.base_url = cfg.base_url.rstrip("/")
        self.api_key = cfg.api_key

    # ---------------------------------------------------------------- 主流程
    def answer(self, question: str, top_k: int | None = None, exclude: set[str] | None = None) -> Answer:
        started = time.perf_counter()
        plan = plan_query(question)
        hits = self.retrieval.search(question, top_k=top_k, exclude=exclude)
        assessment = assess(hits, plan)
        logger.info(
            "问题「{}」→ 命中 {} 条，证据等级 {}（{}）",
            question, len(hits), assessment.level, assessment.reason,
        )

        if assessment.should_refuse:
            return self._refusal(question, assessment, hits, started)

        context = self._build_context(hits)
        messages = [
            {"role": "system", "content": self._system_prompt(context)},
            {"role": "user", "content": question},
        ]
        text, usage = self._chat(messages)
        citations, uncited = self._parse_citations(text, hits)
        return Answer(
            question=question,
            answer=text.strip(),
            citations=citations,
            assessment=assessment,
            hits=hits,
            uncited_sentences=uncited,
            latency_ms=int((time.perf_counter() - started) * 1000),
            usage=usage,
        )

    # ---------------------------------------------------------------- 拒答
    def _refusal(self, question: str, assessment: EvidenceAssessment, hits: list[SearchHit], started: float) -> Answer:
        plan = plan_query(question)
        genes = "/".join(plan.genes) if plan.genes else "目标基因"
        drugs = "/".join(plan.drugs) if plan.drugs else "该药"
        text = (
            f"结论：现有说明书证据不足以回答该问题（证据等级 D）。\n"
            f"依据：\n"
            f"- 已检索 {len(hits)} 条与 {drugs} 相关的说明书段落，但没有任何一条提及 {genes}。\n"
            f"- 说明书（SPL）未收录该基因的相关内容，因此不能据此推断基因型与用药的关系。\n"
            f"注意：该药的基因-药物证据可能只存在于 CPIC 指南或 PharmGKB 注释中，"
            f"当前知识库尚未收录这两类来源；需要时请以 CPIC 指南为准，并由临床药师判断。"
        )
        return Answer(
            question=question,
            answer=text,
            citations=[],
            assessment=assessment,
            refused=True,
            hits=hits,
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    # ---------------------------------------------------------------- 上下文
    def _system_prompt(self, context: str) -> str:
        return render_prompt("answer_system.md", context=context)

    def _build_context(self, hits: list[SearchHit]) -> str:
        blocks: list[str] = []
        for index, hit in enumerate(hits, start=1):
            chunk = hit.chunk
            ev = chunk.evidence or {}
            kind = "表格" if chunk.kind == "table" else "正文"
            text = " ".join(chunk.text.split())
            if len(text) > 1000:
                text = text[:1000] + "…"
            blocks.append(
                f"[{index}] 药品：{chunk.drug} · 章节：{chunk.section_label} · "
                f"生效日期：{ev.get('effective_date', '未知')} · 类型：{kind} · "
                f"基因标注：{'/'.join(chunk.pgx.get('genes', [])) or '无'}\n{text}"
            )
        return "\n\n".join(blocks)

    # ---------------------------------------------------------------- 调用
    def _chat(self, messages: list[dict]) -> tuple[str, dict | None]:
        if not self.api_key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY（.env）")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 900,
            "stream": False,
        }
        last: Exception | None = None
        for attempt in range(3):
            try:
                response = httpx.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=90,
                )
                if response.status_code == 200:
                    data = response.json()
                    return data["choices"][0]["message"]["content"], data.get("usage")
                last = RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
            except Exception as exc:  # noqa: BLE001 - 网络抖动重试
                last = exc
            time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"大模型调用失败：{last}")

    # ---------------------------------------------------------------- 引用
    def _parse_citations(self, text: str, hits: list[SearchHit]) -> tuple[list[Citation], list[str]]:
        orders: list[int] = []
        for raw in _CITATION.findall(text):
            index = int(raw)
            if 1 <= index <= len(hits) and index not in orders:
                orders.append(index)

        citations = [Citation.from_hit(index, hits[index - 1]) for index in orders]

        uncited: list[str] = []
        for sentence in _SENTENCE.findall(text):
            stripped = sentence.strip(" \t-·")
            if len(stripped) < 12 or stripped.endswith("："):
                continue
            if "结论：" in stripped or "注意：" in stripped:
                continue
            if not _CITATION.search(stripped):
                uncited.append(stripped)
        return citations, uncited
