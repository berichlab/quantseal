# Contributing to QuantSeal by BeRichLab

Thank you for contributing to **QuantSeal** (maintained by [BeRichLab](https://github.com/berichlab))! All contributions are licensed under Apache-2.0.

## Core Design Principles

Before submitting a PR, verify that your changes uphold QuantSeal's non-negotiable invariants:

1. **No `exec` / `eval` in strategy evaluation**: Extend the bounded JSON AST in `quantseal/discovery/spec.py` instead.
2. **Fail closed on missing data or sparse controls**: Never coerce `NaN` to `0`, and never declare a win against empty control arms or `< 5` bootstrap date clusters.
3. **Preserve single-shot validation integrity**: Never add shortcuts that reset `validation_evaluated_once` or erase prior-revision contamination labels.
4. **Keep external MCP context discovery-only**: External MCP connectors must remain read-only discovery context and never touch frozen validation or sealed holdout partitions.
5. **Test statistical guarantees**: Any change to `quantseal/core/evalue.py` must pass both symmetric and left-skewed null Monte Carlo Type-I error tests in `tests/test_evalue.py`.

## Development Commands

```bash
# Backend tests & lint
pytest -v
ruff check quantseal tests

# Frontend typecheck & production bundle
cd frontend && npm ci && npm run build
```

## Extending QuantSeal

- **New Data Adapters**: Add a loader returning `LoadedDiscoveryDataset` via `build_dataset_from_raw_frames()` in `quantseal/data/`.
- **New Market Cost Presets**: Add a `CostModel` entry in `MARKET_COST_PRESETS` (`quantseal/core/costs.py`).
- **New LLM Providers**: Extend `complete_text()` in `quantseal/discovery/llm.py`.
- **New Built-in MCP Tools**: Register schemas and handlers in `quantseal/mcp/server.py`.
