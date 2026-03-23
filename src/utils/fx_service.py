from __future__ import annotations

from typing import Optional

from src.core.logging import get_logger

logger = get_logger(__name__)

# Static rates: USD equivalent per 1 unit of foreign currency (as of 2024)
# e.g. 1 EUR = 1.08 USD, 1 GBP = 1.27 USD
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


class FXService:
    """Multi-currency FX normalization service with static rates."""

    def __init__(self, rates: Optional[dict[str, float]] = None):
        self._rates = dict(rates) if rates else dict(RATES_TO_USD)

    def convert_to_usd(self, amount: float, currency_code: str) -> float:
        """Convert amount from given currency to USD."""
        code = (currency_code or "USD").strip().upper()
        rate = self._rates.get(code)
        if rate is None:
            logger.warning("fx_unknown_currency", currency=currency_code)
            return float(amount)  # Assume USD if unknown
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

        # Rate from A to B = (USD per B) / (USD per A)
        return to_rate / from_rate

    def normalize_amount(self, amount: float, currency_code: str) -> float:
        """Alias for convert_to_usd."""
        return self.convert_to_usd(amount, currency_code)

    def refresh_rates(self) -> None:
        """Placeholder for fetching live rates from an API."""
        logger.info("fx_refresh_rates", message="Would fetch live rates from API")
