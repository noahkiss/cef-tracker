# PLAN.md — implementation plan for cef-tracker

This file is the implementation plan. Read `AGENTS.md` first for repo conventions and constraints, then work through the phases below in order. Each phase has explicit verification criteria — confirm them before moving on.

The user (a senior software engineer) has already decided the architecture, the file layout, the conventions, and the field set. Your job is to implement what is described here without expanding scope.

---

## Phase 1 — `script/cef_snapshot.py`

Build the single-file implementation first. It is simpler, and getting it right gives you a working reference for the field extraction and CEFConnect API behavior that you will reuse in Phase 2.

### What to build

A single Python file, `script/cef_snapshot.py`, structured top-down:

1. **Module docstring** — one short paragraph: what this script does, how to run it, where it writes.
2. **Imports** — stdlib first (`pathlib`, `datetime`, `sys`), then third-party (`requests`, `pandas`).
3. **Constants** — `FIELDS` (the human-readable column order for the output), `TICKERS_FILE`, `EXTRACTS_DIR`, URL templates for each CEFConnect endpoint listed in `AGENTS.md` (pricinghistory, performance/annualized, distributionhistory, search/tickers, and the per-fund HTML page), request `HEADERS` (browser-like User-Agent + `Referer`).
4. **`fetch_one_fund(ticker: str, name_lookup: dict[str, str]) -> dict`** — hit each CEFConnect endpoint, parse what each returns, parse the per-fund HTML page with `beautifulsoup4` for the metadata fields (sponsor, leverage_pct, leverage_cost, unii, expense_ratio), and assemble one flat dict keyed by the internal field names from `AGENTS.md`. Return `None` for any field whose source returned nothing. Use the `get_with_backoff` helper (below) for every HTTP call. The `name_lookup` is built once from `search/tickers` in `fetch_all_funds` and passed in.
5. **`get_with_backoff(url: str, headers: dict, max_attempts: int = 3, base_delay: float = 0.5) -> requests.Response`** — small helper that retries transient errors (network errors, HTTP 429, HTTP 5xx) with exponential backoff: `base_delay * 2 ** attempt` seconds between attempts (so 0.5s → 1.0s → 2.0s with the default). Raises after `max_attempts`. Pass through 4xx other than 429 immediately (those won't fix themselves). Add a short `# Teaching:` block above this function explaining what exponential backoff is and why polite retry logic matters when scraping someone else's site.
6. **`fetch_all_funds(tickers: list[str]) -> pandas.DataFrame`** — call `fetch_one_fund` for each ticker, log progress to stdout, collect into a DataFrame in the column order defined by `FIELDS`.
7. **`write_outputs(df: pandas.DataFrame, extracts_dir: pathlib.Path) -> tuple[Path, Path]`** — create `extracts_dir` if it does not exist, generate a timestamp string `YYYYMMDDHHMM`, write `extract-{ts}.xlsx` (using `openpyxl` engine) and `extract-{ts}.csv`, return the two paths.
8. **`read_tickers(path: pathlib.Path) -> list[str]`** — read `tickers.txt`, one ticker per line, strip whitespace, ignore blank lines and lines starting with `#`.
9. **`main()`** — orchestration: read tickers, fetch all funds, write outputs, print where the files landed.
10. **`if __name__ == "__main__": main()`** at the bottom.

### Style

- Type hints on every function signature.
- Docstrings on each function (one to three lines, focused on WHY/contract, not WHAT).
- Sparse inline comments; only where the WHY is non-obvious.
- f-strings; `pathlib.Path`; no `os.path`.
- All HTTP calls go through `get_with_backoff` (exponential backoff, max 3 attempts). No bare `requests.get` in `fetch_one_fund`.

### Files to create in `script/`

- `cef_snapshot.py` (the script itself)
- `requirements.txt` is already seeded; verify it has `requests`, `pandas`, `openpyxl`, `beautifulsoup4`
- `tickers.txt` is already seeded with BIT, BST, PDI, UTG, RFI

### Verification

- `cd script && pip install -r requirements.txt && python cef_snapshot.py` runs cleanly to completion.
- Produces `extracts/extract-YYYYMMDDHHMM.xlsx` and `.csv` with one row per ticker, columns in `FIELDS` order, populated values for all five sample tickers.
- Open the Excel in a spreadsheet program; data is readable and correctly typed (numbers as numbers, percentages as percentages where reasonable).

---

## Phase 2 — `package/` implementation

Now build the multi-module version. The functional behavior is identical to Phase 1; the difference is structure.

### File-by-file

**`package/cef_tracker/models.py`**

- `@dataclass(frozen=True) class Ticker` — a single ticker symbol with optional notes. Just `symbol: str`, `notes: str = ""`. Frozen because tickers are value types.
- `@dataclass class FundSnapshot` — the result of fetching one fund. Fields exactly match the internal field names from `AGENTS.md`. Add `as_of: datetime` and `source: str` so a snapshot knows where it came from and when. Provide a `to_dict()` method that returns a dict with human-readable column names (for output writers).
- A `# Teaching:` callout near `FundSnapshot` explaining what `@dataclass` gives you (init, repr, eq) for free.

**`package/cef_tracker/http.py`**

- `def get_with_backoff(session: requests.Session, url: str, *, headers: dict | None = None, max_attempts: int = 3, base_delay: float = 0.5) -> requests.Response` — shared HTTP helper used by every `DataSource`. Retries transient errors (network errors, HTTP 429, HTTP 5xx) with exponential backoff (`base_delay * 2 ** attempt`). Passes through 4xx other than 429 immediately. Raises `requests.HTTPError` after `max_attempts`.
- A `# Teaching:` callout above it: exponential backoff is the standard polite-retry pattern for talking to services you don't own. Doubling the delay each attempt gives the upstream room to recover from transient load without you hammering it. The same helper is used by both `CEFConnectSource` and `EdgarSource` — pulling it out once is what an ABC-style architecture buys you.

**`package/cef_tracker/sources/base.py`**

- `class DataSource(abc.ABC)` with one abstract method: `def fetch(self, ticker: Ticker) -> FundSnapshot: ...`.
- A `# Teaching:` callout above the class explaining: a `DataSource` is a contract. Any class that fulfills this contract can be used by the rest of the application. Adding Morningstar later means writing a new `MorningstarSource(DataSource)` and changing one line in `config.toml`.

**`package/cef_tracker/sources/cefconnect.py`**

- `class CEFConnectSource(DataSource)` — concrete implementation that combines the JSON endpoints and HTML scrape from `AGENTS.md` into a single `FundSnapshot`.
- `__init__` accepts an optional `requests.Session` for testability. Builds (and caches per-instance) the ticker → name map from `/api/v3/search/tickers` on first `fetch`.
- `fetch` makes the four JSON calls + one HTML fetch (all via `http.get_with_backoff`), runs each through a small private parser (`_parse_pricing`, `_parse_performance`, `_parse_distributions`, `_parse_html_metadata`), merges into one `FundSnapshot`, and returns it. Each parser returns `None` for fields it cannot find rather than raising.
- Add a `# Teaching:` callout near the parser methods explaining why the source presents a single `fetch` interface even though it talks to five URLs internally — the rest of the app shouldn't care that CEFConnect's data lives in five places.

**`package/cef_tracker/sources/edgar.py`** — *real implementation, not a stub.* This source exists primarily to demonstrate that adding a second source under the `DataSource` ABC is a self-contained operation, but the data it returns is also genuinely useful: 19a-1-style distribution notices appear on EDGAR a week or two before CEFConnect reflects them.

- `class EdgarSource(DataSource)` — hits the EDGAR EFTS full-text search endpoint listed in `AGENTS.md`. Searches for 497 filings mentioning the ticker symbol within the last 60 days.
- `__init__(user_agent: str, session: requests.Session | None = None, lookback_days: int = 60)`. The `user_agent` is mandatory (EDGAR requires it; configurable via `config.toml`).
- `fetch` returns a `FundSnapshot` whose `recent_distribution_filings` field is a list of `(filing_date, accession_number, form_type)` tuples. All other fields are `None`.
- All HTTP calls go through `http.get_with_backoff`. EDGAR's 10-req/s limit is well under what we'll generate at this scale; the backoff helper covers the case where EDGAR returns 429 anyway (it does, occasionally, regardless of rate).

**`package/cef_tracker/output/base.py`**

- `class OutputWriter(abc.ABC)` with one abstract method: `def write(self, snapshots: list[FundSnapshot], extract_dir: Path) -> Path: ...` returning the path written.
- `# Teaching:` callout: same pattern as `DataSource`, applied to outputs.

**`package/cef_tracker/output/excel.py`**

- `class ExcelWriter(OutputWriter)` — writes `extract-YYYYMMDDHHMM.xlsx` to the given directory using pandas + openpyxl.
- Column order driven by the field config (passed via `__init__` or read from somewhere predictable).

**`package/cef_tracker/output/csv.py`**

- `class CSVWriter(OutputWriter)` — same shape, writes CSV.

**`package/cef_tracker/diff.py`**

- `@dataclass class FlaggedDelta` — represents one flagged change: `ticker`, `field`, `previous`, `current`, `reason` (one of: `"leverage_cost_change"`, `"unii_negative"`, `"distribution_cut"`, `"discount_extreme"`, `"new_ticker"`, `"removed_ticker"`).
- `def find_previous_extract_dir(extracts_root: Path, current: Path) -> Path | None` — finds the most recent extract directory that is strictly older than `current` by sorting directory names.
- `def diff_snapshots(prior: list[FundSnapshot], current: list[FundSnapshot], thresholds: DiffThresholds) -> list[FlaggedDelta]` — implements the rules from `AGENTS.md`.
- `@dataclass class DiffThresholds` — one container for all configurable thresholds.

**`package/cef_tracker/main.py`**

- `def run(config_path: Path) -> None` — top-level orchestration:
  1. Load config.
  2. Instantiate **all configured data sources** in priority order (e.g. `CEFConnectSource` then `EdgarSource`).
  3. For each ticker, fetch from each source in priority order, then merge the resulting `FundSnapshot`s field-by-field (first non-None wins per `AGENTS.md` "Multi-source merging").
  4. Instantiate configured `OutputWriter`s.
  5. Write outputs to a fresh `extracts/YYYYMMDDHHMM/` directory.
  6. **Append one row per merged snapshot to `history.csv`** at the configured top-level path (per `AGENTS.md` "History capture"). Use `pandas.DataFrame.to_csv(path, mode="a", header=not path.exists(), index=False)`.
  7. Run diff against the previous extract directory if one exists.
  8. Write `run.log` containing per-ticker fetch status (per source) and any flagged deltas.

**`package/cef_tracker/__main__.py`**

- One line: `from .main import run; from pathlib import Path; run(Path(__file__).parent.parent / "config.toml")`. This enables `python -m cef_tracker`.

**`package/cef_tracker/__init__.py`**

- Empty (or a single `__version__ = "0.1.0"` line).

**`package/pyproject.toml`** — already seeded; verify it specifies Python 3.11+ and lists `requests`, `pandas`, `openpyxl`, `beautifulsoup4` as dependencies and `pytest` as a dev dependency. Update `requirements.txt` to match.

**`package/config.toml`** — already seeded with sample tickers (BIT, BST, PDI, UTG, RFI), the field list, output settings, and threshold defaults.

### Verification

- `cd package && pip install -r requirements.txt && python -m cef_tracker` runs cleanly.
- Produces `extracts/YYYYMMDDHHMM/extract-YYYYMMDDHHMM.xlsx`, `.csv`, and `run.log`.
- Run it twice (with a 60+ second gap so the timestamps differ), then a third time after manually editing `extracts/<old>/extract-*.csv` to perturb a leverage cost value. The third run's `run.log` should contain a flagged leverage cost change.

---

## Phase 3 — Tests

Tests pin down logic that can break. No tests of trivia. Implement exactly the seven tests below.

**`package/tests/test_diff.py`**

1. `test_leverage_cost_change_above_threshold_flags` — two snapshots where leverage cost moved +60bps; with threshold=50, expect exactly one `FlaggedDelta` with `reason="leverage_cost_change"`.
2. `test_leverage_cost_change_below_threshold_no_flag` — same setup, +30bps; expect no flag.
3. `test_distribution_cut_detected` — distribution rate dropped from 8.0% to 7.2%; expect one flag with `reason="distribution_cut"`.
4. `test_unii_flips_negative_flags` — UNII went from +0.05 to -0.02; expect one flag with `reason="unii_negative"`.
5. `test_new_ticker_in_current_run` — current snapshot contains a ticker not in prior; expect one flag with `reason="new_ticker"` and the function does not crash.
6. `test_missing_ticker_in_current_run` — prior contains a ticker missing from current; expect one flag with `reason="removed_ticker"`.

**`package/tests/test_cefconnect.py`**

7. `test_field_extraction_from_recorded_responses` — load four JSON fixtures (`cefconnect_BIT_pricing.json`, `cefconnect_BIT_performance.json`, `cefconnect_BIT_distributions.json`, `cefconnect_BIT_search.json`) plus the HTML fixture (`cefconnect_BIT_page.html`), pass them through the corresponding `CEFConnectSource._parse_*` methods (no network), and assert the merged `FundSnapshot` has the expected ticker, name, sponsor, nav, distribution_rate, leverage_pct, and total_return_1y values from the fixtures.

**`package/tests/test_edgar.py`**

8. `test_edgar_filing_parse_from_recorded_response` — load `tests/fixtures/edgar_BIT.json` (a real recorded EFTS search response), pass it through `EdgarSource`'s JSON-to-`FundSnapshot` mapping, assert the resulting `FundSnapshot.recent_distribution_filings` contains the expected number of tuples with the expected `filing_date`, `accession_number`, and `form_type` values.

**`package/tests/test_diff.py`** — add one more diff test:

9. `test_new_edgar_filing_flagged` — current snapshot has a `recent_distribution_filings` entry not present in the prior snapshot; expect one `FlaggedDelta` with `reason="new_distribution_filing"`.

To capture the fixtures: during Phase 4, intercept and save the four real CEFConnect JSON responses, the per-fund HTML page, and one real EDGAR JSON response for `BIT` before parsing them. Save under `package/tests/fixtures/`.

### Verification

- `cd package && pytest -v` — all nine tests pass.
- No network calls during test runs (fixtures are loaded from disk).

---

## Phase 4 — Sample outputs

Produce committed sample outputs for both versions so a reader can see the data shape without running anything.

### Steps

1. Run `script/cef_snapshot.py` against the seeded `script/tickers.txt`. Copy the produced `extract-*.xlsx` and `extract-*.csv` from `script/extracts/` into `script/sample-output/`.
2. Run `python -m cef_tracker` from `package/` **at least twice** (with a 60+ second gap so timestamps differ — this is what enables the diff and gives the second run something to compare against). Copy the most recent run's `extract-*.xlsx`, `extract-*.csv`, and `run.log` from the timestamped subdirectory in `package/extracts/` into `package/sample-output/`. Also copy a representative `history.csv` snippet (first ~20 rows) into `package/sample-output/history-sample.csv` so a reader can see what longitudinal capture looks like.
3. Verify the sample outputs are real, populated, and readable. The package version's `run.log` should show fetches from both CEFConnect and EDGAR per ticker.
4. Commit them.

The `extracts/` directories themselves are gitignored — only `sample-output/` is committed.

---

## Phase 5 — Per-folder READMEs

The top-level README is already complete. Now write each subfolder's README, focused on what is specific to that implementation.

### `script/README.md`

- One-paragraph what-this-is.
- Setup and run (`pip install -r requirements.txt && python cef_snapshot.py`).
- A walkthrough of `cef_snapshot.py` section by section (~5 short sections matching the file's structure).
- "What this version does not do" — bullet list: no diff between runs, no source pluggability, no threshold flagging, no tests. Frame these as deliberate trade-offs of the single-file style, not failures.
- "When to graduate to `package/`" — three or four sentences.
- A small section linking back to the top-level README for data sources and learning resources.

### `package/README.md`

- One-paragraph what-this-is.
- Setup and run (`pip install -r requirements.txt && python -m cef_tracker`).
- "Project layout" — the file tree from `cef_tracker/` with one line per file.
- "Four architectural decisions" — four short subsections covering:
  1. **`config.toml` as the seam** — anything that changes often does not belong in code.
  2. **`DataSource` ABC** — the contract is "give me a Ticker, return a FundSnapshot." Adding Morningstar later means writing a new file and changing one config line. Demonstrate by pointing at the *real* second source already in the repo: `sources/edgar.py` (CEFConnect for the bulk of fields, EDGAR for early-warning distribution notices). Explain the multi-source merge rule (first non-None wins, in source-priority order).
  3. **Dated extract directories + `diff.py`** — per-run isolation beats appending; finding the previous run by date sort beats tracking state explicitly.
  4. **`history.csv` for longitudinal capture** — extract dirs answer "what was in this run"; `history.csv` answers "how has this field moved over time." Two artifacts for two questions, both cheap to maintain. Append-only, never rewritten.
- "How to add a new data source" — step-by-step pointing at `sources/base.py`.
- "How to add a new output writer" — same.
- "What this version does not do yet" — out-of-scope list (no scheduling, no GUI, no real-time, no alerting).
- A small section linking back to the top-level README for data sources and learning resources.

### Verification

- Both READMEs render cleanly on GitHub (preview locally or push and check).
- Both link back to the top-level README for shared content.

---

## Out of scope

Do not, in any phase, add:

- Additional data sources beyond CEFConnect in code (they are *documented* in the top-level README, which is the entire deliverable for them).
- A CLI argument parser more elaborate than `argparse`.
- Scheduling, alerting, GUI, database storage, cloud anything.
- Tests beyond the seven specified.
- Helper abstractions that have only one caller.
- Comments explaining what well-named code already does.

If during implementation you find a genuine reason to deviate from this plan, write it in `STATUS.local.md` (which is gitignored) and stop for human review before proceeding.

---

## Done criteria

The repo is done when:

- All five phases above are complete.
- `pytest -v` passes in `package/`.
- Both `script/` and `package/` produce valid extract files when run.
- `script/sample-output/` and `package/sample-output/` contain committed, real run output.
- All four READMEs (top-level, `script/`, `package/`, plus the inherited content via `CLAUDE.md` → `AGENTS.md`) read cleanly.
- A clean `git status` shows no uncommitted changes that should have been committed.
