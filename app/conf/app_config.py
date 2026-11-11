"""配置结构与加载入口（结构与「电商问数」的 app/conf/app_config.py 一致）。

链路固定为四步：

    YAML 文件
      -> OmegaConf.load        读取配置内容
      -> OmegaConf.structured  准备配置结构
      -> OmegaConf.merge       结构 + 内容合并
      -> OmegaConf.to_object   转成可直接访问属性的对象

之后全项目统一用 `app_config.xxx.yyy` 访问，不再到处解析 YAML 或写死字符串键名。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from omegaconf import OmegaConf


# ---------------------------------------------------------------- 日志
@dataclass
class File:
    enable: bool
    level: str
    path: str
    rotation: str
    retention: str


@dataclass
class Console:
    enable: bool
    level: str


@dataclass
class LoggingConfig:
    file: File
    console: Console


# ---------------------------------------------------------------- 外部服务
@dataclass
class DBConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


@dataclass
class QdrantConfig:
    host: str
    port: int
    embedding_size: int
    collection: str = "pgx_chunks"
    mode: str = "server"


@dataclass
class ESConfig:
    host: str
    port: int
    index_name: str


@dataclass
class EmbeddingConfig:
    """向量化服务。backend=tei 用 Docker 里的 TEI；=dashscope 走云端 API。"""

    backend: str
    host: str
    port: int
    model: str
    dimension: int
    dashscope_model: str = "text-embedding-v4"
    batch_size: int = 10
    workers: int = 4


@dataclass
class LLMConfig:
    model_name: str
    api_key: str
    base_url: str


# ---------------------------------------------------------------- 业务参数
@dataclass
class RagConfig:
    top_k: int = 6
    candidates: int = 40
    max_priority: int = 7
    corpus_path: str = "data/corpus/chunks.jsonl"
    tables_path: str = "data/corpus/tables.jsonl"
    cpic_corpus_path: str = "data/corpus/cpic_chunks.jsonl"
    include_cpic: bool = True


@dataclass
class AppConfig:
    logging: LoggingConfig
    mysql: DBConfig
    qdrant: QdrantConfig
    es: ESConfig
    embedding: EmbeddingConfig
    llm: LLMConfig
    rag: RagConfig = field(default_factory=RagConfig)


# app/conf/app_config.py -> app/conf -> app -> 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = PROJECT_ROOT / "conf" / "app_config.yaml"

# 密钥不进仓库：先从项目根 .env 注入进程环境变量，再用 OmegaConf 的 oc.env 插值读取。
# 兼容本机既有 .env 里的变量名（Deepseek_key / Qwen_key）。
load_dotenv(PROJECT_ROOT / ".env", override=False)
for _alias, _candidates in {
    "DEEPSEEK_API_KEY": ("Deepseek_key", "deepseek_key"),
    "DASHSCOPE_API_KEY": ("Qwen_key", "qwen_key"),
}.items():
    if not os.getenv(_alias):
        for _name in _candidates:
            _value = os.getenv(_name)
            if _value:
                os.environ[_alias] = _value
                break

context = OmegaConf.load(CONFIG_FILE)
schema = OmegaConf.structured(AppConfig)
app_config: AppConfig = OmegaConf.to_object(OmegaConf.merge(schema, context))


def get_project_root() -> Path:
    return PROJECT_ROOT


def get_abs_path(relative: str) -> Path:
    """把配置里的相对路径（如 logs、data/corpus/...）解析成项目内绝对路径。"""
    path = Path(relative)
    return path if path.is_absolute() else PROJECT_ROOT / path


if __name__ == "__main__":
    print(app_config.es.host, app_config.es.port, app_config.qdrant.collection)
    print(app_config.embedding.backend, app_config.embedding.model)
    print(app_config.llm.model_name, "key set:", bool(app_config.llm.api_key))
