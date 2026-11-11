"""向量化客户端：TEI（Docker 推理服务）与 DashScope（云端 API）两种后端。

两者对外接口一致，切换只改 `conf/app_config.yaml` 的 `embedding.backend`：

* `tei`      ：`POST {host}:{port}/embed {"inputs": [...]}`，模型跑在容器里（bge-large-zh-v1.5），
               生产形态、离线可用、无 API 成本；
* `dashscope`：阿里通义 `text-embedding-v4`（1024 维、多语言），
               Docker 还没就绪时的可用方案；用 httpx 直连 REST，不依赖 SDK。
"""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
import numpy as np

from app.conf.app_config import app_config
from app.core.logger import logger

DASHSCOPE_URL = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
DASHSCOPE_BATCH = 10
_MAX_CHARS = 6000


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    return matrix / np.clip(norms, 1e-12, None)


class EmbeddingClient:
    """统一接口：`dim` / `model_name` / `embed_documents` / `embed_query`。"""

    kind = "base"

    def __init__(self, dim: int, model_name: str) -> None:
        self.dim = dim
        self.model_name = model_name

    def embed_documents(self, texts: list[str], **kwargs) -> np.ndarray:  # pragma: no cover - 由子类实现
        raise NotImplementedError

    def embed_query(self, text: str) -> np.ndarray:  # pragma: no cover
        raise NotImplementedError

    def health(self) -> tuple[bool, str]:
        return True, "未实现健康检查"


class DashScopeEmbedding(EmbeddingClient):
    kind = "dashscope"

    def __init__(self) -> None:
        cfg = app_config.embedding
        super().__init__(dim=cfg.dimension, model_name=cfg.dashscope_model)
        self.batch_size = min(cfg.batch_size, DASHSCOPE_BATCH)
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            import os

            key = os.environ.get("DASHSCOPE_API_KEY", "")
            if not key:
                raise RuntimeError("缺少 DASHSCOPE_API_KEY（.env 里的 Qwen_key）")
            self._client = httpx.Client(
                timeout=60, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            )
        return self._client

    def _embed(self, texts: list[str], text_type: str) -> list[list[float]]:
        body = {
            "model": self.model_name,
            "input": {"texts": [t[:_MAX_CHARS] for t in texts]},
            "parameters": {"dimension": self.dim, "text_type": text_type},
        }
        last: Exception | None = None
        for attempt in range(5):
            try:
                response = self.client.post(DASHSCOPE_URL, json=body)
                if response.status_code == 200:
                    return [item["embedding"] for item in response.json()["output"]["embeddings"]]
                if response.status_code in (429, 500, 503):
                    last = RuntimeError(f"HTTP {response.status_code}")
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"DashScope {response.status_code}: {response.text[:200]}")
            except RuntimeError:
                raise
            except Exception as exc:  # noqa: BLE001 - 网络抖动
                last = exc
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"embedding 失败: {last}")

    def embed_documents(
        self,
        texts: list[str],
        *,
        cache_path: Path | None = None,
        workers: int = 4,
        **_,
    ) -> np.ndarray:
        """并发编码 + 断点续传（按批次内容哈希做键，语料顺序变了也不会错用缓存）。"""
        from app.core.text import sha1

        size = self.batch_size
        batches = [(i, texts[i : i + size]) for i in range(0, len(texts), size)]
        done: dict[str, list[list[float]]] = {}

        if cache_path and cache_path.exists():
            skipped = 0
            for line in cache_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = json.loads(line)
                key = record.get("k")
                if not key:      # 旧版缓存按批次下标存（i 键），与内容哈希不兼容，跳过
                    skipped += 1
                    continue
                done[key] = record["v"]
            if done:
                logger.info("embedding 断点续传：命中 {} 批缓存（跳过 {} 条旧格式）", len(done), skipped)

        def key_of(batch: list[str]) -> str:
            return sha1("||".join(t[:500] for t in batch))

        pending = [(i, b) for i, b in batches if key_of(b) not in done]
        handle = cache_path.open("a", encoding="utf-8") if cache_path else None
        lock = threading.Lock()

        try:
            with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
                futures = {
                    pool.submit(self._embed, batch, "document"): (start, key_of(batch))
                    for start, batch in pending
                }
                for count, future in enumerate(as_completed(futures), start=1):
                    start, key = futures[future]
                    vectors = future.result()
                    with lock:
                        done[key] = vectors
                        if handle:
                            handle.write(json.dumps({"k": key, "v": vectors}) + "\n")
                            handle.flush()
                    if count % 20 == 0:
                        logger.info("编码进度 {}/{} 批", count, len(pending))
        finally:
            if handle:
                handle.close()

        ordered = [done[key_of(batch)] for _, batch in batches]
        return _normalize(np.asarray([v for batch in ordered for v in batch], dtype=np.float32))

    def embed_query(self, text: str) -> np.ndarray:
        vector = np.asarray(self._embed([text], "query")[0], dtype=np.float32)
        return _normalize(vector.reshape(1, -1))[0]

    def health(self) -> tuple[bool, str]:
        try:
            self._embed(["health check"], "query")
            return True, f"{self.model_name} 可用"
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"[:80]


