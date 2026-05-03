"""Snapshot a list of closed-end funds from CEFConnect into timestamped Excel/CSV.

Run from this directory:

    pip install -r requirements.txt
    python cef_snapshot.py

Reads tickers from `tickers.txt` (one symbol per line) and writes
`extracts/extract-YYYYMMDDHHMM.xlsx` and `extracts/extract-YYYYMMDDHHMM.csv`
into the working directory. Every run is its own pair of files; nothing is
ever overwritten.
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

# Output column order. Internal field names are snake_case; the rename below
# is what a reader sees in Excel.
FIELDS: list[str] = [
    "ticker",
    "name",
    "sponsor",
    "nav",
    "market_price",
    "discount_pct",
    "leverage_pct",
    "leverage_cost",
    "distribution_rate",
    "roc_pct",
    "unii",
    "expense_ratio",
    "total_return_1y",
    "total_return_3y",
    "total_return_5y",
    "total_return_10y",
]

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

HERE = Path(__file__).parent
TICKERS_FILE = HERE / "tickers.txt"
EXTRACTS_DIR = HERE / "extracts"

PRICING_URL = "https://www.cefconnect.com/api/v3/pricinghistory/{ticker}/{range}"
PERFORMANCE_URL = "https://www.cefconnect.com/api/v3/performance/annualized/{ticker}"
DISTRIBUTIONS_URL = (
    "https://www.cefconnect.com/api/v3/distributionhistory/fund/{ticker}/{start}/{end}"
)
SEARCH_TICKERS_URL = "https://www.cefconnect.com/api/v3/search/tickers"
FUND_PAGE_URL = "https://www.cefconnect.com/fund/{ticker}"

HEADERS_BASE = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


# Teaching: exponential backoff is the standard polite-retry pattern for
# talking to services you don't own. When a request fails for a transient
# reason (the network blipped, the server is briefly overloaded, you got
# rate-limited), retrying immediately just makes the problem worse — you
# add load while the upstream is already struggling. Doubling the delay
# between attempts gives the upstream room to recover. Three attempts with
# a 0.5s base delay caps the worst case at ~3.5s of waiting before giving
# up, which is the right tradeoff for a 60-fund interactive run. We retry
# on network errors, HTTP 429 (rate-limited), and HTTP 5xx (server fault),
# and pass through other 4xx (those are *our* fault and won't fix themselves).
def get_with_backoff(
    url: str,
    headers: dict | None = None,
    max_attempts: int = 3,
    base_delay: float = 0.5,
) -> requests.Response:
    """GET `url` with exponential backoff on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            response = requests.get(url, headers=headers, timeout=15)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == max_attempts - 1:
                raise
            time.sleep(base_delay * 2**attempt)
            continue

        if response.status_code < 400:
            return response
        if response.status_code == 429 or 500 <= response.status_code < 600:
            if attempt == max_attempts - 1:
                response.raise_for_status()
            time.sleep(base_delay * 2**attempt)
            continue
        # Other 4xx — won't fix itself; surface immediately.
        response.raise_for_status()

    # Defensive — should be unreachable.
    if last_exc:
        raise last_exc
    raise RuntimeError(f"get_with_backoff exhausted attempts for {url}")


def _headers_for(ticker: str) -> dict:
    """Browser-ish headers with a per-fund Referer (CEFConnect prefers this)."""
    return {**HEADERS_BASE, "Referer": FUND_PAGE_URL.format(ticker=ticker)}


