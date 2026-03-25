from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx

from src.core.logging import get_logger

logger = get_logger(__name__)

RATES_TO_USD: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.08,
    "GBP": 1.27,
    "CAD": 0.74,
    "AUD": 0.65,
    "JPY": 0.0067,
    "CHF": 1.12,
    "INR": 0.012,
    "BRL": 0.20,
    "MXN": 0.058,
    "NGN": 0.00065,
    "RUB": 0.011,
    "CNY": 0.14,
}

# Free, no-API-key exchange rate endpoints (USD base)
_EXCHANGE_API_URL = "https://open.er-api.com/v6/latest/USD"
_REFRESH_TIMEOUT_SECONDS = 10


class FXService:
    """Multi-currency FX normalization service.

    Uses static built-in rates by default and can refresh from the
    Open Exchange Rates API (free, no key needed) via ``refresh_rates()``.
    """

    def __init__(self, rates: Optional[dict[str, float]] = None):
        self._rates = dict(rates) if rates else dict(RATES_TO_USD)
        self._last_refresh: datetime | None = None

    @property
    def last_refresh(self) -> datetime | None:
        return self._last_refresh

    @property
    def supported_currencies(self) -> list[str]:
        return sorted(self._rates.keys())

    def convert_to_usd(self, amount: float, currency_code: str) -> float:
        """Convert amount from given currency to USD."""
        code = (currency_code or "USD").strip().upper()
        rate = self._rates.get(code)
        if rate is None:
            logger.warning("fx_unknown_currency", currency=currency_code)
            return float(amount)
        return float(amount) * rate

    def get_rate(self, from_currency: str, to_currency: str) -> float:
        """Return exchange rate from one currency to another."""
        from_c = (from_currency or "USD").strip().upper()
        to_c = (to_currency or "USD").strip().upper()

        from_rate = self._rates.get(from_c)
        to_rate = self._rates.get(to_c)

        if from_rate is None:
            logger.warning("fx_unknown_currency", currency=from_currency)
            from_rate = 1.0
        if to_rate is None:
            logger.warning("fx_unknown_currency", currency=to_currency)
            to_rate = 1.0

        return to_rate / from_rate

    def normalize_amount(self, amount: float, currency_code: str) -> float:
        """Alias for convert_to_usd."""
        return self.convert_to_usd(amount, currency_code)

    def refresh_rates(self) -> dict[str, float]:
        """Fetch live exchange rates from Open Exchange Rates API.

        The API returns rates with USD as base, so we invert them to get
        "1 unit of X = ? USD" which matches our internal convention.
        Falls back to existing static rates on any error.
        """
        try:
            resp = httpx.get(_EXCHANGE_API_URL, timeout=_REFRESH_TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()

            if data.get("result") != "success":
                logger.warning("fx_refresh_api_error", detail=data.get("error-type"))
                return dict(self._rates)

            api_rates: dict[str, float] = data.get("rates", {})
            updated: dict[str, float] = {}
            for code, usd_per_one in api_rates.items():
                if usd_per_one and usd_per_one > 0:
                    updated[code] = 1.0 / usd_per_one

            if updated:
                updated["USD"] = 1.0
                self._rates = updated
                self._last_refresh = datetime.now(timezone.utc)
                logger.info(
                    "fx_rates_refreshed",
                    currencies=len(updated),
                    timestamp=self._last_refresh.isoformat(),
                )
            return dict(self._rates)

        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.error("fx_refresh_failed", error=str(exc))
            return dict(self._rates)

    async def refresh_rates_async(self) -> dict[str, float]:
        """Async variant of refresh_rates for use inside async services."""
        try:
            async with httpx.AsyncClient(timeout=_REFRESH_TIMEOUT_SECONDS) as client:
                resp = await client.get(_EXCHANGE_API_URL)
                resp.raise_for_status()
                data = resp.json()

            if data.get("result") != "success":
                logger.warning("fx_refresh_api_error", detail=data.get("error-type"))
                return dict(self._rates)

            api_rates: dict[str, float] = data.get("rates", {})
            updated: dict[str, float] = {}
            for code, usd_per_one in api_rates.items():
                if usd_per_one and usd_per_one > 0:
                    updated[code] = 1.0 / usd_per_one

            if updated:
                updated["USD"] = 1.0
                self._rates = updated
                self._last_refresh = datetime.now(timezone.utc)
                logger.info(
                    "fx_rates_refreshed",
                    currencies=len(updated),
                    timestamp=self._last_refresh.isoformat(),
                )
            return dict(self._rates)

        except (httpx.HTTPError, KeyError, ValueError) as exc:
            logger.error("fx_refresh_failed", error=str(exc))
            return dict(self._rates)
