from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Table, Text, Column, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


stock_tags = Table(
    "stock_tags",
    Base.metadata,
    Column("stock_id", ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), index=True)
    name: Mapped[str] = mapped_column(String(120))
    market: Mapped[str] = mapped_column(String(20), index=True)
    current_price: Mapped[float] = mapped_column(Float, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="stock", cascade="all, delete-orphan")
    tags: Mapped[list["Tag"]] = relationship(secondary=stock_tags, back_populates="stocks")
    rule: Mapped[Optional["PriceRule"]] = relationship(back_populates="stock", cascade="all, delete-orphan", uselist=False)

    __table_args__ = (UniqueConstraint("code", "market", name="uq_stock_code_market"),)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    quantity: Mapped[float] = mapped_column(Float)
    price: Mapped[float] = mapped_column(Float)
    fee: Mapped[float] = mapped_column(Float, default=0)
    tax: Mapped[float] = mapped_column(Float, default=0)
    cash_asset_id: Mapped[Optional[int]] = mapped_column(ForeignKey("manual_assets.id", ondelete="SET NULL"), nullable=True)
    sell_reason: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    stock: Mapped[Stock] = relationship(back_populates="transactions")
    cash_asset: Mapped[Optional["ManualAsset"]] = relationship()


class ManualAsset(Base):
    __tablename__ = "manual_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    asset_type: Mapped[str] = mapped_column(String(20))
    institution: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), index=True)
    balance: Mapped[float] = mapped_column(Float, default=0)
    linked: Mapped[bool] = mapped_column(default=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    stocks: Mapped[list[Stock]] = relationship(secondary=stock_tags, back_populates="tags")


class PriceRule(Base):
    __tablename__ = "price_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), unique=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    take_profit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    position_limit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    stock: Mapped[Stock] = relationship(back_populates="rule")


class RiskSetting(Base):
    __tablename__ = "risk_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    default_position_limit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    loss_limit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stocks.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(160))
    event_date: Mapped[date] = mapped_column(Date, index=True)
    remind_days: Mapped[int] = mapped_column(Integer, default=3)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    confirmed: Mapped[bool] = mapped_column(default=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    stock: Mapped[Optional[Stock]] = relationship()


class WeeklySnapshot(Base):
    __tablename__ = "weekly_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    total_jpy: Mapped[float] = mapped_column(Float)
    usd_jpy: Mapped[float] = mapped_column(Float)
    cny_jpy: Mapped[float] = mapped_column(Float)


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_type: Mapped[str] = mapped_column(String(10))
    period_key: Mapped[str] = mapped_column(String(10))
    good: Mapped[str] = mapped_column(Text, default="")
    improve: Mapped[str] = mapped_column(Text, default="")
    plan: Mapped[str] = mapped_column(Text, default="")
    other: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("period_type", "period_key", name="uq_review_period"),)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
