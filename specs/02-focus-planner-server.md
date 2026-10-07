# 02 — Phase 2 Spec: the `focus-planner` MCP server

Status: **Draft — awaiting review**
Date: 2026-10-07
Owner: Sandipan
Parent: [00-goal.md](00-goal.md) · Builds on: [01-phase1-calendar-connect.md](01-phase1-calendar-connect.md)

---

## 1. Purpose

Build my own MCP server, on the producer side. It plans focus time. It does **not** talk to Google:
Claude fetches events with the Calendar server and passes them to this server.

| Covers | From 00-goal |
|---|---|
| Goals | G4, G5, G6, G7 |
| Success criterion | S2 (S3 is spec 03) |
| Learning outcomes | L2 (primitives), L3 (stdio), L4 (schemas), L6 (Inspector, logging) |

Decision in force: **D2**. Python, using the official MCP Python SDK (FastMCP API).

## 2. What Phase 1 taught us (design inputs)

| Phase 1 finding | What this server does about it |
|---|---|
| The Calendar server does no reasoning: no conflict warnings, no free-time logic. | `find_focus_blocks` computes free time from events + my preferences. |
| `suggest_time` already finds free slots. | We go beyond it: working hours, lunch, buffers, focus length, max blocks per day, no-meeting days. The output is ready for `create_event` with `FOCUS_TIME`. |
| Rules held only while they were in the chat (E6.3). | The calendars to read and write live in `planner://preferences`, and `plan_my_day` puts them into every planning run. |
| Google Tasks arrive as `FOCUS_TIME` events with `transparency: transparent`. | Events marked not busy are ignored when finding free time. |
| A success reply isn't proof (E3). | `plan_my_day` tells Claude to read events back after creating them. |
| Names vs IDs; ask before writing (E4, E6.1). | `plan_my_day` tells Claude to show the plan and get a yes before any write. |

## 3. Architecture

```
 You ──► Claude Code (HOST)
           ├─ MCP client ──► claude.ai Google Calendar (remote, HTTP)   ← reads/writes events
           └─ MCP client ──► focus-planner (LOCAL, stdio)               ← plans; no network
                               ├─ tool:     find_focus_blocks
                               ├─ resource: planner://preferences  (from config/preferences.json)
                               └─ prompt:   plan_my_day
```

- **Transport: stdio.** Claude Code starts the server as a child process. There's no port, no network and no auth (L3).
- **Stateless.** Each call works only from its inputs plus the preferences file. Nothing is stored between calls.
- **The logic is separate from MCP.** The planning code is a pure Python function with no MCP imports, so it can be
  unit-tested without a server. `server.py` is a thin layer that connects it to MCP.

## 4. Tech stack and setup

| Item | Choice | Notes |
|---|---|---|
| Language | Python ≥ 3.10 (machine has 3.14) | |
| MCP SDK | `mcp` package from PyPI (official), FastMCP API | `pip install "mcp[cli]"` adds the `mcp dev` command (launches the Inspector) |
| Env / packaging | `uv` (not installed yet), or `python -m venv` + `pip` | `uv` is free and makes `claude mcp add` commands simpler. Decide in §11. |
| Tests | `pytest` | Unit tests for the planning logic only |
| Inspector | `npx @modelcontextprotocol/inspector` | Node 24 is installed |

**Cost:** everything here is free and runs locally. Nothing in this phase needs a paid service or a billing account.

**Check before coding:** the SDK changes quickly. Before writing code, check the current
`mcp` Python SDK README for the exact import path (`from mcp.server.fastmcp import FastMCP` as of
writing) and the decorator names, and update this spec if they differ.

### Project layout

```
pyproject.toml
config/
  preferences.json          # my settings (committed; no secrets in it)
src/focus_planner/
  __init__.py
  __main__.py               # `python -m focus_planner` → runs the server
  server.py                 # FastMCP wiring: tool, resource, prompt
  planner.py                # pure logic: find_focus_blocks()
  preferences.py            # load + validate preferences.json
tests/
  test_planner.py
.mcp.json                   # project-scoped registration for Claude Code
```

## 5. Resource: `planner://preferences`

**What it is:** my planning settings, read-only, returned as JSON. It's the durable home for rules
that Phase 1 showed don't survive between sessions.

- URI: `planner://preferences`
- MIME type: `application/json`
- Source: `config/preferences.json`, re-read on every request, so edits apply without a restart.
- If the file is missing or invalid: return an MCP error naming the file and the bad field, never made-up defaults.

### Shape (initial values are placeholders; see §11 Q1)

```json
{
  "timezone": "Asia/Kolkata",
  "working_days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
  "working_hours": { "start": "09:30", "end": "18:30" },
  "lunch": { "start": "13:00", "end": "14:00" },
  "focus_block_minutes": 90,
  "min_focus_minutes": 45,
  "buffer_minutes": 10,
  "max_focus_blocks_per_day": 2,
  "no_meeting_days": ["Wed"],
  "calendars": {
    "read": "primary",
    "write": "<MCP Test calendar ID>"
  },
  "focus_event_title": "[MCP] Focus block"
}
```

