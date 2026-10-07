"""Pure planning logic for find_focus_blocks (spec 02 §6).

No MCP imports here, so this can be unit-tested on its own.
"""

from __future__ import annotations

from typing import Any


def find_focus_blocks(
    date: str,
    events: list[dict[str, Any]],
    preferences: dict[str, Any],
    min_minutes: int | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Return focus blocks for one day.

    TODO (implementation step): the algorithm in spec §6, steps 1-7.
    """
    raise NotImplementedError("find_focus_blocks is not implemented yet")
