"""
Service 5: Investigator Copilot
AI-assisted fraud investigation using Claude for reasoning
and Qdrant for similar-case retrieval.
Records full traces to agent_trace for explainability.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.logging import get_logger
from src.models.audit import AgentTrace
from src.models.investigation import FactFraudCase, FactCaseAction
from src.models.transactions import FactAuthorizationEvent
from src.models.scoring import FactModelScore, FactDecision
from src.models.labels import FactFraudLabel

logger = get_logger(__name__)


class VectorMemoryService:
    """Interface to Qdrant for similar-case retrieval."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self._client = None

    async def _get_client(self):
        if self._client is None:
            try:
                from qdrant_client import QdrantClient
                self._client = QdrantClient(
                    host=self.settings.qdrant_host,
                    port=self.settings.qdrant_port,
                )
            except Exception as e:
                logger.warning("qdrant_unavailable", error=str(e))
                self._client = None
        return self._client

    async def search_similar_cases(
        self,
        query_embedding: list[float],
        collection: str = "fraud_case_memory",
        limit: int = 5,
    ) -> list[dict]:
        client = await self._get_client()
        if not client:
            return []
        try:
            results = client.search(
                collection_name=collection,
                query_vector=query_embedding,
                limit=limit,
            )
            return [
                {
                    "id": str(r.id),
                    "score": r.score,
                    "payload": r.payload,
                }
                for r in results
            ]
        except Exception as e:
            logger.warning("qdrant_search_failed", error=str(e))
            return []

    async def store_case_embedding(
        self,
        case_id: str,
        embedding: list[float],
        metadata: dict,
        collection: str = "fraud_case_memory",
    ):
        client = await self._get_client()
        if not client:
            return
        try:
            from qdrant_client.models import PointStruct
            client.upsert(
                collection_name=collection,
                points=[
                    PointStruct(
                        id=hash(case_id) % (2**63),
                        vector=embedding,
                        payload=metadata,
                    )
                ],
            )
        except Exception as e:
            logger.warning("qdrant_store_failed", error=str(e))


