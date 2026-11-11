"""基础服务健康检查：一条命令看清哪些服务已就绪、哪些还差。

用法（在项目根目录）：
    uv run python -m app.scripts.check_services

设计成「不抛异常、只报告」：Docker 还没起、或者只想跑 BM25 时，也要能正常退出，
让开发者看清楚缺的是哪一个，而不是被一串 Traceback 淹没。
"""

from __future__ import annotations

import socket
import sys

from app.conf.app_config import app_config
from app.core.logger import logger


def _tcp(host: str, port: int, timeout: float = 1.5) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, "端口可达"
    except OSError as exc:
        return False, f"{type(exc).__name__}: {exc}"


def _http(url: str, timeout: float = 2.5) -> tuple[bool, str]:
    try:
        import httpx

        response = httpx.get(url, timeout=timeout)
        return response.status_code < 500, f"HTTP {response.status_code}"
    except Exception as exc:  # noqa: BLE001 - 健康检查不抛
        return False, f"{type(exc).__name__}: {exc}"[:80]


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    # MySQL
    ok, note = _tcp(app_config.mysql.host, app_config.mysql.port)
    checks.append(("MySQL         ", ok, note))

    # Qdrant
    ok, note = _http(f"http://{app_config.qdrant.host}:{app_config.qdrant.port}/collections")
    checks.append(("Qdrant        ", ok, note))

    # Elasticsearch
    ok, note = _http(f"http://{app_config.es.host}:{app_config.es.port}")
    checks.append(("Elasticsearch ", ok, note))

    # TEI Embedding（/health 返回 200 表示模型已加载）
    if app_config.embedding.backend == "tei":
        ok, note = _http(f"http://{app_config.embedding.host}:{app_config.embedding.port}/health")
        checks.append(("TEI Embedding ", ok, note))
    else:
        checks.append(("TEI Embedding ", True, f"跳过（backend={app_config.embedding.backend}）"))

    # LLM 密钥（只看有没有配，不发请求）
    key = app_config.llm.api_key.strip()
    checks.append(("LLM 密钥      ", bool(key), f"{app_config.llm.model_name} / {'已配置' if key else '缺失'}"))

    print("=" * 68)
    for name, ok, note in checks:
        print(f"{'✅' if ok else '❌'} {name} {note}")
    print("=" * 68)

    ready = sum(1 for _, ok, _ in checks if ok)
    print(f"就绪 {ready}/{len(checks)}")
    for name, ok, note in checks:
        if not ok:
            logger.warning("服务未就绪: {} {}", name.strip(), note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
