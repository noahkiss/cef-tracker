"""CEFConnect data source: combines four JSON endpoints + one HTML scrape."""

from __future__ import annotations

from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from ..http import get_with_backoff
from ..models import FundSnapshot, Ticker
from .base import DataSource

PRICING_URL = "https://www.cefconnect.com/api/v3/pricinghistory/{ticker}/{range}"
PERFORMANCE_URL = "https://www.cefconnect.com/api/v3/performance/annualized/{ticker}"
DISTRIBUTIONS_URL = (
    "https://www.cefconnect.com/api/v3/distributionhistory/fund/{ticker}/{start}/{end}"
)
SEARCH_TICKERS_URL = "https://www.cefconnect.com/api/v3/search/tickers"
FUND_PAGE_URL = "https://www.cefconnect.com/fund/{ticker}"

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_pct(text: str | None) -> float | None:
    if not text:
        return None
    return _safe_float(text.strip().replace(",", "").rstrip("%").strip())


class CEFConnectSource(DataSource):
    """CEFConnect data, fetched as four JSON calls + one HTML scrape per fund."""

    name = "cefconnect"

    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()
        # Cache the ticker -> name map across fetches in the same run.
        self._name_lookup: dict[str, str] | None = None

    # Teaching: this source presents a single `fetch` interface even though
    # internally it talks to five URLs. The rest of the app shouldn't care
    # that CEFConnect's data lives in five places — that's an implementation
    # detail of *this* source. Each parser is a small private method so they
    # can be tested individually against recorded fixtures (see
    # tests/test_cefconnect.py).
    def fetch(self, ticker: Ticker) -> FundSnapshot:
        symbol = ticker.symbol.upper()
        headers = self._headers_for(symbol)
        snapshot = FundSnapshot(ticker=symbol, as_of=datetime.now(), source=self.name)

        snapshot.name = self._lookup_name(symbol)

        pricing = self._get_json(PRICING_URL.format(ticker=symbol, range="5D"), headers)
        for k, v in self._parse_pricing(pricing).items():
            setattr(snapshot, k, v)

        performance = self._get_json(PERFORMANCE_URL.format(ticker=symbol), headers)
        for k, v in self._parse_performance(performance).items():
            setattr(snapshot, k, v)

        today = datetime.now().date()
        start = (today - timedelta(days=365)).strftime("%m-%d-%Y")
        end = today.strftime("%m-%d-%Y")
        distributions = self._get_json(
            DISTRIBUTIONS_URL.format(ticker=symbol, start=start, end=end), headers
        )
        for k, v in self._parse_distributions(distributions, snapshot.market_price).items():
            setattr(snapshot, k, v)

        html = self._get_text(FUND_PAGE_URL.format(ticker=symbol), headers)
        for k, v in self._parse_html_metadata(html).items():
            setattr(snapshot, k, v)

        return snapshot

    def _lookup_name(self, symbol: str) -> str | None:
        if self._name_lookup is None:
            response = get_with_backoff(
                self._session, SEARCH_TICKERS_URL, headers={"User-Agent": USER_AGENT}
            )
            rows = response.json()
            self._name_lookup = {
                (row.get("Ticker") or "").strip().upper(): (row.get("Result") or "").strip()
                for row in rows
                if row.get("Ticker") and row.get("Result")
            }
        return self._name_lookup.get(symbol)

    def _headers_for(self, symbol: str) -> dict:
        return {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Referer": FUND_PAGE_URL.format(ticker=symbol),
        }

    def _get_json(self, url: str, headers: dict) -> dict:
        return get_with_backoff(self._session, url, headers=headers).json()

    def _get_text(self, url: str, headers: dict) -> str:
        return get_with_backoff(self._session, url, headers=headers).text

    @staticmethod
    def _parse_pricing(payload: dict) -> dict:
        data = payload.get("Data") if isinstance(payload, dict) else None
        rows = (data or {}).get("PriceHistory") or []
        if not rows:
            return {"nav": None, "market_price": None, "discount_pct": None}
        latest = rows[0]
        return {
            "nav": _safe_float(latest.get("NAVData")),
            "market_price": _safe_float(latest.get("Data")),
            "discount_pct": _safe_float(latest.get("DiscountData")),
        }

    @staticmethod
    def _parse_performance(payload: dict) -> dict:
        rows = payload.get("Data", []) if isinstance(payload, dict) else []
        horizon_map = {
            "1YEAR": "total_return_1y",
            "3YEAR": "total_return_3y",
            "5YEAR": "total_return_5y",
            "10YEAR": "total_return_10y",
        }
        out: dict = {v: None for v in horizon_map.values()}
        for row in rows:
            label = (row.get("Type") or "").upper().replace(" ", "")
            key = horizon_map.get(label)
            if key:
                out[key] = _safe_float(row.get("NAVTR"))
        return out

    @staticmethod
    def _parse_distributions(payload: dict, market_price: float | None) -> dict:
        rows = payload.get("Data", []) if isinstance(payload, dict) else []
        if not rows:
            return {"distribution_rate": None, "roc_pct": None}
        latest_totdiv = _safe_float(rows[0].get("TotDiv"))
        if latest_totdiv is not None and market_price:
            distribution_rate = (12.0 * latest_totdiv / market_price) * 100.0
        else:
            distribution_rate = None
        totdiv_sum = 0.0
        capret_sum = 0.0
        for row in rows:
            totdiv_sum += _safe_float(row.get("TotDiv")) or 0.0
            capret_sum += _safe_float(row.get("CapitalReturn")) or 0.0
        roc_pct = (capret_sum / totdiv_sum * 100.0) if totdiv_sum else None
        return {"distribution_rate": distribution_rate, "roc_pct": roc_pct}

    @staticmethod
    def _parse_html_metadata(html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")

        sponsor: str | None = None
        for strong in soup.find_all("strong"):
            if "fund sponsor" in strong.get_text(" ", strip=True).lower():
                parent = strong.parent
                if parent:
                    label = strong.get_text(" ", strip=True)
                    cleaned = parent.get_text(" ", strip=True).replace(label, "", 1).strip(" : ")
                    if cleaned:
                        sponsor = cleaned
                        break

        leverage_table = _table_after(soup, "Leverage")
        # "Effective Leverage" appears twice (USD + %); match the percent row.
        leverage_pct = _parse_pct(_row_value(leverage_table, "Effective Leverage (%)"))

        # CEFConnect dropped the dedicated Leverage Cost row; the closest live
        # signal is the Annual Expense Ratios "Interest Expense" line.
        expense_table = _table_after(soup, "Annual Expense Ratios")
        leverage_cost = _parse_pct(_row_value(expense_table, "Interest Expense"))
        # The expense table's bottom row is just "Total:" (not "Total Expense Ratio").
        expense_ratio = _parse_pct(_row_value(expense_table, "Total"))

        unii: float | None = None
        for strong in soup.find_all("strong"):
            if "unii" in strong.get_text(" ", strip=True).lower():
                parent = strong.find_parent(["tr", "p", "div"]) or strong.parent
                if parent is None:
                    continue
                text = parent.get_text(" ", strip=True).replace("(", "-").replace(")", "")
                for token in reversed(text.split()):
                    cleaned = token.lstrip("$").rstrip("%").replace(",", "")
                    value = _safe_float(cleaned)
                    if value is not None:
                        unii = value
                        break
                if unii is not None:
                    break

        return {
            "sponsor": sponsor,
            "leverage_pct": leverage_pct,
            "leverage_cost": leverage_cost,
            "unii": unii,
            "expense_ratio": expense_ratio,
        }


def _row_value(table, label_text: str) -> str | None:
    if table is None:
        return None
    target = label_text.strip().lower()
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        head = cells[0].get_text(" ", strip=True).lower()
        if target in head:
            return cells[-1].get_text(" ", strip=True)
    return None


def _table_after(soup: BeautifulSoup, header_text: str):
    target = header_text.strip().lower()
    for header in soup.find_all(["h5", "h4", "h3", "strong"]):
        if target in header.get_text(" ", strip=True).lower():
            sibling = header.find_next("table")
            if sibling is not None:
                return sibling
    return None
