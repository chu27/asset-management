from datetime import date, timedelta
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models


MARKET_CURRENCY = {"japan": "JPY", "us": "USD", "china": "CNY"}


def get_rates(db: Session) -> dict[str, Any]:
    rows = {item.key: item.value for item in db.scalars(select(models.Setting)).all()}
    return {
        "usd_jpy": float(rows.get("usd_jpy", "150.2")),
        "cny_jpy": float(rows.get("cny_jpy", "20.6")),
        "updated_at": rows.get("rates_updated_at", "演示汇率"),
        "source": rows.get("rates_source", "fallback"),
    }


def set_setting(db: Session, key: str, value: str) -> None:
    item = db.get(models.Setting, key)
    if item:
        item.value = value
    else:
        db.add(models.Setting(key=key, value=value))


def calculate_stock(stock: models.Stock) -> dict[str, Any]:
    quantity = 0.0
    cost = 0.0
    realized = 0.0
    for transaction in sorted(stock.transactions, key=lambda item: (item.trade_date, item.id)):
        if transaction.kind == "buy":
            quantity += transaction.quantity
            cost += transaction.quantity * transaction.price + transaction.fee
        else:
            if transaction.quantity > quantity + 1e-9:
                raise ValueError(f"{stock.code} 的卖出数量超过当时持仓")
            average = cost / quantity if quantity else 0
            sold_cost = average * transaction.quantity
            proceeds = transaction.quantity * transaction.price - transaction.fee - transaction.tax
            realized += proceeds - sold_cost
            quantity -= transaction.quantity
            cost = max(0.0, cost - sold_cost)
            if quantity <= 1e-9:
                quantity = 0.0
                cost = 0.0
    market_value = quantity * stock.current_price
    profit = market_value - cost
    return {
        "quantity": quantity,
        "cost": cost,
        "average_cost": cost / quantity if quantity else 0,
        "market_value": market_value,
        "profit": profit,
        "profit_rate": profit / cost * 100 if cost else 0,
        "realized_profit": realized,
    }


def converted_jpy(market: str, value: float, rates: dict[str, Any]) -> float:
    if market == "us":
        return value * rates["usd_jpy"]
    if market == "china":
        return value * rates["cny_jpy"]
    return value


def portfolio(db: Session, include_closed: bool = False) -> dict[str, Any]:
    rates = get_rates(db)
    items = []
    total_jpy = 0.0
    for stock in db.scalars(select(models.Stock).order_by(models.Stock.market, models.Stock.code)).unique().all():
        values = calculate_stock(stock)
        if not include_closed and values["quantity"] <= 0:
            continue
        value_jpy = converted_jpy(stock.market, values["market_value"], rates)
        total_jpy += value_jpy
        items.append({
            "id": stock.id,
            "code": stock.code,
            "name": stock.name,
            "market": stock.market,
            "currency": MARKET_CURRENCY[stock.market],
            "current_price": stock.current_price,
            "tags": [tag.name for tag in stock.tags],
            "rule": {
                "stop_loss": stock.rule.stop_loss if stock.rule else None,
                "take_profit": stock.rule.take_profit if stock.rule else None,
                "position_limit": stock.rule.position_limit if stock.rule else None,
            },
            "value_jpy": value_jpy,
            **values,
        })
    for item in items:
        item["position_rate"] = item["value_jpy"] / total_jpy * 100 if total_jpy else 0
    return {"positions": items, "total_stock_jpy": total_jpy, "rates": rates}


