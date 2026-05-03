"""Top-level orchestration: fetch all funds from all configured sources, write."""

from __future__ import annotations

import sys
import tomllib
from dataclasses import asdict, fields
from datetime import datetime
from pathlib import Path

import pandas as pd

from .diff import DiffThresholds, diff_snapshots, find_previous_extract_dir
from .models import COLUMN_LABELS, FundSnapshot, Ticker, merge_snapshots
from .output.base import OutputWriter
from .output.csv import CSVWriter
from .output.excel import ExcelWriter
from .sources.base import DataSource
from .sources.cefconnect import CEFConnectSource
from .sources.edgar import EdgarSource

SOURCE_REGISTRY: dict[str, type[DataSource]] = {
    "cefconnect": CEFConnectSource,
    "edgar": EdgarSource,
}

OUTPUT_REGISTRY: dict[str, type[OutputWriter]] = {
    "excel": ExcelWriter,
    "csv": CSVWriter,
}


def run(config_path: Path) -> None:
    """End-to-end: load config, fetch every ticker from every source, write."""
    config = tomllib.loads(config_path.read_text())
    config_dir = config_path.parent

    tickers = [Ticker(symbol=t) for t in config["fund_universe"]["tickers"]]
    field_names = config["fields"]["include"]
    sources = _build_sources(config)
    writers = _build_writers(config, field_names)
    thresholds = DiffThresholds(
        leverage_cost_change_bps=config["diff"].get("leverage_cost_change_bps", 50.0),
        flag_unii_negative=config["diff"].get("flag_unii_negative", True),
        flag_distribution_cut=config["diff"].get("flag_distribution_cut", True),
        discount_zscore_threshold=config["diff"].get("discount_zscore_threshold", 2.0),
        flag_new_distribution_filing=config["diff"].get("flag_new_distribution_filing", True),
    )

    extracts_root = (config_dir / config["output"]["extracts_dir"]).resolve()
    history_path = (config_dir / config["output"]["history_path"]).resolve()
    timestamp = datetime.now().strftime("%Y%m%d%H%M")
    extract_dir = extracts_root / timestamp

    log_lines: list[str] = [f"Run started: {datetime.now().isoformat(timespec='seconds')}"]
    merged_snapshots: list[FundSnapshot] = []

    for ticker in tickers:
        per_source: list[FundSnapshot] = []
        for source in sources:
            try:
                snap = source.fetch(ticker)
                per_source.append(snap)
                log_lines.append(f"  {ticker.symbol} <- {source.name}: ok")
            except Exception as exc:
                log_lines.append(f"  {ticker.symbol} <- {source.name}: FAILED ({exc})")
        if per_source:
            merged_snapshots.append(merge_snapshots(per_source))
        else:
            log_lines.append(f"  {ticker.symbol}: no source returned data, skipping")

    extract_dir.mkdir(parents=True, exist_ok=True)
    written_paths = []
    for writer in writers:
        path = writer.write(merged_snapshots, extract_dir)
        written_paths.append(path)
        log_lines.append(f"Wrote {path}")

    _append_history(merged_snapshots, history_path, field_names)
    log_lines.append(f"Appended {len(merged_snapshots)} rows to {history_path}")

    prior_dir = find_previous_extract_dir(extracts_root, extract_dir)
    if prior_dir is not None:
        prior = _load_snapshots(prior_dir, field_names)
        deltas = diff_snapshots(prior, merged_snapshots, thresholds)
        if deltas:
            log_lines.append(f"Flagged deltas vs {prior_dir.name}:")
            for d in deltas:
                log_lines.append(
                    f"  [{d.reason}] {d.ticker}.{d.field}: {d.previous} -> {d.current}"
                )
        else:
            log_lines.append(f"No flagged deltas vs {prior_dir.name}")
    else:
        log_lines.append("No prior extract found; skipping diff.")

    (extract_dir / "run.log").write_text("\n".join(log_lines) + "\n")
    print("\n".join(log_lines))


def _build_sources(config: dict) -> list[DataSource]:
    sources: list[DataSource] = []
    for name in config["sources"]["enabled"]:
        cls = SOURCE_REGISTRY.get(name)
        if cls is None:
            print(f"Unknown source '{name}' in config, skipping", file=sys.stderr)
            continue
        if name == "edgar":
            edgar_cfg = config["sources"].get("edgar", {})
            sources.append(EdgarSource(
                user_agent=edgar_cfg.get("user_agent", "cef-tracker (you@example.com)"),
                lookback_days=edgar_cfg.get("lookback_days", 60),
            ))
        else:
            sources.append(cls())
    return sources


def _build_writers(config: dict, fields_list: list[str]) -> list[OutputWriter]:
    writers: list[OutputWriter] = []
    for name in config["output"]["formats"]:
        cls = OUTPUT_REGISTRY.get(name)
        if cls is None:
            print(f"Unknown output format '{name}', skipping", file=sys.stderr)
            continue
        writers.append(cls(fields=fields_list))
    return writers


def _append_history(
    snapshots: list[FundSnapshot], history_path: Path, fields_list: list[str]
) -> None:
    if not snapshots:
        return
    rows = []
    for snap in snapshots:
        row: dict = {
            "as_of_timestamp": snap.as_of.isoformat(timespec="seconds"),
            "source": snap.source,
        }
        for f in fields_list:
            row[f] = getattr(snap, f, None)
        rows.append(row)
    df = pd.DataFrame(rows)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(
        history_path,
        mode="a",
        header=not history_path.exists(),
        index=False,
    )


def _load_snapshots(extract_dir: Path, fields_list: list[str]) -> list[FundSnapshot]:
    """Reconstruct FundSnapshots from a prior run's CSV (best-effort)."""
    csv_files = sorted(extract_dir.glob("extract-*.csv"))
    if not csv_files:
        return []
    df = pd.read_csv(csv_files[-1])
    snapshots: list[FundSnapshot] = []
    label_to_field = {v: k for k, v in COLUMN_LABELS.items()}
    valid_field_names = {f.name for f in fields(FundSnapshot)}
    for _, row in df.iterrows():
        kwargs = {
            "ticker": str(row.get("Ticker", "")),
            "as_of": datetime.now(),
            "source": "prior",
        }
        for label, value in row.items():
            field_name = label_to_field.get(label)
            if field_name is None or field_name in {"ticker"}:
                continue
            if field_name not in valid_field_names:
                continue
            if pd.isna(value):
                kwargs[field_name] = None
            elif field_name in {"name", "sponsor"}:
                kwargs[field_name] = str(value)
            else:
                try:
                    kwargs[field_name] = float(value)
                except (TypeError, ValueError):
                    kwargs[field_name] = None
        snapshots.append(FundSnapshot(**kwargs))
    return snapshots
