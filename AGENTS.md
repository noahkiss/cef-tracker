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

## CEFConnect data sources

CEFConnect's data is served two ways: an undocumented JSON API used by the page's chart widgets, and server-rendered HTML containing the slow-moving fund metadata fields. Neither requires auth. Both versions of the tool combine them inside a single source module so the rest of the code only sees one CEFConnect source.

**Why two transports:** an earlier `funds/{TICKER}` JSON endpoint covered the whole fund-detail block in one call, but it has been removed from `/api/v3/`. The remaining JSON endpoints cover daily/historical series and performance; the metadata fields (sponsor, leverage, UNII, expense ratio) only exist in the HTML. The pivot is documented in MAKING-OF.md (Round 9).

### JSON endpoints (still live)

| Endpoint | Returns | Fields it covers |
|---|---|---|
| `https://www.cefconnect.com/api/v3/pricinghistory/{TICKER}/{range}` (range: `5D`, `1M`, `1Y`, `3Y`, `5Y`, `All`) | Daily rows with NAV, market price, discount per day | `nav`, `market_price`, `discount_pct` (latest row); also feeds discount Z-score |
| `https://www.cefconnect.com/api/v3/performance/annualized/{TICKER}` | Trailing returns: 3M / 6M / 1Y / 3Y / 5Y / 10Y, with `PriceTR` / `NAVTR` etc. | `total_return_1y/3y/5y/10y` (use `NAVTR`) |
| `https://www.cefconnect.com/api/v3/distributionhistory/fund/{TICKER}/{MM-DD-YYYY}/{MM-DD-YYYY}` | Per-distribution rows with `TotDiv`, `Income`, `CapitalReturn`, declared/ex/pay dates | `distribution_rate` (12 × latest `TotDiv` ÷ market price), `roc_pct` (sum of `CapitalReturn` ÷ sum of `TotDiv` over the trailing window) |
| `https://www.cefconnect.com/api/v3/search/tickers` | Full ticker list (~360 funds) with each fund's `Result` (full name) | `name` — fetch once per run and look up by ticker |

All return `{"Data": [...]}` shapes. Send a normal browser-like `User-Agent` and `Referer: https://www.cefconnect.com/fund/{TICKER}` to be polite. Response shapes can change without notice (the API is undocumented). The package version's `tests/fixtures/cefconnect_BIT_*.json` should hold real recorded responses so tests are reproducible offline.

### HTML scrape (for the metadata fields)

`https://www.cefconnect.com/fund/{TICKER}` is server-rendered ASP.NET. The fields that don't have a JSON endpoint live in stable table rows. Parse with `beautifulsoup4`. Fields and locator hints:

| Field | Locator hint |
|---|---|
| `sponsor` | `<p><strong>Fund Sponsor</strong><br />…</p>` (in the page header block) |
| `leverage_pct` | "Effective Leverage" row in the Leverage `<table>` (`<h5 class="subhead">Leverage</h5>` precedes it) |
| `leverage_cost` | "Leverage Cost" row in same Leverage table |
| `unii` | UNII reporting block — section heading varies by sponsor; locate by `<strong>` text containing "UNII" |
| `expense_ratio` | "Total Expense Ratio" row in the "Annual Expense Ratios" `<h5 class="subhead">` table (use the total, not "Other Expenses") |

Scrape resilience guidance: locate by surrounding `<strong>` text rather than by full ASP.NET ID, since the IDs are long and brittle. Return `None` if a field cannot be found rather than crashing — the diff engine and outputs handle missing values.

The `cefconnect_BIT_page.html` fixture (recorded once, committed under `tests/fixtures/`) is what the HTML parsing test pins against.

## SEC EDGAR API (package version only — second data source)

The package version includes a second data source: SEC EDGAR for early detection of distribution notices (filed as 497-series filings with section-19 distribution notice content). This exists primarily as a working demonstration that adding a new source under the `DataSource` ABC is a self-contained operation.

