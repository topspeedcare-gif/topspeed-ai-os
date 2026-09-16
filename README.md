# TOPSPEED AI OS

Independent ecommerce operations core for TOPSPEED.

The repository is governed by the frozen architecture and data-contract documents in its root.
The current implementation scope is PHASE 2 only: identifiers, enums, state transitions,
engine-independent JSON Schemas, canonical JSON, and payload hashing.

## Development

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
ruff check .
ruff format --check .
pytest
```

No database, external API, Slack integration, LLM prompt, agent, or execution adapter is
included in PHASE 2.
