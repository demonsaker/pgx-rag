"""文本基础能力：规范化、分词、指纹、分位数。

分词的三个刻意设计（都是踩过的坑）：
1. 索引与查询共用同一套分词，`HLA-B` 两侧都切成 `hla` + `b`，天然对齐；
2. 等位基因 `*57:01` 与 `*5701` 两种写法统一去冒号，否则纯格式差异就漏召回；
3. 去停用词但保留 `*` 开头的等位基因 token。
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

TOKEN_RE = re.compile(r"[a-z0-9]+|\*[0-9]{1,2}(?::[0-9]{1,2})?")

STOPWORDS = frozenset(
    """
    a an and are as at be been but by can could did do does for from had has have how i if in into is it its
    may might must no not of on or other our should so some such than that the their them then there these they
    this those to was were what when where which who why will with would you your
    """.split()
)

_WS = re.compile(r"\s+")
_ZERO_WIDTH = re.compile(r"[\u200b-\u200d\ufeff\u00ad]")
_KEY_RE = re.compile(r"[^a-z0-9]+")


def normalize_text(raw: str) -> str:
    """统一空白与不可见字符，不改写内容。"""
    if not raw:
        return ""
    text = unicodedata.normalize("NFKC", raw)
    text = _ZERO_WIDTH.sub("", text)
    return text.replace("\u00a0", " ").strip()


def collapse_ws(raw: str) -> str:
    return _WS.sub(" ", normalize_text(raw)).strip()


def tokenize(text: str) -> list[str]:
    tokens = TOKEN_RE.findall(text.lower())
    out: list[str] = []
    for token in tokens:
        if token.startswith("*"):
            out.append(token.replace(":", ""))
        elif len(token) > 1 and token not in STOPWORDS:
            out.append(token)
    return out


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def text_key(text: str) -> str:
    """近似去重指纹：忽略大小写、标点、空白差异。"""
    return sha1(_KEY_RE.sub(" ", text.lower()).strip())


def slug(text: str) -> str:
    return _KEY_RE.sub("-", text.lower()).strip("-")


def percentile(values: list[int], q: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = q * (len(ordered) - 1)
    lo, hi = int(pos), min(int(pos) + 1, len(ordered) - 1)
    return round(ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo))


def est_tokens(text: str) -> int:
    """粗估 token：英文约 4 字符/token。"""
    return max(1, round(len(text) / 4))
