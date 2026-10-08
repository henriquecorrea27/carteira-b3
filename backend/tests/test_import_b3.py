from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "b3"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _files(*names):
    return [("files", (name, (FIXTURES / name).read_bytes(), XLSX)) for name in names]


BOTH = ("negociacao_sample.xlsx", "movimentacao_sample.xlsx")


def _rows(report, **match):
    return [r for r in report["rows"] if all(r.get(k) == v for k, v in match.items())]


def test_preview_classifies_rows_and_writes_nothing(client):
    res = client.post("/api/import/b3/preview", files=_files(*BOTH))
    assert res.status_code == 200, res.text
    report = res.json()
    assert report["files"] == {
        "negociacao_sample.xlsx": "b3_negociacao",
        "movimentacao_sample.xlsx": "b3_movimentacao",
    }
    assert report["counts"] == {"NEW": 18, "IGNORED": 28}
    assert report["committed"] is False
    assert client.get("/api/transactions").json() == []

    futures = [r for r in report["rows"] if r["reason"] == "mercado futuro (fora da carteira)"]
    assert len(futures) == 7  # 3 in Negociação + 4 in Movimentação
    settlement = _rows(report, file="movimentacao_sample.xlsx", status="IGNORED")
    assert any("liquidação de negócio" in r["reason"] for r in settlement)


def test_commit_rebuilds_the_expected_portfolio(client):
    report = client.post("/api/import/b3/commit", files=_files(*BOTH)).json()
    assert report["inserted"] == 18

    positions = {p["ticker"]: p for p in client.get("/api/portfolio/positions").json()}
    assert {t: p["quantity"] for t, p in positions.items()} == {
        "WEGE3": "80",
        "TAEE4": "20",
        "ITSA4": "52",
        "BBAS3": "10",
    }
    assert positions["WEGE3"]["avg_price"] == "52.3"
    assert positions["BBAS3"]["avg_price"] == "27.85"  # 278,50 / 10 after the 1:2 split
    assert positions["ITSA4"]["pending_bonus_cost"] is True
    assert positions["ITSA4"]["name"] == "ITAUSA S/A"
    assert positions["TAEE4"]["provents_net"] == "10.00"


def test_split_and_reverse_split_factors_come_from_the_position(client):
    report = client.post("/api/import/b3/preview", files=_files(*BOTH)).json()
    (split,) = _rows(report, type="SPLIT")
    (reverse,) = _rows(report, type="REVERSE_SPLIT")
    assert (split["ticker"], split["factor"]) == ("BBAS3", "2")
    assert (reverse["ticker"], reverse["factor"]) == ("MGLU3", "10")


def test_jcp_gross_is_rebuilt_from_the_net_credited_amount(client):
    report = client.post("/api/import/b3/preview", files=_files(*BOTH)).json()
    jcp = {(r["ticker"], r["date"]): r for r in _rows(report, type="JCP")}
    # net 8,50 at 15% → gross 10,00, tax 1,50
    assert (jcp[("ITSA4", "2023-12-20")]["gross_amount"], jcp[("ITSA4", "2023-12-20")]["tax_withheld"]) == (
        "10.00",
        "1.50",
    )


def test_reimport_is_idempotent_and_identical_trades_are_kept(client):
    client.post("/api/import/b3/commit", files=_files(*BOTH))
    again = client.post("/api/import/b3/commit", files=_files(*BOTH)).json()
    assert again["inserted"] == 0
    assert again["counts"] == {"DUPLICATE": 18, "IGNORED": 28}
    taee = client.get("/api/transactions", params={"ticker": "TAEE4", "type": "BUY"}).json()
    assert len(taee) == 2


def test_same_file_twice_in_one_upload_is_deduplicated(client):
    report = client.post("/api/import/b3/preview", files=_files("negociacao_sample.xlsx") * 2).json()
    assert report["counts"]["NEW"] == 9
    assert report["counts"]["DUPLICATE"] == 9


def test_manual_entry_lookalike_is_flagged_and_skipped_unless_confirmed(client):
    manual = {"date": "2025-07-10", "ticker": "WEGE3", "type": "BUY", "quantity": "100", "price": "52.30"}
    assert client.post("/api/transactions", json=manual).status_code == 201

    report = client.post("/api/import/b3/commit", files=_files(*BOTH)).json()
    (flagged,) = _rows(report, status="POSSIBLE_DUPLICATE")
    assert flagged["ticker"] == "WEGE3"
    assert report["inserted"] == 17
    wege = {p["ticker"]: p for p in client.get("/api/portfolio/positions").json()}["WEGE3"]
    assert wege["quantity"] == "80"


def test_movements_without_trades_report_ledger_errors(client):
    report = client.post("/api/import/b3/preview", files=_files("movimentacao_sample.xlsx")).json()
    errors = _rows(report, status="ERROR")
    assert {r["type"] for r in errors} >= {"BONUS", "SPLIT", "REVERSE_SPLIT"}
    assert all(r["reason"] for r in errors)


def test_unknown_file_is_rejected(client):
    files = [("files", ("x.xlsx", b"not a spreadsheet", XLSX))]
    res = client.post("/api/import/b3/preview", files=files)
    assert res.status_code == 422
