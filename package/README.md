# `package/` — multi-module CEF snapshot

A multi-module Python package that does the same job as [`../script/`](../script/) — fetches a snapshot of CEF data and writes timestamped Excel + CSV files — but is structured so you can extend it without reading every file first. New data source? One file plus one config line. New output format? Same. Diff this run against the previous one? `diff.py` already does it.

## Setup and run

```bash
cd package
pip install -r requirements.txt
python -m cef_tracker
```

Output (per run):

```
extracts/YYYYMMDDHHMM/extract-YYYYMMDDHHMM.xlsx
extracts/YYYYMMDDHHMM/extract-YYYYMMDDHHMM.csv
extracts/YYYYMMDDHHMM/run.log
history.csv                      ← appended to on every run
```

## Project layout

```
package/
├── config.toml                  ← seam: tickers, fields, sources, thresholds
├── pyproject.toml
├── requirements.txt
├── cef_tracker/
│   ├── __init__.py              ← __version__
│   ├── __main__.py              ← entry point: python -m cef_tracker
│   ├── main.py                  ← orchestration: fetch → merge → write → diff
│   ├── models.py                ← Ticker, FundSnapshot, merge_snapshots
│   ├── http.py                  ← shared get_with_backoff for every source
│   ├── diff.py                  ← FlaggedDelta + diff rules
│   ├── sources/
│   │   ├── base.py              ← DataSource ABC
│   │   ├── cefconnect.py        ← four JSON endpoints + HTML scrape
│   │   └── edgar.py             ← EDGAR EFTS — early 19a-1 detection
│   └── output/
│       ├── base.py              ← OutputWriter ABC
│       ├── excel.py
│       └── csv.py
├── tests/
│   ├── test_diff.py             ← pins each diff rule
│   ├── test_cefconnect.py       ← parses recorded BIT JSON+HTML offline
│   ├── test_edgar.py            ← parses recorded EFTS response offline
│   └── fixtures/                ← real CEFConnect + EDGAR responses for BIT
└── sample-output/               ← committed real run output for reference
```

## Four architectural decisions

### 1. `config.toml` as the seam

Anything that changes often does not belong in code. The ticker list, the field set, which data sources are enabled, the diff thresholds, the EDGAR contact email — all live in `config.toml`. Code only changes when *behavior* changes.

This is the difference between editing one row of a config file to add a ticker and grepping for hardcoded `["BIT", "BST", ...]` lists in three places.

### 2. The `DataSource` ABC

The contract is simple: *given a `Ticker`, return a `FundSnapshot`*. That's it.

`sources/cefconnect.py` and `sources/edgar.py` are both concrete `DataSource`s. They look completely different on the inside — one combines four JSON endpoints with an HTML scrape, the other talks to the SEC's EFTS search index — but the rest of the application doesn't care. It just calls `source.fetch(ticker)`.

When a run uses more than one source, snapshots are merged field-by-field in `models.merge_snapshots`: **first non-None value wins, in source-priority order from `config.toml`**. CEFConnect is configured as primary (it provides the bulk of the fields); EDGAR is secondary (it contributes `recent_distribution_filings`, a field CEFConnect doesn't expose). This is what lets EDGAR exist as a thin source that only fills in one column without having to pretend it knows the NAV.

**Adding Morningstar later** is a self-contained operation: write `sources/morningstar.py` with a `MorningstarSource(DataSource)` class, register it in `main.SOURCE_REGISTRY`, add `"morningstar"` to `[sources] enabled` in `config.toml`. No other file changes.

### 3. Dated extract directories + `diff.py`

Each run lands in `extracts/YYYYMMDDHHMM/`. Per-run isolation beats appending to a shared file: the run's output is a complete artifact you can audit, version, or send to someone, and two simultaneous runs can't corrupt each other.

`diff.py` finds the previous run by sorting directory names lexicographically (which works because `YYYYMMDDHHMM` sorts the same as time). It compares the current run's snapshots against the previous run's and emits a `FlaggedDelta` for each rule that triggered (leverage cost moved by more than the configured threshold, distribution rate dropped, UNII flipped negative, new or removed ticker, new EDGAR distribution filing). The flagged deltas land in `run.log`.

**Finding the previous run by date sort beats tracking state explicitly.** No "last_run.txt" pointer to keep in sync, no SQLite, no implicit assumption about who ran what when.

### 4. `history.csv` for longitudinal capture

The per-run extract directories answer one question: *"what was in the run on YYYY-MM-DD?"* That's the audit-and-diff lens.

`history.csv` answers a different question: *"how has BIT's distribution rate moved over the last twelve months?"* That's the time-series lens. Trying to answer it by reading and concatenating dozens of extract files is enough friction to stop you from asking the question. Append-only `history.csv` makes it cheap.

Two artifacts for two questions, both cheap to maintain. Append-only — never rewritten.

## How to add a new data source

1. Create `cef_tracker/sources/your_source.py`.
2. Define `class YourSource(DataSource)` with `name = "your_source"` and a `fetch(self, ticker) -> FundSnapshot` method. Use `cef_tracker.http.get_with_backoff(self._session, url, headers=...)` for any HTTP — you get retries and polite backoff for free.
3. Return a `FundSnapshot` with the fields your source can populate; leave the others as `None`. The merge step combines you with whatever else is enabled.
4. Register the class in `cef_tracker/main.SOURCE_REGISTRY`.
5. Add `"your_source"` to the `[sources] enabled` array in `config.toml`. If your source needs config (an API key, a contact email), add a `[sources.your_source]` table to `config.toml` and read it from `_build_sources` in `main.py`.

That's the whole change. No edits to existing source code.

## How to add a new output writer

Same shape. Create `cef_tracker/output/your_format.py`, define `class YourWriter(OutputWriter)` with `name = "your_format"` and a `write(self, snapshots, extract_dir) -> Path` method, register it in `main.OUTPUT_REGISTRY`, add `"your_format"` to the `[output] formats` array in `config.toml`.

## What this version does *not* do yet

Out of scope on purpose:

- **No scheduling.** Run it manually, or wrap it in `cron` / Task Scheduler.
- **No GUI.** It's a CLI tool. The output opens in Excel.
- **No real-time alerting.** Flagged deltas land in `run.log`; nothing pages anyone.
- **No additional data sources in code.** Other sources (Morningstar, S&P, Bloomberg) are *documented* in the top-level README but not implemented — adding them is the contributor's onboarding exercise.

## Where to look next

- [Top-level README](../README.md) for the data-source primer, the EDGAR background, and the learning resources.
- [`../script/`](../script/) for the single-file version of the same tool.
