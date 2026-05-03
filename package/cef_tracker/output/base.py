"""OutputWriter contract — what every output backend must implement."""

from __future__ import annotations

import abc
from pathlib import Path

from ..models import FundSnapshot


# Teaching: same pattern as DataSource, applied to outputs. Adding a new
# format (Parquet, JSON, Google Sheets) means writing one new file under
# output/ and naming it in config.toml. No other code changes.
class OutputWriter(abc.ABC):
    """Contract: write a list of FundSnapshots to disk under `extract_dir`."""

    name: str = "abstract"

    @abc.abstractmethod
    def write(self, snapshots: list[FundSnapshot], extract_dir: Path) -> Path:
        """Write the snapshots and return the path to the written file."""
