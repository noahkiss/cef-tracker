# AGENTS.md — orientation for AI coding agents

This file exists because LLM coding agents (Claude Code, Cursor, Aider, Codex, etc.) do not automatically read `README.md`. The README is for humans; this file is for you.

## What this project is

A Python tool that fetches a snapshot of public closed-end fund (CEF) data from CEFConnect's JSON API and writes it to timestamped Excel and CSV files. The repo contains **two implementations of the same tool** as a comparative learning artifact:

- `script/` — single-file Python, idiomatic top-down style
- `package/` — multi-module Python with explicit interfaces, designed for extension

Both are first-class. Neither is "better." The point of having both is the comparison itself.

## Repo layout

```
cef-tracker/
├── README.md            ← human-facing project intro, data sources, learning resources
├── AGENTS.md            ← this file
├── CLAUDE.md            ← @AGENTS.md (Claude Code reads this)
├── PLAN.md              ← phased implementation plan; follow it if implementing
├── LICENSE              ← MIT
├── .gitignore
├── script/
│   ├── README.md
│   ├── cef_snapshot.py        ← the single-file implementation
│   ├── tickers.txt            ← seeded
│   ├── requirements.txt       ← seeded
│   └── sample-output/         ← committed sample run output
└── package/
    ├── README.md
    ├── pyproject.toml         ← seeded
    ├── config.toml            ← seeded
    ├── cef_tracker/
    │   ├── __init__.py
    │   ├── __main__.py
    │   ├── models.py
    │   ├── sources/{base.py, cefconnect.py}
    │   ├── output/{base.py, excel.py, csv.py}
    │   ├── diff.py
    │   └── main.py
    ├── tests/
    │   ├── test_diff.py
    │   ├── test_cefconnect.py
    │   └── fixtures/
    └── sample-output/         ← committed sample run output (with run.log)
```

## Conventions

- **Python version floor: 3.11.** Uses stdlib `tomllib`. Do not pull in `tomli` as a dependency.
- **Output filenames** in both versions use the format `extract-YYYYMMDDHHMM.xlsx` and `extract-YYYYMMDDHHMM.csv`. No standard or "latest" filename — every run is its own timestamped file. This is deliberate: it avoids collisions when two extracts are open simultaneously, and it preserves history without an explicit archiving step.
- **Never write into an existing user workbook.** Both versions only ever write standalone timestamped extract files. A tool that automatically modifies a shared workbook is one bad assumption away from corrupting weeks of manual annotations.
- **Sample tickers for testing and committed sample output**: BIT, BST, PDI, UTG, RFI. These are diverse, liquid CEFs across categories.
- **The `extracts/` directory is gitignored.** Real runs do not commit data. The `sample-output/` directory in each folder *is* committed and should contain one representative run captured against the sample tickers.
- **Comments**: sparse, idiomatic, only where the WHY is non-obvious. The `package/` version may use `# Teaching:` callout comments at the architecture decision points (ABC contracts, dataclass usage, config-as-seam) so a reader can find the conceptual high points by searching for that prefix. Do not over-comment.

## CEFConnect API endpoints

Undocumented JSON, no auth required. These are the endpoints both versions of the tool use:

| Endpoint | Returns |
|---|---|
| `https://www.cefconnect.com/api/v3/funds/{TICKER}` | Fund metadata, leverage, distributions, current NAV/price/discount, trailing returns |
| `https://www.cefconnect.com/api/v3/pricinghistory/{TICKER}/?type=ALL` | Full price/NAV history with computed discount per day |
| `https://www.cefconnect.com/api/v3/distributionHistory/{TICKER}` | Distribution history with ROC categorization |

The primary endpoint for both implementations is `funds/{TICKER}`. Response shapes can change without notice (the API is undocumented). The package version's `tests/fixtures/cefconnect_BIT.json` should hold a real recorded response so tests are reproducible offline.

## Field set to extract

The fields the tool pulls per fund (see `package/config.toml` for the canonical list, and the constant in `script/cef_snapshot.py` for the script's mirror of it):

- `ticker`, `name`, `sponsor`
- `nav`, `market_price`, `discount_pct`
- `leverage_pct`, `leverage_cost`
- `distribution_rate`, `roc_pct`
- `unii`
- `expense_ratio`
- `total_return_1y`, `total_return_3y`, `total_return_5y`, `total_return_10y` (NAV total return)

Field names in the output should be human-readable (e.g. `Discount %`, not `discount_pct`) — the snake_case names above are internal.

## Diff logic (package/ only)

`package/cef_tracker/diff.py` compares the most recent snapshot against the previous one (found by sorting `extracts/` directories by date). It produces a list of "flagged" deltas based on thresholds in `config.toml`:

- Leverage cost moved by more than configured bps (default 50 bps, either direction)
- UNII flipped from non-negative to negative
- Distribution rate dropped (any decrease)
- Discount Z-score (vs. trailing history) above configured threshold (default 2.0)
- New ticker present in current run but not prior (handle without crashing)
- Ticker present in prior run but not current (mark as removed, do not silently drop)

These behaviors are exactly what `tests/test_diff.py` should pin down.

## Style notes

- Type hints throughout. They are documentation that the type checker can verify.
- `pathlib.Path`, not `os.path`.
- f-strings for string interpolation.
- `dataclass` (frozen where appropriate) for value types.
- `requests` for HTTP. Set a User-Agent. Handle network errors gracefully (retry once, then fail loudly).
- Keep dependencies minimal: `requests`, `pandas`, `openpyxl`, `pytest` (package only). Nothing else is justified at this scope.

## What not to do

- Do not add features beyond what `PLAN.md` lists.
- Do not add a CLI argument parser more elaborate than `argparse` in either version.
- Do not add scheduling, alerting, GUI, database storage, or cloud anything. All explicitly out of scope.
- Do not add data sources beyond CEFConnect to the implementation. Other sources are documented in the README so a future contributor can add them — that documentation is the artifact.
- Do not write tests that only verify trivia. See `PLAN.md` Phase 3 for the specific list of tests to write.
