import json
import re
from pathlib import Path

import pytest

from focus_planner.preferences import PreferencesError, load_preferences


def test_committed_preferences_load():
    prefs = load_preferences()
    assert prefs["timezone"] == "Asia/Kolkata"
    assert prefs["calendars"]["read"] == "primary"


def test_missing_file_names_the_path(tmp_path: Path):
    missing = tmp_path / "nope.json"
    with pytest.raises(PreferencesError, match="nope.json"):
        load_preferences(missing)


def _write(tmp_path: Path, **overrides) -> Path:
    prefs = {**load_preferences(), **overrides}
    path = tmp_path / "prefs.json"
    path.write_text(json.dumps(prefs))
    return path


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"timezone": "Mars/Olympus"}, "timezone"),
        ({"working_days": ["Mon", "Funday"]}, "working_days"),
        ({"working_days": "Mon-Fri"}, "working_days"),
        ({"no_meeting_days": ["Wed", "Wed"]}, "no_meeting_days"),
        ({"working_hours": {"start": "9:30", "end": "18:30"}}, "working_hours.start"),
        ({"working_hours": {"start": "18:30", "end": "09:30"}}, "working_hours"),
        ({"lunch": {"start": "12:30"}}, "lunch.end"),
        ({"focus_block_minutes": "120"}, "focus_block_minutes"),
        ({"min_focus_minutes": 10}, "min_focus_minutes"),
        ({"min_focus_minutes": 150}, "min_focus_minutes"),
        ({"buffer_minutes": -5}, "buffer_minutes"),
        ({"max_focus_blocks_per_day": 0}, "max_focus_blocks_per_day"),
        ({"max_focus_blocks_per_day": True}, "max_focus_blocks_per_day"),
        ({"calendars": {"read": "primary"}}, "calendars.write"),
        ({"focus_event_title": "  "}, "focus_event_title"),
        ({"focus_minutes": 90}, "focus_minutes"),  # unknown field (typo)
    ],
)
def test_bad_field_is_named(tmp_path: Path, overrides, field):
    with pytest.raises(PreferencesError, match=f"'{re.escape(field)}'") as exc:
        load_preferences(_write(tmp_path, **overrides))
    assert "prefs.json" in str(exc.value)


def test_missing_field_is_named(tmp_path: Path):
    prefs = load_preferences()
    del prefs["lunch"]
    path = tmp_path / "prefs.json"
    path.write_text(json.dumps(prefs))
    with pytest.raises(PreferencesError, match="missing field 'lunch'"):
        load_preferences(path)
