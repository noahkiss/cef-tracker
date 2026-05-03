"""Excel writer — extract-YYYYMMDDHHMM.xlsx via pandas + openpyxl."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..models import COLUMN_LABELS, FundSnapshot
from .base import OutputWriter


class ExcelWriter(OutputWriter):
    name = "excel"

    def __init__(self, fields: list[str] | None = None) -> None:
        # `fields` is the internal-name column order; default to COLUMN_LABELS.
        self._fields = fields or list(COLUMN_LABELS.keys())

    def write(self, snapshots: list[FundSnapshot], extract_dir: Path) -> Path:
        extract_dir.mkdir(parents=True, exist_ok=True)
        timestamp = extract_dir.name
        path = extract_dir / f"extract-{timestamp}.xlsx"
        df = _to_dataframe(snapshots, self._fields)
        df.to_excel(path, index=False, engine="openpyxl")
        return path


def _to_dataframe(snapshots: list[FundSnapshot], fields: list[str]) -> pd.DataFrame:
    rows = [snap.to_dict() for snap in snapshots]
    columns = [COLUMN_LABELS[f] for f in fields if f in COLUMN_LABELS]
    return pd.DataFrame(rows, columns=columns)
