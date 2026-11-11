"""ORM 模型：与 docker/mysql/init/01_schema.sql 的表结构一一对应。

为什么 SQL 与 ORM 各维护一份：
* SQL 负责「容器首次启动就建好库」，不依赖 Python 进程；
* ORM 负责「代码里类型安全地读写」。
两者字段必须一致——`init_meta_db.py` 会用 ORM 的 `create_all` 补齐缺失表，
所以改表结构时以这里为准，再同步更新 SQL。
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, JSON, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT, MEDIUMTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# MySQL 用 MEDIUMTEXT/LONGTEXT，SQLite 没有这些类型 → 用 Text 兜底
LongText = Text().with_variant(MEDIUMTEXT(), "mysql")
HugeText = Text().with_variant(LONGTEXT(), "mysql")


class Base(DeclarativeBase):
    pass


class Drug(Base):
    __tablename__ = "drugs"

    drug: Mapped[str] = mapped_column(String(64), primary_key=True)
    drug_class: Mapped[str | None] = mapped_column(String(128))
    genes: Mapped[list | None] = mapped_column(JSON)
    topic: Mapped[str | None] = mapped_column(String(255))


class Document(Base):
    __tablename__ = "documents"

    set_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    drug: Mapped[str] = mapped_column(String(64), index=True)
    label_id: Mapped[str | None] = mapped_column(String(64))
    brand_name: Mapped[str | None] = mapped_column(String(255))
    manufacturer: Mapped[str | None] = mapped_column(String(255))
    route: Mapped[str | None] = mapped_column(String(64))
    effective_date: Mapped[date | None] = mapped_column(Date)
    ingredient_count: Mapped[int] = mapped_column(SmallInteger, default=1)
    api_url: Mapped[str | None] = mapped_column(Text)
    dailymed_url: Mapped[str | None] = mapped_column(Text)


class ChunkRow(Base):
    __tablename__ = "chunks"

    chunk_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    set_id: Mapped[str | None] = mapped_column(String(64))
    drug: Mapped[str] = mapped_column(String(64), index=True)
    drug_class: Mapped[str | None] = mapped_column(String(128))
    section: Mapped[str] = mapped_column(String(128), index=True)
    section_label: Mapped[str | None] = mapped_column(String(255))
    section_priority: Mapped[int] = mapped_column(SmallInteger, default=5, index=True)
    kind: Mapped[str] = mapped_column(String(8), index=True)
    heading: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(LongText)
    chars: Mapped[int] = mapped_column(Integer, default=0)
    est_tokens: Mapped[int] = mapped_column(Integer, default=0)
    pgx_genes: Mapped[list | None] = mapped_column(JSON)
    pgx_phenotypes: Mapped[list | None] = mapped_column(JSON)
    pgx_alleles: Mapped[list | None] = mapped_column(JSON)
    is_pgx: Mapped[int] = mapped_column(SmallInteger, default=0, index=True)
    table_id: Mapped[str | None] = mapped_column(String(64))
    row_start: Mapped[int | None] = mapped_column(Integer)
    row_end: Mapped[int | None] = mapped_column(Integer)
    evidence: Mapped[dict | None] = mapped_column(JSON)


class LabelTableRow(Base):
    __tablename__ = "label_tables"

    table_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    drug: Mapped[str] = mapped_column(String(64), index=True)
    section: Mapped[str] = mapped_column(String(128))
    caption: Mapped[str | None] = mapped_column(Text)
    headers: Mapped[list | None] = mapped_column(JSON)
    rows: Mapped[list | None] = mapped_column(HugeText)   # 二维数组 JSON（MySQL 用 LONGTEXT）
    n_rows: Mapped[int] = mapped_column(Integer, default=0)
    n_cols: Mapped[int] = mapped_column(Integer, default=0)
    header_source: Mapped[str | None] = mapped_column(String(16))
    has_rowspan: Mapped[int] = mapped_column(SmallInteger, default=0)
    has_colspan: Mapped[int] = mapped_column(SmallInteger, default=0)
    footnotes: Mapped[list | None] = mapped_column(JSON)
    html_sha: Mapped[str | None] = mapped_column(String(40))
    html: Mapped[str | None] = mapped_column(LongText)


class IndexBuild(Base):
    __tablename__ = "index_builds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    target: Mapped[str] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(128))
    chunks: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------- CPIC（指南侧证据）
class CpicPair(Base):
    """基因-药对：CPIC 证据等级与检测建议。"""

    __tablename__ = "cpic_pair"

    pairid: Mapped[int] = mapped_column(Integer, primary_key=True)
    genesymbol: Mapped[str] = mapped_column(String(32), index=True)
    drugid: Mapped[str | None] = mapped_column(String(64), index=True)
    guidelineid: Mapped[int | None] = mapped_column(Integer)
    cpiclevel: Mapped[str | None] = mapped_column(String(8))
    pgxtesting: Mapped[str | None] = mapped_column(String(32))
    usedforrecommendation: Mapped[int | None] = mapped_column(SmallInteger)


class CpicRecommendation(Base):
    """按表型的用药推荐：分类（Strong/Moderate/Optional）+ 推荐原文。"""

    __tablename__ = "cpic_recommendation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guidelineid: Mapped[int | None] = mapped_column(Integer, index=True)
    drugid: Mapped[str | None] = mapped_column(String(64), index=True)
    classification: Mapped[str | None] = mapped_column(String(32), index=True)
    phenotypes: Mapped[dict | None] = mapped_column(JSON)
    allelestatus: Mapped[dict | None] = mapped_column(JSON)
    implications: Mapped[dict | None] = mapped_column(JSON)
    drugrecommendation: Mapped[str | None] = mapped_column(Text)
    activityscore: Mapped[dict | None] = mapped_column(JSON)
    population: Mapped[str | None] = mapped_column(String(64))
    comments: Mapped[str | None] = mapped_column(Text)


class CpicDiplotype(Base):
    """星号型 → 表型映射：把检测报告的 `CYP2C19 *2/*3` 翻译成表型。"""

    __tablename__ = "cpic_diplotype"

    genesymbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    diplotype: Mapped[str] = mapped_column(String(191), primary_key=True)
    generesult: Mapped[str | None] = mapped_column(String(64), index=True)
    totalactivityscore: Mapped[str | None] = mapped_column(String(16))
    ehrpriority: Mapped[str | None] = mapped_column(String(32))
    consultationtext: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)


class CpicGeneResult(Base):
    """表型级结果：`Poor Metabolizer` 这类结论 + 解读文本 + 风险优先级。"""

    __tablename__ = "cpic_gene_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    genesymbol: Mapped[str] = mapped_column(String(32), index=True)
    result: Mapped[str | None] = mapped_column(String(64), index=True)
    activityscore: Mapped[str | None] = mapped_column(String(16))
    ehrpriority: Mapped[str | None] = mapped_column(String(64))
    consultationtext: Mapped[str | None] = mapped_column(Text)


__all__ = [
    "Base", "Drug", "Document", "ChunkRow", "LabelTableRow", "IndexBuild",
    "CpicPair", "CpicRecommendation", "CpicDiplotype", "CpicGeneResult",
]