def asset_summary(db: Session) -> dict[str, Any]:
    portfolio_data = portfolio(db)
    grouped = {"JPY": {"stock": 0.0, "cash": 0.0, "deposit": 0.0}, "USD": {"stock": 0.0, "cash": 0.0, "deposit": 0.0}, "CNY": {"stock": 0.0, "cash": 0.0, "deposit": 0.0}}
    rows = []
    for position in portfolio_data["positions"]:
        grouped[position["currency"]]["stock"] += position["market_value"]
        rows.append({"id": f"stock-{position['id']}", "name": position["name"], "secondary": position["code"], "asset_type": "stock", "institution": {"japan": "日股", "us": "美股", "china": "科技"}[position["market"]], "currency": position["currency"], "balance": position["market_value"], "source": "auto", "linked": False})
    for asset in db.scalars(select(models.ManualAsset).order_by(models.ManualAsset.currency, models.ManualAsset.id)).all():
        grouped[asset.currency][asset.asset_type] += asset.balance
        rows.append({"id": asset.id, "name": asset.name, "secondary": asset.note or "", "asset_type": asset.asset_type, "institution": asset.institution or "—", "currency": asset.currency, "balance": asset.balance, "source": "manual", "linked": asset.linked})
    totals = {currency: sum(values.values()) for currency, values in grouped.items()}
    rates = portfolio_data["rates"]
    converted = {"JPY": totals["JPY"], "USD": totals["USD"] * rates["usd_jpy"], "CNY": totals["CNY"] * rates["cny_jpy"]}
    total_jpy = sum(converted.values())
    return {"rows": rows, "breakdown": grouped, "currency_totals": totals, "converted_jpy": converted, "total_jpy": total_jpy, "total_cny": total_jpy / rates["cny_jpy"] if rates["cny_jpy"] else 0, "rates": rates}


def analysis(db: Session) -> dict[str, Any]:
    data = portfolio(db)
    tags: dict[str, dict[str, Any]] = {}
    for position in data["positions"]:
        for tag in position["tags"]:
            entry = tags.setdefault(tag, {"name": tag, "value_jpy": 0.0, "stocks": []})
            entry["value_jpy"] += position["value_jpy"]
            entry["stocks"].append({"id": position["id"], "code": position["code"], "name": position["name"], "position_rate": position["position_rate"]})
    for entry in tags.values():
        entry["rate"] = entry["value_jpy"] / data["total_stock_jpy"] * 100 if data["total_stock_jpy"] else 0
    return {**data, "tags": sorted(tags.values(), key=lambda item: item["rate"], reverse=True)}


def reminders(db: Session) -> list[dict[str, Any]]:
    data = portfolio(db)
    risk = db.get(models.RiskSetting, 1)
    results = []
    for position in data["positions"]:
        rule = position["rule"]
        if rule["stop_loss"] and position["current_price"] <= rule["stop_loss"]:
            results.append({"id": f"stop-{position['id']}", "status": "active", "kind": "价格提醒", "title": f"{position['code']} {position['name']}", "headline": "已到达止损点", "detail": f"当前 {position['current_price']:.2f} · 止损点 {rule['stop_loss']:.2f}"})
        if rule["take_profit"] and position["current_price"] >= rule["take_profit"]:
            results.append({"id": f"profit-{position['id']}", "status": "active", "kind": "价格提醒", "title": f"{position['code']} {position['name']}", "headline": "已到达止盈点", "detail": f"当前 {position['current_price']:.2f} · 止盈点 {rule['take_profit']:.2f}"})
        limit = rule["position_limit"] or (risk.default_position_limit if risk else None)
        if limit and position["position_rate"] > limit:
            results.append({"id": f"position-{position['id']}", "status": "active", "kind": "仓位提醒", "title": f"{position['code']} {position['name']}", "headline": "单只股票仓位过高", "detail": f"当前 {position['position_rate']:.1f}% · 上限 {limit:.1f}%"})
        if risk and risk.loss_limit and position["profit_rate"] <= -risk.loss_limit:
            results.append({"id": f"loss-{position['id']}", "status": "active", "kind": "亏损提醒", "title": f"{position['code']} {position['name']}", "headline": "亏损幅度达到提醒标准", "detail": f"当前 {position['profit_rate']:.1f}% · 提醒标准 -{risk.loss_limit:.1f}%"})
    today = date.today()
    for event in db.scalars(select(models.Event).order_by(models.Event.event_date)).all():
        days = (event.event_date - today).days
        if 0 <= days <= event.remind_days:
            results.append({"id": f"event-{event.id}", "status": "upcoming", "kind": event.event_type, "title": event.title, "headline": f"还有{days}天", "detail": f"{event.event_date.isoformat()} · {'自动同步' if event.source == 'auto' else '手动添加'}"})
    return results


