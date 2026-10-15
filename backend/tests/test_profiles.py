from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.api import profiles as profiles_api
from app.core import db, profiles
from app.core.config import get_settings
from app.core.db import Base
from app.core.profiles import Profile, ProfileConfigError, parse_profiles
from app.main import app
from app.market_data.service import SOURCE_PRICES, record_status
from app.models import DataSourceStatus, WatchlistItem
from app.notifications import service
from app.rules import service as rules_service

URL = "postgresql+psycopg://carteira:s3cr%40t@localhost:5432/carteira"
TEST_URL = "postgresql+psycopg://carteira:s3cr%40t@localhost:5432/carteira_test"


def test_without_profiles_the_app_has_a_single_primary_profile():
    assert parse_profiles("", URL) == [Profile("principal", "Minha carteira", URL, True)]


def test_each_extra_profile_gets_its_own_database_on_the_same_server():
    me, dad = parse_profiles(" eu:Eu , pai:Pai ", URL, TEST_URL)
    assert (me.id, me.name, me.primary, me.database_url) == ("eu", "Eu", True, URL)
    assert (dad.id, dad.name, dad.primary, dad.database) == ("pai", "Pai", False, "carteira_pai")
    dad_url, base = make_url(dad.database_url), make_url(URL)
    assert (dad_url.username, dad_url.password, dad_url.host) == (base.username, base.password, base.host)
    assert parse_profiles("eu,mae", URL)[1].name == "Mae"


@pytest.mark.parametrize("spec", ["eu,Pai!", "eu,eu", "eu,1x", "eu,test"])
def test_invalid_profiles_are_rejected(spec):
    # "test" would land on carteira_test, wiped by the test suite
    with pytest.raises(ProfileConfigError):
        parse_profiles(spec, URL, TEST_URL)


@pytest.fixture
def two_profiles(monkeypatch, session_factory):
    """Profile A = the test database; B = the same database in another schema (a real, separate set of
    tables: the closest the suite gets to a second database without CREATEDB)."""
    test_url = get_settings().database_url_test
    engine = create_engine(test_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS profile_b CASCADE"))
        conn.execute(text("CREATE SCHEMA profile_b"))
    engine.dispose()
    b_url = make_url(test_url).update_query_dict({"options": "-csearch_path=profile_b"})
    pair = (
        Profile("ta", "A", test_url, True),
        Profile("tb", "B", b_url.render_as_string(hide_password=False), False),
    )
    Base.metadata.create_all(db.sessionmaker_for(pair[1]).kw["bind"])
    monkeypatch.setattr(profiles, "get_profiles", lambda: pair)
    monkeypatch.setattr(profiles_api, "get_profiles", lambda: pair)
    yield pair
    for p in pair:
        if (maker := db._makers.pop(p.id, None)) is not None:
            maker.kw["bind"].dispose()
    engine = create_engine(test_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA profile_b CASCADE"))
    engine.dispose()


def test_profiles_never_see_each_other(two_profiles):
    buy = {"date": "2024-01-02", "ticker": "WEGE3", "type": "BUY", "quantity": "100", "price": "10"}
    with TestClient(app) as client:  # the real get_session: the X-Profile header picks the database
        assert [p["id"] for p in client.get("/api/profiles").json()] == ["ta", "tb"]
        assert client.get("/api/profiles").json()[1] == {
            "id": "tb",
            "name": "B",
            "primary": False,
            "discord": False,
        }

        assert client.post("/api/transactions", json=buy, headers={"X-Profile": "tb"}).status_code == 201
        assert len(client.get("/api/transactions", headers={"X-Profile": "tb"}).json()) == 1
        assert client.get("/api/transactions").json() == []  # no header → first profile
        assert client.get("/api/transactions", headers={"X-Profile": "ta"}).json() == []

        res = client.get("/api/transactions", headers={"X-Profile": "xx"})
        assert res.status_code == 400
        assert "Perfil desconhecido" in res.json()["detail"]


def test_discord_is_only_for_the_first_profile(two_profiles, monkeypatch):
    first, other = two_profiles
    settings = get_settings()
    monkeypatch.setattr(settings, "discord_webhook_url", "https://discord.test/main")
    monkeypatch.setattr(settings, "discord_watchlist_webhook_url", "https://discord.test/mm200")
    assert service.get_notifier(first) is not None and service.watchlist_channel(first) == "SEPARATE"
    assert service.get_notifier(other) is None
    assert service.get_watchlist_notifier(other) is None and service.watchlist_channel(other) is None

    with TestClient(app) as client:
        res = client.get("/api/report/preview", headers={"X-Profile": "tb"})
        assert res.status_code == 200 and res.json()["configured"] is False
        assert client.post("/api/report/send", headers={"X-Profile": "tb"}).status_code == 400


def test_price_history_sync_memo_is_kept_per_database(two_profiles, monkeypatch):
    calls = []
    monkeypatch.setattr(
        rules_service.fundamentals, "fetch_range", lambda s, m, t, a, b, resync: calls.append(t)
    )
    for profile in two_profiles:
        with db.session_for(profile) as session:
            rules_service.sync_history(session, "WEGE3", object(), date(2026, 10, 14))
            rules_service.sync_history(session, "WEGE3", object(), date(2026, 10, 14))
    assert calls == ["WEGE3", "WEGE3"]  # once per profile, not once for both


def test_refresh_is_due_once_per_business_day_after_the_report_time(session_factory):
    with session_factory() as session:
        now = datetime(2026, 10, 14, 20, 0)  # Wednesday, after 19:00
        assert service.refresh_due(session, now)
        record_status(session, SOURCE_PRICES, True)
        session.commit()
        st = session.get(DataSourceStatus, SOURCE_PRICES)
        st.last_success_at = datetime(2026, 10, 14, 21, 30, tzinfo=UTC)  # 18:30 in São Paulo: before 19:00
        session.commit()
        assert service.refresh_due(session, now)
        st.last_success_at = datetime(2026, 10, 14, 22, 30, tzinfo=UTC)  # 19:30 in São Paulo
        session.commit()
        assert not service.refresh_due(session, now)
        assert not service.refresh_due(session, datetime(2026, 10, 15, 10, 0))  # Thursday morning
        assert service.refresh_due(session, datetime(2026, 10, 15, 19, 5))


def test_watchlist_is_separate_per_profile(two_profiles):
    first, other = two_profiles
    with db.session_for(other) as session:
        session.add(WatchlistItem(ticker="PETR4"))
        session.commit()
    with db.session_for(first) as session:
        assert not service.has_watchlist(session)
    with db.session_for(other) as session:
        assert service.has_watchlist(session)
