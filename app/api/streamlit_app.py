"""Demo 页面（Streamlit）：输入药物/基因/表型/场景 → RAG 回答 + CPIC 标准答案对照。

    uv run streamlit run app/api/streamlit_app.py

定位：RAG 是主体（通俗、指令清晰、逐句引用），CPIC 查表是同屏可见的**标准答案**，
方便药师一眼比对"系统说的"和"指南说的"是否一致。
"""

from __future__ import annotations

import asyncio

import streamlit as st
from sqlalchemy import select

from app.clients.mysql import make_engine, make_session_factory
from app.core.logger import logger
from app.entities.drugs import DRUGS
from app.models.orm import CpicGeneResult, CpicRecommendation
from app.services.evidence_card import EvidenceCardService
from app.services.generation_service import GenerationService

st.set_page_config(page_title="pgx-rag · 药物基因组学证据核对", page_icon="💊", layout="wide")


@st.cache_resource
def get_generation() -> GenerationService:
    return GenerationService()


@st.cache_resource
def get_cards() -> EvidenceCardService:
    return EvidenceCardService()


@st.cache_data(show_spinner=False)
def load_phenotypes() -> dict[str, list[str]]:
    """基因 -> 可选表型（来自 CPIC 推荐与表型解读两处）。"""

    async def query():
        engine = make_engine()
        factory = make_session_factory(engine)
        try:
            async with factory() as session:
                recs = (await session.execute(select(CpicRecommendation))).scalars().all()
                results = (await session.execute(select(CpicGeneResult))).scalars().all()
        finally:
            await engine.dispose()
        mapping: dict[str, set[str]] = {}
        for rec in recs:
            for gene, value in (rec.phenotypes or {}).items():
                if value:
                    mapping.setdefault(gene, set()).add(value)
            for gene, value in (rec.allelestatus or {}).items():
                if value:
                    mapping.setdefault(gene, set()).add(value)
        for row in results:
            if row.result:
                mapping.setdefault(row.genesymbol, set()).add(row.result)
        return {gene: sorted(values) for gene, values in mapping.items()}

    return asyncio.run(query())


@st.cache_data(show_spinner=False)
def load_contexts(drug: str, gene: str) -> list[str]:
    async def query():
        engine = make_engine()
        factory = make_session_factory(engine)
        try:
            async with factory() as session:
                recs = (await session.execute(select(CpicRecommendation))).scalars().all()
        finally:
            await engine.dispose()
        return sorted({(rec.population or "").strip() for rec in recs if rec.population})

    return asyncio.run(query())


PHENOTYPE_ORDER = [
    "Poor Metabolizer", "Likely Poor Metabolizer", "Intermediate Metabolizer",
    "Normal Metabolizer", "Rapid Metabolizer", "Ultrarapid Metabolizer",
    "Decreased Function", "Normal Function", "Poor Function",
]


def sort_phenotypes(values: list[str]) -> list[str]:
    def key(value: str):
        for index, name in enumerate(PHENOTYPE_ORDER):
            if value.lower() == name.lower():
                return (index, value)
        return (len(PHENOTYPE_ORDER), value)

    return sorted(values, key=key)


# ---------------------------------------------------------------------- 侧边栏
st.sidebar.header("查询条件")
drug_options = {d["drug"]: d for d in DRUGS}
drug = st.sidebar.selectbox("药物", sorted(drug_options), index=sorted(drug_options).index("clopidogrel"))

genes = drug_options[drug].get("genes") or []
phenotype_map = load_phenotypes()
gene = st.sidebar.selectbox("基因", genes if genes else ["CYP2C19"])

candidates = phenotype_map.get(gene, [])
if not candidates:
    st.sidebar.warning(f"CPIC 里没有 {gene} 的表型值，可手填")
    phenotype = st.sidebar.text_input("表型（手填）", "Poor Metabolizer")
else:
    phenotype = st.sidebar.selectbox("表型 / 等位基因状态", sort_phenotypes(candidates))

context = st.sidebar.text_input("临床场景（可选，如 CVI ACS PCI）", "")

