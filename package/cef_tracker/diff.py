"""Compare the current run against the most recent prior run."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import FundSnapshot


@dataclass
class FlaggedDelta:
    ticker: str
    field: str
    previous: Any
    current: Any
    reason: str


@dataclass
class DiffThresholds:
    leverage_cost_change_bps: float = 50.0
    flag_unii_negative: bool = True
    flag_distribution_cut: bool = True
    discount_zscore_threshold: float = 2.0
    flag_new_distribution_filing: bool = True


def find_previous_extract_dir(extracts_root: Path, current: Path) -> Path | None:
    """Most recent dir strictly older than `current` (lexicographic on YYYYMMDDHHMM)."""
    if not extracts_root.exists():
        return None
    candidates = sorted(
        d for d in extracts_root.iterdir()
        if d.is_dir() and d.name < current.name
    )
    return candidates[-1] if candidates else None


def diff_snapshots(
    prior: list[FundSnapshot],
    current: list[FundSnapshot],
    thresholds: DiffThresholds,
) -> list[FlaggedDelta]:
    """Apply the diff rules from AGENTS.md to two lists of snapshots."""
    prior_by_ticker = {s.ticker: s for s in prior}
    current_by_ticker = {s.ticker: s for s in current}
    flags: list[FlaggedDelta] = []

    for ticker, snap in current_by_ticker.items():
        if ticker not in prior_by_ticker:
            flags.append(FlaggedDelta(ticker, "ticker", None, ticker, "new_ticker"))
            continue
        prev = prior_by_ticker[ticker]

        if (
            prev.leverage_cost is not None
            and snap.leverage_cost is not None
        ):
            # Both are percent values; convert delta to bps (×100).
            delta_bps = abs(snap.leverage_cost - prev.leverage_cost) * 100.0
            if delta_bps > thresholds.leverage_cost_change_bps:
                flags.append(FlaggedDelta(
                    ticker, "leverage_cost", prev.leverage_cost, snap.leverage_cost,
                    "leverage_cost_change",
                ))

        if (
            thresholds.flag_unii_negative
            and prev.unii is not None
            and snap.unii is not None
            and prev.unii >= 0
            and snap.unii < 0
        ):
            flags.append(FlaggedDelta(
                ticker, "unii", prev.unii, snap.unii, "unii_negative",
            ))

        if (
            thresholds.flag_distribution_cut
            and prev.distribution_rate is not None
            and snap.distribution_rate is not None
            and snap.distribution_rate < prev.distribution_rate
        ):
            flags.append(FlaggedDelta(
                ticker, "distribution_rate", prev.distribution_rate,
                snap.distribution_rate, "distribution_cut",
            ))

        # Skip flagging when the prior snapshot has no recorded filings — that's
        # ambiguous (could mean "no filings then" or "filings weren't captured
        # in the prior extract"; CSV roundtrips don't preserve this list).
        if (
            thresholds.flag_new_distribution_filing
            and prev.recent_distribution_filings
        ):
            prev_accessions = {a for _, a, _ in prev.recent_distribution_filings}
            for entry in snap.recent_distribution_filings:
                if entry[1] not in prev_accessions:
                    flags.append(FlaggedDelta(
                        ticker, "recent_distribution_filings",
                        None, entry, "new_distribution_filing",
                    ))

    for ticker in prior_by_ticker:
        if ticker not in current_by_ticker:
            flags.append(FlaggedDelta(ticker, "ticker", ticker, None, "removed_ticker"))

    return flags
