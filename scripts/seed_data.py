"""
Seed script — populates the fraud platform with realistic demo data
for all dimensions, transactions, scores, decisions, labels, and graph.
"""
import asyncio
import random
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from src.core.database import get_engine, get_session_factory, init_db
from src.models.dimensions import DimCustomer, DimAccount, DimCard, DimMerchant, DimDevice, DimIP
from src.models.scoring import DimModelRegistry


async def seed():
    await init_db()
    factory = get_session_factory()

    async with factory() as db:
        model = DimModelRegistry(
            model_version="xgb-v4.2.0",
            model_family="xgboost",
            model_type="binary_classifier",
            feature_version="v2.3.1",
            threshold_decline=0.85,
            threshold_review=0.55,
            threshold_stepup=0.35,
            deployment_status="production",
            owner="fraud-ml-team",
        )
        db.add(model)

        shadow_model = DimModelRegistry(
            model_version="lgb-v5.0.0-rc1",
            model_family="lightgbm",
            model_type="binary_classifier",
            feature_version="v2.3.1",
            threshold_decline=0.85,
            threshold_review=0.55,
            threshold_stepup=0.35,
            deployment_status="shadow",
            owner="fraud-ml-team",
        )
        db.add(shadow_model)

        customers = []
        for i in range(20):
            c = DimCustomer(
                external_customer_ref=f"CUST-{1000+i}",
                customer_since_dt=datetime.now(timezone.utc).date() - timedelta(days=random.randint(30, 1000)),
                kyc_status=random.choice(["verified", "verified", "verified", "pending"]),
                risk_segment=random.choice(["low", "low", "low", "medium", "high"]),
                home_country_code=random.choice(["US", "US", "US", "GB", "CA", "DE"]),
                home_region=random.choice(["CA", "NY", "TX", "FL", "WA"]),
                birth_year=random.randint(1960, 2000),
            )
            db.add(c)
            customers.append(c)
        await db.flush()

        accounts = []
        for c in customers:
            a = DimAccount(
                customer_id=c.customer_id,
                account_status="active",
                account_type=random.choice(["checking", "savings", "credit"]),
                open_date=c.customer_since_dt,
                billing_country_code=c.home_country_code,
            )
            db.add(a)
            accounts.append(a)
        await db.flush()

        cards = []
        for a in accounts:
            card = DimCard(
                account_id=a.account_id,
                pan_token=f"tok_{random.randint(100000, 999999)}_{a.account_id}",
                card_product=random.choice(["Platinum", "Gold", "Standard", "Business"]),
                network=random.choice(["visa", "mastercard", "amex"]),
                card_status="active",
                issue_date=a.open_date,
                expiry_month=random.randint(1, 12),
                expiry_year=random.randint(2026, 2030),
            )
            db.add(card)
            cards.append(card)
        await db.flush()

        merchants = []
        merchant_names = [
            ("Amazon", "5411", "ecommerce"),
            ("Walmart", "5411", "retail"),
            ("Shell Gas", "5541", "fuel"),
            ("Netflix", "4899", "streaming"),
            ("Uber", "4121", "rideshare"),
            ("ShadyStore", "5999", "unknown"),
            ("CryptoExchange", "6051", "crypto"),
            ("GambleSite", "7995", "gambling"),
        ]
        for name, mcc, cat in merchant_names:
            m = DimMerchant(
                merchant_name=name,
                mcc=mcc,
                merchant_category=cat,
                acquirer_id=f"ACQ-{random.randint(100, 999)}",
                merchant_country_code=random.choice(["US", "US", "GB", "NG", "RU"]),
                risk_tier="high" if cat in ("crypto", "gambling", "unknown") else "standard",
            )
            db.add(m)
            merchants.append(m)
        await db.flush()

        devices = []
        for i in range(15):
            d = DimDevice(
                device_id=f"dev-{random.randint(10000, 99999)}",
                device_fingerprint=f"fp-{random.randint(100000, 999999)}",
                os_family=random.choice(["iOS", "Android", "Windows", "macOS"]),
                app_version=f"{random.randint(1,5)}.{random.randint(0,9)}.{random.randint(0,9)}",
                browser_family=random.choice(["Chrome", "Safari", "Firefox", None]),
                emulator_flag=random.random() < 0.1,
                rooted_jailbroken_flag=random.random() < 0.05,
            )
            db.add(d)
            devices.append(d)
        await db.flush()

        ips = []
        for i in range(10):
            ip = DimIP(
                ip_address=f"{random.randint(1,223)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}",
                geo_country_code=random.choice(["US", "GB", "NG", "RU", "BR"]),
                geo_region=random.choice(["California", "London", "Lagos", "Moscow", "Sao Paulo"]),
                geo_city=random.choice(["San Francisco", "London", "Lagos", "Moscow", "Sao Paulo"]),
                asn=f"AS{random.randint(1000, 9999)}",
                proxy_vpn_tor_flag=random.random() < 0.15,
                hosting_provider_flag=random.random() < 0.1,
                ip_risk_score=random.uniform(0, 0.8),
            )
            db.add(ip)
            ips.append(ip)
        await db.flush()

        await db.commit()
        print(f"Seeded: {len(customers)} customers, {len(accounts)} accounts, "
              f"{len(cards)} cards, {len(merchants)} merchants, "
              f"{len(devices)} devices, {len(ips)} IPs, 2 models")


if __name__ == "__main__":
    asyncio.run(seed())
