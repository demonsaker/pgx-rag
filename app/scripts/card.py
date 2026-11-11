"""证据卡 CLI：药师/医生核对用。

    uv run python -m app.scripts.card --drug clopidogrel --phenotype "Poor Metabolizer"
    uv run python -m app.scripts.card --drug clopidogrel --phenotype "Poor Metabolizer" --context "CVI ACS PCI"
    uv run python -m app.scripts.card --drug simvastatin --gene SLCO1B1 --phenotype "Decreased Function" --json
    uv run python -m app.scripts.card --drug abacavir --phenotype "*57:01 positive"
"""

from __future__ import annotations

import argparse
import json

from app.core.logger import logger
from app.services.evidence_card import EvidenceCardService


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 PGx 证据卡（专业侧）")
    parser.add_argument("--drug", required=True)
    parser.add_argument("--phenotype", required=True, help='如 "Poor Metabolizer" / "Decreased Function" / "*57:01 positive"')
    parser.add_argument("--gene", default=None, help="不传则用药物的默认基因")
    parser.add_argument("--context", default=None, help='临床场景，如 "CVI ACS PCI"；不传则列出全部场景')
    parser.add_argument("--label-top", type=int, default=5, help="说明书侧召回段数")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    service = EvidenceCardService()
    card = service.build(
        args.drug, args.phenotype, gene=args.gene, context=args.context, label_top_k=args.label_top
    )
    if args.json:
        print(json.dumps(card.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(card.render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