default_question = f"患者 {gene} 检测结果为「{phenotype}」，能否使用 {drug}？"
if context.strip():
    default_question += f"（临床场景：{context.strip()}）"
question = st.sidebar.text_area("问题（可改写）", default_question, height=96)

run = st.sidebar.button("生成", type="primary", use_container_width=True)

# ---------------------------------------------------------------------- 主体
st.title("💊 pgx-rag · 药物基因组学证据核对")
st.caption("RAG 给通俗、可执行的答案并逐句引用；CPIC 标准答案同屏对照。数据源：FDA 说明书 + CPIC 指南。")

col_left, col_right = st.columns([3, 2], gap="large")

with col_left:
    st.subheader("① RAG 回答（主体）")
    if not run:
        st.info("左侧选择「药物 / 基因 / 表型」，点「生成」。")
    else:
        with st.spinner("检索 + 生成中…"):
            answer = get_generation().answer(question)
        level = answer.assessment
        badge = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴"}.get(level.level, "⚪")
        st.markdown(f"{badge} **证据等级 {level.level}** · {level.reason}")
        if answer.refused:
            st.error(answer.answer)
        else:
            st.markdown(answer.answer)
        st.caption(f"检索 {len(answer.hits)} 条 · 引用 {len(answer.citations)} 处 · 耗时 {answer.latency_ms} ms")

        if answer.uncited_sentences:
            with st.expander(f"⚠ {len(answer.uncited_sentences)} 句没有引用标记", expanded=False):
                for sentence in answer.uncited_sentences:
                    st.write(f"- {sentence}")

        if answer.citations:
            with st.expander("引用原文（点开核对）", expanded=False):
                for citation in answer.citations:
                    hit = next((h for h in answer.hits if h.chunk_id == citation.chunk_id), None)
                    st.markdown(f"**[{citation.index}] {citation.label()}**")
                    if hit:
                        st.code(" ".join(hit.chunk.text.split())[:900], language="text")
                    st.caption(citation.chunk_id)

with col_right:
    st.subheader("② CPIC 标准答案对照")
    if run:
        with st.spinner("查询 CPIC 指南…"):
            try:
                card = get_cards().build(drug, phenotype, gene=gene, context=context.strip() or None)
            except Exception as exc:  # noqa: BLE001 - demo 页面不因单次失败崩溃
                st.warning(f"证据卡生成失败：{exc}")
                card = None
        if card:
            st.markdown(
                f"**CPIC 等级** {card.cpic_level or '未收录'} · "
                f"**检测建议** {card.pgx_testing or '未标注'}"
            )
            if card.phenotype_risk:
                st.caption(f"表型风险：{card.phenotype_risk}")
            if not card.recommendations:
                st.warning("该表型在 CPIC 中没有对应推荐（可能只有剂量表或研究性证据）")
            for rec in card.recommendations[:6]:
                ctx = rec.get("population") or "未标注场景"
                st.markdown(f"- **[{ctx}]** `{rec.get('classification')}` {rec.get('drugrecommendation')}")
            verdict = card.consistency.get("verdict")
            color = {"一致": "green", "指南更严格": "blue", "说明书更保守": "blue",
                     "存在明显差异": "red", "说明书未收录该基因": "orange"}.get(verdict, "gray")
            st.markdown(f"**一致性**：:{color}[{verdict}]")
            st.caption(card.consistency.get("note", ""))
            with st.expander("说明书侧原文", expanded=not card.gene_in_label):
                if card.label_note:
                    st.warning(card.label_note)
                for chunk in card.label_chunks[:4]:
                    st.markdown(f"**{chunk['section_label']}**（{chunk['effective_date']}） `{chunk['chunk_id']}`")
                    st.code(chunk["snippet"], language="text")
    else:
        st.info("生成后显示 CPIC 推荐、说明书原文与一致性判定。")

st.divider()
st.caption("说明：本工具用于证据核验，不构成诊疗建议；RAG 答案的每一句都可点开引用核对原文。")
