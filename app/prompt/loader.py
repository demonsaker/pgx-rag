"""提示词加载：读 prompts/ 下的静态文件，按需缓存。

提示词放源码目录之外（`prompts/`），改文案不用动代码；加载时做一次性缓存，
避免每次请求都读盘。缺文件时直接报错，而不是悄悄用空字符串继续跑。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.conf.app_config import PROJECT_ROOT

PROMPT_DIR = PROJECT_ROOT / "prompts"


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    path = PROMPT_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"提示词不存在：{path}")
    return path.read_text(encoding="utf-8")


def render_prompt(name: str, **variables: str) -> str:
    """只做简单占位替换（不用 str.format，避免提示词里的花括号被误解释）。"""
    text = load_prompt(name)
    for key, value in variables.items():
        text = text.replace("{" + key + "}", value)
    return text
