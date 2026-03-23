from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# MCC-based spending profiles: (mean_log, sigma_log) for lognormal amounts
# ---------------------------------------------------------------------------
_MCC_PROFILES: dict[str, tuple[float, float, float, float]] = {
    # category: (lognorm_mu, lognorm_sigma, clip_lo, clip_hi)
    "groceries":  (3.8, 0.65, 20.0,  200.0),
    "gas":        (3.6, 0.30, 30.0,   80.0),
    "restaurant": (3.3, 0.60, 15.0,  150.0),
    "ecommerce":  (4.0, 1.00, 10.0, 2000.0),
    "travel":     (5.5, 0.70, 50.0, 5000.0),
    "utilities":  (4.2, 0.40, 30.0,  500.0),
}
_MCC_KEYS = list(_MCC_PROFILES.keys())

_FRAUD_TYPES = [
    "card_testing",
    "ato",
    "friendly_fraud",
    "merchant_compromise",
    "fraud_ring",
    "synthetic_identity",
]
_FRAUD_RATES_DEFAULT = {
    "card_testing":         0.003,
    "ato":                  0.005,
    "friendly_fraud":       0.003,
    "merchant_compromise":  0.002,
    "fraud_ring":           0.005,
    "synthetic_identity":   0.002,
}


@dataclass
class FraudSimulator:
    """Vectorised fraud simulation engine that produces platform-compatible datasets."""

    n_customers: int = 5_000
    n_merchants: int = 800
    n_devices: int = 3_000

    _rng: np.random.Generator = field(init=False, repr=False)

    # ------------------------------------------------------------------ public
    def generate(
        self,
        n_transactions: int = 50_000,
        fraud_rate: float = 0.02,
        start_date: str | datetime = "2025-01-01",
        end_date: str | datetime = "2025-06-30",
        seed: int = 42,
    ) -> pd.DataFrame:
        """Return a fully-populated transactions DataFrame."""
        self._rng = np.random.default_rng(seed)
        start = _to_dt(start_date)
        end = _to_dt(end_date)

        rate_map = self._scale_fraud_rates(fraud_rate)
        n_fraud = int(n_transactions * fraud_rate)
        n_normal = n_transactions - n_fraud

        fraud_budget = self._allocate_fraud_budget(n_fraud, rate_map)

        df_normal = self._gen_normal(n_normal, start, end)
        fraud_frames = [
            self._gen_card_testing(fraud_budget["card_testing"], start, end),
            self._gen_ato(fraud_budget["ato"], start, end),
            self._gen_friendly_fraud(fraud_budget["friendly_fraud"], start, end),
            self._gen_merchant_compromise(fraud_budget["merchant_compromise"], start, end),
            self._gen_fraud_ring(fraud_budget["fraud_ring"], start, end),
            self._gen_synthetic_identity(fraud_budget["synthetic_identity"], start, end),
        ]

        df = pd.concat([df_normal, *fraud_frames], ignore_index=True)
        df = df.sort_values("event_time").reset_index(drop=True)
        df["transaction_id"] = np.arange(1, len(df) + 1)
        self._compute_features(df)
        return df

    def generate_with_graph_data(
        self,
        n_transactions: int = 50_000,
        fraud_rate: float = 0.02,
        start_date: str | datetime = "2025-01-01",
        end_date: str | datetime = "2025-06-30",
        seed: int = 42,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return (transactions_df, graph_edges_df)."""
        df = self.generate(n_transactions, fraud_rate, start_date, end_date, seed)
        edges = self._build_graph_edges(df)
        return df, edges

    @staticmethod
    def generate_temporal_drift(
        base_df: pd.DataFrame,
        drift_factor: float = 2.0,
        drift_start_pct: float = 0.7,
    ) -> pd.DataFrame:
        """Introduce concept drift in the later portion of a dataset.

        Simulates real-world pattern evolution: fraud amounts scale up,
        new device/IP churn increases, and card-testing shifts to larger
        micro-amounts.
        """
        df = base_df.copy()
        n = len(df)
        pivot = int(n * drift_start_pct)
        drift_mask = df.index >= pivot
        rng = np.random.default_rng(99)

        fraud_drift = drift_mask & (df["is_fraud"])
        if fraud_drift.any():
            noise = rng.lognormal(0, 0.3, size=fraud_drift.sum())
            df.loc[fraud_drift, "billing_amount_usd"] = (
                df.loc[fraud_drift, "billing_amount_usd"] * drift_factor * noise
            ).round(2)

        ct_mask = drift_mask & (df["fraud_type"] == "card_testing")
        if ct_mask.any():
            df.loc[ct_mask, "billing_amount_usd"] = rng.uniform(5, 25, size=ct_mask.sum()).round(2)
            df.loc[ct_mask, "auth_amount"] = df.loc[ct_mask, "billing_amount_usd"]

        drift_all = df.index >= pivot
        n_drift = drift_all.sum()
        if n_drift > 0:
            device_pool_size = max(10, int(n_drift * 0.4))
            new_devices = [f"dev_drift_{i:06d}" for i in range(device_pool_size)]
            df.loc[drift_all, "device_id"] = rng.choice(new_devices, size=n_drift)

            new_ips = [f"10.{rng.integers(1,255)}.{rng.integers(0,255)}.{rng.integers(1,254)}"
                       for _ in range(max(10, int(n_drift * 0.3)))]
            df.loc[drift_all, "ip_address"] = rng.choice(new_ips, size=n_drift)

        late_fraud = drift_mask & df["is_fraud"]
        if late_fraud.any():
            df.loc[late_fraud, "amount_vs_customer_p95_ratio"] = (
                df.loc[late_fraud, "amount_vs_customer_p95_ratio"] * drift_factor
            ).clip(upper=50.0)
            df.loc[late_fraud, "device_risk_score"] = np.minimum(
                df.loc[late_fraud, "device_risk_score"] + 0.2, 1.0,
            )
            df.loc[late_fraud, "behavioral_risk_score"] = np.minimum(
                df.loc[late_fraud, "behavioral_risk_score"] + 0.15, 1.0,
            )

        return df

    # -------------------------------------------------------------- internals

    def _scale_fraud_rates(self, total_rate: float) -> dict[str, float]:
        base_sum = sum(_FRAUD_RATES_DEFAULT.values())
        scale = total_rate / base_sum if base_sum > 0 else 1.0
        return {k: v * scale for k, v in _FRAUD_RATES_DEFAULT.items()}

    def _allocate_fraud_budget(self, n_fraud: int, rate_map: dict[str, float]) -> dict[str, int]:
        total_rate = sum(rate_map.values())
        budget: dict[str, int] = {}
        allocated = 0
        items = list(rate_map.items())
        for i, (k, v) in enumerate(items):
            if i == len(items) - 1:
                budget[k] = max(1, n_fraud - allocated)
            else:
                n = max(1, int(round(n_fraud * v / total_rate)))
                budget[k] = n
                allocated += n
        return budget

    # --------------------------------------------------- entity ID generators
    def _customer_ids(self, n: int, pool: Optional[int] = None) -> np.ndarray:
        pool = pool or self.n_customers
        return self._rng.integers(1, pool + 1, size=n)

    def _account_ids(self, customer_ids: np.ndarray) -> np.ndarray:
        return customer_ids * 10 + self._rng.integers(0, 3, size=len(customer_ids))

    def _card_ids(self, account_ids: np.ndarray) -> np.ndarray:
        return account_ids * 100 + self._rng.integers(0, 5, size=len(account_ids))

    def _merchant_ids(self, n: int, pool: Optional[int] = None) -> np.ndarray:
        pool = pool or self.n_merchants
        return self._rng.integers(1, pool + 1, size=n)

    def _device_ids(self, n: int, pool: Optional[int] = None) -> np.ndarray:
        pool = pool or self.n_devices
        indices = self._rng.integers(0, pool, size=n)
        return np.array([f"dev_{i:06d}" for i in indices])

    def _ip_addresses(self, n: int) -> np.ndarray:
        octets = self._rng.integers(1, 255, size=(n, 4))
        return np.array([f"{a}.{b}.{c}.{d}" for a, b, c, d in octets])

    def _random_times(self, n: int, start: datetime, end: datetime) -> np.ndarray:
        """Time-of-day weighted random timestamps (more activity 9am-9pm)."""
        span_s = (end - start).total_seconds()
        offsets = self._rng.uniform(0, span_s, size=n)

        hours = (offsets % 86400) / 3600.0
        weights = np.exp(-((hours - 14) ** 2) / (2 * 5**2))
        accept = self._rng.random(n) < (weights / weights.max())
        offsets[~accept] = (offsets[~accept] + self._rng.uniform(7, 12, size=(~accept).sum()) * 3600) % span_s

        base = np.datetime64(start.replace(tzinfo=None), "us")
        return base + (offsets * 1e6).astype("timedelta64[us]")

    # --------------------------------------------------- normal transactions
    def _gen_normal(self, n: int, start: datetime, end: datetime) -> pd.DataFrame:
        rng = self._rng
        cust = self._customer_ids(n)
        acct = self._account_ids(cust)
        card = self._card_ids(acct)
        merch = self._merchant_ids(n)
        mcc_idx = rng.integers(0, len(_MCC_KEYS), size=n)
        mccs = np.array(_MCC_KEYS)[mcc_idx]

        amounts = np.empty(n, dtype=np.float64)
        for i, key in enumerate(_MCC_KEYS):
            mask = mcc_idx == i
            if mask.any():
                mu, sig, lo, hi = _MCC_PROFILES[key]
                amounts[mask] = np.clip(rng.lognormal(mu, sig, size=mask.sum()), lo, hi)
        amounts = np.round(amounts, 2)

        channels = rng.choice(["pos", "web", "mobile", "api"], size=n, p=[0.4, 0.3, 0.25, 0.05])
        auth_types = np.where(
            np.isin(channels, ["web", "mobile", "api"]),
            rng.choice(["card_not_present", "recurring"], size=n, p=[0.8, 0.2]),
            "card_present",
        )
        entry_modes = np.where(
            channels == "pos",
            rng.choice(["chip", "swipe", "tap"], size=n, p=[0.5, 0.2, 0.3]),
            "keyed",
        )
        countries = rng.choice(
            ["US", "US", "US", "US", "GB", "CA", "DE", "FR", "AU"],
            size=n,
        )

        return pd.DataFrame({
            "customer_id":          cust,
            "account_id":           acct,
            "card_id":              card,
            "merchant_id":          merch,
            "device_id":            self._device_ids(n),
            "ip_address":           self._ip_addresses(n),
            "auth_type":            auth_types,
            "channel":              channels,
            "entry_mode":           entry_modes,
            "auth_amount":          amounts,
            "currency_code":        np.where(countries == "US", "USD",
                                    np.where(countries == "GB", "GBP",
                                    np.where(countries == "CA", "CAD",
                                    np.where(countries == "AU", "AUD", "EUR")))),
            "merchant_country_code": countries,
            "billing_amount_usd":   amounts,
            "event_time":           self._random_times(n, start, end),
            "is_fraud":             False,
            "fraud_type":           "normal",
            "chargeback_delay_days": np.nan,
            "mcc_category":         mccs,
        })

    # --------------------------------------------------- card testing
    def _gen_card_testing(self, n: int, start: datetime, end: datetime) -> pd.DataFrame:
        rng = self._rng
        n_bursts = max(1, n // 8)
        burst_cards = self._customer_ids(n_bursts)
        burst_acct = self._account_ids(burst_cards)
        burst_card = self._card_ids(burst_acct)

        rows_per_burst = np.diff(np.sort(rng.integers(0, n, size=n_bursts - 1)))
        rows_per_burst = np.concatenate([[n - rows_per_burst.sum()], rows_per_burst])
        rows_per_burst = np.clip(rows_per_burst, 1, None)

        cust, acct, card = [], [], []
        times_list = []
        for i, count in enumerate(rows_per_burst):
            c = int(count)
            cust.extend([burst_cards[i]] * c)
            acct.extend([burst_acct[i]] * c)
            card.extend([burst_card[i]] * c)
            base_time = self._random_times(1, start, end)[0]
            offsets = np.sort(rng.integers(5, 300, size=c)).astype("timedelta64[s]")
            times_list.append(base_time + offsets)

        n_actual = len(cust)
        amounts = np.round(rng.uniform(1.0, 5.0, size=n_actual), 2)

        return pd.DataFrame({
            "customer_id":           np.array(cust),
            "account_id":            np.array(acct),
            "card_id":               np.array(card),
            "merchant_id":           self._merchant_ids(n_actual),
            "device_id":             self._device_ids(n_actual),
            "ip_address":            self._ip_addresses(n_actual),
            "auth_type":             "card_not_present",
            "channel":               rng.choice(["web", "mobile"], size=n_actual),
            "entry_mode":            "keyed",
            "auth_amount":           amounts,
            "currency_code":         "USD",
            "merchant_country_code": rng.choice(["US", "GB", "DE", "RU", "NG"], size=n_actual),
            "billing_amount_usd":    amounts,
            "event_time":            np.concatenate(times_list)[:n_actual],
            "is_fraud":              True,
            "fraud_type":            "card_testing",
            "chargeback_delay_days": rng.integers(7, 45, size=n_actual).astype(float),
            "mcc_category":          "ecommerce",
        })

    # --------------------------------------------------- account takeover
    def _gen_ato(self, n: int, start: datetime, end: datetime) -> pd.DataFrame:
        rng = self._rng
        cust = self._customer_ids(n)
        acct = self._account_ids(cust)
        card = self._card_ids(acct)

        new_devices = np.array([f"dev_ato_{i:06d}" for i in rng.integers(0, 500, size=n)])
        foreign_ips = np.array([
            f"{rng.integers(100,200)}.{rng.integers(0,255)}.{rng.integers(0,255)}.{rng.integers(1,254)}"
            for _ in range(n)
        ])

        amounts = np.round(rng.lognormal(6.5, 0.8, size=n).clip(200, 10_000), 2)

        return pd.DataFrame({
            "customer_id":           cust,
            "account_id":            acct,
            "card_id":               card,
            "merchant_id":           self._merchant_ids(n),
            "device_id":             new_devices,
            "ip_address":            foreign_ips,
            "auth_type":             "card_not_present",
            "channel":               rng.choice(["web", "mobile"], size=n, p=[0.6, 0.4]),
            "entry_mode":            "keyed",
            "auth_amount":           amounts,
            "currency_code":         "USD",
            "merchant_country_code": rng.choice(["US", "GB", "RU", "NG", "BR", "CN"], size=n),
            "billing_amount_usd":    amounts,
            "event_time":            self._random_times(n, start, end),
            "is_fraud":              True,
            "fraud_type":            "ato",
            "chargeback_delay_days": rng.integers(7, 60, size=n).astype(float),
            "mcc_category":          rng.choice(["ecommerce", "travel"], size=n),
        })

    # --------------------------------------------------- friendly fraud
    def _gen_friendly_fraud(self, n: int, start: datetime, end: datetime) -> pd.DataFrame:
        rng = self._rng
        cust = self._customer_ids(n)
        acct = self._account_ids(cust)
        card = self._card_ids(acct)

        mcc_idx = rng.integers(0, len(_MCC_KEYS), size=n)
        mccs = np.array(_MCC_KEYS)[mcc_idx]
        amounts = np.empty(n, dtype=np.float64)
        for i, key in enumerate(_MCC_KEYS):
            mask = mcc_idx == i
            if mask.any():
                mu, sig, lo, hi = _MCC_PROFILES[key]
                amounts[mask] = np.clip(rng.lognormal(mu, sig, size=mask.sum()), lo, hi)
        amounts = np.round(amounts, 2)

        channels = rng.choice(["pos", "web", "mobile"], size=n, p=[0.3, 0.4, 0.3])

        return pd.DataFrame({
            "customer_id":           cust,
            "account_id":            acct,
            "card_id":               card,
            "merchant_id":           self._merchant_ids(n),
            "device_id":             self._device_ids(n),
            "ip_address":            self._ip_addresses(n),
            "auth_type":             np.where(channels == "pos", "card_present", "card_not_present"),
            "channel":               channels,
            "entry_mode":            np.where(channels == "pos",
                                              rng.choice(["chip", "tap"], size=n), "keyed"),
            "auth_amount":           amounts,
            "currency_code":         "USD",
            "merchant_country_code": "US",
            "billing_amount_usd":    amounts,
            "event_time":            self._random_times(n, start, end),
            "is_fraud":              True,
            "fraud_type":            "friendly_fraud",
            "chargeback_delay_days": rng.integers(30, 120, size=n).astype(float),
            "mcc_category":          mccs,
        })

    # --------------------------------------------------- merchant compromise
    def _gen_merchant_compromise(self, n: int, start: datetime, end: datetime) -> pd.DataFrame:
        rng = self._rng
        n_compromised = max(1, n // 15)
        bad_merchants = self._merchant_ids(n_compromised, pool=50)

        merchant_assign = rng.choice(bad_merchants, size=n)
        cust = self._customer_ids(n)
        acct = self._account_ids(cust)
        card = self._card_ids(acct)
        amounts = np.round(rng.lognormal(4.5, 0.9, size=n).clip(20, 3000), 2)

        base_times = {}
        event_times = np.empty(n, dtype="datetime64[us]")
        for i in range(n):
            mid = int(merchant_assign[i])
            if mid not in base_times:
                base_times[mid] = self._random_times(1, start, end)[0]
            event_times[i] = base_times[mid] + np.timedelta64(int(rng.integers(0, 7200)), "s")

        return pd.DataFrame({
            "customer_id":           cust,
            "account_id":            acct,
            "card_id":               card,
            "merchant_id":           merchant_assign,
            "device_id":             self._device_ids(n),
            "ip_address":            self._ip_addresses(n),
            "auth_type":             rng.choice(["card_present", "card_not_present"], size=n),
            "channel":               rng.choice(["pos", "web"], size=n, p=[0.6, 0.4]),
            "entry_mode":            rng.choice(["chip", "swipe", "keyed"], size=n),
            "auth_amount":           amounts,
            "currency_code":         "USD",
            "merchant_country_code": rng.choice(["US", "US", "GB"], size=n),
            "billing_amount_usd":    amounts,
            "event_time":            event_times,
            "is_fraud":              True,
            "fraud_type":            "merchant_compromise",
            "chargeback_delay_days": rng.integers(14, 90, size=n).astype(float),
            "mcc_category":          rng.choice(["restaurant", "gas", "ecommerce"], size=n),
        })

    # --------------------------------------------------- fraud ring
    def _gen_fraud_ring(self, n: int, start: datetime, end: datetime) -> pd.DataFrame:
        rng = self._rng
        n_rings = max(1, n // 12)
        ring_size = max(3, n // n_rings)

        shared_devices = [f"dev_ring_{i:04d}" for i in range(n_rings)]
        shared_ips = [
            f"45.{rng.integers(0,255)}.{rng.integers(0,255)}.{rng.integers(1,254)}"
            for _ in range(n_rings)
        ]

        records: dict[str, list] = {k: [] for k in [
            "customer_id", "account_id", "card_id", "merchant_id",
            "device_id", "ip_address", "event_time",
        ]}
        for ring_idx in range(n_rings):
            sz = min(ring_size, n - len(records["customer_id"]))
            if sz <= 0:
                break
            ring_custs = self._customer_ids(max(2, sz // 3), pool=200)
            members = rng.choice(ring_custs, size=sz, replace=True)
            accts = self._account_ids(members)
            cards = self._card_ids(accts)
            base_time = self._random_times(1, start, end)[0]

            records["customer_id"].extend(members.tolist())
            records["account_id"].extend(accts.tolist())
            records["card_id"].extend(cards.tolist())
            records["merchant_id"].extend(self._merchant_ids(sz).tolist())
            dev_choices = rng.choice(
                [shared_devices[ring_idx], *self._device_ids(2).tolist()], size=sz,
            )
            records["device_id"].extend(dev_choices.tolist())
            ip_choices = rng.choice(
                [shared_ips[ring_idx], *self._ip_addresses(2).tolist()], size=sz,
            )
            records["ip_address"].extend(ip_choices.tolist())
            offsets = np.sort(rng.integers(0, 86400, size=sz)).astype("timedelta64[s]")
            records["event_time"].extend((base_time + offsets).tolist())

        n_actual = len(records["customer_id"])
        amounts = np.round(rng.lognormal(5.0, 1.0, size=n_actual).clip(50, 5000), 2)

        return pd.DataFrame({
            "customer_id":           np.array(records["customer_id"]),
            "account_id":            np.array(records["account_id"]),
            "card_id":               np.array(records["card_id"]),
            "merchant_id":           np.array(records["merchant_id"]),
            "device_id":             np.array(records["device_id"]),
            "ip_address":            np.array(records["ip_address"]),
            "auth_type":             "card_not_present",
            "channel":               rng.choice(["web", "mobile"], size=n_actual),
            "entry_mode":            "keyed",
            "auth_amount":           amounts,
            "currency_code":         "USD",
            "merchant_country_code": rng.choice(["US", "GB", "DE", "NG"], size=n_actual),
            "billing_amount_usd":    amounts,
            "event_time":            np.array(records["event_time"], dtype="datetime64[us]"),
            "is_fraud":              True,
            "fraud_type":            "fraud_ring",
            "chargeback_delay_days": rng.integers(7, 60, size=n_actual).astype(float),
            "mcc_category":          rng.choice(["ecommerce", "travel"], size=n_actual),
        })

    # --------------------------------------------------- synthetic identity
    def _gen_synthetic_identity(self, n: int, start: datetime, end: datetime) -> pd.DataFrame:
        rng = self._rng
        synth_custs = np.arange(900_000, 900_000 + n)
        acct = synth_custs * 10
        card = acct * 100

        span_s = (end - start).total_seconds()
        recent_start = start + timedelta(seconds=span_s * 0.8)
        amounts = np.round(rng.lognormal(6.0, 0.9, size=n).clip(100, 8000), 2)

        return pd.DataFrame({
            "customer_id":           synth_custs,
            "account_id":            acct,
            "card_id":               card,
            "merchant_id":           self._merchant_ids(n),
            "device_id":             np.array([f"dev_synth_{i:06d}" for i in range(n)]),
            "ip_address":            self._ip_addresses(n),
            "auth_type":             "card_not_present",
            "channel":               rng.choice(["web", "mobile"], size=n),
            "entry_mode":            "keyed",
            "auth_amount":           amounts,
            "currency_code":         "USD",
            "merchant_country_code": rng.choice(["US", "US", "GB", "CA"], size=n),
            "billing_amount_usd":    amounts,
            "event_time":            self._random_times(n, recent_start, end),
            "is_fraud":              True,
            "fraud_type":            "synthetic_identity",
            "chargeback_delay_days": rng.integers(7, 90, size=n).astype(float),
            "mcc_category":          rng.choice(["ecommerce", "travel", "utilities"], size=n),
        })

    # --------------------------------------------------- feature computation
    def _compute_features(self, df: pd.DataFrame) -> None:
        """Vectorised computation of all 19 feature columns in-place."""
        rng = self._rng
        n = len(df)
        is_fraud = df["is_fraud"].values.astype(bool)
        fraud_type = df["fraud_type"].values

        # -- velocity features (Poisson-based with fraud-type scaling) ------
        base_cust_1h  = rng.poisson(1.5, size=n).astype(np.float64)
        base_cust_24h = rng.poisson(5.0, size=n).astype(np.float64)
        base_card_10m = rng.poisson(0.5, size=n).astype(np.float64)
        base_merch_10m = rng.poisson(2.0, size=n).astype(np.float64)

        ct_mask = fraud_type == "card_testing"
        base_card_10m[ct_mask] = rng.poisson(12, size=ct_mask.sum())
        base_cust_1h[ct_mask] = rng.poisson(15, size=ct_mask.sum())

        ato_mask = fraud_type == "ato"
        base_cust_1h[ato_mask] = rng.poisson(6, size=ato_mask.sum())
        base_cust_24h[ato_mask] = rng.poisson(12, size=ato_mask.sum())

        mc_mask = fraud_type == "merchant_compromise"
        base_merch_10m[mc_mask] = rng.poisson(20, size=mc_mask.sum())

        ring_mask = fraud_type == "fraud_ring"
        base_cust_24h[ring_mask] = rng.poisson(10, size=ring_mask.sum())

        df["customer_txn_count_1h"]  = base_cust_1h.astype(int)
        df["customer_txn_count_24h"] = base_cust_24h.astype(int)
        df["card_txn_count_10m"]     = base_card_10m.astype(int)
        df["merchant_txn_count_10m"] = base_merch_10m.astype(int)

        # -- spend features -------------------------------------------------
        df["customer_spend_24h"] = np.round(
            df["billing_amount_usd"].values * base_cust_24h * rng.uniform(0.3, 1.2, size=n), 2,
        )

        # -- merchant chargeback rate (beta-distributed) --------------------
        cb_rate = rng.beta(1, 200, size=n)
        cb_rate[mc_mask] = rng.beta(5, 20, size=mc_mask.sum())
        df["merchant_chargeback_rate_30d"] = np.round(cb_rate, 4)

        # -- device / IP sharing features -----------------------------------
        device_txn_1d = rng.poisson(3, size=n).astype(np.float64)
        device_acct_30d = np.ones(n, dtype=np.float64)
        ip_acct_7d = np.ones(n, dtype=np.float64)
        ip_card_7d = np.ones(n, dtype=np.float64)

        ring_mask_or_synth = (fraud_type == "fraud_ring") | (fraud_type == "synthetic_identity")
        device_acct_30d[ring_mask_or_synth] = rng.poisson(4, size=ring_mask_or_synth.sum()) + 2
        ip_acct_7d[ring_mask_or_synth] = rng.poisson(3, size=ring_mask_or_synth.sum()) + 2
        ip_card_7d[ring_mask_or_synth] = rng.poisson(5, size=ring_mask_or_synth.sum()) + 2

        device_txn_1d[ct_mask] = rng.poisson(20, size=ct_mask.sum())

        df["device_txn_count_1d"]     = device_txn_1d.astype(int)
        df["device_account_count_30d"] = device_acct_30d.astype(int)
        df["ip_account_count_7d"]      = ip_acct_7d.astype(int)
        df["ip_card_count_7d"]         = ip_card_7d.astype(int)

        # -- geo features ---------------------------------------------------
        geo_home = rng.exponential(15, size=n)
        geo_home[ato_mask] = rng.exponential(3000, size=ato_mask.sum())
        geo_home[ring_mask] = rng.exponential(800, size=ring_mask.sum())
        synth_mask = fraud_type == "synthetic_identity"
        geo_home[synth_mask] = rng.exponential(500, size=synth_mask.sum())

        df["geo_distance_from_home_km"] = np.round(geo_home, 3)
        df["geo_distance_from_last_txn_km"] = np.round(
            np.where(is_fraud, rng.exponential(200, size=n), rng.exponential(5, size=n)), 3,
        )

        # -- time since last txn --------------------------------------------
        df["seconds_since_last_txn"] = np.where(
            ct_mask,
            rng.integers(5, 120, size=n),
            np.where(is_fraud, rng.integers(60, 3600, size=n), rng.integers(300, 86400, size=n)),
        ).astype(int)

        # -- amount anomaly ratios ------------------------------------------
        amt = df["billing_amount_usd"].values.astype(np.float64)
        cust_p95 = np.where(is_fraud, amt * rng.uniform(0.15, 0.6, size=n), amt * rng.uniform(0.6, 1.4, size=n))
        cust_p95 = np.where(cust_p95 > 0, amt / cust_p95, 1.0)
        df["amount_vs_customer_p95_ratio"] = np.round(cust_p95.clip(0.01, 30.0), 4)

        merch_p95 = np.where(is_fraud, amt * rng.uniform(0.2, 0.5, size=n), amt * rng.uniform(0.7, 1.3, size=n))
        merch_p95 = np.where(merch_p95 > 0, amt / merch_p95, 1.0)
        df["amount_vs_merchant_p95_ratio"] = np.round(merch_p95.clip(0.01, 20.0), 4)

        # -- boolean / risk score features ----------------------------------
        vpn_prob = np.where(is_fraud, 0.35, 0.02)
        df["proxy_vpn_tor_flag"] = rng.random(n) < vpn_prob

        device_risk = rng.beta(2, 20, size=n)
        device_risk[ato_mask] = rng.beta(8, 5, size=ato_mask.sum())
        device_risk[ring_mask_or_synth] = rng.beta(6, 6, size=ring_mask_or_synth.sum())
        df["device_risk_score"] = np.round(device_risk.clip(0, 1), 4)

        behavior_risk = rng.beta(2, 30, size=n)
        behavior_risk[is_fraud] = rng.beta(5, 5, size=is_fraud.sum())
        df["behavioral_risk_score"] = np.round(behavior_risk.clip(0, 1), 4)

        graph_risk = rng.beta(1, 50, size=n)
        graph_risk[ring_mask] = rng.beta(8, 3, size=ring_mask.sum())
        graph_risk[synth_mask] = rng.beta(6, 4, size=synth_mask.sum())
        df["graph_cluster_risk_score"] = np.round(graph_risk.clip(0, 1), 4)

        df.drop(columns=["mcc_category"], inplace=True)

    # --------------------------------------------------- graph edges
    def _build_graph_edges(self, df: pd.DataFrame) -> pd.DataFrame:
        """Build entity-relationship graph edges from transaction data."""
        acct_dev = (
            df.groupby(["account_id", "device_id"]).size()
            .reset_index(name="weight")
        )
        acct_dev.rename(columns={"account_id": "src_node_id", "device_id": "dst_node_id"}, inplace=True)
        acct_dev["src_node_id"] = "acct_" + acct_dev["src_node_id"].astype(str)
        acct_dev["edge_type"] = "account_device"

        acct_ip = (
            df.groupby(["account_id", "ip_address"]).size()
            .reset_index(name="weight")
        )
        acct_ip.rename(columns={"account_id": "src_node_id", "ip_address": "dst_node_id"}, inplace=True)
        acct_ip["src_node_id"] = "acct_" + acct_ip["src_node_id"].astype(str)
        acct_ip["edge_type"] = "account_ip"

        dev_ip = (
            df.groupby(["device_id", "ip_address"]).size()
            .reset_index(name="weight")
        )
        dev_ip.rename(columns={"device_id": "src_node_id", "ip_address": "dst_node_id"}, inplace=True)
        dev_ip["edge_type"] = "device_ip"

        edges = pd.concat([acct_dev, acct_ip, dev_ip], ignore_index=True)
        edges["weight"] = edges["weight"].clip(upper=50.0).astype(float)
        return edges[["src_node_id", "dst_node_id", "edge_type", "weight"]].reset_index(drop=True)


# ---------------------------------------------------------------------- utils
def _to_dt(val: str | datetime) -> datetime:
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(val).replace(tzinfo=timezone.utc)
