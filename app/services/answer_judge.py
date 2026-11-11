"""答案处置方向判定（评测用）。

为什么不用关键词规则：中文答案里「**不是绝对禁用**」「**未给出禁用结论**」这类否定表达，
关键词会直接命中「禁用」判成"避免"，把本来谨慎、正确的答案判成不一致。
第一版用规则时方向一致率被压到 59.5%，逐条看失败案例才发现是抽取器的问题。

做法：让模型只读「问题 + 答案」，在**不知道金标准**的情况下判定主要处置方向，
并给出依据句与理由，便于人工复核（避免黑箱）。

档位与 CPIC 侧保持一致：0 标准剂量 / 2 调整或监测 / 3 避免或禁用 / null 未给出方向。
"""

from __future__ import annotations

import json
import re

import httpx

from app.conf.app_config import app_config
from app.core.logger import logger

_JUDGE_PROMPT = """你是药物基因组学评审员。只读下面的【问题】和【系统答案】，判断答案给出的**主要处置方向**。

档位定义（与 CPIC 侧规则保持一致）：
- 3：明确不要使用该药（不得使用 / 禁用 / 避免使用 / 不推荐使用 / 禁忌）
- 2：需要改动方案后才能用（减量、延长间隔、监测、权衡后可试用、**考虑更换为其他药**）
- 0：可以使用标准剂量 / 无需特殊处理
- null：答案没有给出明确处置方向（例如只说"说明书未提及该基因"，或只是描述机制与数据）

判定纪律：
1. 只看【结论】部分给出的处置，不要把"依据"里针对其他表型的表述当成结论；
2. 注意否定与限定：如「不是绝对禁用」「未给出禁用结论」「仅在无替代方案时考虑」都不判为 3；
3. 「考虑替代/建议换用其他药」属于 2，不是 3；只有"不得/禁止/避免使用"才是 3；
4. 若结论同时含多档，取**针对该患者表型的最终建议**；
5. 只输出 JSON，不要解释格式之外的内容。

输出格式：
{"action": 0 | 2 | 3 | null, "sentence": "<答案中支撑该判定的原句>", "rationale": "<不超过 40 字>"}
"""


class DirectionJudge:
    def __init__(self, model: str | None = None) -> None:
        cfg = app_config.llm
        self.model = model or cfg.model_name
        self.base_url = cfg.base_url.rstrip("/")
        self.api_key = cfg.api_key

    def judge(self, question: str, answer: str) -> dict:
        if not self.api_key:
            return {"action": None, "sentence": "", "rationale": "缺少 API key"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _JUDGE_PROMPT},
                {"role": "user", "content": f"【问题】{question}\n\n【系统答案】{answer[:2500]}"},
            ],
            "temperature": 0,
            "max_tokens": 300,
            "response_format": {"type": "json_object"},
        }
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            action = data.get("action")
            action = int(action) if action in (0, 2, 3) else None
            return {
                "action": action,
                "sentence": str(data.get("sentence", ""))[:300],
                "rationale": str(data.get("rationale", ""))[:200],
            }
        except Exception as exc:  # noqa: BLE001 - 判分失败不该炸掉整轮评测
            logger.warning("方向判定失败：{}", exc)
            return {"action": None, "sentence": "", "rationale": f"判定失败：{type(exc).__name__}"}
