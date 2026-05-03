"""End-to-end parser tests against recorded CEFConnect responses for BIT."""

from __future__ import annotations

import json
from pathlib import Path

from cef_tracker.sources.cefconnect import CEFConnectSource

FIXTURES = Path(__file__).parent / "fixtures"


def test_field_extraction_from_recorded_responses():
    pricing = json.loads((FIXTURES / "cefconnect_BIT_pricing.json").read_text())
    performance = json.loads((FIXTURES / "cefconnect_BIT_performance.json").read_text())
    distributions = json.loads((FIXTURES / "cefconnect_BIT_distributions.json").read_text())
    search = json.loads((FIXTURES / "cefconnect_BIT_search.json").read_text())
    html = (FIXTURES / "cefconnect_BIT_page.html").read_text()

    pricing_fields = CEFConnectSource._parse_pricing(pricing)
    perf_fields = CEFConnectSource._parse_performance(performance)
    dist_fields = CEFConnectSource._parse_distributions(
        distributions, market_price=pricing_fields["market_price"]
    )
    html_fields = CEFConnectSource._parse_html_metadata(html)
    name = next(
        (row["Result"] for row in search if row.get("Ticker") == "BIT"), None
    )

    assert name == "BlackRock Multi-Sector Income Trust"
    assert html_fields["sponsor"] == "BlackRock"
    assert pricing_fields["nav"] == 13.5
    assert pricing_fields["market_price"] == 12.82
    assert pricing_fields["discount_pct"] == -5.04
    assert html_fields["leverage_pct"] == 30.40
    assert perf_fields["total_return_1y"] == 8.57
    assert dist_fields["distribution_rate"] is not None
    assert 11.0 < dist_fields["distribution_rate"] < 12.0
