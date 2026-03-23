"""
Slack and notification integration for fraud ops alerts.
"""
from __future__ import annotations

import asyncio
from typing import Optional
from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)


class SlackNotifier:
    def __init__(self):
        self.settings = get_settings()
        self._client = None

    def _get_client(self):
        if self._client is None and self.settings.slack_bot_token:
            try:
                from slack_sdk.web.async_client import AsyncWebClient
                self._client = AsyncWebClient(token=self.settings.slack_bot_token)
            except Exception:
                pass
        return self._client

    async def send_fraud_alert(
        self,
        auth_event_id: int,
        risk_band: str,
        fraud_probability: float,
        decision: str,
        reason_codes: list[str],
    ):
        client = self._get_client()
        if not client:
            logger.info("slack_disabled", event="fraud_alert")
            return

        emoji = {"critical": ":rotating_light:", "high": ":warning:", "medium": ":large_yellow_circle:"}.get(risk_band, ":white_circle:")

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{emoji} Fraud Alert — Auth #{auth_event_id}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Risk Band:* {risk_band}"},
                    {"type": "mrkdwn", "text": f"*Probability:* {fraud_probability:.4f}"},
                    {"type": "mrkdwn", "text": f"*Decision:* {decision}"},
                    {"type": "mrkdwn", "text": f"*Reasons:* {', '.join(reason_codes[:3])}"},
                ],
            },
        ]

        try:
            await asyncio.wait_for(
                client.chat_postMessage(
                    channel=self.settings.slack_fraud_ops_channel,
                    blocks=blocks,
                    text=f"Fraud alert: auth #{auth_event_id} - {risk_band}",
                ),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            logger.warning("slack_send_timeout", auth_event_id=auth_event_id)
        except Exception as e:
            logger.warning("slack_send_failed", error=str(e))

    async def send_model_alert(
        self,
        model_version: str,
        alert_type: str,
        details: str,
    ):
        client = self._get_client()
        if not client:
            return

        try:
            await client.chat_postMessage(
                channel=self.settings.slack_model_alerts_channel,
                text=f":chart_with_downwards_trend: Model Alert [{model_version}] — {alert_type}: {details}",
            )
        except Exception as e:
            logger.warning("slack_model_alert_failed", error=str(e))

    async def send_case_escalation(self, case_id: int, priority: str, reason: str):
        client = self._get_client()
        if not client:
            return

        try:
            await client.chat_postMessage(
                channel=self.settings.slack_fraud_ops_channel,
                text=f":eyes: Case #{case_id} escalated (priority: {priority}) — {reason}",
            )
        except Exception as e:
            logger.warning("slack_escalation_failed", error=str(e))
