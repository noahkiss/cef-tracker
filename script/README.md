# `script/` — single-file CEF snapshot

A one-file Python program that reads tickers from `tickers.txt`, fetches each fund's data from CEFConnect, and writes a timestamped Excel + CSV pair into `extracts/`. Idiomatic top-down Python; no abstractions, no config file, no tests. The companion to [`../package/`](../package/), which solves the same problem with a multi-module structure.

## Setup and run

```bash
cd script
pip install -r requirements.txt
python cef_snapshot.py
```

Output:

```
extracts/extract-YYYYMMDDHHMM.xlsx
extracts/extract-YYYYMMDDHHMM.csv
```

Each run writes its own pair of timestamped files. Nothing is ever overwritten.

If you don't have `pip` set up the way the script expects, see the top-level [README](../README.md#tooling-pip-and-uv) for the `uv` alternative.

## Walk-through of `cef_snapshot.py`

The file is structured top-down so you can read it cover to cover.

1. **Module docstring + constants.** What the script does, where it writes, the column order (`FIELDS`), the URL templates for the four CEFConnect JSON endpoints plus the per-fund HTML page, and the request headers (a normal browser User-Agent and per-fund Referer — CEFConnect prefers this).

2. **`get_with_backoff`.** All HTTP calls flow through this helper. It retries transient failures (network errors, HTTP 429, HTTP 5xx) with exponential backoff (0.5s → 1.0s → 2.0s); other 4xx errors pass through immediately. The `# Teaching:` callout above it explains *why* exponential backoff is the right pattern when scraping someone else's site.

3. **`fetch_one_fund` + four `_parse_*` helpers.** One fund's worth of data: hit pricinghistory for NAV / market price / discount, performance/annualized for trailing returns, distributionhistory for distribution rate and ROC %, then scrape the per-fund HTML page with BeautifulSoup for sponsor / leverage / expense ratio. Each parser returns `None` for fields it cannot find, so a missing value never crashes the run.

4. **`fetch_all_funds`.** Loops over the ticker list, calls `fetch_one_fund` for each, and collects results into a pandas DataFrame in the column order from `FIELDS`.

5. **`write_outputs` + `read_tickers` + `main`.** The plumbing: read `tickers.txt`, call `fetch_all_funds`, write timestamped Excel and CSV via pandas + openpyxl, print the file paths.

## What this version does *not* do

These are deliberate trade-offs of the single-file style, not failures:

- **No diff between runs.** Each run is independent. Compare manually if you need to.
- **No source pluggability.** Adding a second source means editing `cef_snapshot.py` directly.
- **No threshold flagging.** A leverage-cost spike or distribution cut shows up in the data but isn't called out.
- **No tests.** A single file with one well-defined behavior is small enough to verify by reading and running.

## When to graduate to `package/`

If you find yourself making one of these changes more than once, the multi-module version's structure starts paying back:

- Adding new data sources (Morningstar, EDGAR, your own broker's API).
- Comparing this run to the previous one and flagging significant moves.
- Running it on a schedule and accumulating history.
- Sharing the code with someone else who needs to extend it without reading the whole thing first.

## Where to look next

- [Top-level README](../README.md) for the data-source primer and learning resources.
- [`../package/`](../package/) for the multi-module version of the same tool.