class TEIEmbedding(EmbeddingClient):
    kind = "tei"

    def __init__(self) -> None:
        cfg = app_config.embedding
        super().__init__(dim=cfg.dimension, model_name=cfg.model)
        self.url = f"http://{cfg.host}:{cfg.port}"
        self.batch_size = 16

    def embed_documents(self, texts: list[str], *, cache_path: Path | None = None, workers: int = 1, **_) -> np.ndarray:
        vectors: list[list[float]] = []
        with httpx.Client(timeout=120) as client:
            for start in range(0, len(texts), self.batch_size):
                batch = [t[:_MAX_CHARS] for t in texts[start : start + self.batch_size]]
                response = client.post(f"{self.url}/embed", json={"inputs": batch, "truncate": True})
                response.raise_for_status()
                vectors.extend(response.json())
                if start % (self.batch_size * 20) == 0:
                    logger.info("TEI 编码进度 {}/{}", min(start + self.batch_size, len(texts)), len(texts))
        return _normalize(np.asarray(vectors, dtype=np.float32))

    def embed_query(self, text: str) -> np.ndarray:
        with httpx.Client(timeout=60) as client:
            response = client.post(f"{self.url}/embed", json={"inputs": [text], "truncate": True})
            response.raise_for_status()
            vector = np.asarray(response.json()[0], dtype=np.float32)
        return _normalize(vector.reshape(1, -1))[0]

    def health(self) -> tuple[bool, str]:
        try:
            with httpx.Client(timeout=10) as client:
                return client.get(f"{self.url}/health").status_code == 200, self.url
        except Exception as exc:  # noqa: BLE001
            return False, f"{type(exc).__name__}: {exc}"[:80]


def make_embedding_client(fallback: bool = True) -> EmbeddingClient:
    """按配置选后端；TEI 不可达时自动回退到云端（仅开发期）。

    `conf/app_config.yaml` 里 `embedding.backend` 表达的是**目标形态**（TEI 容器），
    Docker 还没就绪时不让整条链路直接崩掉，而是回退到 DashScope 并把原因写进日志——
    这样"环境没起全"和"代码有 bug"能区分开。
    """
    backend = app_config.embedding.backend.lower()
    if backend == "tei":
        client = TEIEmbedding()
        ok, note = client.health()
        if ok:
            return client
        if fallback:
            logger.warning("TEI 不可用（{}），本次回退到 DashScope embedding", note)
            return DashScopeEmbedding()
        raise RuntimeError(f"TEI 不可用：{note}")
    if backend == "dashscope":
        return DashScopeEmbedding()
    raise ValueError(f"未知 embedding.backend: {backend}")
