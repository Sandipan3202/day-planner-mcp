"""find_focus_blocks logic: one test per edge case in spec 02 §6, plus the B3 Friday.

Preferences are a fixed copy of the D5 values (not the live config file), so editing
config/preferences.json can't break these tests. Every call passes `now` explicitly
so results don't depend on the real clock.
"""

from typing import Any

import pytest

from focus_planner.planner import PlannerInputError, find_focus_blocks

THU = "2026-10-08"
FRI = "2026-10-09"
SAT = "2026-10-10"
BEFORE = "2026-10-01T08:00:00+05:30"  # a `now` that doesn't fall on any test date

PREFS: dict[str, Any] = {
    "timezone": "Asia/Kolkata",
    "working_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
    "working_hours": {"start": "09:30", "end": "18:30"},
    "lunch": {"start": "12:30", "end": "13:30"},
    "focus_block_minutes": 120,
    "min_focus_minutes": 60,
    "buffer_minutes": 10,
    "max_focus_blocks_per_day": 2,
    "no_meeting_days": [],
    "calendars": {"read": "primary", "write": "test@group.calendar.google.com"},
    "focus_event_title": "[MCP] Focus block",
}


def prefs(**overrides: Any) -> dict[str, Any]:
    return {**PREFS, **overrides}


def ev(day: str, start: str, end: str, **extra: Any) -> dict[str, Any]:
    return {"start": f"{day}T{start}:00+05:30", "end": f"{day}T{end}:00+05:30", **extra}


