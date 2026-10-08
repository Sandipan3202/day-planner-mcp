"""MCP wiring for focus-planner: one tool, one resource, one prompt (spec 02 §5-7).

Kept thin on purpose: the logic lives in planner.py and preferences.py.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from pydantic import BaseModel, Field

from focus_planner import planner
from focus_planner.preferences import PreferencesError, load_preferences

# stdout is the protocol channel, so all logs go to stderr.
logging.basicConfig(
    stream=sys.stderr,
    level=os.environ.get("FOCUS_PLANNER_LOG", "INFO"),
    format="%(asctime)s %(levelname)s focus-planner: %(message)s",
)
log = logging.getLogger("focus_planner")

server = MCPServer(
    name="focus-planner",
    instructions="Plans focus time. Does not access any calendar: pass it events fetched elsewhere.",
)


@server.resource(
    "planner://preferences",
    name="preferences",
    description="My planning settings: working hours, lunch, focus length, buffers, and which calendars to read and write.",
    mime_type="application/json",
)
def preferences_resource() -> str:
    log.info("resource read: planner://preferences")
    try:
        return json.dumps(load_preferences(), indent=2)
    except PreferencesError as e:
        # ResourceError passes the message (file + bad field) to the client; other errors are hidden.
        raise ResourceError(str(e)) from e


class Event(BaseModel):
    """One calendar event, simplified from the Calendar server's list_events output."""

    start: str = Field(
        description="Start: ISO 8601 datetime with offset (start.dateTime), or YYYY-MM-DD for all-day (start.date)."
    )
    end: str = Field(
        description="End: ISO 8601 datetime with offset (end.dateTime), or YYYY-MM-DD for all-day "
        "(end.date, which is exclusive: the next day)."
    )
    busy: bool = Field(
        default=True,
        description='false if transparency == "transparent", or availability == "AVAILABILITY_FREE", '
        "or I declined the event. Otherwise true.",
    )
    title: str | None = Field(default=None, description="The event summary. Only used to explain results.")


class Block(BaseModel):
    start: str
    end: str
    minutes: int


class Skipped(BaseModel):
    start: str
    end: str
    reason: str


class FocusPlan(BaseModel):
    date: str
    timezone: str
    working_day: bool
    no_meeting_day: bool
    blocks: list[Block]
    skipped: list[Skipped]
    notes: list[str]


FIND_FOCUS_BLOCKS_DESCRIPTION = """Find free slots for deep work on one day, from that day's calendar events and my preferences
(planner://preferences: working hours, lunch, focus-block length, buffers, daily cap).
This tool does not read any calendar: fetch the events with the Calendar server first and pass them in.

Convert each event from list_events like this:
- start: start.dateTime (ISO 8601 with offset), or start.date (YYYY-MM-DD) for all-day events.
- end:   end.dateTime, or end.date for all-day events.
- busy:  false if ANY of these hold, otherwise true:
    * transparency == "transparent" (this includes Google Tasks, which show up as FOCUS_TIME events)
    * availability == "AVAILABILITY_FREE"
    * I declined the event (my attendee responseStatus == "declined")
- title: summary.
Pass every event of the day, including free ones (they are reported in notes, not treated as busy).

Returns blocks (ready for create_event), the gaps it skipped and why, and notes.
Times are in the preferences time zone."""


@server.tool(description=FIND_FOCUS_BLOCKS_DESCRIPTION)
def find_focus_blocks(
    date: Annotated[str, Field(description="The day to plan, YYYY-MM-DD, in the preferences time zone.")],
    events: Annotated[
        list[Event], Field(description="All of that day's events, converted as described above. May be [].")
    ],
    min_minutes: Annotated[
        int | None,
        Field(ge=15, description="Overrides min_focus_minutes from preferences for this call. At least 15."),
    ] = None,
    now: Annotated[
        str | None,
        Field(
            description="ISO 8601 datetime. If it falls on `date`, time before it is ignored. "
            "Defaults to the real current time; mainly for testing."
        ),
    ] = None,
) -> FocusPlan:
    started = time.perf_counter()
    try:
        result = planner.find_focus_blocks(
            date=date,
            events=[e.model_dump() for e in events],
            preferences=load_preferences(),
            min_minutes=min_minutes,
            now=now,
        )
    except (planner.PlannerInputError, PreferencesError) as e:
        log.info(
            "tool call: find_focus_blocks date=%s events=%d -> error in %.1f ms",
            date,
            len(events),
            (time.perf_counter() - started) * 1000,
        )
        raise ToolError(str(e)) from e
    log.info(
        "tool call: find_focus_blocks date=%s events=%d -> %d blocks, %d skipped in %.1f ms",
        date,
        len(events),
        len(result["blocks"]),
        len(result["skipped"]),
        (time.perf_counter() - started) * 1000,
    )
    return FocusPlan.model_validate(result)


@server.prompt()
def plan_my_day(date: str = "today") -> str:
    """Placeholder. The real workflow text (spec §7) comes in the implementation step."""
    log.info("prompt get: plan_my_day date=%s (stub)", date)
    return f"(stub) Plan my day for {date}."


def run() -> None:
    log.info("starting focus-planner over stdio")
    server.run("stdio")
