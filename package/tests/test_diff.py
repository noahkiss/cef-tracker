"""Diff rule tests — pin down the behavior described in AGENTS.md."""

from __future__ import annotations

from datetime import datetime

from cef_tracker.diff import DiffThresholds, diff_snapshots
from cef_tracker.models import FundSnapshot

NOW = datetime(2026, 5, 3, 12, 0, 0)
THRESHOLDS = DiffThresholds()


def _snap(ticker: str, **fields) -> FundSnapshot:
    return FundSnapshot(ticker=ticker, as_of=NOW, source="test", **fields)


def test_leverage_cost_change_above_threshold_flags():
    prior = [_snap("BIT", leverage_cost=2.00)]
    current = [_snap("BIT", leverage_cost=2.60)]  # +60 bps
    flags = diff_snapshots(prior, current, THRESHOLDS)
    assert len(flags) == 1
    assert flags[0].reason == "leverage_cost_change"
    assert flags[0].ticker == "BIT"


def test_leverage_cost_change_below_threshold_no_flag():
    prior = [_snap("BIT", leverage_cost=2.00)]
    current = [_snap("BIT", leverage_cost=2.30)]  # +30 bps
    assert diff_snapshots(prior, current, THRESHOLDS) == []


def test_distribution_cut_detected():
    prior = [_snap("BIT", distribution_rate=8.0)]
    current = [_snap("BIT", distribution_rate=7.2)]
    flags = diff_snapshots(prior, current, THRESHOLDS)
    assert [f.reason for f in flags] == ["distribution_cut"]


def test_unii_flips_negative_flags():
    prior = [_snap("BIT", unii=0.05)]
    current = [_snap("BIT", unii=-0.02)]
    flags = diff_snapshots(prior, current, THRESHOLDS)
    assert [f.reason for f in flags] == ["unii_negative"]


def test_new_ticker_in_current_run():
    prior = [_snap("BIT")]
    current = [_snap("BIT"), _snap("PDI")]
    flags = diff_snapshots(prior, current, THRESHOLDS)
    assert len(flags) == 1
    assert flags[0].ticker == "PDI"
    assert flags[0].reason == "new_ticker"


def test_missing_ticker_in_current_run():
    prior = [_snap("BIT"), _snap("PDI")]
    current = [_snap("BIT")]
    flags = diff_snapshots(prior, current, THRESHOLDS)
    assert len(flags) == 1
    assert flags[0].ticker == "PDI"
    assert flags[0].reason == "removed_ticker"


def test_new_edgar_filing_flagged():
    prior = [_snap("BIT", recent_distribution_filings=[
        ("2026-03-01", "0000123-26-000001", "497"),
    ])]
    current = [_snap("BIT", recent_distribution_filings=[
        ("2026-03-01", "0000123-26-000001", "497"),
        ("2026-04-15", "0000123-26-000002", "497"),
    ])]
    flags = diff_snapshots(prior, current, THRESHOLDS)
    assert len(flags) == 1
    assert flags[0].reason == "new_distribution_filing"
    assert flags[0].current == ("2026-04-15", "0000123-26-000002", "497")
