from __future__ import annotations

import pytest

from src.utils.fx_service import FXService


class TestFXService:
    def test_usd_identity(self):
        """Converting USD to USD returns same amount."""
        fx = FXService()
        assert fx.convert_to_usd(100.0, "USD") == 100.0
        assert fx.convert_to_usd(50.5, "USD") == 50.5

    def test_eur_to_usd(self):
        """Test EUR conversion."""
        fx = FXService()
        # 1 EUR = 1.08 USD
        assert fx.convert_to_usd(1.0, "EUR") == pytest.approx(1.08)
        assert fx.convert_to_usd(100.0, "EUR") == pytest.approx(108.0)

    def test_gbp_to_usd(self):
        """Test GBP conversion."""
        fx = FXService()
        # 1 GBP = 1.27 USD
        assert fx.convert_to_usd(1.0, "GBP") == pytest.approx(1.27)
        assert fx.convert_to_usd(100.0, "GBP") == pytest.approx(127.0)

    def test_jpy_to_usd(self):
        """Test JPY conversion (large amount)."""
        fx = FXService()
        # 1 JPY = 0.0067 USD
        assert fx.convert_to_usd(1.0, "JPY") == pytest.approx(0.0067)
        # 1,000,000 JPY
        assert fx.convert_to_usd(1_000_000.0, "JPY") == pytest.approx(6700.0)

    def test_unknown_currency(self):
        """Returns amount unchanged with warning."""
        fx = FXService()
        result = fx.convert_to_usd(100.0, "XYZ")
        assert result == 100.0
        result = fx.convert_to_usd(50.0, "UNKNOWN")
        assert result == 50.0

    def test_get_rate(self):
        """Test cross-rate calculation."""
        fx = FXService()
        # USD to USD
        assert fx.get_rate("USD", "USD") == pytest.approx(1.0)
        # EUR to USD: to_rate/from_rate = 1.0/1.08
        assert fx.get_rate("EUR", "USD") == pytest.approx(1.0 / 1.08)
        # USD to EUR: to_rate/from_rate = 1.08/1.0
        assert fx.get_rate("USD", "EUR") == pytest.approx(1.08)
        # GBP to EUR
        assert fx.get_rate("GBP", "EUR") == pytest.approx(1.08 / 1.27)
        # Unknown currency falls back to 1.0 rate
        assert fx.get_rate("XYZ", "USD") == pytest.approx(1.0)
