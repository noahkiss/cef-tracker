"""Shared HTTP helper for every DataSource."""

from __future__ import annotations

import time

import requests


# Teaching: exponential backoff is the standard polite-retry pattern for
# talking to services you don't own. When a request fails for a transient
# reason — a network blip, a brief upstream overload, a rate-limit — retrying
# immediately just adds load while the upstream is already struggling.
# Doubling the delay between attempts (0.5s -> 1.0s -> 2.0s) gives the
# upstream room to recover. We retry on network errors, HTTP 429, and
# HTTP 5xx; we pass through other 4xx immediately because those are *our*
# fault and won't fix themselves.
#
# Pulling this helper out of the data sources is what the DataSource ABC
# architecture buys you: both CEFConnectSource and EdgarSource share one
# implementation, and a future MorningstarSource gets the same behavior for
# free.
def get_with_backoff(
    session: requests.Session,
    url: str,
    *,
    headers: dict | None = None,
    max_attempts: int = 3,
    base_delay: float = 0.5,
    timeout: float = 15.0,
) -> requests.Response:
    """GET `url` with exponential backoff on transient errors."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            response = session.get(url, headers=headers, timeout=timeout)
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
        response.raise_for_status()

    if last_exc:
        raise last_exc
    raise RuntimeError(f"get_with_backoff exhausted attempts for {url}")
