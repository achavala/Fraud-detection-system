"""
Deterministic rules engine — runs alongside ML models.
Supports versioned rule sets, severity levels, and explanation generation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.logging import get_logger
from src.models.scoring import FactRuleScore

logger = get_logger(__name__)

RULE_SET_VERSION = "rules-v3.1.0"


class Rule:
    def __init__(self, rule_id: str, name: str, severity: str, condition_fn, explanation_fn):
        self.rule_id = rule_id
        self.name = name
        self.severity = severity
        self.condition_fn = condition_fn
        self.explanation_fn = explanation_fn

    def evaluate(self, features: dict, context: dict) -> tuple[bool, float, str]:
        fired = self.condition_fn(features, context)
        score = 1.0 if fired else 0.0
        explanation = self.explanation_fn(features, context) if fired else ""
        return fired, score, explanation


def _high_velocity_card(f, c):
    return f.get("card_txn_count_10m", 0) >= 5

def _high_velocity_card_explain(f, c):
    return f"Card used {f.get('card_txn_count_10m', 0)} times in 10 minutes"

def _multi_account_device(f, c):
    return f.get("device_account_count_30d", 0) >= 3

def _multi_account_device_explain(f, c):
    return f"Device linked to {f.get('device_account_count_30d', 0)} accounts in 30 days"

def _vpn_proxy(f, c):
    return f.get("proxy_vpn_tor_flag", False)

def _vpn_proxy_explain(f, c):
    return "Transaction originated from VPN/proxy/Tor"

def _high_amount_ratio(f, c):
    return f.get("amount_vs_customer_p95_ratio", 0) > 3.0

def _high_amount_explain(f, c):
    return f"Amount is {f.get('amount_vs_customer_p95_ratio', 0):.1f}x customer's p95"

def _multi_ip_cards(f, c):
    return f.get("ip_card_count_7d", 0) >= 5

def _multi_ip_cards_explain(f, c):
    return f"IP used with {f.get('ip_card_count_7d', 0)} different cards in 7 days"

def _rapid_fire(f, c):
    return (f.get("seconds_since_last_txn") or 999999) < 30

def _rapid_fire_explain(f, c):
    return f"Only {f.get('seconds_since_last_txn', 0)}s since last transaction"

def _emulator_device(f, c):
    return f.get("device_risk_score", 0) >= 0.4

def _emulator_device_explain(f, c):
    return f"Device risk score is {f.get('device_risk_score', 0):.2f} (emulator/rooted)"

def _high_spend_24h(f, c):
    return f.get("customer_spend_24h", 0) > 5000

def _high_spend_24h_explain(f, c):
    return f"Customer spent ${f.get('customer_spend_24h', 0):.0f} in 24h"


DEFAULT_RULES = [
    Rule("R001", "high_velocity_card_10m", "high", _high_velocity_card, _high_velocity_card_explain),
    Rule("R002", "multi_account_device_30d", "high", _multi_account_device, _multi_account_device_explain),
    Rule("R003", "vpn_proxy_tor", "medium", _vpn_proxy, _vpn_proxy_explain),
    Rule("R004", "amount_exceeds_3x_p95", "medium", _high_amount_ratio, _high_amount_explain),
    Rule("R005", "multi_card_ip_7d", "high", _multi_ip_cards, _multi_ip_cards_explain),
    Rule("R006", "rapid_fire_under_30s", "high", _rapid_fire, _rapid_fire_explain),
    Rule("R007", "emulator_rooted_device", "medium", _emulator_device, _emulator_device_explain),
    Rule("R008", "high_spend_24h", "low", _high_spend_24h, _high_spend_24h_explain),
]


class RulesEngine:
    def __init__(self, db: AsyncSession, rules: list[Rule] | None = None):
        self.db = db
        self.rules = rules or DEFAULT_RULES

    async def evaluate(
        self,
        auth_event_id: int,
        features: dict,
        context: dict | None = None,
    ) -> list[FactRuleScore]:
        context = context or {}
        results = []
        now = datetime.now(timezone.utc)

        for rule in self.rules:
            fired, score, explanation = rule.evaluate(features, context)
            record = FactRuleScore(
                auth_event_id=auth_event_id,
                rule_set_version=RULE_SET_VERSION,
                rule_id=rule.rule_id,
                rule_name=rule.name,
                fired_flag=fired,
                severity=rule.severity,
                contribution_score=score,
                explanation=explanation,
                score_time=now,
            )
            self.db.add(record)
            results.append(record)

        await self.db.flush()
        logger.info(
            "rules_evaluated",
            auth_event_id=auth_event_id,
            fired_count=sum(1 for r in results if r.fired_flag),
        )
        return results

    def compute_aggregate_rule_score(self, results: list[FactRuleScore]) -> float:
        """Weighted aggregate of all fired rules — combined with ML score."""
        severity_weights = {"high": 0.3, "medium": 0.15, "low": 0.05}
        total = 0.0
        for r in results:
            if r.fired_flag:
                total += severity_weights.get(r.severity, 0.1)
        return min(total, 1.0)
