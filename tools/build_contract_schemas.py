"""Regenerate committed JSON Schemas from the frozen contract definitions."""

from __future__ import annotations

import json
from pathlib import Path

from topspeed_ai_os.contracts.definitions import CONTRACT_NAMES, build_schema


def main() -> None:
    destination = (
        Path(__file__).resolve().parents[1] / "src" / "topspeed_ai_os" / "contracts" / "schemas"
    )
    destination.mkdir(parents=True, exist_ok=True)
    for contract_name in CONTRACT_NAMES:
        path = destination / f"{contract_name.lower()}.schema.json"
        path.write_text(
            json.dumps(build_schema(contract_name), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