def _safe_float(value: object) -> float | None:
    """Coerce to float, returning None for missing or unparseable values."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_pct(text: str) -> float | None:
    """Parse '34.21%' or '-3.45 %' style text into a float, percent-stripped."""
    if not text:
        return None
    cleaned = text.strip().replace(",", "").rstrip("%").strip()
    return _safe_float(cleaned)


def fetch_name_lookup() -> dict[str, str]:
    """Build TICKER → fund name from the search/tickers endpoint."""
    response = get_with_backoff(SEARCH_TICKERS_URL, headers=HEADERS_BASE)
    rows = response.json()
    lookup: dict[str, str] = {}
    for row in rows or []:
        ticker = (row.get("Ticker") or "").strip().upper()
        name = row.get("Result") or row.get("Name")
        if ticker and name:
            lookup[ticker] = name.strip()
    return lookup


def _parse_pricing(payload: dict) -> dict:
    """Latest NAV / market_price / discount_pct from pricinghistory."""
    data = payload.get("Data") if isinstance(payload, dict) else None
    rows = (data or {}).get("PriceHistory") or []
    if not rows:
        return {"nav": None, "market_price": None, "discount_pct": None}
    # PriceHistory is sorted newest-first.
    latest = rows[0]
    return {
        "nav": _safe_float(latest.get("NAVData")),
        "market_price": _safe_float(latest.get("Data")),
        "discount_pct": _safe_float(latest.get("DiscountData")),
    }


def _parse_performance(payload: dict) -> dict:
    """Trailing NAV total returns by horizon (1Y / 3Y / 5Y / 10Y)."""
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


def _parse_distributions(payload: dict, market_price: float | None) -> dict:
    """Distribution rate (12 × latest TotDiv / price) and ROC % over the window."""
    rows = payload.get("Data", []) if isinstance(payload, dict) else []
    if not rows:
        return {"distribution_rate": None, "roc_pct": None}

    latest_totdiv = _safe_float(rows[0].get("TotDiv"))
    distribution_rate: float | None
    if latest_totdiv is not None and market_price:
        distribution_rate = (12.0 * latest_totdiv / market_price) * 100.0
    else:
        distribution_rate = None

    totdiv_sum = 0.0
    capret_sum = 0.0
    for row in rows:
        td = _safe_float(row.get("TotDiv")) or 0.0
        cr = _safe_float(row.get("CapitalReturn")) or 0.0
        totdiv_sum += td
        capret_sum += cr
    roc_pct = (capret_sum / totdiv_sum * 100.0) if totdiv_sum else None

    return {"distribution_rate": distribution_rate, "roc_pct": roc_pct}


def _row_value(table, label_text: str) -> str | None:
    """Find a `<tr>` whose first cell matches `label_text` and return its
    last cell text. Returns None if no match."""
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
    """Return the first `<table>` that follows a heading containing `header_text`."""
    target = header_text.strip().lower()
    for header in soup.find_all(["h5", "h4", "h3", "strong"]):
        if target in header.get_text(" ", strip=True).lower():
            sibling = header.find_next("table")
            if sibling is not None:
                return sibling
    return None


def _parse_html_metadata(html: str) -> dict:
    """Sponsor, leverage, UNII, expense ratio from the per-fund HTML page.

    Locators key off surrounding text (`<strong>` labels, table-row labels)
    rather than ASP.NET IDs because the IDs change without notice.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Sponsor — look for a <strong>Fund Sponsor</strong> followed by a value.
    sponsor: str | None = None
    for strong in soup.find_all("strong"):
        if "fund sponsor" in strong.get_text(" ", strip=True).lower():
            parent = strong.parent
            if parent:
                # Collect text after the <strong>, dropping the label itself.
                text = parent.get_text(" ", strip=True)
                label = strong.get_text(" ", strip=True)
                cleaned = text.replace(label, "", 1).strip(" : ")
                if cleaned:
                    sponsor = cleaned
                    break

    leverage_table = _table_after(soup, "Leverage")
    # The leverage table renders "Effective Leverage" twice — once as USD and
    # once as a percent. Match the percent row explicitly.
    leverage_pct = _parse_pct(
        _row_value(leverage_table, "Effective Leverage (%)") or ""
    )
    # CEFConnect dropped the dedicated "Leverage Cost" row; the closest live
    # signal is the Annual Expense Ratios "Interest Expense" line. We keep the
    # field name (downstream diff rule depends on it) and source it there.
    expense_table = _table_after(soup, "Annual Expense Ratios")
    leverage_cost = _parse_pct(_row_value(expense_table, "Interest Expense") or "")
    # The expense table's bottom row is just "Total:" (not "Total Expense Ratio").
    expense_ratio = _parse_pct(_row_value(expense_table, "Total") or "")

    # UNII — locate by surrounding <strong> containing "UNII".
    unii: float | None = None
    for strong in soup.find_all("strong"):
        if "unii" in strong.get_text(" ", strip=True).lower():
            # Most sponsors render the value in the same row/parent text.
            parent = strong.find_parent(["tr", "p", "div"]) or strong.parent
            if parent is None:
                continue
            text = parent.get_text(" ", strip=True)
            # Pull the rightmost numeric token (handles "$0.05" / "0.05" / "(0.02)").
            for token in reversed(text.replace("(", "-").replace(")", "").split()):
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


