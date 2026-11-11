"""日志：loguru 统一接管（配置来自 logging 分组）。

对应教学项目的「配置 + 日志」基础能力：
* 文件日志：按大小轮转（rotation）、按天保留（retention），落到 conf 里配的 path；
* 控制台日志：开发时看实时输出；
* 全项目统一 `from app.core.logger import logger`，不再各写各的 print。
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from app.conf.app_config import app_config, get_abs_path

_configured = False


def setup_logger() -> "logger":
    """进程内只配置一次；重复调用返回同一个 logger。"""
    global _configured
    if _configured:
        return logger

    conf = app_config.logging
    logger.remove()

    if conf.console.enable:
        logger.add(
            # 用 stdout 而不是 stderr：PowerShell 会把 stderr 当成错误记录，
            # 正常日志看起来像报错（NativeCommandError），排查时很干扰。
            sys.stdout,
            level=conf.console.level,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        )

    if conf.file.enable:
        log_dir: Path = get_abs_path(conf.file.path)
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_dir / "pgx_rag_{time:YYYY-MM-DD}.log",
            level=conf.file.level,
            rotation=conf.file.rotation,
            retention=conf.file.retention,
            encoding="utf-8",
            # enqueue=True 更适合 FastAPI 多线程，但短脚本进程退出时可能来不及 flush，
            # 导致"日志文件是空的"这种诡异现象；这里先关掉，保证写盘可靠。
            enqueue=False,
        )

    _configured = True
    return logger


def get_logger():
    return setup_logger()


# 导入即完成配置：`from app.core.logger import logger` 就能拿到
# 「控制台 + 文件」两个 sink，避免出现"只 import 没调用 setup、日志不落盘"的坑。
setup_logger()
