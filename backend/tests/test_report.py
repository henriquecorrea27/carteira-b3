"""F7 — daily report: due day / catch-up, send log, changes vs. the previous report, rendering, Discord."""

import json
from datetime import date, datetime, time
from decimal import Decimal as D

import httpx
import pytest

from app.main import app
from app.models import AnalysisSnapshot, CorporateEvent, DataSourceStatus, PriceHistory, ReportDispatch
from app.notifications import service
from app.notifications.base import NotifierError, split_message
from app.notifications.discord import DiscordNotifier
from app.notifications.report import build_report, render

THU = date(2026, 10, 8)  # Thursday; 12/10 (Monday) is a holiday
AT = time(19, 0)


class FakeNotifier:
    name = "fake"
    max_length = 2000

    def __init__(self, fail: bool = False):
        self.sent: list[list[str]] = []
        self.fail = fail

    def send(self, messages):
        if self.fail:
            raise NotifierError("offline")
        self.sent.append(messages)


# --- schedule ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 10, 8, 19, 0), date(2026, 10, 8)),  # at the configured time
        (datetime(2026, 10, 8, 18, 59), date(2026, 10, 7)),  # before it: yesterday's report is due
        (datetime(2026, 10, 10, 11, 0), date(2026, 10, 9)),  # Saturday → Friday
        (datetime(2026, 10, 12, 20, 0), date(2026, 10, 9)),  # holiday Monday → Friday
        (datetime(2026, 10, 13, 9, 0), date(2026, 10, 9)),  # Tuesday morning → Friday
    ],
)
def test_due_report_date(now, expected):
    assert service.due_report_date(now, AT) == expected


# --- message splitting and Discord ------------------------------------------------------------


def test_split_message_keeps_sections_and_limit():
    text = "\n\n".join(["## title", "a" * 1500, "b" * 600, "c\n" * 10])
    chunks = split_message(text, 2000)
    assert all(len(c) <= 2000 for c in chunks)
    assert chunks[0] == "## title\n\n" + "a" * 1500
    assert chunks[1].startswith("b" * 600)
    assert "".join(chunks).replace("\n", "") == text.replace("\n", "")


def test_split_message_cuts_huge_lines():
    chunks = split_message("x" * 4500, 2000)
    assert [len(c) for c in chunks] == [2000, 2000, 500]


def _discord(handler):
    return DiscordNotifier(
        "https://discord.test/api/webhooks/1/secret", httpx.Client(transport=httpx.MockTransport(handler))
    )


def test_discord_posts_each_message_without_mentions():
    calls = []

    def handler(request):
        calls.append((request.url.params.get("wait"), json.loads(request.content)))
        return httpx.Response(200, json={"id": "1"})

    _discord(handler).send(["one", "two"])
    assert [c[1]["content"] for c in calls] == ["one", "two"]
    assert calls[0][0] == "true"
    assert calls[0][1]["allowed_mentions"] == {"parse": []}


def test_discord_retries_rate_limit(monkeypatch):
    monkeypatch.setattr("app.notifications.discord.time.sleep", lambda s: None)
    responses = iter([httpx.Response(429, json={"retry_after": 0.1}), httpx.Response(204)])
    _discord(lambda request: next(responses)).send(["hi"])


def test_discord_error_never_leaks_the_url():
    with pytest.raises(NotifierError) as err:
        _discord(lambda request: httpx.Response(404, json={"message": "Unknown Webhook"})).send(["hi"])
    assert "DISCORD_WEBHOOK_URL" in str(err.value)
    assert "secret" not in str(err.value)


# --- report content ---------------------------------------------------------------------------


