"""plan_my_day rendering (spec 02 §7): date resolution and the preferences pasted in."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from focus_planner.preferences import load_preferences
from focus_planner.prompts import PromptArgumentError, render_plan_my_day, resolve_date

# 23:30 UTC on Oct 7 is already 05:00 on Oct 8 in Kolkata, so "today" must be Oct 8.
NOW = datetime(2026, 10, 7, 23, 30, tzinfo=ZoneInfo("UTC"))


@pytest.fixture
def prefs():
    return load_preferences()


@pytest.mark.parametrize(
    "arg, expected",
    [("today", date(2026, 10, 8)), ("Tomorrow", date(2026, 10, 9)), ("2026-10-12", date(2026, 10, 12))],
)
def test_resolve_date(arg, expected):
    assert resolve_date(arg, date(2026, 10, 8)) == expected


@pytest.mark.parametrize("bad", ["next week", "2026-02-30", "10/09/2026", ""])
def test_resolve_bad_date(bad):
    with pytest.raises(PromptArgumentError, match="today"):
        resolve_date(bad, date(2026, 10, 8))


def test_today_uses_preferences_time_zone(prefs):
    assert "Thu 2026-10-08" in render_plan_my_day("today", prefs, now=NOW)


def test_tomorrow_has_the_steps_and_preferences(prefs):
    text = render_plan_my_day("tomorrow", prefs, now=NOW)
    assert "Fri 2026-10-09" in text
    # Preferences pasted in, so the rules survive a fresh session (E6.3).
    assert prefs["calendars"]["write"] in text
    assert '"buffer_minutes": 10' in text
    # Full-day read window in the preferences offset.
    assert "startTime 2026-10-09T00:00:00+05:30, endTime 2026-10-10T00:00:00+05:30" in text
    # Busy rules, confirm-before-write, busy normal event (FOCUS_TIME is rejected on MCP Test), read-back.
    for phrase in ("transparent", "AVAILABILITY_FREE", "declined", "Do NOT create anything yet",
                   "availability AVAILABILITY_BUSY", "notificationLevel NONE", "Read the events back"):
        assert phrase in text
    assert "eventType FOCUS_TIME" not in text
    assert f'summary "{prefs["focus_event_title"]}"' in text


def test_weekend_and_no_meeting_day_heads_up(prefs):
    text = render_plan_my_day("2026-10-10", {**prefs, "no_meeting_days": ["Sat"]}, now=NOW)
    assert "Sat, which is not one of my working days" in text
    assert "no-meeting day" in text
    assert "Heads-up" not in render_plan_my_day("2026-10-09", prefs, now=NOW)


def test_reads_write_calendar_so_reruns_dont_duplicate(prefs):
    # Spec 03 R5 / Q2 (a): existing blocks on calendars.write must count as busy.
    text = render_plan_my_day("2026-10-09", prefs, now=NOW)
    write_cal = prefs["calendars"]["write"]
    assert f'a. calendarId "{prefs["calendars"]["read"]}"' in text
    assert f'b. calendarId "{write_cal}"' in text
    assert f'for events from "{write_cal}": always true' in text
    assert "already planned" in text
    assert "nothing to create" in text
