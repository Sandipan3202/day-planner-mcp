"""Load and validate config/preferences.json (spec 02 §5)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Repo root is three levels up from src/focus_planner/preferences.py.
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "preferences.json"


class PreferencesError(ValueError):
    """The preferences file is missing or invalid."""


def preferences_path() -> Path:
    """The file to read; FOCUS_PLANNER_PREFERENCES overrides the default."""
    return Path(os.environ.get("FOCUS_PLANNER_PREFERENCES", DEFAULT_PATH))


def load_preferences(path: Path | None = None) -> dict[str, Any]:
    """Read the preferences file fresh on every call, so edits apply without a restart.

    TODO (implementation step): validate every field from spec §5 and name the
    bad field in the error.
    """
    path = path or preferences_path()
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as e:
        raise PreferencesError(f"Preferences file not found: {path}") from e
    except json.JSONDecodeError as e:
        raise PreferencesError(f"Preferences file is not valid JSON: {path}: {e}") from e