def seed_database(db: Session) -> None:
    if db.scalar(select(models.Stock.id).limit(1)):
        return
    stocks = [
        models.Stock(code="7203", name="丰田汽车", market="japan", current_price=2850),
        models.Stock(code="4755", name="乐天集团", market="japan", current_price=820),
        models.Stock(code="7267", name="本田汽车", market="japan", current_price=1550),
        models.Stock(code="AAPL", name="苹果", market="us", current_price=202),
        models.Stock(code="688981", name="中芯国际", market="china", current_price=45.5),
    ]
    db.add_all(stocks)
    db.flush()
    transactions = [
        models.Transaction(stock_id=stocks[0].id, kind="buy", trade_date=date(2025, 6, 12), quantity=100, price=2600, fee=500),
        models.Transaction(stock_id=stocks[1].id, kind="buy", trade_date=date(2025, 9, 4), quantity=200, price=748, fee=400),
        models.Transaction(stock_id=stocks[2].id, kind="buy", trade_date=date(2025, 11, 20), quantity=100, price=1445, fee=500),
        models.Transaction(stock_id=stocks[3].id, kind="buy", trade_date=date(2026, 1, 8), quantity=10, price=184.5, fee=5),
        models.Transaction(stock_id=stocks[4].id, kind="buy", trade_date=date(2026, 3, 16), quantity=100, price=42.8, fee=20),
    ]
    db.add_all(transactions)
    assets = [
        models.ManualAsset(name="SBI证券账户现金", asset_type="cash", institution="SBI证券", currency="JPY", balance=800000, linked=True),
        models.ManualAsset(name="三菱UFJ定期存款", asset_type="deposit", institution="三菱UFJ银行", currency="JPY", balance=3000000),
        models.ManualAsset(name="美元现金", asset_type="cash", institution="SBI证券", currency="USD", balance=5000, linked=True),
        models.ManualAsset(name="美元定期存款", asset_type="deposit", institution="银行账户", currency="USD", balance=10000),
        models.ManualAsset(name="人民币现金", asset_type="cash", institution="投资账户", currency="CNY", balance=100000, linked=True),
        models.ManualAsset(name="人民币定期存款", asset_type="deposit", institution="中国工商银行", currency="CNY", balance=200000),
    ]
    db.add_all(assets)
    tags = {name: models.Tag(name=name) for name in ["AI", "Mag7", "汽车", "日本制造", "互联网", "半导体"]}
    db.add_all(tags.values())
    db.flush()
    stocks[0].tags = [tags["汽车"], tags["日本制造"]]
    stocks[1].tags = [tags["互联网"]]
    stocks[2].tags = [tags["汽车"], tags["日本制造"]]
    stocks[3].tags = [tags["AI"], tags["Mag7"]]
    stocks[4].tags = [tags["AI"], tags["半导体"]]
    db.add(models.RiskSetting(id=1, default_position_limit=None, loss_limit=None))
    db.add_all([
        models.Event(stock_id=stocks[3].id, event_type="财报提醒", title="苹果预计公布财报", event_date=date.today() + timedelta(days=3), remind_days=5, source="manual"),
        models.Event(stock_id=stocks[0].id, event_type="分红除权", title="丰田汽车预计除权日", event_date=date.today() + timedelta(days=12), remind_days=14, source="manual"),
    ])
    set_setting(db, "usd_jpy", "150.2")
    set_setting(db, "cny_jpy", "20.6")
    set_setting(db, "rates_updated_at", "演示汇率")
    set_setting(db, "rates_source", "fallback")
    base = 1650000
    for week in range(52):
        snapshot_date = date.today() - timedelta(days=(51 - week) * 7)
        total = base + week * 10500 + ((week % 7) - 3) * 18000
        db.add(models.WeeklySnapshot(snapshot_date=snapshot_date, total_jpy=total, usd_jpy=150.2, cny_jpy=20.6))
    db.commit()
