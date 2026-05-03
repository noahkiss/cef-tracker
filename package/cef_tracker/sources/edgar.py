"""SEC EDGAR EFTS source — early detection of 19a-1 distribution notices."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import requests

from ..http import get_with_backoff
from ..models import FundSnapshot, Ticker
from .base import DataSource

EFTS_URL = (
    "https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22"
    "&forms=497&dateRange=custom&startdt={start}&enddt={end}"
)


class EdgarSource(DataSource):
    """Polite EDGAR full-text search over recent 497 filings.

    Returns a FundSnapshot whose `recent_distribution_filings` is a list of
    `(filing_date, accession_number, form_type)` tuples for any 497 filing
    matching the ticker symbol within the lookback window. All other fields
    are None — this source contributes one signal, not a full snapshot, and
    relies on `merge_snapshots` to combine it with CEFConnect's view.
    """

    name = "edgar"

    def __init__(
        self,
        user_agent: str,
        session: requests.Session | None = None,
        lookback_days: int = 60,
    ) -> None:
        if not user_agent or "@" not in user_agent:
            # EDGAR requires a contact-bearing User-Agent per their fair-access policy.
            raise ValueError(
                "EdgarSource requires a user_agent containing a contact email "
                "(e.g. 'cef-tracker (you@example.com)')"
            )
        self._user_agent = user_agent
        self._session = session or requests.Session()
        self._lookback_days = lookback_days

    def fetch(self, ticker: Ticker) -> FundSnapshot:
        symbol = ticker.symbol.upper()
        end = date.today()
        start = end - timedelta(days=self._lookback_days)
        url = EFTS_URL.format(ticker=symbol, start=start.isoformat(), end=end.isoformat())
        response = get_with_backoff(
            self._session,
            url,
            headers={"User-Agent": self._user_agent, "Accept": "application/json"},
        )
        return FundSnapshot(
            ticker=symbol,
            as_of=datetime.now(),
            source=self.name,
            recent_distribution_filings=self.parse_filings(response.json()),
        )

    @staticmethod
    def parse_filings(payload: dict) -> list[tuple[str, str, str]]:
        """Extract (filing_date, accession_number, form_type) tuples from EFTS."""
        hits = (((payload or {}).get("hits") or {}).get("hits")) or []
        out: list[tuple[str, str, str]] = []
        for hit in hits:
            src = hit.get("_source") or {}
            file_date = src.get("file_date")
            accession = src.get("adsh") or hit.get("_id", "").split(":", 1)[0]
            form = src.get("form") or src.get("file_type") or "497"
            if file_date and accession:
                out.append((file_date, accession, form))
        return out
