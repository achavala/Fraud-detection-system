from __future__ import annotations

import random
from datetime import datetime, timezone

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)

COLLECTIONS = [
    "fraud_case_memory",
    "merchant_attack_patterns",
    "investigator_notes",
]

PAYLOAD_INDEX_FIELDS = [
    "case_id",
    "fraud_category",
    "merchant_id",
    "created_at",
]

DIMENSION = 1536


async def ensure_collections() -> None:
    """
    Connect to Qdrant, create collections if they don't exist,
    and add payload indexes. Handles graceful failure if Qdrant is unavailable.
    """
    settings = get_settings()
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams, PayloadSchemaType

        client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )

        for collection_name in COLLECTIONS:
            try:
                collections = client.get_collections().collections
                exists = any(c.name == collection_name for c in collections)

                if exists:
                    logger.info("qdrant_collection_exists", collection=collection_name)
                    continue

                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=DIMENSION,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info("qdrant_collection_created", collection=collection_name)

                for field_name in PAYLOAD_INDEX_FIELDS:
                    try:
                        client.create_payload_index(
                            collection_name=collection_name,
                            field_name=field_name,
                            field_schema=PayloadSchemaType.KEYWORD,
                        )
                        logger.debug(
                            "qdrant_payload_index_created",
                            collection=collection_name,
                            field=field_name,
                        )
                    except Exception as idx_err:
                        logger.warning(
                            "qdrant_index_creation_warning",
                            collection=collection_name,
                            field=field_name,
                            error=str(idx_err),
                        )

            except Exception as coll_err:
                logger.warning(
                    "qdrant_collection_setup_failed",
                    collection=collection_name,
                    error=str(coll_err),
                )

    except Exception as e:
        logger.warning(
            "qdrant_unavailable",
            error=str(e),
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )


async def seed_test_cases() -> None:
    """
    Generate 10 sample fraud case embeddings (random vectors) and store them
    in fraud_case_memory with realistic metadata payloads.
    Useful for testing similar-case retrieval.
    """
    settings = get_settings()
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct

        client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )

        collections = client.get_collections().collections
        if not any(c.name == "fraud_case_memory" for c in collections):
            logger.warning(
                "seed_skipped_collection_missing",
                collection="fraud_case_memory",
            )
            return

        fraud_categories = [
            "card_not_present",
            "account_takeover",
            "friendly_fraud",
            "identity_theft",
            "merchant_fraud",
        ]
        sample_cases = [
            {
                "case_id": f"CASE-{1000 + i}",
                "fraud_category": random.choice(fraud_categories),
                "merchant_id": f"MCH-{random.randint(100, 999)}",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "amount_usd": round(random.uniform(50, 5000), 2),
                "channel": random.choice(["ecommerce", "mobile", "in_store", "atm"]),
                "outcome": random.choice(["confirmed_fraud", "false_positive", "pending"]),
            }
            for i in range(10)
        ]

        points = [
            PointStruct(
                id=1000 + i,
                vector=[random.uniform(-0.1, 0.1) for _ in range(DIMENSION)],
                payload={
                    "case_id": case["case_id"],
                    "fraud_category": case["fraud_category"],
                    "merchant_id": case["merchant_id"],
                    "created_at": case["created_at"],
                    "amount_usd": case["amount_usd"],
                    "channel": case["channel"],
                    "outcome": case["outcome"],
                },
            )
            for i, case in enumerate(sample_cases)
        ]

        client.upsert(collection_name="fraud_case_memory", points=points)
        logger.info(
            "qdrant_seed_complete",
            collection="fraud_case_memory",
            count=len(points),
        )

    except Exception as e:
        logger.warning(
            "qdrant_seed_failed",
            error=str(e),
        )
