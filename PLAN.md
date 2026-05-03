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
3. **Constants** — `FIELDS` (the human-readable column order for the output), `TICKERS_FILE`, `EXTRACTS_DIR`, `CEFCONNECT_FUNDS_URL` template, request `HEADERS` (set a polite User-Agent).
4. **`fetch_one_fund(ticker: str) -> dict`** — hit `https://www.cefconnect.com/api/v3/funds/{TICKER}`, raise on HTTP error, return the parsed JSON. Map the JSON's keys to the internal field names listed in `AGENTS.md`. Handle missing fields by returning `None` for them.
5. **`fetch_all_funds(tickers: list[str]) -> pandas.DataFrame`** — call `fetch_one_fund` for each ticker, log progress to stdout, collect into a DataFrame in the column order defined by `FIELDS`.
6. **`write_outputs(df: pandas.DataFrame, extracts_dir: pathlib.Path) -> tuple[Path, Path]`** — create `extracts_dir` if it does not exist, generate a timestamp string `YYYYMMDDHHMM`, write `extract-{ts}.xlsx` (using `openpyxl` engine) and `extract-{ts}.csv`, return the two paths.
7. **`read_tickers(path: pathlib.Path) -> list[str]`** — read `tickers.txt`, one ticker per line, strip whitespace, ignore blank lines and lines starting with `#`.
8. **`main()`** — orchestration: read tickers, fetch all funds, write outputs, print where the files landed.
9. **`if __name__ == "__main__": main()`** at the bottom.

### Style

- Type hints on every function signature.
- Docstrings on each function (one to three lines, focused on WHY/contract, not WHAT).
- Sparse inline comments; only where the WHY is non-obvious.
- f-strings; `pathlib.Path`; no `os.path`.
- Handle CEFConnect HTTP errors with one retry, then raise.

### Files to create in `script/`

- `cef_snapshot.py` (the script itself)
- `requirements.txt` is already seeded; verify it has `requests`, `pandas`, `openpyxl`
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

**`package/cef_tracker/sources/base.py`**

- `class DataSource(abc.ABC)` with one abstract method: `def fetch(self, ticker: Ticker) -> FundSnapshot: ...`.
- A `# Teaching:` callout above the class explaining: a `DataSource` is a contract. Any class that fulfills this contract can be used by the rest of the application. Adding Morningstar later means writing a new `MorningstarSource(DataSource)` and changing one line in `config.toml`.

**`package/cef_tracker/sources/cefconnect.py`**

- `class CEFConnectSource(DataSource)` — concrete implementation hitting `https://www.cefconnect.com/api/v3/funds/{TICKER}`.
- `__init__` accepts an optional `requests.Session` for testability.
- `fetch` does the HTTP call, maps the JSON to `FundSnapshot`, returns it.
- One retry on transient HTTP error, then raises.

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

- `def run(config_path: Path) -> None` — top-level orchestration. Loads config, instantiates the configured `DataSource`, fetches all snapshots, instantiates configured `OutputWriter`s, writes outputs to a fresh `extracts/YYYYMMDDHHMM/` directory, runs diff against the previous extract directory if one exists, writes `run.log` to the same directory containing per-ticker fetch status and any flagged deltas.

**`package/cef_tracker/__main__.py`**

- One line: `from .main import run; from pathlib import Path; run(Path(__file__).parent.parent / "config.toml")`. This enables `python -m cef_tracker`.

**`package/cef_tracker/__init__.py`**

- Empty (or a single `__version__ = "0.1.0"` line).

**`package/pyproject.toml`** — already seeded; verify it specifies Python 3.11+ and lists `requests`, `pandas`, `openpyxl` as dependencies and `pytest` as a dev dependency.

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

7. `test_field_extraction_from_recorded_response` — load `tests/fixtures/cefconnect_BIT.json` (a real recorded API response, captured during Phase 4's sample-output run), pass it through `CEFConnectSource`'s JSON-to-`FundSnapshot` mapping, assert the resulting `FundSnapshot` has the expected ticker, name, leverage_pct, and distribution_rate values from the fixture.

To capture the fixture: during Phase 4, intercept and save one real JSON response to `tests/fixtures/cefconnect_BIT.json` before parsing it.

### Verification

- `cd package && pytest -v` — all seven tests pass.
- No network calls during test runs (the fixture is loaded from disk).

---

## Phase 4 — Sample outputs

Produce committed sample outputs for both versions so a reader can see the data shape without running anything.

### Steps

1. Run `script/cef_snapshot.py` against the seeded `script/tickers.txt`. Copy the produced `extract-*.xlsx` and `extract-*.csv` from `script/extracts/` into `script/sample-output/`.
2. Run `python -m cef_tracker` from `package/`. Copy the produced `extract-*.xlsx`, `extract-*.csv`, and `run.log` from the timestamped subdirectory in `package/extracts/` into `package/sample-output/`.
3. Verify the sample outputs are real, populated, and readable.
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
- "Three architectural decisions" — three short subsections covering:
  1. **`config.toml` as the seam** — anything that changes often does not belong in code.
  2. **`DataSource` ABC** — the contract is "give me a Ticker, return a FundSnapshot." Adding Morningstar later means writing a new file and changing one config line.
  3. **Dated extract directories + `diff.py`** — per-run isolation beats appending; finding the previous run by date sort beats tracking state explicitly.
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
