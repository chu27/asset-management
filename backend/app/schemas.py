from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class BuyCreate(BaseModel):
    trade_date: date
    market: str
    code: str
    name: Optional[str] = None
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    fee: float = Field(default=0, ge=0)
    cash_asset_id: Optional[int] = None
    note: Optional[str] = None


class SellCreate(BaseModel):
    trade_date: date
    stock_id: int
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    fee: float = Field(default=0, ge=0)
    tax: float = Field(default=0, ge=0)
    cash_asset_id: Optional[int] = None
    sell_reason: str
    note: Optional[str] = None


class TransactionUpdate(BaseModel):
    trade_date: date
    market: str
    code: str
    name: Optional[str] = None
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    fee: float = Field(default=0, ge=0)
    tax: float = Field(default=0, ge=0)
    cash_asset_id: Optional[int] = None
    sell_reason: Optional[str] = None
    note: Optional[str] = None


class PriceUpdate(BaseModel):
    current_price: float = Field(gt=0)


class MarketPriceEntry(BaseModel):
    stock_id: int
    price: float = Field(gt=0)


class MarketPricesConfirm(BaseModel):
    prices: list[MarketPriceEntry]


class ManualAssetCreate(BaseModel):
    name: str
    asset_type: str
    institution: Optional[str] = None
    currency: str
    balance: float = Field(default=0, ge=0)
    linked: bool = False
    note: Optional[str] = None


class ManualAssetUpdate(ManualAssetCreate):
    pass


class TagsUpdate(BaseModel):
    tags: list[str]


class RuleUpdate(BaseModel):
    stop_loss: Optional[float] = Field(default=None, gt=0)
    take_profit: Optional[float] = Field(default=None, gt=0)
    position_limit: Optional[float] = Field(default=None, gt=0, le=100)


class RiskUpdate(BaseModel):
    default_position_limit: Optional[float] = Field(default=None, gt=0, le=100)
    loss_limit: Optional[float] = Field(default=None, gt=0, le=100)


class EventCreate(BaseModel):
    stock_id: Optional[int] = None
    event_type: str
    title: str
    event_date: date
    remind_days: int = Field(default=3, ge=0, le=365)
    source: str = "manual"
    confirmed: bool = False
    note: Optional[str] = None


class ReviewUpdate(BaseModel):
    good: str = ""
    improve: str = ""
    plan: str = ""
    other: str = ""