| Endpoint | Returns |
|---|---|
| `https://efts.sec.gov/LATEST/search-index?q=%22{TICKER}%22&forms=497&dateRange=custom&startdt=YYYY-MM-DD&enddt=YYYY-MM-DD` | EDGAR full-text search results (JSON) for 497 filings mentioning the ticker |
| `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={CIK}&type=497&dateb=&owner=include&count=40&output=atom` | Atom feed of 497 filings for a given fund registrant CIK |
| `https://www.sec.gov/files/company_tickers.json` | Ticker → CIK mapping (operating companies); fund-series tickers may need EDGAR series/class lookup instead |

Notes for the implementer:
- EDGAR requires a polite User-Agent including a contact email (per their fair-access policy: `User-Agent: cef-tracker (your-email@example.com)`). Make this configurable via `config.toml`.
- Rate limit: max 10 requests per second per IP. Respect it.
- For v1, use the EFTS full-text search keyed by ticker symbol — it is the simplest route and avoids the CIK mapping rabbit hole.
- The `EdgarSource.fetch(ticker)` returns a `FundSnapshot` whose `recent_distribution_filings` field contains a list of `(filing_date, accession_number, form_type)` tuples for filings within the last 60 days. Most fields will be `None` since EDGAR is not the source for NAV / leverage / etc. — that is fine; the diff engine merges sparse snapshots from multiple sources by ticker.

## Multi-source merging

A run may invoke more than one data source. When this happens, snapshots from different sources for the same ticker are merged field-by-field, with the rule: **the first non-None value wins, in source-priority order from `config.toml`**. CEFConnect is configured as primary; EDGAR is configured as secondary and contributes `recent_distribution_filings` (a field CEFConnect does not provide).

## History capture

In addition to the per-run extract files, the package version maintains a top-level append-only `history.csv` (configurable path; gitignored). On every run, after writing the per-run extracts, the orchestrator appends one row per ticker per run to `history.csv` with columns: `as_of_timestamp`, `source`, `ticker`, plus all configured fields in long format (one row per field-value if the long-format option is enabled, or one row per ticker with all fields as columns if wide-format is enabled — wide is the default and simpler).

Why this matters: per-run extract dirs are good for diff and audit ("what was in the run on 2026-05-03"); a single append-only `history.csv` is what you reach for when you want to answer "how has BIT's distribution rate moved over the last twelve months?" without reading and concatenating dozens of extract files. Both serve different purposes — keep both.

Implementation note: append (do not rewrite). If `history.csv` does not exist, create it with a header. If it exists, append rows without the header. Use `pandas.DataFrame.to_csv(path, mode="a", header=not path.exists(), index=False)`.

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
- New 19a-1-style EDGAR filing detected for a ticker since the prior run (early-warning flag, sourced from `recent_distribution_filings`)

These behaviors are exactly what `tests/test_diff.py` should pin down.

## Style notes

- Type hints throughout. They are documentation that the type checker can verify.
- `pathlib.Path`, not `os.path`.
- f-strings for string interpolation.
- `dataclass` (frozen where appropriate) for value types.
- `requests` for HTTP. Set a User-Agent. Handle network errors gracefully (retry once, then fail loudly).
- Keep dependencies minimal: `requests`, `pandas`, `openpyxl`, `beautifulsoup4` (HTML parse for the CEFConnect metadata fields), `pytest` (package only). Nothing else is justified at this scope.

## What not to do

- Do not add features beyond what `PLAN.md` lists.
- Do not add a CLI argument parser more elaborate than `argparse` in either version.
- Do not add scheduling, alerting, GUI, database storage, or cloud anything. All explicitly out of scope.
- Do not add data sources beyond CEFConnect to the implementation. Other sources are documented in the README so a future contributor can add them — that documentation is the artifact.
- Do not write tests that only verify trivia. See `PLAN.md` Phase 3 for the specific list of tests to write.