def _seed(client, session_factory):
    items = [
        {"date": "2026-09-01", "ticker": "CMIG4", "type": "BUY", "quantity": "100", "price": "10"},
        {"date": "2026-09-01", "ticker": "BBAS3", "type": "BUY", "quantity": "10", "price": "20"},
        {"date": "2026-09-01", "ticker": "HGLG11", "type": "BUY", "quantity": "2", "price": "150"},
        {"date": "2026-09-01", "ticker": "TAEE4", "type": "BUY", "quantity": "5", "price": "15"},
        {"date": "2026-09-20", "ticker": "CMIG4", "type": "DIVIDEND", "quantity": "100", "price": "0.5",
         "payment_date": "2026-10-08"},
        {"date": "2026-09-25", "ticker": "BBAS3", "type": "JCP", "quantity": "10", "price": "1",
         "payment_date": "2026-10-06"},
    ]  # fmt: skip
    assert client.post("/api/transactions/batch", json={"items": items}).status_code == 201
    with session_factory() as s:
        for ticker, prev, close in [("CMIG4", "11", "12"), ("BBAS3", "25", "24"), ("HGLG11", "150", "153")]:
            for day, value in [(date(2026, 10, 7), prev), (THU, close)]:
                s.add(
                    PriceHistory(ticker=ticker, date=day, close=D(value), close_adjusted=D(value), source="t")
                )
        for ticker, decision, score, reason, details in [
            (
                "CMIG4",
                "BUY",
                "83.5",
                "Margem de segurança Graham 58,9% a favor",
                {"technical": {"distance": "0.03862", "sma_days": 200}},
            ),
            ("BBAS3", "WAIT", "75.4", "CAGR lucro 5a 2,9% contra", {}),  # no chart analysis
        ]:
            s.add(
                AnalysisSnapshot(
                    ticker=ticker, date=THU, decision=decision, score_final=D(score), main_reason=reason,
                    last_dfp=date(2025, 12, 31), last_itr=date(2026, 6, 30), rules_version=1, details=details,
                )
            )  # fmt: skip
        s.add(
            CorporateEvent(
                event_key="k1", source="b3", issuer="CMIG", isin="BRCMIGACNPR3", ticker="CMIG4",
                category="CASH", label="JRS CAP PROPRIO", tx_type="JCP", record_date=date(2026, 10, 14),
                ex_date=date(2026, 10, 15), payment_date=date(2026, 12, 30), value=D("0.2"),
            )
        )  # fmt: skip
        s.add(DataSourceStatus(source="cdi", ok=False, message="timeout"))
        s.commit()


NOW = datetime(2026, 10, 8, 19, 5)


def test_report_sections(client, session_factory):
    _seed(client, session_factory)
    with session_factory() as s:
        report = build_report(s, THU, NOW, baseline={"CMIG4": "WAIT", "BBAS3": "WAIT"})
        text = render(report)
    assert [(c.ticker, c.previous, c.current) for c in report.changes] == [("CMIG4", "WAIT", "BUY")]
    assert [s.ticker for s in report.stocks] == ["CMIG4", "BBAS3"]  # BUY before WAIT
    assert report.unanalyzed == ["TAEE4"]
    assert [o.ticker for o in report.others] == ["HGLG11"]
    assert [(p.ticker, p.net) for p in report.paid] == [("CMIG4", D("50.00"))]  # only today's payment
    assert [(u.ticker, u.record_date) for u in report.upcoming] == [("CMIG4", date(2026, 10, 14))]
    assert report.upcoming_until == date(2026, 10, 16)  # 5 business days, skipping the 12/10 holiday

    assert "## 📊 Carteira B3 · qui, 08/10/2026" in text
    assert "**Carteira no dia:** +5,57%" in text  # (1821 − 1725) / 1725
    assert "Patrimônio" not in text and "1.821" not in text
    assert "**CMIG4**: 🟡 Aguardar → **🟢 Comprar** · nota 83,5" in text
    assert "**CMIG4** · nota 83,5 · R$ 12,00 (+9,09%) · MM200 +3,9%" in text
    assert "-# Margem de segurança Graham 58,9% a favor" in text
    assert "**BBAS3** · nota 75,4 · R$ 24,00 (−4,00%)\n" in text  # no SMA distance without chart analysis
    assert "**HGLG11** R$ 153,00 (+2,00%)" in text
    assert "Pagos hoje: **R$ 50,00** líquido" in text
    assert "- **CMIG4** com 14/10 · JCP R$ 0,2000/ação (≈ R$ 16,50 líquido) · paga 30/12" in text
    assert "Falha na fonte CDI (Banco Central): timeout" in text
    assert "Sem análise das regras: TAEE4" in text
    assert "DFP 31/12/2025 · ITR 30/06/2026" in text


def test_first_report_has_no_changes_and_late_flag(client, session_factory):
    _seed(client, session_factory)
    with session_factory() as s:
        text = render(build_report(s, THU, datetime(2026, 10, 9, 9, 30), late=True))
    assert "Primeiro relatório" in text
    assert "⏰ Enviado com atraso em 09/10 às 09:30" in text
    # The day's change is Thursday's, not the flat Thursday → Saturday of a late weekend run
    with session_factory() as s:
        text = render(build_report(s, THU, datetime(2026, 10, 10, 11, 0), late=True))
    assert "**Carteira no dia:** +5,57%" in text


