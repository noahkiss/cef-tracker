"""Value types used across the package."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime


# Teaching: @dataclass(frozen=True) gives a value type for free —
# auto-generated __init__, __repr__, and __eq__, plus immutability so we can
# safely use Tickers as dict keys or pass them around without worrying about
# accidental mutation. The cost is one decorator line.
@dataclass(frozen=True)
class Ticker:
    """A single closed-end fund ticker symbol."""

    symbol: str
    notes: str = ""


# Internal field names → human-readable column labels for output writers.
COLUMN_LABELS: dict[str, str] = {
    "ticker": "Ticker",
    "name": "Name",
    "sponsor": "Sponsor",
    "nav": "NAV",
    "market_price": "Market Price",
    "discount_pct": "Discount %",
    "leverage_pct": "Leverage %",
    "leverage_cost": "Leverage Cost %",
    "distribution_rate": "Distribution Rate %",
    "roc_pct": "ROC %",
    "unii": "UNII",
    "expense_ratio": "Expense Ratio %",
    "total_return_1y": "1Y Total Return %",
    "total_return_3y": "3Y Total Return %",
    "total_return_5y": "5Y Total Return %",
    "total_return_10y": "10Y Total Return %",
}


# Teaching: @dataclass (without frozen) gives mutable instances we can build up
# field-by-field as a fetch progresses. Every field is Optional because any
# given source may not provide it — sparse snapshots are merged downstream.
@dataclass
class FundSnapshot:
    """One source's view of one fund at a point in time.

    Snapshots from multiple sources for the same ticker are merged
    field-by-field by `main.run`: first non-None value wins, in
    source-priority order from config.
    """

    ticker: str
    as_of: datetime
    source: str

    name: str | None = None
    sponsor: str | None = None
    nav: float | None = None
    market_price: float | None = None
    discount_pct: float | None = None
    leverage_pct: float | None = None
    leverage_cost: float | None = None
    distribution_rate: float | None = None
    roc_pct: float | None = None
    unii: float | None = None
    expense_ratio: float | None = None
    total_return_1y: float | None = None
    total_return_3y: float | None = None
    total_return_5y: float | None = None
    total_return_10y: float | None = None

    # EDGAR-specific: list of (filing_date, accession_number, form_type) tuples.
    recent_distribution_filings: list[tuple[str, str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Flat dict keyed by human-readable column labels, for output writers."""
        return {label: getattr(self, key) for key, label in COLUMN_LABELS.items()}


def merge_snapshots(snapshots: list[FundSnapshot]) -> FundSnapshot:
    """Merge multiple snapshots for one ticker.

    First non-None value wins per field, in the order snapshots are passed.
    The first snapshot's `as_of` and `source` win. EDGAR's
    `recent_distribution_filings` lists are concatenated (deduplicated by
    accession_number).
    """
    if not snapshots:
        raise ValueError("merge_snapshots requires at least one snapshot")
    base = snapshots[0]
    merged_kwargs: dict = {
        "ticker": base.ticker,
        "as_of": base.as_of,
        "source": base.source,
    }
    skip = {"ticker", "as_of", "source", "recent_distribution_filings"}
    for f in fields(FundSnapshot):
        if f.name in skip:
            continue
        chosen = None
        for snap in snapshots:
            value = getattr(snap, f.name)
            if value is not None:
                chosen = value
                break
        merged_kwargs[f.name] = chosen

    seen_accessions: set[str] = set()
    filings: list[tuple[str, str, str]] = []
    for snap in snapshots:
        for entry in snap.recent_distribution_filings:
            accession = entry[1]
            if accession not in seen_accessions:
                seen_accessions.add(accession)
                filings.append(entry)
    merged_kwargs["recent_distribution_filings"] = filings

    return FundSnapshot(**merged_kwargs)
