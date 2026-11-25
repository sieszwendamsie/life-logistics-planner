"""Offline tests: no network. The fixture has the same shape as Ryanair's
cheapestPerDay answer (hand-written, not a recording: see the PR note)."""

import json
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

import pytest

from planner import cli
from planner.fares import FareError, describe, month_fares, month_url, parse_month

FIXTURE = Path(__file__).parent / "fixtures" / "ryanair_cheapest_per_day.json"
NOW = datetime(2026, 11, 25, 22, 0, tzinfo=UTC)


class FakeFetch:
    def __init__(self, body: bytes | None = None, error: str | None = None) -> None:
        self.body, self.error, self.urls = body, error, []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        if self.error:
            raise FareError(self.error)
        assert self.body is not None
        return self.body


def test_parse_skips_unavailable_and_sold_out() -> None:
    days = parse_month(FIXTURE.read_bytes(), "POZ", "BGY")
    assert [d.depart.day for d in days] == [4, 5]
    assert days[0].price_eur == 39.99 and days[0].arrive.hour == 14


@pytest.mark.parametrize("raw", [b"not json", b"{}", b'{"outbound": {"fares": [{"price": {}}]}}'])
def test_parse_rejects_unexpected_shapes(raw: bytes) -> None:
    with pytest.raises(FareError):
        parse_month(raw, "POZ", "BGY")


def test_parse_rejects_other_currency() -> None:
    body = json.loads(FIXTURE.read_text())
    body["outbound"]["fares"][1]["price"]["currencyCode"] = "PLN"
    with pytest.raises(FareError, match="PLN"):
        parse_month(json.dumps(body).encode(), "POZ", "BGY")


def test_window_filter() -> None:
    days = parse_month(FIXTURE.read_bytes(), "POZ", "BGY")
    midday, early = days
    assert midday.fits(time(7, 0), time(18, 30))
    assert not early.fits(time(7, 0), time(18, 30))  # departs 05:45
    assert early.fits(None, None)
    assert not midday.fits(None, time(14, 0))  # lands 14:30


def test_live_fetch_then_cache_hit(tmp_path: Path) -> None:
    fetch = FakeFetch(FIXTURE.read_bytes())
    first = month_fares("POZ", "BGY", "2027-02", fetch=fetch, cache_dir=tmp_path, now=NOW)
    assert not first.from_cache and fetch.urls == [month_url("POZ", "BGY", "2027-02")]
    later = NOW + timedelta(hours=1)
    again = month_fares("POZ", "BGY", "2027-02", fetch=fetch, cache_dir=tmp_path, now=later)
    assert again.from_cache and len(fetch.urls) == 1
    assert again.checked_at == NOW and again.source_url == first.source_url
    assert len(again.days) == 2


def test_stale_cache_is_refetched_and_never_used_when_offline(tmp_path: Path) -> None:
    month_fares(
        "POZ", "BGY", "2027-02", fetch=FakeFetch(FIXTURE.read_bytes()), cache_dir=tmp_path, now=NOW
    )
    next_day = NOW + timedelta(hours=30)
    with pytest.raises(FareError, match="blocked"):
        month_fares(
            "POZ",
            "BGY",
            "2027-02",
            fetch=FakeFetch(error="blocked"),
            cache_dir=tmp_path,
            now=next_day,
        )


def test_refresh_ignores_fresh_cache(tmp_path: Path) -> None:
    fetch = FakeFetch(FIXTURE.read_bytes())
    month_fares("POZ", "BGY", "2027-02", fetch=fetch, cache_dir=tmp_path, now=NOW)
    month_fares("POZ", "BGY", "2027-02", fetch=fetch, cache_dir=tmp_path, now=NOW, refresh=True)
    assert len(fetch.urls) == 2


def test_describe_shows_source_and_check_time(tmp_path: Path) -> None:
    m = month_fares(
        "POZ", "BGY", "2027-02", fetch=FakeFetch(FIXTURE.read_bytes()), cache_dir=tmp_path, now=NOW
    )
    text = "\n".join(describe(m, time(7, 0), time(18, 30)))
    assert "live, checked 2026-11-25 22:00 UTC" in text
    assert "Thu 2027-02-04 12:40-14:30" in text and "05:45" not in text


def test_cli_reports_failure_instead_of_guessing(monkeypatch, capsys) -> None:
    def blocked(*_a, **_k):
        raise FareError("Ryanair answered HTTP 403 (blocked or rate-limited)")

    monkeypatch.setattr(cli, "month_fares", blocked)
    code = cli.main(
        [
            "fares",
            "--month",
            "2027-02",
            "--constraints",
            "examples/constraints.yaml",
            "--route",
            "POZ-BGY",
        ]
    )
    out = capsys.readouterr().out
    assert code == 2 and "NOT live-checked" in out and "find-flights" in out