| Field | Meaning |
|---|---|
| `timezone` | IANA zone for interpreting `HH:MM` settings and formatting output |
| `working_days`, `working_hours` | Focus blocks only go inside these |
| `lunch` | Treated as busy |
| `focus_block_minutes` | Preferred length. Longer gaps are cut into blocks of this size |
| `min_focus_minutes` | Gaps shorter than this (after buffers) are not worth a block |
| `buffer_minutes` | Kept free before and after every busy event |
| `max_focus_blocks_per_day` | Cap, longest blocks first |
| `no_meeting_days` | Reported in the output and in `plan_my_day`, so Claude can mention that meetings shouldn't be booked then. It doesn't change the free-time maths |
| `calendars.read` / `.write` | D3, made durable. `primary` avoids putting my Gmail address in the repo |
| `focus_event_title` | Title for created blocks. The `[MCP]` prefix keeps them easy to find while testing |

## 6. Tool: `find_focus_blocks`

**Purpose:** given one day's events, return the free slots that are good enough for deep work, based on my preferences.

### Input schema

| Param | Type | Required | Description |
|---|---|---|---|
| `date` | string `YYYY-MM-DD` | yes | The day to plan, in the preferences time zone |
| `events` | array of `Event` | yes (may be `[]`) | That day's events from the Calendar server, simplified (below) |
| `min_minutes` | integer ≥ 15 | no | Overrides `min_focus_minutes` for this call |
| `now` | ISO 8601 datetime | no | If on `date`, ignore time before it. Defaults to the real current time. Mainly for tests |

`Event`:

| Field | Type | Required | How Claude maps it from `list_events` output |
|---|---|---|---|
| `start` | ISO 8601 datetime with offset, or `YYYY-MM-DD` for all-day | yes | `start.dateTime`, or `start.date` |
| `end` | same | yes | `end.dateTime`, or `end.date` |
| `busy` | boolean | no, default `true` | `false` if `transparency == "transparent"` or `availability == "AVAILABILITY_FREE"`, or if I declined |
| `title` | string | no | `summary`, only used to explain results |

**Why a simplified `Event` and not Google's raw format** (an L4 decision): a small, clear schema keeps this
server independent of Google, makes the tool easy to test in the Inspector by hand, and the
tool description tells Claude exactly how to convert. The cost is that Claude has to do the conversion correctly,
and spec 03 tests that. The tool description must spell out the `busy` rules above.

### Output

Structured JSON (also returned as text for clients that only show text):

```json
{
  "date": "2026-10-08",
  "timezone": "Asia/Kolkata",
  "working_day": true,
  "no_meeting_day": false,
  "blocks": [
    { "start": "2026-10-08T09:30:00+05:30", "end": "2026-10-08T11:00:00+05:30", "minutes": 90 },
    { "start": "2026-10-08T15:10:00+05:30", "end": "2026-10-08T16:40:00+05:30", "minutes": 90 }
  ],
  "skipped": [
    { "start": "2026-10-08T11:40:00+05:30", "end": "2026-10-08T12:10:00+05:30", "reason": "shorter than 45 min" }
  ],
  "notes": ["1 event ignored: marked free (\"MCP-2\")"]
}
```

### Algorithm

1. Load preferences. If `date` isn't a working day, return `working_day: false`, no blocks, and a note.
2. Window = `working_hours` on `date`. If `now` falls on `date`, the window starts at `max(start, now)`, rounded up to the next 5 minutes.
3. Busy intervals = events with `busy: true` + lunch. All-day busy events block the whole day.
   Times are converted to the preferences time zone. Intervals are clipped to the window, and overlapping ones merged.
4. Grow each busy interval by `buffer_minutes` on both sides, then merge again.
5. Free gaps = window minus busy. Drop gaps shorter than the minimum, recording them in `skipped`.
6. Split each gap into blocks of `focus_block_minutes`. A leftover piece of at least the minimum becomes a shorter block.
7. Keep the `max_focus_blocks_per_day` longest blocks (ties go to the earlier one), then sort by start time.

### Errors

Bad input returns an MCP **tool error** (`isError: true`) with a message the model can act on.
The server must not crash. Cases:
- `date` not a valid date; `start`/`end` not parseable; `end` ≤ `start`
- `min_minutes` < 15
- the preferences file is missing or invalid

### Edge cases to cover in tests

