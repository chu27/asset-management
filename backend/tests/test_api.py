import os
from pathlib import Path

TEST_DB = Path(__file__).parent / "test_sbi.db"
os.environ["SBI_DATABASE_PATH"] = str(TEST_DB)

from fastapi.testclient import TestClient
from app.database import Base, engine
from app.main import app


def setup_module():
    if TEST_DB.exists():
        TEST_DB.unlink()
    Base.metadata.create_all(engine)


def teardown_module():
    Base.metadata.drop_all(engine)
    if TEST_DB.exists():
        TEST_DB.unlink()


def test_health_and_seeded_portfolio():
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        portfolio = client.get("/api/portfolio").json()
        assert len(portfolio["positions"]) == 5
        assert portfolio["total_stock_jpy"] > 0


def test_buy_and_sell_validation():
    with TestClient(app) as client:
        stock = client.get("/api/portfolio").json()["positions"][0]
        response = client.post("/api/transactions/sell", json={"trade_date": "2026-08-16", "stock_id": stock["id"], "quantity": stock["quantity"] + 1, "price": stock["current_price"], "fee": 0, "tax": 0, "sell_reason": "测试"})
        assert response.status_code == 400


def test_tags_and_rules():
    with TestClient(app) as client:
        stock = client.get("/api/portfolio").json()["positions"][0]
        assert client.put(f"/api/stocks/{stock['id']}/tags", json={"tags": ["AI", "测试Tag"]}).status_code == 200
        assert client.put(f"/api/stocks/{stock['id']}/rule", json={"stop_loss": 100, "take_profit": 9999, "position_limit": 20}).status_code == 200
        analysis = client.get("/api/analysis").json()
        assert any(item["name"] == "测试Tag" for item in analysis["tags"])


def test_optional_stock_name_and_transaction_update():
    with TestClient(app) as client:
        created = client.post("/api/transactions/buy", json={"trade_date": "2026-08-16", "market": "us", "code": "OPTIONAL", "quantity": 2, "price": 10, "fee": 0})
        assert created.status_code == 201
        transaction_id = created.json()["id"]

        updated = client.patch(f"/api/transactions/{transaction_id}", json={"trade_date": "2026-08-15", "market": "japan", "code": "9999", "name": "修改后的股票", "quantity": 3, "price": 12, "fee": 1, "tax": 0, "note": "修改后的买入原因"})
        assert updated.status_code == 200

        transaction = next(item for item in client.get("/api/transactions").json() if item["id"] == transaction_id)
        assert transaction["market"] == "japan"
        assert transaction["code"] == "9999"
        assert transaction["name"] == "修改后的股票"
        assert transaction["quantity"] == 3
        assert transaction["price"] == 12
        assert transaction["note"] == "修改后的买入原因"


def test_market_preview_and_confirm(monkeypatch):
    class FakeCloses:
        iloc = None

        def __init__(self):
            self.iloc = self

        def dropna(self):
            return self

        def __len__(self):
            return 1

        def __getitem__(self, index):
            assert index == -1
            return 123.45

    class FakeHistory:
        empty = False

        def __getitem__(self, key):
            assert key == "Close"
            return FakeCloses()

    class FakeTicker:
        fast_info = {"last_price": None}

        def history(self, **_):
            return FakeHistory()

    monkeypatch.setattr("app.main.yf.Ticker", lambda _: FakeTicker())
    with TestClient(app) as client:
        before = client.get("/api/portfolio").json()["positions"]
        old_price = before[0]["current_price"]
        response = client.post("/api/market/preview")
        assert response.status_code == 200
        items = response.json()["items"]
        assert items[0]["suggested_price"] == 123.45
        assert client.get("/api/portfolio").json()["positions"][0]["current_price"] == old_price

        confirmed = client.post("/api/market/confirm", json={"prices": [{"stock_id": items[0]["stock_id"], "price": 234.56}]})
        assert confirmed.status_code == 200
        position = next(item for item in client.get("/api/portfolio").json()["positions"] if item["id"] == items[0]["stock_id"])
        assert position["current_price"] == 234.56


def test_fund_asset_is_included_and_cannot_link_transactions():
    with TestClient(app) as client:
        created = client.post("/api/assets", json={"name": "测试基金", "asset_type": "fund", "currency": "CNY", "balance": 12345, "linked": True})
        assert created.status_code == 201

        summary = client.get("/api/assets").json()
        fund = next(item for item in summary["rows"] if item["name"] == "测试基金")
        assert fund["asset_type"] == "fund"
        assert fund["linked"] is False
        assert "institution" not in fund
        assert summary["breakdown"]["CNY"]["fund"] == 12345