def test_paid_since_previous_report(client, session_factory):
    _seed(client, session_factory)
    with session_factory() as s:
        report = build_report(s, THU, NOW, baseline={}, paid_since=date(2026, 10, 5))
        text = render(report)
    assert [p.ticker for p in report.paid] == ["BBAS3", "CMIG4"]
    assert "Pagos desde 06/10: **R$ 58,25** líquido" in text  # 50 + 10 × 1 − 17,5% JCP (2026)


# --- scheduled runs ---------------------------------------------------------------------------


def test_scheduled_run_sends_once_then_catches_up_late(client, session_factory):
    _seed(client, session_factory)
    notifier = FakeNotifier()
    with session_factory() as s:
        assert service.run_scheduled(s, notifier, NOW).status == "SENT"
        assert service.run_scheduled(s, notifier, datetime(2026, 10, 8, 23, 0)).status == "ALREADY_SENT"
        assert service.run_scheduled(s, notifier, datetime(2026, 10, 9, 10, 0)).status == "ALREADY_SENT"
        # Friday's report was missed (computer off); Saturday's run sends it, marked as late
        run = service.run_scheduled(s, notifier, datetime(2026, 10, 10, 9, 0))
        assert (run.status, run.day, run.late) == ("SENT", date(2026, 10, 9), True)
        rows = s.query(ReportDispatch).order_by(ReportDispatch.id).all()
    assert len(notifier.sent) == 2
    assert [(r.report_date, r.trigger, r.status, r.late) for r in rows] == [
        (THU, "SCHEDULED", "SENT", False),
        (date(2026, 10, 9), "SCHEDULED", "SENT", True),
    ]
    assert rows[0].decisions == {"CMIG4": "BUY", "BBAS3": "WAIT"}
    assert "Mudanças desde o último relatório\nNenhuma ação mudou de decisão." in rows[1].content


def test_failed_send_is_retried_next_run(client, session_factory):
    _seed(client, session_factory)
    with session_factory() as s:
        run = service.run_scheduled(s, FakeNotifier(fail=True), NOW)
        assert (run.status, run.error) == ("FAILED", "offline")
        assert service.run_scheduled(s, FakeNotifier(), datetime(2026, 10, 8, 20, 0)).status == "SENT"


def test_refresh_runs_before_sending_and_not_when_already_sent(client, session_factory):
    _seed(client, session_factory)
    calls = []

    def refresh(session):
        calls.append(1)
        return ["cotações: offline"]

    with session_factory() as s:
        run = service.run_scheduled(s, FakeNotifier(), NOW, refresh=refresh)
        assert run.refresh_errors == ["cotações: offline"]
        service.run_scheduled(s, FakeNotifier(), NOW, refresh=refresh)
    assert calls == [1]


def test_not_configured(session_factory):
    with session_factory() as s:
        assert service.run_scheduled(s, None, NOW).status == "NOT_CONFIGURED"


# --- API --------------------------------------------------------------------------------------


def test_preview_and_manual_send(client, session_factory):
    _seed(client, session_factory)
    notifier = FakeNotifier()
    app.dependency_overrides[service.get_notifier] = lambda: notifier
    preview = client.get("/api/report/preview").json()
    assert preview["configured"] is True
    assert preview["content"].startswith("## 📊 Carteira B3")
    assert preview["messages"] == [preview["content"]]

    sent = client.post("/api/report/send").json()
    assert (sent["trigger"], sent["status"]) == ("MANUAL", "SENT")
    assert len(notifier.sent) == 1
    # A manual send never counts as the scheduled report of the day
    with session_factory() as s:
        assert service.last_sent(s) is None
    assert [d["trigger"] for d in client.get("/api/report/dispatches").json()] == ["MANUAL"]


def test_manual_send_errors(client):
    app.dependency_overrides[service.get_notifier] = lambda: None
    res = client.post("/api/report/send")
    assert res.status_code == 400
    assert "DISCORD_WEBHOOK_URL" in res.json()["detail"]
    app.dependency_overrides[service.get_notifier] = lambda: FakeNotifier(fail=True)
    res = client.post("/api/report/send")
    assert res.status_code == 502
    assert res.json()["detail"] == "Relatório não enviado: offline"