def fetch_one_fund(ticker: str, name_lookup: dict[str, str]) -> dict:
    """Fetch one fund from CEFConnect and return a flat dict keyed by FIELDS."""
    headers = _headers_for(ticker)
    snapshot: dict = {field: None for field in FIELDS}
    snapshot["ticker"] = ticker
    snapshot["name"] = name_lookup.get(ticker.upper())

    # 1Y window for the distribution history.
    today = datetime.now().date()
    one_year_ago = today - timedelta(days=365)
    start = one_year_ago.strftime("%m-%d-%Y")
    end = today.strftime("%m-%d-%Y")

    pricing = get_with_backoff(
        PRICING_URL.format(ticker=ticker, range="5D"), headers=headers
    ).json()
    snapshot.update(_parse_pricing(pricing))

    performance = get_with_backoff(
        PERFORMANCE_URL.format(ticker=ticker), headers=headers
    ).json()
    snapshot.update(_parse_performance(performance))

    distributions = get_with_backoff(
        DISTRIBUTIONS_URL.format(ticker=ticker, start=start, end=end), headers=headers
    ).json()
    snapshot.update(_parse_distributions(distributions, snapshot.get("market_price")))

    html = get_with_backoff(
        FUND_PAGE_URL.format(ticker=ticker), headers=headers
    ).text
    snapshot.update(_parse_html_metadata(html))

    return snapshot


def fetch_all_funds(tickers: list[str]) -> pd.DataFrame:
    """Fetch all tickers in order, logging progress, returning a DataFrame."""
    name_lookup = fetch_name_lookup()
    rows: list[dict] = []
    for i, ticker in enumerate(tickers, start=1):
        print(f"[{i}/{len(tickers)}] {ticker} …", flush=True)
        try:
            rows.append(fetch_one_fund(ticker, name_lookup))
        except Exception as exc:
            print(f"  ! {ticker} failed: {exc}", file=sys.stderr)
            rows.append({**{f: None for f in FIELDS}, "ticker": ticker})
    return pd.DataFrame(rows, columns=FIELDS)


def write_outputs(df: pd.DataFrame, extracts_dir: Path) -> tuple[Path, Path]:
    """Write timestamped xlsx + csv into `extracts_dir`. Returns the two paths."""
    extracts_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M")
    xlsx_path = extracts_dir / f"extract-{timestamp}.xlsx"
    csv_path = extracts_dir / f"extract-{timestamp}.csv"

    labeled = df.rename(columns=COLUMN_LABELS)
    labeled.to_excel(xlsx_path, index=False, engine="openpyxl")
    labeled.to_csv(csv_path, index=False)
    return xlsx_path, csv_path


def read_tickers(path: Path) -> list[str]:
    """Read tickers, one per line. Skip blanks and `#` comments."""
    tickers: list[str] = []
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tickers.append(stripped.upper())
    return tickers


def main() -> None:
    tickers = read_tickers(TICKERS_FILE)
    if not tickers:
        print(f"No tickers found in {TICKERS_FILE}.", file=sys.stderr)
        sys.exit(1)
    print(f"Fetching {len(tickers)} funds from CEFConnect …")
    df = fetch_all_funds(tickers)
    xlsx_path, csv_path = write_outputs(df, EXTRACTS_DIR)
    print(f"Wrote {xlsx_path}")
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
