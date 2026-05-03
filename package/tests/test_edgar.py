"""Pin EDGAR EFTS payload parsing against a recorded response."""

from __future__ import annotations

import json
from pathlib import Path

from cef_tracker.sources.edgar import EdgarSource

FIXTURE = Path(__file__).parent / "fixtures" / "edgar_BIT.json"


def test_edgar_filing_parse_from_recorded_response():
    payload = json.loads(FIXTURE.read_text())
    filings = EdgarSource.parse_filings(payload)
    assert len(filings) == 2
    assert filings[0] == ("2026-04-10", "0001999371-26-008092", "497")
    assert filings[1] == ("2026-03-27", "0000225322-26-000072", "497")