| Case | Expected |
|---|---|
| No events | Working hours minus lunch, split into blocks, capped |
| Weekend / non-working day | `working_day: false`, no blocks |
| Event partly outside working hours | Clipped; only the part inside counts |
| Overlapping events (like E6.2) | Merged into one busy interval |
| Free / transparent event (Google Task) | Ignored; reported in `notes` |
| All-day busy event | No blocks |
| Back-to-back meetings with 10-min gaps | No block in between (the buffers use up the gap) |
| `now` mid-day | Nothing before `now` |
| `now` after working hours | No blocks, with a note |
| Events in another time zone's offset | Converted correctly |
| Gap of exactly `min_minutes` | Included |

## 7. Prompt: `plan_my_day`

**Purpose:** a reusable, user-picked starting point for planning. In Claude Code it shows up as a slash command
(something like `/mcp__focus-planner__plan_my_day`; confirm the exact name in `/mcp`).

| Argument | Required | Default | Meaning |
|---|---|---|---|
| `date` | no | `today` | `today`, `tomorrow`, or `YYYY-MM-DD` |

**It returns a user message** that includes the current preferences (the server reads the file and pastes
the values in, so the rules are always in context, which fixes E6.3) and these steps:

1. Work out the date in the preferences time zone.
2. Call the Calendar server's `list_events` on `calendars.read` for that full day (not paged past what's needed).
3. Convert the events to the `find_focus_blocks` input. Apply the `busy` rules exactly.
4. Call `find_focus_blocks`.
5. Show the proposed blocks (and any notes, e.g. a no-meeting day). **Ask for confirmation. Don't write yet.**
6. On a yes, call `create_event` for each block on **`calendars.write` only** (always pass `calendarId`),
   with `summary` = `focus_event_title`, `eventType: FOCUS_TIME`, and `notificationLevel: NONE`.
7. Read the events back with `list_events` on `calendars.write` and report what actually exists.

Phase 2 tests only that the prompt **renders correctly** (Inspector and slash command). Running the whole flow
from start to finish is spec 03.

## 8. Logging and debugging (L6)

- **Never write to stdout.** stdout carries the JSON-RPC protocol, and any stray `print()` breaks the connection.
- Log to **stderr** with Python `logging` (level from the env var `FOCUS_PLANNER_LOG`, default `INFO`):
  one line per request with the tool, resource or prompt name, the inputs summarized (event count, not contents), duration and result size.
- Debug in three layers, in this order:
  1. `pytest`: the logic, with no MCP involved.
  2. **MCP Inspector**: the server on its own, with no model.
  3. Claude Code: the model using the server.

## 9. Registration in Claude Code (G6)

Use **project scope** so the config lives in the repo as `.mcp.json` and anyone cloning it gets the same setup.
The exact command depends on §11 Q2; the shape is:

```bash
claude mcp add --scope project focus-planner -- <python-or-uv command> -m focus_planner
```

Check: `/mcp` lists `focus-planner` as connected, with **Capabilities: tools, resources, prompts**. Compare this with
the Calendar server, which showed tools only.

## 10. Acceptance criteria (S2)

- [ ] B1. `pytest` passes, with at least one test per edge case in §6.
- [ ] B2. Inspector: the server connects; `tools/list` shows `find_focus_blocks` with the input schema in §6.
- [ ] B3. Inspector: calling `find_focus_blocks` with Phase 1's real Friday Oct 9 events (07:00–08:00, 09:00–10:00,
      a free Task 14:00–17:00, 18:00–19:00) returns blocks that avoid busy time plus buffers and lunch, and lists the Task in `notes`.
- [ ] B4. Inspector: a bad input (e.g. `end` before `start`) returns a tool error, and the server keeps running.
- [ ] B5. Inspector: `resources/list` shows `planner://preferences`, and reading it returns the file's JSON.
- [ ] B6. Inspector: `prompts/list` shows `plan_my_day`; getting it with `date=tomorrow` returns the steps with the preferences filled in.
- [ ] B7. Claude Code: `/mcp` shows `focus-planner` connected with all three capabilities; `.mcp.json` is committed.
- [ ] B8. Claude Code: asking Claude to "find focus blocks for this list of events" calls the tool correctly (no Calendar server needed).
- [ ] B9. Nothing is written to stdout except protocol messages (check: log lines appear only in stderr / the Inspector's log panel).

## 11. Open questions (decide before coding)

- **Q1. My real preferences:** working hours, lunch, focus length, minimum block, buffer, blocks per day, no-meeting days.
- **Q2. Environment tool:** install `uv` (free) or use the built-in `venv` + `pip`?
- **Q3. Write calendar ID in `preferences.json`:** commit the MCP Test ID (it reveals nothing personal and it's already
  in spec 01), or keep the file git-ignored with a committed `preferences.example.json`?

## 12. Out of scope (for this phase)

- Any Google API access or OAuth in this server.
- HTTP transport or remote hosting (possible Phase 3, which would need a cost check first).
- Tools that change preferences (edit the JSON file by hand).
- Planning more than one day per call.
- The end-to-end "plan my day and create the blocks" run: that's spec 03.