class EmbeddingService:
    """Generate embeddings via OpenAI API."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()

    async def embed(self, text: str) -> list[float]:
        if not self.settings.openai_api_key:
            return [0.0] * self.settings.openai_embedding_dimension

        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.settings.openai_api_key)
            response = await client.embeddings.create(
                model=self.settings.openai_embedding_model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.warning("embedding_failed", error=str(e))
            return [0.0] * self.settings.openai_embedding_dimension


class InvestigatorCopilot:
    """
    AI copilot for fraud investigators.
    Uses Claude for reasoning and Qdrant for memory.
    Every step is traced to agent_trace for auditability.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        self.vector_memory = VectorMemoryService()
        self.embedding_service = EmbeddingService()

    async def investigate_case(self, case_id: int) -> dict:
        """Full AI-assisted investigation of a fraud case."""
        start = time.monotonic()
        steps = []

        case = await self._load_case(case_id)
        if not case:
            return {"error": f"Case {case_id} not found"}

        steps.append(await self._trace_step(
            case_id=case_id,
            auth_event_id=case.auth_event_id,
            step_index=0,
            step_type="load_case",
            input_data={"case_id": case_id},
            output_data={"case_status": case.case_status, "priority": case.priority},
        ))

        transaction = await self._load_transaction(case.auth_event_id)
        scores = await self._load_scores(case.auth_event_id)
        decision = await self._load_decision(case.auth_event_id)
        labels = await self._load_labels(case.auth_event_id)

        steps.append(await self._trace_step(
            case_id=case_id,
            auth_event_id=case.auth_event_id,
            step_index=1,
            step_type="gather_context",
            input_data={"auth_event_id": case.auth_event_id},
            output_data={
                "has_transaction": transaction is not None,
                "score_count": len(scores),
                "has_decision": decision is not None,
                "label_count": len(labels),
            },
        ))

        context_text = self._build_context_text(case, transaction, scores, decision, labels)

        similar_cases = await self._find_similar_cases(context_text)
        steps.append(await self._trace_step(
            case_id=case_id,
            auth_event_id=case.auth_event_id,
            step_index=2,
            step_type="similar_case_retrieval",
            input_data={"query_length": len(context_text)},
            output_data={"similar_count": len(similar_cases)},
        ))

        analysis = await self._ai_analyze(context_text, similar_cases)
        steps.append(await self._trace_step(
            case_id=case_id,
            auth_event_id=case.auth_event_id,
            step_index=3,
            step_type="ai_analysis",
            input_data={"context_length": len(context_text)},
            output_data={"analysis_length": len(analysis.get("summary", ""))},
            model_name=self.settings.anthropic_model,
        ))

        total_ms = int((time.monotonic() - start) * 1000)
        logger.info("case_investigated", case_id=case_id, steps=len(steps), latency_ms=total_ms)

        return {
            "case_id": case_id,
            "analysis": analysis,
            "similar_cases": similar_cases,
            "trace_steps": len(steps),
            "latency_ms": total_ms,
        }

    async def summarize_risk(self, auth_event_id: int) -> dict:
        """Quick risk summary for a transaction — suitable for dashboard display."""
        scores = await self._load_scores(auth_event_id)
        decision = await self._load_decision(auth_event_id)

        if not scores:
            return {"summary": "No scoring data available", "risk_level": "unknown"}

        champion = next((s for s in scores if not s.shadow_mode_flag), scores[0])
        reason_codes = champion.top_reason_codes or []

        risk_factors = []
        for code in reason_codes:
            risk_factors.append(self._explain_reason_code(code))

        return {
            "auth_event_id": auth_event_id,
            "fraud_probability": float(champion.calibrated_probability or champion.fraud_probability),
            "risk_band": champion.risk_band,
            "decision": decision.decision_type if decision else "unknown",
            "model_version": champion.model_version,
            "risk_factors": risk_factors,
            "reason_codes": reason_codes,
        }

    async def recommend_action(self, case_id: int) -> dict:
        """AI-generated recommended action for a case."""
        case = await self._load_case(case_id)
        if not case:
            return {"recommendation": "Case not found", "confidence": 0}

        scores = await self._load_scores(case.auth_event_id)
        if not scores:
            return {"recommendation": "Insufficient data for recommendation", "confidence": 0.3}

        champion = next((s for s in scores if not s.shadow_mode_flag), scores[0])
        prob = float(champion.calibrated_probability or champion.fraud_probability)

        if prob >= 0.85:
            rec = "CONFIRM_FRAUD"
            explanation = "Very high fraud probability with strong signal indicators"
            confidence = 0.9
        elif prob >= 0.65:
            rec = "ESCALATE"
            explanation = "High fraud probability — requires senior review"
            confidence = 0.7
        elif prob >= 0.40:
            rec = "GATHER_MORE_INFO"
            explanation = "Moderate risk — contact customer or request additional verification"
            confidence = 0.6
        else:
            rec = "CLOSE_NOT_FRAUD"
            explanation = "Low fraud probability — likely false positive"
            confidence = 0.8

        await self._trace_step(
            case_id=case_id,
            auth_event_id=case.auth_event_id,
            step_index=0,
            step_type="recommendation",
            input_data={"probability": prob},
            output_data={"recommendation": rec, "confidence": confidence},
        )

        return {
            "case_id": case_id,
            "recommendation": rec,
            "explanation": explanation,
            "confidence": confidence,
            "fraud_probability": prob,
        }

    async def _load_case(self, case_id: int) -> Optional[FactFraudCase]:
        result = await self.db.execute(
            select(FactFraudCase).where(FactFraudCase.case_id == case_id)
        )
        return result.scalar_one_or_none()

    async def _load_transaction(self, auth_event_id: int) -> Optional[FactAuthorizationEvent]:
        result = await self.db.execute(
            select(FactAuthorizationEvent).where(
                FactAuthorizationEvent.auth_event_id == auth_event_id
            )
        )
        return result.scalar_one_or_none()

    async def _load_scores(self, auth_event_id: int) -> list:
        result = await self.db.execute(
            select(FactModelScore).where(
                FactModelScore.auth_event_id == auth_event_id
            )
        )
        return list(result.scalars().all())

    async def _load_decision(self, auth_event_id: int) -> Optional[FactDecision]:
        result = await self.db.execute(
            select(FactDecision).where(
                FactDecision.auth_event_id == auth_event_id
            )
        )
        return result.scalar_one_or_none()

    async def _load_labels(self, auth_event_id: int) -> list:
        result = await self.db.execute(
            select(FactFraudLabel).where(
                FactFraudLabel.auth_event_id == auth_event_id
            )
        )
        return list(result.scalars().all())

    async def _find_similar_cases(self, context_text: str) -> list[dict]:
        embedding = await self.embedding_service.embed(context_text[:8000])
        return await self.vector_memory.search_similar_cases(embedding)

    async def _ai_analyze(
        self, context: str, similar_cases: list[dict]
    ) -> dict:
        """Run Claude analysis — falls back to deterministic if API unavailable."""
        if not self.settings.anthropic_api_key:
            return self._deterministic_analysis(context)

        try:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=self.settings.anthropic_api_key)

            similar_text = "\n".join(
                f"- Case {c.get('id', 'unknown')}: score={c.get('score', 0):.2f}"
                for c in similar_cases[:3]
            ) or "No similar cases found."

            prompt = f"""Analyze this fraud case and provide:
1. A brief summary of the risk
2. Key risk indicators
3. Recommended next steps
4. Confidence level (low/medium/high)

Case Context:
{context[:4000]}

Similar Historical Cases:
{similar_text}"""

            response = await client.messages.create(
                model=self.settings.anthropic_model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            return {
                "summary": response.content[0].text,
                "model": self.settings.anthropic_model,
                "source": "ai",
            }
        except Exception as e:
            logger.warning("ai_analysis_fallback", error=str(e))
            return self._deterministic_analysis(context)

    def _deterministic_analysis(self, context: str) -> dict:
        return {
            "summary": "Deterministic analysis: review transaction details and scoring signals manually.",
            "model": "deterministic",
            "source": "fallback",
        }

    def _build_context_text(self, case, transaction, scores, decision, labels) -> str:
        parts = [f"Case ID: {case.case_id}", f"Status: {case.case_status}"]
        if transaction:
            parts.append(f"Amount: {transaction.auth_amount} {transaction.currency_code}")
            parts.append(f"Channel: {transaction.channel}")
            parts.append(f"Auth Type: {transaction.auth_type}")
        if scores:
            champion = next((s for s in scores if not s.shadow_mode_flag), scores[0])
            parts.append(f"Fraud Probability: {champion.fraud_probability}")
            parts.append(f"Risk Band: {champion.risk_band}")
            parts.append(f"Reason Codes: {champion.top_reason_codes}")
        if decision:
            parts.append(f"Decision: {decision.decision_type}")
        if labels:
            for label in labels:
                parts.append(f"Label: fraud={label.is_fraud}, source={label.label_source}")
        return "\n".join(parts)

    def _explain_reason_code(self, code: str) -> str:
        explanations = {
            "HIGH_CARD_VELOCITY": "Card used an unusually high number of times in a short window",
            "MULTI_ACCOUNT_DEVICE": "Device is linked to multiple distinct accounts",
            "MULTI_CARD_IP": "IP address used with multiple different cards",
            "VPN_PROXY_TOR": "Transaction routed through anonymizing proxy",
            "UNUSUAL_AMOUNT": "Transaction amount significantly exceeds customer's typical spend",
            "RAPID_FIRE": "Very short time gap between consecutive transactions",
            "RISKY_DEVICE": "Device shows indicators of emulation or rooting",
            "FRAUD_RING_PROXIMITY": "Account is connected to other suspicious entities in graph",
            "BASELINE_RISK": "Standard risk level — no specific anomaly detected",
        }
        return explanations.get(code, f"Risk indicator: {code}")

    async def _trace_step(
        self,
        case_id: int,
        auth_event_id: int,
        step_index: int,
        step_type: str,
        input_data: dict,
        output_data: dict,
        model_name: str = None,
    ) -> AgentTrace:
        start = time.monotonic()
        trace = AgentTrace(
            auth_event_id=auth_event_id,
            case_id=case_id,
            step_index=step_index,
            step_type=step_type,
            input_json=input_data,
            output_json=output_data,
            model_name=model_name,
            latency_ms=int((time.monotonic() - start) * 1000),
        )
        self.db.add(trace)
        await self.db.flush()
        return trace
