"""CPIC 客户端：抓取权威的「基因-药物」结构化数据。

CPIC 官方 API（`api.cpicpgx.org/v1`，PostgREST）提供的是**结构化表**，不是 PDF：

* `/pair`           基因-药对，含 `cpiclevel`(A/B/C/D) 与 `pgxtesting`(Testing Required / Actionable PGx)
* `/recommendation` 按表型的推荐，含 `classification`(Strong/Moderate/Optional)、`drugrecommendation`、`implications`
* `/diplotype`      星号型 → 表型映射（`CYP2C19 *2/*3` → Intermediate Metabolizer）
* `/allele`         等位基因功能状态与活性值

为什么这件事关键：说明书（SPL）经常**不收录**某些基因（实测 simvastatin 50 个标签里
SLCO1B1 出现 0 次），而 CPIC 有——两个源互补，才能在专业场景站得住。
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from app.core.logger import logger

BASE_URL = "https://api.cpicpgx.org/v1"
USER_AGENT = "pgx-rag/0.1 (pharmacogenomics RAG demo)"


class CpicClient:
    def __init__(self, base_url: str = BASE_URL, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT})

    def _get(self, endpoint: str, **params: Any) -> list[dict]:
        url = f"{self.base_url}/{endpoint}"
        last: Exception | None = None
        for attempt in range(4):
            try:
                response = self.client.get(url, params=params)
                if response.status_code == 200:
                    data = response.json()
                    return data if isinstance(data, list) else [data]
                if response.status_code in (429, 500, 502, 503, 504):
                    last = RuntimeError(f"HTTP {response.status_code}")
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"CPIC {endpoint} -> HTTP {response.status_code}: {response.text[:160]}")
            except RuntimeError:
                raise
            except Exception as exc:  # noqa: BLE001 - 网络抖动
                last = exc
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"CPIC {endpoint} 抓取失败: {last}")

    # ------------------------------------------------------------------ 基础表
    def drugs(self) -> list[dict]:
        return self._get("drug", limit=5000)

    def pairs(self) -> list[dict]:
        return self._get("pair", limit=5000)

    def recommendations(self) -> list[dict]:
        return self._get("recommendation", limit=10000)

    def diplotypes(self, genes: list[str] | None = None) -> list[dict]:
        rows = self._get("diplotype", limit=20000)
        if genes:
            wanted = {g.upper() for g in genes}
            rows = [r for r in rows if str(r.get("genesymbol", "")).upper() in wanted]
        return rows

    def alleles(self, genes: list[str] | None = None) -> list[dict]:
        rows = self._get("allele", limit=20000)
        if genes:
            wanted = {g.upper() for g in genes}
            rows = [r for r in rows if str(r.get("genesymbol", "")).upper() in wanted]
        return rows

    def gene_results(self, genes: list[str] | None = None) -> list[dict]:
        """表型级结果：result（Poor Metabolizer…）+ 解读文本 + EHR 风险优先级。

        注意：CPIC 只对 CYP2D6/DPYD/CYP3A5 提供「双倍型 → 表型」表；
        CYP2C19 这类要靠等位基因功能规则推导，或直接由检验报告给出表型。
        """
        rows = self._get("gene_result", limit=20000)
        if genes:
            wanted = {g.upper() for g in genes}
            rows = [r for r in rows if str(r.get("genesymbol", "")).upper() in wanted]
        return rows

    def guidelines(self) -> list[dict]:
        return self._get("guideline", limit=5000)

    def close(self) -> None:
        self.client.close()


def filter_for_drugs(
    *,
    pairs: list[dict],
    recommendations: list[dict],
    drugs: list[dict],
    drug_names: list[str],
) -> tuple[list[dict], list[dict], list[str]]:
    """把全量 CPIC 数据收敛到我们关心的药。

    返回（pairs, recommendations, 命中的基因集合）。
    """
    name_to_id = {str(d.get("name", "")).lower(): d.get("drugid") for d in drugs}
    ids = {name_to_id[name.lower()] for name in drug_names if name.lower() in name_to_id}
    missing = [name for name in drug_names if name.lower() not in name_to_id]

    my_pairs = [p for p in pairs if p.get("drugid") in ids and not p.get("removed")]
    my_recs = [r for r in recommendations if r.get("drugid") in ids]
    genes = sorted({p.get("genesymbol") for p in my_pairs if p.get("genesymbol")})

    if missing:
        logger.warning("CPIC 里找不到这些药的 drugid：{}", missing)
    logger.info("CPIC 收敛：{} 个药 -> {} 个 pair / {} 条推荐 / 基因 {}", len(ids), len(my_pairs), len(my_recs), genes)
    return my_pairs, my_recs, genes
