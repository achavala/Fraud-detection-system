from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.utils.notifications import SlackNotifier


class TestSlackNotifier:
    def test_fraud_alert_without_token(self):
        """Verify it logs and returns gracefully when no token."""
        with patch("src.utils.notifications.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                slack_bot_token=None,
                slack_fraud_ops_channel="#fraud-ops",
                slack_model_alerts_channel="#model-alerts",
            )
            with patch("src.utils.notifications.logger") as mock_logger:
                notifier = SlackNotifier()
                import asyncio
                asyncio.run(notifier.send_fraud_alert(
                    auth_event_id=123,
                    risk_band="high",
                    fraud_probability=0.85,
                    decision="manual_review",
                    reason_codes=["HIGH_CARD_VELOCITY"],
                ))
                mock_logger.info.assert_called_once()

    def test_fraud_alert_message_format(self):
        """Mock the Slack client, verify message blocks are correctly formatted."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage = AsyncMock()

        with patch("src.utils.notifications.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                slack_bot_token="xoxb-fake",
                slack_fraud_ops_channel="#fraud-ops",
                slack_model_alerts_channel="#model-alerts",
            )
            with patch.object(SlackNotifier, "_get_client", return_value=mock_client):
                notifier = SlackNotifier()
                import asyncio
                asyncio.run(notifier.send_fraud_alert(
                    auth_event_id=456,
                    risk_band="critical",
                    fraud_probability=0.92,
                    decision="hard_decline",
                    reason_codes=["VPN_PROXY_TOR", "HIGH_CARD_VELOCITY", "RAPID_FIRE"],
                ))
                mock_client.chat_postMessage.assert_called_once()
                call_kwargs = mock_client.chat_postMessage.call_args[1]
                assert call_kwargs["channel"] == "#fraud-ops"
                blocks = call_kwargs["blocks"]
                assert len(blocks) >= 2
                assert blocks[0]["type"] == "header"
                assert "456" in blocks[0]["text"]["text"]
                assert blocks[1]["type"] == "section"
                fields = blocks[1]["fields"]
                assert any("critical" in f["text"].lower() for f in fields)
                assert any("0.9200" in f["text"] or "0.92" in f["text"] for f in fields)
                assert any("VPN_PROXY_TOR" in f["text"] for f in fields)

    def test_model_alert_format(self):
        """Verify model alert message."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage = AsyncMock()

        with patch("src.utils.notifications.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                slack_bot_token="xoxb-fake",
                slack_fraud_ops_channel="#fraud-ops",
                slack_model_alerts_channel="#model-alerts",
            )
            with patch.object(SlackNotifier, "_get_client", return_value=mock_client):
                notifier = SlackNotifier()
                import asyncio
                asyncio.run(notifier.send_model_alert(
                    model_version="xgb-v4.2.0",
                    alert_type="drift_detected",
                    details="PSI > 0.25 on customer_txn_count_1h",
                ))
                mock_client.chat_postMessage.assert_called_once()
                call_args = mock_client.chat_postMessage.call_args
                assert call_args[1]["channel"] == "#model-alerts"
                assert "xgb-v4.2.0" in call_args[1]["text"]
                assert "drift_detected" in call_args[1]["text"]
                assert "PSI" in call_args[1]["text"]

    def test_case_escalation_format(self):
        """Verify escalation message."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage = AsyncMock()

        with patch("src.utils.notifications.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                slack_bot_token="xoxb-fake",
                slack_fraud_ops_channel="#fraud-ops",
                slack_model_alerts_channel="#model-alerts",
            )
            with patch.object(SlackNotifier, "_get_client", return_value=mock_client):
                notifier = SlackNotifier()
                import asyncio
                asyncio.run(notifier.send_case_escalation(
                    case_id=789,
                    priority="critical",
                    reason="Customer dispute",
                ))
                mock_client.chat_postMessage.assert_called_once()
                call_args = mock_client.chat_postMessage.call_args
                assert call_args[1]["channel"] == "#fraud-ops"
                assert "789" in call_args[1]["text"]
                assert "critical" in call_args[1]["text"]
                assert "Customer dispute" in call_args[1]["text"]

    def test_slack_send_failure_handled(self):
        """Mock client that raises, verify exception is caught."""
        mock_client = AsyncMock()
        mock_client.chat_postMessage = AsyncMock(side_effect=Exception("Network error"))

        with patch("src.utils.notifications.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                slack_bot_token="xoxb-fake",
                slack_fraud_ops_channel="#fraud-ops",
                slack_model_alerts_channel="#model-alerts",
            )
            with patch.object(SlackNotifier, "_get_client", return_value=mock_client):
                notifier = SlackNotifier()
                import asyncio
                # Should not raise
                asyncio.run(notifier.send_fraud_alert(
                    auth_event_id=999,
                    risk_band="high",
                    fraud_probability=0.7,
                    decision="manual_review",
                    reason_codes=["UNUSUAL_AMOUNT"],
                ))
