"""Load and validate config/preferences.json (spec 02 §5)."""

from __future__ import annotations

import json
import os
import re
from datetime import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Repo root is three levels up from src/focus_planner/preferences.py.
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "preferences.json"

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")  # index == date.weekday()

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

FIELDS = (
    "timezone",
    "working_days",
    "working_hours",
    "lunch",
    "focus_block_minutes",
    "min_focus_minutes",
    "buffer_minutes",
    "max_focus_blocks_per_day",
    "no_meeting_days",
    "calendars",
    "focus_event_title",
)


class PreferencesError(ValueError):
    """The preferences file is missing or invalid."""


def preferences_path() -> Path:
    """The file to read; FOCUS_PLANNER_PREFERENCES overrides the default."""
    return Path(os.environ.get("FOCUS_PLANNER_PREFERENCES", DEFAULT_PATH))


def load_preferences(path: Path | None = None) -> dict[str, Any]:
    """Read the preferences file fresh on every call, so edits apply without a restart.

    Every field in spec §5 is required and checked; errors name the file and the bad field.
    """
    path = path or preferences_path()
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError as e:
        raise PreferencesError(f"Preferences file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise PreferencesError(f"Preferences file is not valid JSON: {path}: {e}") from e
    try:
        return validate_preferences(raw)
    except PreferencesError as e:
        raise PreferencesError(f"Invalid preferences file {path}: {e}") from e


def parse_hhmm(value: str) -> time:
    """'09:30' -> time(9, 30). Assumes the value already passed validation."""
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def validate_preferences(prefs: Any) -> dict[str, Any]:
    """Check every field in spec §5. Raises PreferencesError naming the first bad field."""
    if not isinstance(prefs, dict):
        raise PreferencesError("top level must be a JSON object")

    missing = [f for f in FIELDS if f not in prefs]
    if missing:
        raise PreferencesError(f"missing field '{missing[0]}'")
    unknown = sorted(set(prefs) - set(FIELDS))
    if unknown:
        raise PreferencesError(f"unknown field '{unknown[0]}' (typo?)")

    tz = prefs["timezone"]
    if not isinstance(tz, str) or not tz:
        raise PreferencesError("field 'timezone': expected an IANA time zone name like 'Asia/Kolkata'")
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise PreferencesError(f"field 'timezone': unknown time zone {tz!r}") from e

    _check_days(prefs, "working_days")
    _check_days(prefs, "no_meeting_days")
    _check_time_range(prefs, "working_hours")
    _check_time_range(prefs, "lunch")

    _check_int(prefs, "focus_block_minutes", minimum=15)
    _check_int(prefs, "min_focus_minutes", minimum=15)
    _check_int(prefs, "buffer_minutes", minimum=0)
    _check_int(prefs, "max_focus_blocks_per_day", minimum=1)
    if prefs["min_focus_minutes"] > prefs["focus_block_minutes"]:
        raise PreferencesError(
            "field 'min_focus_minutes': must not be larger than 'focus_block_minutes' "
            f"({prefs['min_focus_minutes']} > {prefs['focus_block_minutes']})"
        )

    calendars = prefs["calendars"]
    if not isinstance(calendars, dict):
        raise PreferencesError("field 'calendars': expected an object with 'read' and 'write'")
    for key in ("read", "write"):
        value = calendars.get(key)
        if not isinstance(value, str) or not value.strip():
            raise PreferencesError(f"field 'calendars.{key}': expected a non-empty calendar ID")

    title = prefs["focus_event_title"]
    if not isinstance(title, str) or not title.strip():
        raise PreferencesError("field 'focus_event_title': expected a non-empty string")

    return prefs


def _check_days(prefs: dict[str, Any], field: str) -> None:
    days = prefs[field]
    if not isinstance(days, list):
        raise PreferencesError(f"field '{field}': expected a list of day names like ['Mon', 'Tue']")
    for day in days:
        if day not in DAY_NAMES:
            raise PreferencesError(f"field '{field}': {day!r} is not one of {', '.join(DAY_NAMES)}")
    if len(set(days)) != len(days):
        raise PreferencesError(f"field '{field}': has a day listed twice")


def _check_time_range(prefs: dict[str, Any], field: str) -> None:
    value = prefs[field]
    if not isinstance(value, dict):
        raise PreferencesError(f"field '{field}': expected an object with 'start' and 'end' as HH:MM")
    for key in ("start", "end"):
        hhmm = value.get(key)
        if not isinstance(hhmm, str) or not _HHMM.match(hhmm):
            raise PreferencesError(f"field '{field}.{key}': expected HH:MM (24-hour, e.g. '09:30'), got {hhmm!r}")
    if parse_hhmm(value["start"]) >= parse_hhmm(value["end"]):
        raise PreferencesError(f"field '{field}': start {value['start']} must be before end {value['end']}")


def _check_int(prefs: dict[str, Any], field: str, minimum: int) -> None:
    value = prefs[field]
    # bool is a subclass of int; reject it explicitly.
    if not isinstance(value, int) or isinstance(value, bool):
        raise PreferencesError(f"field '{field}': expected a whole number, got {value!r}")
    if value < minimum:
        raise PreferencesError(f"field '{field}': must be at least {minimum}, got {value}")
