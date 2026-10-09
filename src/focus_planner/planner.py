"""Pure planning logic for find_focus_blocks (spec 02 §6).

No MCP imports here, so this can be unit-tested on its own.

All interval maths is done on timezone-aware datetimes in UTC, and converted to the
preferences time zone only for output, so events with any offset compare correctly.
"""

from __future__ import annotations

import re
from datetime import date as Date
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from focus_planner.preferences import DAY_NAMES, parse_hhmm

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

Interval = tuple[datetime, datetime]


class PlannerInputError(ValueError):
    """Bad tool input. The message is written for the model to read and fix."""


def find_focus_blocks(
    date: str,
    events: list[dict[str, Any]],
    preferences: dict[str, Any],
    min_minutes: int | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Return focus blocks for one day, following spec §6 steps 1-8.

    `preferences` must already be validated (see preferences.validate_preferences).
    `events` items have `start`, `end`, optional `busy` (default True) and `title`.

    One deliberate detail: buffers are added *before* clipping to the window, so a
    meeting that ends at 09:25 still keeps 09:25-09:35 free even though it sits
    outside working hours (or before `now`).
    """
    tz = ZoneInfo(preferences["timezone"])

    # --- Validate all input up front, so bad input errors even on a day off.
    day = _parse_date(date, "date")
    if min_minutes is not None and min_minutes < 15:
        raise PlannerInputError(f"min_minutes must be at least 15, got {min_minutes}")
    now_dt = _parse_datetime(now, "now", tz) if now is not None else datetime.now(timezone.utc)
    parsed = [_parse_event(e, i, tz) for i, e in enumerate(events)]

    minimum = min_minutes if min_minutes is not None else preferences["min_focus_minutes"]
    # A block shorter than the minimum would make no sense, so a high override stretches the block size too.
    block_len = max(preferences["focus_block_minutes"], minimum)
    buffer = timedelta(minutes=preferences["buffer_minutes"])
    day_name = DAY_NAMES[day.weekday()]

    result: dict[str, Any] = {
        "date": day.isoformat(),
        "timezone": preferences["timezone"],
        "working_day": day_name in preferences["working_days"],
        "no_meeting_day": day_name in preferences["no_meeting_days"],
        "blocks": [],
        "skipped": [],
        "notes": [],
    }
    notes: list[str] = result["notes"]

    free_titles = [ev["title"] for ev in parsed if not ev["busy"]]
    if free_titles:
        notes.append(
            f"{_plural(len(free_titles), 'event')} ignored: marked free ({', '.join(_quote(t) for t in free_titles)})"
        )
    if result["no_meeting_day"]:
        notes.append(f"{day_name} is a no-meeting day: don't book meetings on it.")

    # --- Step 1: working day?
    if not result["working_day"]:
        notes.append(f"{day.isoformat()} is a {day_name}, which is not a working day. No focus blocks planned.")
        return result

    # --- Step 2: the cap. Focus blocks already on the calendar (busy, titled focus_event_title, starting on this
    # date) use it up. Checked before `now`, so a re-run late in the day still says the cap is the reason.
    cap = preferences["max_focus_blocks_per_day"]
    focus_title = preferences["focus_event_title"]
    existing = sum(
        1 for ev in parsed if ev["busy"] and ev["title"] == focus_title and ev["start"].astimezone(tz).date() == day
    )
    left = max(cap - existing, 0)
    if existing:
        notes.append(
            f"{_plural(existing, 'existing focus block')} ({_quote(focus_title)}) already "
            f"{'counts' if existing == 1 else 'count'} toward the daily cap of {cap}."
        )
    if not left:
        notes.append("Daily cap already used up: no new focus blocks.")
        return result

    # --- Step 3: the window, trimmed by `now` if it falls on this date.
    hours = preferences["working_hours"]
    win_start = _at(day, hours["start"], tz)
    win_end = _at(day, hours["end"], tz)
    now_local = now_dt.astimezone(tz)
    if now_local.date() == day:
        rounded = _round_up_5(now_local).astimezone(timezone.utc)
        if rounded >= win_end:
            notes.append(
                f"It is already {now_local:%H:%M}, after working hours end ({hours['end']}). No focus blocks left today."
            )
            return result
        win_start = max(win_start, rounded)

    # --- Step 4: busy intervals = busy events + lunch.
    busy: list[Interval] = [(ev["start"], ev["end"]) for ev in parsed if ev["busy"]]
    lunch = preferences["lunch"]
    busy.append((_at(day, lunch["start"], tz), _at(day, lunch["end"], tz)))
    all_day = [ev["title"] for ev in parsed if ev["busy"] and ev["all_day"] and ev["start"] <= win_start < ev["end"]]
    if all_day:
        notes.append(f"All-day busy event blocks the whole day: {', '.join(_quote(t) for t in all_day)}")

    # --- Step 5: grow by the buffer, merge, then clip to the window.
    grown = _merge([(s - buffer, e + buffer) for s, e in busy])
    clipped = [(max(s, win_start), min(e, win_end)) for s, e in grown]
    clipped = [(s, e) for s, e in clipped if s < e]

    # --- Step 6: free gaps, dropping the short ones.
    blocks: list[Interval] = []
    for gap_start, gap_end in _gaps(win_start, win_end, clipped):
        if _minutes(gap_start, gap_end) < minimum:
            result["skipped"].append(_skipped(gap_start, gap_end, f"shorter than {minimum} min", tz))
            continue
        # --- Step 7: cut the gap into blocks; a leftover of at least the minimum is a shorter block.
        cursor = gap_start
        step = timedelta(minutes=block_len)
        while cursor + step <= gap_end:
            blocks.append((cursor, cursor + step))
            cursor += step
        if cursor < gap_end:
            if _minutes(cursor, gap_end) >= minimum:
                blocks.append((cursor, gap_end))
            else:
                result["skipped"].append(_skipped(cursor, gap_end, f"leftover shorter than {minimum} min", tz))

    # --- Step 8: keep what's left of the cap, longest first (ties: earlier), then sort by start.
    if len(blocks) > left:
        dropped = len(blocks) - left
        blocks = sorted(blocks, key=lambda b: (-(b[1] - b[0]), b[0]))[:left]
        notes.append(f"{_plural(dropped, 'more block')} would fit, but the daily cap is {cap}.")
    blocks.sort()

    result["blocks"] = [
        {"start": _iso(s, tz), "end": _iso(e, tz), "minutes": _minutes(s, e)} for s, e in blocks
    ]
    if not blocks and not all_day:
        notes.append("No free gap long enough for a focus block.")
    return result


# --- Parsing -----------------------------------------------------------------


def _parse_date(value: Any, field: str) -> Date:
    if not isinstance(value, str) or not _DATE.match(value):
        raise PlannerInputError(f"{field} must be a date as YYYY-MM-DD, got {value!r}")
    try:
        return Date.fromisoformat(value)
    except ValueError as e:
        raise PlannerInputError(f"{field} is not a real date: {value!r}") from e


def _parse_datetime(value: Any, field: str, tz: ZoneInfo) -> datetime:
    """ISO 8601 datetime -> aware UTC datetime. A missing offset means the preferences time zone."""
    if not isinstance(value, str):
        raise PlannerInputError(f"{field} must be an ISO 8601 datetime string, got {value!r}")
    text = value.strip()
    if text.endswith(("Z", "z")):  # Python 3.10's fromisoformat doesn't accept 'Z'.
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as e:
        raise PlannerInputError(
            f"{field} is not an ISO 8601 datetime: {value!r} (expected e.g. 2026-10-09T09:00:00+05:30)"
        ) from e
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(timezone.utc)


def _parse_event(event: Any, index: int, tz: ZoneInfo) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise PlannerInputError(f"events[{index}] must be an object with 'start' and 'end'")
    title = event.get("title") or f"event #{index + 1}"
    where = f"events[{index}] ({_quote(title)})"
    for key in ("start", "end"):
        if key not in event:
            raise PlannerInputError(f"{where} is missing '{key}'")

    def parse(field: str) -> tuple[datetime, bool]:
        value = event[field]
        if isinstance(value, str) and _DATE.match(value):
            d = _parse_date(value, f"{where}.{field}")
            return datetime(d.year, d.month, d.day, tzinfo=tz).astimezone(timezone.utc), True
        return _parse_datetime(value, f"{where}.{field}", tz), False

    start, start_is_date = parse("start")
    end, end_is_date = parse("end")
    if end <= start:
        raise PlannerInputError(
            f"{where}: end {event['end']!r} must be after start {event['start']!r}"
            + (" (all-day events end on the next day, exclusive)" if end_is_date else "")
        )
    busy = event.get("busy", True)
    if not isinstance(busy, bool):
        raise PlannerInputError(f"{where}.busy must be true or false, got {busy!r}")
    return {"start": start, "end": end, "busy": busy, "title": title, "all_day": start_is_date and end_is_date}


# --- Interval helpers --------------------------------------------------------


def _merge(intervals: list[Interval]) -> list[Interval]:
    """Sort and merge overlapping or touching intervals."""
    merged: list[Interval] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _gaps(win_start: datetime, win_end: datetime, busy: list[Interval]) -> list[Interval]:
    """The window minus `busy` (which must be merged, sorted and inside the window)."""
    gaps: list[Interval] = []
    cursor = win_start
    for start, end in busy:
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < win_end:
        gaps.append((cursor, win_end))
    return gaps


def _at(day: Date, hhmm: str, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, parse_hhmm(hhmm), tzinfo=tz).astimezone(timezone.utc)


def _round_up_5(dt: datetime) -> datetime:
    """Round up to the next whole 5 minutes on the local clock (already-round times stay put)."""
    floored = dt.replace(minute=dt.minute - dt.minute % 5, second=0, microsecond=0)
    return floored if floored == dt else floored + timedelta(minutes=5)


def _minutes(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 60)


def _iso(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).isoformat()


def _skipped(start: datetime, end: datetime, reason: str, tz: ZoneInfo) -> dict[str, str]:
    return {"start": _iso(start, tz), "end": _iso(end, tz), "reason": reason}


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _quote(text: str) -> str:
    return f'"{text}"'
