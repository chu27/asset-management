from datetime import date, datetime, timedelta
from contextlib import asynccontextmanager
from typing import Optional

import httpx
import yfinance as yf
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, schemas, services
from .database import Base, SessionLocal, engine, get_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        services.seed_database(db)
    yield


app = FastAPI(title="SBI 股票与资产管理 API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3002", "http://localhost:3002"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/portfolio")
def get_portfolio(db: Session = Depends(get_db)):
    return services.portfolio(db)


@app.get("/api/transactions")
def get_transactions(db: Session = Depends(get_db)):
    rows = db.scalars(select(models.Transaction).order_by(models.Transaction.trade_date.desc(), models.Transaction.id.desc())).all()
    return [{"id": item.id, "stock_id": item.stock_id, "code": item.stock.code, "name": item.stock.name, "market": item.stock.market, "kind": item.kind, "trade_date": item.trade_date, "quantity": item.quantity, "price": item.price, "fee": item.fee, "tax": item.tax, "cash_asset_id": item.cash_asset_id, "sell_reason": item.sell_reason, "note": item.note} for item in rows]


def validate_cash(db: Session, cash_asset_id: Optional[int], market: str) -> Optional[models.ManualAsset]:
    if cash_asset_id is None:
        return None
    asset = db.get(models.ManualAsset, cash_asset_id)
    if not asset or asset.asset_type != "cash" or not asset.linked:
        raise HTTPException(400, "请选择已经关联投资记录的现金账户")
    if asset.currency != services.MARKET_CURRENCY[market]:
        raise HTTPException(400, "现金账户币种与股票市场不一致")
    return asset


@app.post("/api/transactions/buy", status_code=201)
def create_buy(payload: schemas.BuyCreate, db: Session = Depends(get_db)):
    market = payload.market.lower()
    if market not in services.MARKET_CURRENCY:
        raise HTTPException(400, "市场必须是 japan、us 或 china")
    code = payload.code.strip().upper()
    if not code:
        raise HTTPException(400, "股票代码不能为空")
    stock = db.scalar(select(models.Stock).where(models.Stock.code == code, models.Stock.market == market))
    if not stock:
        stock = models.Stock(code=code, name=(payload.name or "").strip(), market=market, current_price=payload.price)
        db.add(stock)
        db.flush()
    elif payload.name and payload.name.strip():
        stock.name = payload.name.strip()
    cash = validate_cash(db, payload.cash_asset_id, market)
    expense = payload.quantity * payload.price + payload.fee
    if cash and cash.balance < expense:
        raise HTTPException(400, "现金账户余额不足")
    if cash:
        cash.balance -= expense
    transaction = models.Transaction(stock_id=stock.id, kind="buy", trade_date=payload.trade_date, quantity=payload.quantity, price=payload.price, fee=payload.fee, tax=0, cash_asset_id=payload.cash_asset_id, note=payload.note)
    db.add(transaction)
    db.commit()
    return {"id": transaction.id, "message": "买入记录已保存"}


@app.post("/api/transactions/sell", status_code=201)
def create_sell(payload: schemas.SellCreate, db: Session = Depends(get_db)):
    stock = db.get(models.Stock, payload.stock_id)
    if not stock:
        raise HTTPException(404, "股票不存在")
    current = services.calculate_stock(stock)
    if payload.quantity > current["quantity"] + 1e-9:
        raise HTTPException(400, "卖出数量超过当前持仓")
    cash = validate_cash(db, payload.cash_asset_id, stock.market)
    proceeds = payload.quantity * payload.price - payload.fee - payload.tax
    if proceeds < 0:
        raise HTTPException(400, "实际到账不能为负数")
    if cash:
        cash.balance += proceeds
    transaction = models.Transaction(stock_id=stock.id, kind="sell", trade_date=payload.trade_date, quantity=payload.quantity, price=payload.price, fee=payload.fee, tax=payload.tax, cash_asset_id=payload.cash_asset_id, sell_reason=payload.sell_reason, note=payload.note)
    db.add(transaction)
    db.commit()
    return {"id": transaction.id, "message": "卖出记录已保存"}


@app.delete("/api/transactions/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    item = db.get(models.Transaction, transaction_id)
    if not item:
        raise HTTPException(404, "交易记录不存在")
    cash = item.cash_asset
    amount = item.quantity * item.price
    if cash:
        if item.kind == "buy":
            cash.balance += amount + item.fee
        else:
            rollback = amount - item.fee - item.tax
            if cash.balance < rollback:
                raise HTTPException(400, "现金余额不足，无法撤销这笔卖出记录")
            cash.balance -= rollback
    db.delete(item)
    db.flush()
    try:
        services.calculate_stock(item.stock)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    return {"message": "交易记录已删除"}


@app.patch("/api/transactions/{transaction_id}")
def update_transaction(transaction_id: int, payload: schemas.TransactionUpdate, db: Session = Depends(get_db)):
    item = db.get(models.Transaction, transaction_id)
    if not item:
        raise HTTPException(404, "交易记录不存在")

    market = payload.market.lower()
    if market not in services.MARKET_CURRENCY:
        raise HTTPException(400, "市场必须是 japan、us 或 china")
    code = payload.code.strip().upper()
    if not code:
        raise HTTPException(400, "股票代码不能为空")

    old_stock = item.stock
    old_cash = item.cash_asset
    old_amount = item.quantity * item.price
    if old_cash:
        if item.kind == "buy":
            old_cash.balance += old_amount + item.fee
        else:
            old_proceeds = old_amount - item.fee - item.tax
            if old_cash.balance < old_proceeds:
                db.rollback()
                raise HTTPException(400, "现金余额不足，无法修改这笔卖出记录")
            old_cash.balance -= old_proceeds

    target_stock = db.scalar(select(models.Stock).where(models.Stock.code == code, models.Stock.market == market))
    if not target_stock:
        target_stock = models.Stock(code=code, name=(payload.name or "").strip(), market=market, current_price=payload.price)
        db.add(target_stock)
        db.flush()
    elif payload.name and payload.name.strip():
        target_stock.name = payload.name.strip()

    new_cash = validate_cash(db, payload.cash_asset_id, market)

    item.stock = target_stock
    item.trade_date = payload.trade_date
    item.quantity = payload.quantity
    item.price = payload.price
    item.fee = payload.fee
    item.tax = 0 if item.kind == "buy" else payload.tax
    item.cash_asset_id = payload.cash_asset_id
    item.note = payload.note
    item.sell_reason = None if item.kind == "buy" else payload.sell_reason

    new_amount = item.quantity * item.price
    if new_cash:
        if item.kind == "buy":
            new_expense = new_amount + item.fee
            if new_cash.balance < new_expense:
                db.rollback()
                raise HTTPException(400, "现金账户余额不足，无法保存修改")
            new_cash.balance -= new_expense
        else:
            new_proceeds = new_amount - item.fee - item.tax
            if new_proceeds < 0:
                db.rollback()
                raise HTTPException(400, "实际到账不能为负数")
            new_cash.balance += new_proceeds

    db.flush()
    try:
        services.calculate_stock(old_stock)
        if target_stock.id != old_stock.id:
            services.calculate_stock(target_stock)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    return {"message": "交易记录已修改"}


@app.patch("/api/stocks/{stock_id}/price")
def update_price(stock_id: int, payload: schemas.PriceUpdate, db: Session = Depends(get_db)):
    stock = db.get(models.Stock, stock_id)
    if not stock:
        raise HTTPException(404, "股票不存在")
    stock.current_price = payload.current_price
    db.commit()
    return {"message": "当前价格已更新"}


def latest_market_price(ticker) -> Optional[float]:
    """Prefer yfinance's fast quote and fall back to the latest daily close."""
    price = ticker.fast_info.get("last_price")
    if price and float(price) > 0:
        return float(price)
    history = ticker.history(period="5d", auto_adjust=False)
    if history.empty:
        return None
    closes = history["Close"].dropna()
    return float(closes.iloc[-1]) if len(closes) else None


@app.post("/api/market/preview")
def preview_market_prices(db: Session = Depends(get_db)):
    items = []
    for position in services.portfolio(db)["positions"]:
        suffix = ".T" if position["market"] == "japan" else ".SS" if position["market"] == "china" else ""
        symbol = f"{position['code']}{suffix}"
        suggested_price = None
        try:
            suggested_price = latest_market_price(yf.Ticker(symbol))
        except Exception:
            pass
        items.append({
            "stock_id": position["id"],
            "code": position["code"],
            "name": position["name"],
            "market": position["market"],
            "symbol": symbol,
            "current_price": position["current_price"],
            "suggested_price": suggested_price,
            "status": "ready" if suggested_price else "failed",
        })
    return {"items": items}


@app.post("/api/market/confirm")
def confirm_market_prices(payload: schemas.MarketPricesConfirm, db: Session = Depends(get_db)):
    if not payload.prices:
        raise HTTPException(400, "没有可更新的价格")
    updated = []
    seen = set()
    for entry in payload.prices:
        if entry.stock_id in seen:
            continue
        stock = db.get(models.Stock, entry.stock_id)
        if not stock:
            db.rollback()
            raise HTTPException(404, f"股票 {entry.stock_id} 不存在")
        stock.current_price = entry.price
        updated.append(stock.code)
        seen.add(entry.stock_id)
    db.commit()
    return {"updated": updated, "count": len(updated)}


def _external_date(value):
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime().date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


@app.post("/api/events/refresh")
def refresh_company_events(db: Session = Depends(get_db)):
    created = 0
    failed = []
    for position in services.portfolio(db)["positions"]:
        suffix = ".T" if position["market"] == "japan" else ".SS" if position["market"] == "china" else ""
        symbol = f"{position['code']}{suffix}"
        try:
            ticker = yf.Ticker(symbol)
            calendar = ticker.calendar or {}
            candidates = [
                ("财报公布", "Earnings Date", f"{position['code']} {position['name']} 预计公布财报"),
                ("除权日期", "Ex-Dividend Date", f"{position['code']} {position['name']} 预计除权日"),
            ]
            for event_type, key, title in candidates:
                event_date = _external_date(calendar.get(key) if isinstance(calendar, dict) else None)
                if not event_date or event_date < date.today():
                    continue
                exists = db.scalar(select(models.Event.id).where(models.Event.stock_id == position["id"], models.Event.event_type == event_type, models.Event.event_date == event_date, models.Event.source == "auto"))
                if not exists:
                    db.add(models.Event(stock_id=position["id"], event_type=event_type, title=title, event_date=event_date, remind_days=5, source="auto", confirmed=False))
                    created += 1
            option_dates = ticker.options
            if option_dates:
                option_date = _external_date(option_dates[0])
                if option_date and option_date >= date.today():
                    exists = db.scalar(select(models.Event.id).where(models.Event.stock_id == position["id"], models.Event.event_type == "期权到期", models.Event.event_date == option_date, models.Event.source == "auto"))
                    if not exists:
                        db.add(models.Event(stock_id=position["id"], event_type="期权到期", title=f"{position['code']} {position['name']} 最近期权到期日", event_date=option_date, remind_days=3, source="auto", confirmed=True))
                        created += 1
        except Exception:
            failed.append(symbol)
    db.commit()
    return {"created": created, "failed": failed}


@app.get("/api/assets")
def get_assets(db: Session = Depends(get_db)):
    return services.asset_summary(db)


@app.post("/api/assets", status_code=201)
def create_asset(payload: schemas.ManualAssetCreate, db: Session = Depends(get_db)):
    if payload.asset_type not in {"cash", "deposit"} or payload.currency not in {"JPY", "USD", "CNY"}:
        raise HTTPException(400, "资产类型或币种不正确")
    item = models.ManualAsset(**payload.model_dump())
    if item.asset_type == "deposit":
        item.linked = False
    db.add(item)
    db.commit()
    return {"id": item.id, "message": "资产已添加"}


@app.put("/api/assets/{asset_id}")
def update_asset(asset_id: int, payload: schemas.ManualAssetUpdate, db: Session = Depends(get_db)):
    item = db.get(models.ManualAsset, asset_id)
    if not item:
        raise HTTPException(404, "资产不存在")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    if item.asset_type == "deposit":
        item.linked = False
    db.commit()
    return {"message": "资产已更新"}


@app.delete("/api/assets/{asset_id}")
def delete_asset(asset_id: int, db: Session = Depends(get_db)):
    item = db.get(models.ManualAsset, asset_id)
    if not item:
        raise HTTPException(404, "资产不存在")
    db.delete(item)
    db.commit()
    return {"message": "资产已删除"}


@app.post("/api/rates/refresh")
def refresh_rates(db: Session = Depends(get_db)):
    try:
        with httpx.Client(timeout=10, follow_redirects=True) as client:
            response = client.get("https://api.frankfurter.dev/v1/latest", params={"from": "USD", "to": "JPY,CNY"})
            response.raise_for_status()
            payload = response.json()
        usd_jpy = float(payload["rates"]["JPY"])
        usd_cny = float(payload["rates"]["CNY"])
        cny_jpy = usd_jpy / usd_cny
        services.set_setting(db, "usd_jpy", str(usd_jpy))
        services.set_setting(db, "cny_jpy", str(cny_jpy))
        services.set_setting(db, "rates_updated_at", datetime.now().isoformat(timespec="minutes"))
        services.set_setting(db, "rates_source", "Frankfurter")
        db.commit()
        return services.get_rates(db)
    except Exception as exc:
        raise HTTPException(502, f"汇率更新失败，继续使用最后成功数据：{exc}") from exc


@app.get("/api/analysis")
def get_analysis(db: Session = Depends(get_db)):
    return services.analysis(db)


@app.put("/api/stocks/{stock_id}/tags")
def update_tags(stock_id: int, payload: schemas.TagsUpdate, db: Session = Depends(get_db)):
    stock = db.get(models.Stock, stock_id)
    if not stock:
        raise HTTPException(404, "股票不存在")
    names = list(dict.fromkeys(name.strip() for name in payload.tags if name.strip()))
    tags = []
    for name in names:
        tag = db.scalar(select(models.Tag).where(models.Tag.name == name))
        if not tag:
            tag = models.Tag(name=name)
            db.add(tag)
        tags.append(tag)
    stock.tags = tags
    db.commit()
    return {"tags": names, "message": "Tag已更新"}


@app.put("/api/stocks/{stock_id}/rule")
def update_rule(stock_id: int, payload: schemas.RuleUpdate, db: Session = Depends(get_db)):
    stock = db.get(models.Stock, stock_id)
    if not stock:
        raise HTTPException(404, "股票不存在")
    rule = stock.rule or models.PriceRule(stock_id=stock.id)
    for key, value in payload.model_dump().items():
        setattr(rule, key, value)
    db.add(rule)
    db.commit()
    return {"message": "提醒规则已保存"}


@app.get("/api/risk")
def get_risk(db: Session = Depends(get_db)):
    item = db.get(models.RiskSetting, 1) or models.RiskSetting(id=1)
    return {"default_position_limit": item.default_position_limit, "loss_limit": item.loss_limit}


@app.put("/api/risk")
def update_risk(payload: schemas.RiskUpdate, db: Session = Depends(get_db)):
    item = db.get(models.RiskSetting, 1) or models.RiskSetting(id=1)
    item.default_position_limit = payload.default_position_limit
    item.loss_limit = payload.loss_limit
    db.add(item)
    db.commit()
    return {"message": "统一风险规则已保存"}


@app.get("/api/history")
def get_history(range_key: str = Query("1y", alias="range"), db: Session = Depends(get_db)):
    weeks = {"1m": 5, "3m": 13, "6m": 26, "ytd": 53, "1y": 52, "3y": 156, "5y": 260, "all": 9999}.get(range_key, 52)
    cutoff = date(date.today().year, 1, 1) if range_key == "ytd" else date.today() - timedelta(weeks=weeks)
    rows = db.scalars(select(models.WeeklySnapshot).where(models.WeeklySnapshot.snapshot_date >= cutoff).order_by(models.WeeklySnapshot.snapshot_date)).all()
    return [{"date": item.snapshot_date, "total_jpy": item.total_jpy} for item in rows]


@app.post("/api/history/snapshot")
def create_snapshot(db: Session = Depends(get_db)):
    total = services.portfolio(db)["total_stock_jpy"]
    rates = services.get_rates(db)
    today = date.today()
    item = db.scalar(select(models.WeeklySnapshot).where(models.WeeklySnapshot.snapshot_date == today))
    if item:
        item.total_jpy = total
        item.usd_jpy = rates["usd_jpy"]
        item.cny_jpy = rates["cny_jpy"]
    else:
        db.add(models.WeeklySnapshot(snapshot_date=today, total_jpy=total, usd_jpy=rates["usd_jpy"], cny_jpy=rates["cny_jpy"]))
    db.commit()
    return {"message": "本周股票资产快照已保存"}


@app.get("/api/reminders")
def get_reminders(db: Session = Depends(get_db)):
    return services.reminders(db)


@app.get("/api/events")
def get_events(db: Session = Depends(get_db)):
    rows = db.scalars(select(models.Event).order_by(models.Event.event_date)).all()
    return [{"id": item.id, "stock_id": item.stock_id, "stock": f"{item.stock.code} {item.stock.name}" if item.stock else None, "event_type": item.event_type, "title": item.title, "event_date": item.event_date, "remind_days": item.remind_days, "source": item.source, "confirmed": item.confirmed, "note": item.note} for item in rows]


@app.post("/api/events", status_code=201)
def create_event(payload: schemas.EventCreate, db: Session = Depends(get_db)):
    if payload.stock_id and not db.get(models.Stock, payload.stock_id):
        raise HTTPException(404, "股票不存在")
    item = models.Event(**payload.model_dump())
    db.add(item)
    db.commit()
    return {"id": item.id, "message": "事件已添加"}


@app.delete("/api/events/{event_id}")
def delete_event(event_id: int, db: Session = Depends(get_db)):
    item = db.get(models.Event, event_id)
    if not item:
        raise HTTPException(404, "事件不存在")
    db.delete(item)
    db.commit()
    return {"message": "事件已删除"}


@app.get("/api/reviews/{period_type}/{period_key}")
def get_review(period_type: str, period_key: str, db: Session = Depends(get_db)):
    review = db.scalar(select(models.Review).where(models.Review.period_type == period_type, models.Review.period_key == period_key))
    transactions = db.scalars(select(models.Transaction).where(models.Transaction.kind == "sell").order_by(models.Transaction.trade_date.desc())).all()
    if period_type == "month":
        transactions = [item for item in transactions if item.trade_date.strftime("%Y-%m") == period_key]
    else:
        transactions = [item for item in transactions if item.trade_date.strftime("%Y") == period_key]
    sales = [{"id": item.id, "stock": f"{item.stock.code} {item.stock.name}", "trade_date": item.trade_date, "reason": item.sell_reason, "note": item.note} for item in transactions]
    content = {"good": "", "improve": "", "plan": "", "other": ""} if not review else {"good": review.good, "improve": review.improve, "plan": review.plan, "other": review.other}
    return {"period_type": period_type, "period_key": period_key, "sell_count": len(sales), "sales": sales, **content}


@app.put("/api/reviews/{period_type}/{period_key}")
def update_review(period_type: str, period_key: str, payload: schemas.ReviewUpdate, db: Session = Depends(get_db)):
    if period_type not in {"month", "year"}:
        raise HTTPException(400, "复盘类型必须是 month 或 year")
    review = db.scalar(select(models.Review).where(models.Review.period_type == period_type, models.Review.period_key == period_key))
    if not review:
        review = models.Review(period_type=period_type, period_key=period_key)
    for key, value in payload.model_dump().items():
        setattr(review, key, value)
    db.add(review)
    db.commit()
    return {"message": "投资复盘已保存"}
