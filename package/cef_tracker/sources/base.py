"""DataSource contract — what every fund-data backend must implement."""

from __future__ import annotations

import abc

from ..models import FundSnapshot, Ticker


# Teaching: a DataSource is a contract. Any class that fulfills this contract
# can be used by the rest of the application. Adding Morningstar later means
# writing a new MorningstarSource(DataSource) and changing one line in
# config.toml — no other code in the package needs to know it exists. That
# property is what the abstract base class buys you over a bag of free
# functions.
class DataSource(abc.ABC):
    """Contract: given a Ticker, return one source's view as a FundSnapshot."""

    name: str = "abstract"

    @abc.abstractmethod
    def fetch(self, ticker: Ticker) -> FundSnapshot:
        """Fetch one fund's data. Return a FundSnapshot with this source's fields
        populated and unknown fields left as None."""
