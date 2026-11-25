from datetime import time

from planner.models import Travel
from planner.routes import route_windows, ryanair_month_url, table

TRAVEL = Travel.model_validate(
    {
        "route_tiers": [
            {"name": "best", "origins": ["POZ"], "destinations": ["BLQ"]},
            {"name": "far", "origins": ["WAW"], "destinations": ["BLQ"]},
        ],
        "home_rides": {"POZ": {"hours": 0.5, "price_eur": 14}},
        "family_lifts": {"WAW": {"hours": 3, "km": 315}},
        "italy_drives": {"BLQ": {"km": 63, "hours": 1, "toll_eur": 5.3}},
    }
)


def test_family_and_martin_time_windows() -> None:
    w = {(r.origin, r.destination): r for r in route_windows(TRAVEL)}
    out = w[("POZ", "BLQ")]
    assert out.family_depart_after == time(7, 0)  # 05:00 + 0.5 h taxi + 1.5 h airport
    assert out.family_arrive_by == time(18, 30)  # 20:00 - 1 h drive - 0.5 h bags
    back = w[("BLQ", "WAW")]
    assert back.family_depart_after == time(7, 30)  # 05:00 + 1 h drive + 1.5 h
    assert back.family_arrive_by == time(16, 30)  # 20:00 - 3 h lift - 0.5 h
    far = w[("WAW", "BLQ")]
    assert far.martin_depart_after is None and "bus/train" in far.note


def test_table_lists_month_links() -> None:
    text = table(route_windows(TRAVEL), "2027-02")
    assert ryanair_month_url("POZ", "BLQ", "2027-02") in text
    assert "outboundMonthOfDate=2027-02-01" in text
