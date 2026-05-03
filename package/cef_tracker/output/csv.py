"""CSV writer — extract-YYYYMMDDHHMM.csv."""

from __future__ import annotations

from pathlib import Path

from ..models import COLUMN_LABELS, FundSnapshot
from .base import OutputWriter
from .excel import _to_dataframe


class CSVWriter(OutputWriter):
    name = "csv"

    def __init__(self, fields: list[str] | None = None) -> None:
        self._fields = fields or list(COLUMN_LABELS.keys())

    def write(self, snapshots: list[FundSnapshot], extract_dir: Path) -> Path:
        extract_dir.mkdir(parents=True, exist_ok=True)
        timestamp = extract_dir.name
        path = extract_dir / f"extract-{timestamp}.csv"
        df = _to_dataframe(snapshots, self._fields)
        df.to_csv(path, index=False)
        return path
