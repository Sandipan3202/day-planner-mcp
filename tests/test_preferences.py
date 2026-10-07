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