def spans(items: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """[{start, end, ...}] -> [("HH:MM", "HH:MM")] for readable asserts."""
    return [(i["start"][11:16], i["end"][11:16]) for i in items]


def plan(events: list[dict[str, Any]], day: str = THU, p: dict[str, Any] | None = None, **kw: Any):
    kw.setdefault("now", BEFORE)
    return find_focus_blocks(day, events, p or PREFS, **kw)


# --- §6 edge cases -----------------------------------------------------------


def test_no_events_gives_working_hours_minus_lunch_capped():
    r = plan([])
    assert r["working_day"] is True
    # Gaps 09:30-12:20 and 13:40-18:30 (lunch + 10 min buffers) -> three 120-min blocks, cap keeps the first two.
    assert spans(r["blocks"]) == [("09:30", "11:30"), ("13:40", "15:40")]
    assert [b["minutes"] for b in r["blocks"]] == [120, 120]
    assert r["blocks"][0]["start"] == "2026-10-08T09:30:00+05:30"
    assert any("daily cap is 2" in n for n in r["notes"])


def test_weekend_is_not_a_working_day():
    r = plan([], day=SAT)
    assert r["working_day"] is False
    assert r["blocks"] == []
    assert any("not a working day" in n for n in r["notes"])


def test_event_partly_outside_working_hours_is_clipped():
    events = [ev(THU, "08:00", "10:00"), ev(THU, "18:00", "20:00")]
    r = plan(events, p=prefs(max_focus_blocks_per_day=10))
    # 08:00-10:00 blocks only 09:30-10:10; 18:00-20:00 blocks only 17:50-18:30.
    assert spans(r["blocks"]) == [("10:10", "12:10"), ("13:40", "15:40"), ("15:40", "17:40")]


def test_overlapping_events_merge_into_one_busy_interval():
    events = [ev(THU, "10:00", "11:00"), ev(THU, "10:30", "11:30")]
    r = plan(events, p=prefs(buffer_minutes=0, max_focus_blocks_per_day=10))
    # One busy stretch 10:00-11:30: a 30-min gap before it, a 60-min block after it.
    assert spans(r["skipped"])[0] == ("09:30", "10:00")
    assert spans(r["blocks"])[0] == ("11:30", "12:30")


def test_free_event_is_ignored_and_reported():
    task = ev(THU, "09:30", "18:30", busy=False, title="MCP-2")
    assert plan([task])["blocks"] == plan([])["blocks"]
    assert '1 event ignored: marked free ("MCP-2")' in plan([task])["notes"]


def test_all_day_busy_event_blocks_the_day():
    r = plan([{"start": THU, "end": FRI, "title": "Offsite"}])
    assert r["blocks"] == []
    assert any("Offsite" in n for n in r["notes"])


def test_back_to_back_meetings_10_min_apart_leave_no_block_between():
    events = [ev(THU, "14:00", "15:00"), ev(THU, "15:10", "16:10"), ev(THU, "16:20", "17:20")]
    r = plan(events, p=prefs(max_focus_blocks_per_day=10))
    # Buffers swallow the 10-min gaps: one busy stretch 13:50-17:30.
    for start, end in spans(r["blocks"]) + spans(r["skipped"]):
        assert end <= "13:50" or start >= "17:30"
    assert ("17:30", "18:30") in spans(r["blocks"])


def test_now_mid_day_ignores_earlier_time():
    r = plan([], p=prefs(max_focus_blocks_per_day=10), now=f"{THU}T11:02:00+05:30")
    # 11:02 rounds up to 11:05.
    assert spans(r["blocks"])[0] == ("11:05", "12:20")
    assert r["blocks"][0]["minutes"] == 75
    assert all(b["start"] >= f"{THU}T11:05" for b in r["blocks"] + r["skipped"])


def test_now_after_working_hours_gives_no_blocks():
    r = plan([], now=f"{THU}T19:00:00+05:30")
    assert r["blocks"] == []
    assert any("after working hours" in n for n in r["notes"])


def test_events_in_another_offset_are_converted():
    # 22:00 on Oct 7 in UTC-7 is 10:30 on Oct 8 in Kolkata; Z is UTC.
    events = [{"start": "2026-10-07T22:00:00-07:00", "end": "2026-10-08T06:00:00Z"}]  # 10:30-11:30 IST
    r = plan(events, p=prefs(buffer_minutes=0, max_focus_blocks_per_day=10))
    assert spans(r["blocks"])[:2] == [("09:30", "10:30"), ("11:30", "12:30")]


def test_gap_of_exactly_min_minutes_is_included():
    events = [ev(THU, "10:30", "12:30")]
    p = prefs(buffer_minutes=0, max_focus_blocks_per_day=10)
    assert spans(plan(events, p=p)["blocks"])[0] == ("09:30", "10:30")
    # One minute more than the gap and it's skipped instead.
    r = plan(events, p=p, min_minutes=61)
    assert ("09:30", "10:30") not in spans(r["blocks"])
    assert r["skipped"][0]["reason"] == "shorter than 61 min"


# --- B3: Phase 1's real Friday ----------------------------------------------


def test_b3_friday_oct_9():
    events = [
        ev(FRI, "07:00", "08:00", title="Early"),
        ev(FRI, "09:00", "10:00", title="travel to SSB"),
        ev(FRI, "14:00", "17:00", busy=False, title="Task"),
        ev(FRI, "18:00", "19:00", title="Evening"),
    ]
    r = plan(events, day=FRI)
    # Busy+buffers: ..-10:10, lunch 12:20-13:40, 17:50-..; the free Task doesn't count.
    assert spans(r["blocks"]) == [("10:10", "12:10"), ("13:40", "15:40")]
    assert '1 event ignored: marked free ("Task")' in r["notes"]


# --- Bad input ---------------------------------------------------------------


@pytest.mark.parametrize("bad", ["2026-13-01", "2026-02-30", "tomorrow", "2026/10/08", ""])
def test_bad_date(bad):
    with pytest.raises(PlannerInputError, match="date"):
        plan([], day=bad)


def test_end_before_start():
    with pytest.raises(PlannerInputError, match=r"events\[0\].*must be after start"):
        plan([ev(THU, "11:00", "10:00", title="Backwards")])


def test_end_equal_to_start():
    with pytest.raises(PlannerInputError, match="must be after start"):
        plan([ev(THU, "11:00", "11:00")])


def test_unparseable_event_time():
    with pytest.raises(PlannerInputError, match=r"events\[0\].*start"):
        plan([{"start": "lunchtime", "end": f"{THU}T11:00:00+05:30"}])


def test_min_minutes_below_15():
    with pytest.raises(PlannerInputError, match="min_minutes"):
        plan([], min_minutes=10)


def test_bad_now():
    with pytest.raises(PlannerInputError, match="now"):
        plan([], now="soon")
