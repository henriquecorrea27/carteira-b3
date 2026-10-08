from datetime import date, timedelta


def _buy(day="2024-01-02", ticker="WEGE3", qty="100", price="10", costs="5", **extra):
    return {
        "date": day,
        "ticker": ticker,
        "type": "BUY",
        "quantity": qty,
        "price": price,
        "costs": costs,
        **extra,
    }


def _sell(day="2024-03-01", ticker="WEGE3", qty="60", price="15", costs="3"):
    return {"date": day, "ticker": ticker, "type": "SELL", "quantity": qty, "price": price, "costs": costs}


def test_create_buy_normalizes_fractional_ticker_and_serializes_decimals_as_strings(client):
    res = client.post("/api/transactions", json=_buy(ticker="wege3f", broker="  XP  "))
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["ticker"] == "WEGE3"
    assert body["quantity"] == "100"
    assert body["price"] == "10"
    assert body["costs"] == "5.00"
    assert body["broker"] == "XP"
    assert body["source"] == "MANUAL"


def test_positions_and_summary_follow_the_ledger(client):
    client.post(
        "/api/transactions/batch",
        json={"items": [_buy(), _buy(day="2024-02-01", qty="50", price="13", costs="2.5"), _sell()]},
    )
    positions = client.get("/api/portfolio/positions").json()
    assert len(positions) == 1
    pos = positions[0]
    assert (pos["ticker"], pos["quantity"], pos["avg_price"], pos["total_cost"]) == (
        "WEGE3",
        "90",
        "11.05",
        "994.50",
    )
    assert pos["realized_result"] == "234.00"
    assert pos["asset_class"] == "STOCK"

    summary = client.get("/api/portfolio/summary").json()
    assert summary["invested"] == "994.50"
    assert summary["realized_result"] == "234.00"
    assert summary["open_positions"] == 1


def test_oversell_is_rejected_with_row_index_and_nothing_is_saved(client):
    res = client.post("/api/transactions/batch", json={"items": [_buy(qty="10"), _sell(qty="11")]})
    assert res.status_code == 422
    issue = res.json()["detail"][0]
    assert issue["code"] == "INSUFFICIENT_POSITION"
    assert issue["row"] == 1
    assert "maior que a posição" in issue["message"]
    assert client.get("/api/transactions").json() == []


def test_batch_field_errors_point_to_the_row(client):
    res = client.post(
        "/api/transactions/batch",
        json={"items": [_buy(), {"date": "2024-01-03", "ticker": "PETR", "type": "BUY"}]},
    )
    assert res.status_code == 422
    rows = {issue["row"] for issue in res.json()["detail"]}
    assert rows == {1}


def test_future_trade_is_rejected(client):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    res = client.post("/api/transactions", json=_buy(day=tomorrow))
    assert res.status_code == 422
    assert "futuro" in res.json()["detail"][0]["message"]


def test_deleting_a_buy_that_backs_a_later_sell_is_blocked(client):
    created = client.post("/api/transactions/batch", json={"items": [_buy(qty="10"), _sell(qty="10")]}).json()
    res = client.delete(f"/api/transactions/{created[0]['id']}")
    assert res.status_code == 422
    assert res.json()["detail"][0]["transaction_id"] == created[1]["id"]
    assert client.delete(f"/api/transactions/{created[1]['id']}").status_code == 204
    assert client.delete(f"/api/transactions/{created[0]['id']}").status_code == 204


def test_edit_marks_row_as_user_edited_and_recalculates(client):
    created = client.post("/api/transactions", json=_buy()).json()
    res = client.put(f"/api/transactions/{created['id']}", json=_buy(price="20", costs="0"))
    assert res.status_code == 200
    assert res.json()["user_edited"] is True
    assert client.get("/api/portfolio/positions").json()[0]["avg_price"] == "20"


def test_jcp_withholding_uses_rate_by_payment_date(client):
    client.post(
        "/api/transactions", json=_buy(day="2025-01-02", ticker="CMIG4", qty="337", price="10", costs="0")
    )
    jcp_2025 = {
        "date": "2025-11-20",
        "ticker": "CMIG4",
        "type": "JCP",
        "quantity": "337",
        "price": "0.11",
        "payment_date": "2025-12-30",
    }
    jcp_2026 = {**jcp_2025, "payment_date": "2026-01-30"}
    first = client.post("/api/transactions", json=jcp_2025).json()
    second = client.post("/api/transactions", json=jcp_2026).json()
    # gross 37,07 ; 15% → 5,56 ; 17,5% → 6,49
    assert (first["gross_amount"], first["tax_withheld"], first["net_amount"]) == ("37.07", "5.56", "31.51")
    assert (second["tax_withheld"], second["net_amount"]) == ("6.49", "30.58")
    assert first["status"] == "PAID"
    assert client.get("/api/portfolio/summary").json()["provents_net_total"] == "62.09"


def test_bonus_without_cost_flags_pending(client):
    client.post("/api/transactions", json=_buy(ticker="ITSA4", qty="100", price="12", costs="0"))
    client.post(
        "/api/transactions", json={"date": "2024-11-29", "ticker": "ITSA4", "type": "BONUS", "quantity": "10"}
    )
    pos = client.get("/api/portfolio/positions").json()[0]
    assert pos["quantity"] == "110"
    assert pos["pending_bonus_cost"] is True
    assert client.get("/api/portfolio/summary").json()["pending_bonus_cost"] == 1


def test_asset_search_and_class_override(client):
    client.post("/api/transactions", json=_buy(ticker="BOVA11", costs="0"))
    assert client.get("/api/assets/search", params={"q": "bov"}).json()[0]["asset_class"] == "FII"  # inferred
    patched = client.patch("/api/assets/BOVA11", json={"asset_class": "ETF"}).json()
    assert (patched["asset_class"], patched["class_confirmed"]) == ("ETF", True)


def test_list_filters(client):
    client.post("/api/transactions/batch", json={"items": [_buy(), _buy(ticker="ITSA4", costs="0"), _sell()]})
    assert len(client.get("/api/transactions", params={"ticker": "wege3"}).json()) == 2
    assert len(client.get("/api/transactions", params={"type": "SELL"}).json()) == 1
    assert (
        len(
            client.get(
                "/api/transactions", params={"type": ["BUY", "SELL"], "date_from": "2024-02-01"}
            ).json()
        )
        == 1
    )
