"""MySQL 连接：异步引擎与会话工厂（SQLAlchemy 2.0 + asyncmy）。

配置来自 `app_config.mysql`；测试或降级时可用环境变量 `PGX_DATABASE_URL` 覆盖
（例如 `sqlite+aiosqlite:///./data/pgx_meta.db`），代码无需改动。
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.conf.app_config import app_config


def make_database_url() -> str:
    override = os.environ.get("PGX_DATABASE_URL")
    if override:
        return override
    cfg = app_config.mysql
    return (
        f"mysql+asyncmy://{cfg.user}:{cfg.password}@{cfg.host}:{cfg.port}/{cfg.database}"
        "?charset=utf8mb4"
    )


def make_engine(echo: bool = False) -> AsyncEngine:
    return create_async_engine(make_database_url(), echo=echo, pool_pre_ping=True, future=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
