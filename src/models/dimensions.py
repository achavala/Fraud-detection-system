"""
Core business dimensions: customer, account, card, merchant, device, IP.
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    Numeric,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, TIMESTAMP
from sqlalchemy.orm import relationship
from src.core.database import Base


class DimCustomer(Base):
    __tablename__ = "dim_customer"

    customer_id = Column(BigInteger, primary_key=True, autoincrement=True)
    external_customer_ref = Column(String(255), unique=True, index=True)
    customer_since_dt = Column(Date)
    kyc_status = Column(String(50), default="pending")
    risk_segment = Column(String(20), default="low")
    home_country_code = Column(String(2))
    home_region = Column(String(100))
    birth_year = Column(Integer)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")
    updated_at = Column(TIMESTAMP(timezone=True), server_default="now()")

    accounts = relationship("DimAccount", back_populates="customer")


class DimAccount(Base):
    __tablename__ = "dim_account"

    account_id = Column(BigInteger, primary_key=True, autoincrement=True)
    customer_id = Column(BigInteger, ForeignKey("dim_customer.customer_id"), nullable=False, index=True)
    account_status = Column(String(50), default="active")
    account_type = Column(String(50))
    open_date = Column(Date)
    close_date = Column(Date)
    billing_country_code = Column(String(2))
    autopay_flag = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")
    updated_at = Column(TIMESTAMP(timezone=True), server_default="now()")

    customer = relationship("DimCustomer", back_populates="accounts")
    cards = relationship("DimCard", back_populates="account")


class DimCard(Base):
    __tablename__ = "dim_card"

    card_id = Column(BigInteger, primary_key=True, autoincrement=True)
    account_id = Column(BigInteger, ForeignKey("dim_account.account_id"), nullable=False, index=True)
    pan_token = Column(String(255), unique=True, index=True)
    card_product = Column(String(100))
    network = Column(String(50))
    card_status = Column(String(50), default="active")
    issue_date = Column(Date)
    expiry_month = Column(Integer)
    expiry_year = Column(Integer)
    wallet_tokenized_flag = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")
    updated_at = Column(TIMESTAMP(timezone=True), server_default="now()")

    account = relationship("DimAccount", back_populates="cards")


class DimMerchant(Base):
    __tablename__ = "dim_merchant"

    merchant_id = Column(BigInteger, primary_key=True, autoincrement=True)
    merchant_name = Column(String(500))
    mcc = Column(String(10), index=True)
    merchant_category = Column(String(200))
    acquirer_id = Column(String(100))
    merchant_country_code = Column(String(2))
    risk_tier = Column(String(20), default="standard")
    onboarding_date = Column(Date)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()")
    updated_at = Column(TIMESTAMP(timezone=True), server_default="now()")


class DimDevice(Base):
    __tablename__ = "dim_device"

    device_id = Column(String(255), primary_key=True)
    device_fingerprint = Column(String(512), index=True)
    os_family = Column(String(50))
    app_version = Column(String(50))
    browser_family = Column(String(100))
    emulator_flag = Column(Boolean, default=False)
    rooted_jailbroken_flag = Column(Boolean, default=False)
    first_seen_at = Column(TIMESTAMP(timezone=True), server_default="now()")
    last_seen_at = Column(TIMESTAMP(timezone=True), server_default="now()")


class DimIP(Base):
    __tablename__ = "dim_ip"

    ip_address = Column(INET, primary_key=True)
    geo_country_code = Column(String(2))
    geo_region = Column(String(200))
    geo_city = Column(String(200))
    asn = Column(String(100))
    proxy_vpn_tor_flag = Column(Boolean, default=False)
    hosting_provider_flag = Column(Boolean, default=False)
    ip_risk_score = Column(Numeric(8, 4), default=0)
    first_seen_at = Column(TIMESTAMP(timezone=True), server_default="now()")
    last_seen_at = Column(TIMESTAMP(timezone=True), server_default="now()")
