"""Text for the plan_my_day prompt (spec 02 §7).

No MCP imports here, so the rendered text can be unit-tested on its own.
"""

from __future__ import annotations

import json
import re
from datetime import date as Date
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from focus_planner.preferences import DAY_NAMES

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class PromptArgumentError(ValueError):
    """A bad prompt argument. The message says what's accepted."""


def resolve_date(value: str, today: Date) -> Date:
    """'today', 'tomorrow' or YYYY-MM-DD -> a date. `today` is in the preferences time zone."""
    text = value.strip().lower()
    if text == "today":
        return today
    if text == "tomorrow":
        return today + timedelta(days=1)
    if _DATE.match(text):
        try:
            return Date.fromisoformat(text)
        except ValueError:
            pass
    raise PromptArgumentError(f"date must be 'today', 'tomorrow' or YYYY-MM-DD, got {value!r}")


def render_plan_my_day(date: str, preferences: dict[str, Any], now: datetime | None = None) -> str:
    """The user message for plan_my_day, with the date resolved and the preferences pasted in.

    The server resolves 'today'/'tomorrow' itself (in the preferences time zone), so the
    model never has to guess what day it is.
    """
    tz = ZoneInfo(preferences["timezone"])
    today = (now or datetime.now(tz)).astimezone(tz).date()
    day = resolve_date(date, today)
    next_day = day + timedelta(days=1)
    offset = datetime(day.year, day.month, day.day, tzinfo=tz).strftime("%z")
    offset = f"{offset[:3]}:{offset[3:]}"  # +0530 -> +05:30
    day_name = DAY_NAMES[day.weekday()]
    read_cal = preferences["calendars"]["read"]
    write_cal = preferences["calendars"]["write"]
    title = preferences["focus_event_title"]

    heads_up = []
    if day_name not in preferences["working_days"]:
        heads_up.append(f"- {day.isoformat()} is a {day_name}, which is not one of my working days.")
    if day_name in preferences["no_meeting_days"]:
        heads_up.append(f"- {day_name} is a no-meeting day: mention that meetings shouldn't be booked on it.")
    heads_up_text = ("\nHeads-up:\n" + "\n".join(heads_up) + "\n") if heads_up else ""

    return f"""\
Plan my focus time for {day_name} {day.isoformat()} (time zone {preferences["timezone"]}).
{heads_up_text}
My planning preferences (from planner://preferences; these rules apply to this whole run):
```json
{json.dumps(preferences, indent=2)}
```

Follow these steps in order:

1. The date is {day.isoformat()} in {preferences["timezone"]}. Use exactly that day.

2. Fetch that day's events with the Calendar server's `list_events`:
   calendarId "{read_cal}", startTime {day.isoformat()}T00:00:00{offset}, endTime {next_day.isoformat()}T00:00:00{offset},
   orderBy startTime. One call covering the full day; don't page past what's needed.

3. Convert every event (including free ones) to the `find_focus_blocks` input:
   - start: start.dateTime, or start.date for an all-day event
   - end:   end.dateTime, or end.date for an all-day event
   - busy:  false if transparency is "transparent" (Google Tasks arrive like this),
            or availability is "AVAILABILITY_FREE", or I declined it; otherwise true
   - title: summary

4. Call focus-planner's `find_focus_blocks` with date "{day.isoformat()}" and those events.

5. Show me the proposed blocks (start, end, length) and any notes or skipped gaps worth mentioning.
   Then ask me to confirm. Do NOT create anything yet.

6. Only after I say yes, call `create_event` once per block with:
   calendarId "{write_cal}" (always pass it; never write to "{read_cal}"),
   summary "{title}", the block's startTime and endTime, timeZone "{preferences["timezone"]}",
   eventType FOCUS_TIME, notificationLevel NONE.

7. Read the events back with `list_events` on calendarId "{write_cal}" for {day.isoformat()},
   and report what actually exists there, not what the create calls said.
"""
