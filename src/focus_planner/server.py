"""MCP wiring for focus-planner: one tool, one resource, one prompt (spec 02 §5-7).

Kept thin on purpose: the logic lives in planner.py and preferences.py.
"""

from __future__ import annotations

import json
import logging
import os
import sys

from mcp.server.mcpserver import MCPServer

from focus_planner.preferences import load_preferences

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
    return json.dumps(load_preferences(), indent=2)


@server.tool()
def find_focus_blocks(date: str) -> str:
    """Placeholder. The real input schema (spec §6) comes in the implementation step."""
    log.info("tool call: find_focus_blocks date=%s (stub)", date)
    return "find_focus_blocks is not implemented yet."


@server.prompt()
def plan_my_day(date: str = "today") -> str:
    """Placeholder. The real workflow text (spec §7) comes in the implementation step."""
    log.info("prompt get: plan_my_day date=%s (stub)", date)
    return f"(stub) Plan my day for {date}."


def run() -> None:
    log.info("starting focus-planner over stdio")
    server.run("stdio")
