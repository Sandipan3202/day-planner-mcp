# 00 — Goal Spec: Day Planner over MCP

Status: **Approved — open questions resolved**
Date: 2026-10-07
Owner: Sandipan

---

## 1. Why this project exists

The real goal is **learning MCP (Model Context Protocol) end to end**. The Day Planner product is
the vehicle: small enough to finish, real enough to exercise every major MCP concept.

## 2. One-line product

Claude reads and manages my Google Calendar through an existing MCP server, then uses
**my own MCP server ("focus-planner")** alongside it to find and protect focus time.

## 3. Goals

### Phase 1: Use an existing MCP server (consumer side)
- G1. Connect Claude to my Google Calendar through an available Google Calendar MCP server.
- G2. Using plain-language prompts, list today's/this week's events, create an event, and move or delete one.
- G3. Understand what happened under the hood: which **tools** the server exposed, what
  arguments Claude sent, what came back, and how auth (OAuth) was handled.

### Phase 2: Build my own MCP server (producer side)
- G4. Build a local MCP server, `focus-planner`, from scratch using an official MCP SDK.
- G5. Expose at least one of each MCP primitive:
  - **Tool**, e.g. `find_focus_blocks(events, min_minutes)` → free slots long enough for deep work
  - **Resource**, e.g. `planner://preferences` → my working hours, focus-block length, no-meeting days
  - **Prompt**, e.g. `plan_my_day` → a reusable template that tells Claude how to plan a day
- G6. Register it in Claude Code next to the Calendar server, so that a single request
  ("plan my day and block focus time") uses **both servers together**.
- G7. Debug and test it with the **MCP Inspector**, not only through Claude.

## 4. Learning outcomes (what I should be able to explain at the end)

- L1. The roles of **host, client and server**, and who talks to whom.
- L2. The three server primitives (**tools, resources, prompts**) and when to use each.
- L3. Transports: **stdio** (local process) vs **Streamable HTTP** (remote), and why Phase 2 starts with stdio.
- L4. How tool schemas (JSON Schema inputs) shape what the model can do.
- L5. How auth works for a remote server (OAuth) compared with a local one (none or env-var secrets).
- L6. How to inspect, log and debug MCP traffic.

## 5. Success criteria (definition of done)

- S1. Phase 1: from Claude Code, I can ask "what's on my calendar tomorrow?" and get a correct answer,
  and create a test event that appears in Google Calendar.
- S2. Phase 2: `focus-planner` runs locally, passes manual checks in the MCP Inspector
  (all tools, resources and prompts listed and callable), and is registered in Claude Code.
- S3. End-to-end: one prompt makes Claude fetch events (Calendar server), compute focus blocks
  (my server), and create those blocks as calendar events (Calendar server).
- S4. A short `docs/learning-notes.md` answers L1–L6 in my own words.

## 6. Non-goals (out of scope for now)

- No web UI or frontend.
- No deployment to the cloud in Phases 1–2. A remote HTTP version could be a later Phase 3.
- No multi-user support; it's just my calendar.
- My server will **not** talk to Google directly. Calendar access stays with the existing server,
  which keeps the two servers' jobs separate and shows how servers are composed.

## 7. Constraints & assumptions

- Dev environment: WSL (Linux) + VS Code + Claude Code.
- Personal Google account. Events are read from my main calendar; created events go on a dedicated "MCP Test" calendar (D3).
- Free tooling only.

## 8. Decisions (resolved 2026-10-07)

- **D1 (was Q1). Calendar MCP server:** start with the Google Calendar **connector built into Claude**
  (hosted, OAuth sign-in, minimal setup). Optionally try a **self-hosted open-source** server
  later (Google Cloud project + OAuth client) for the hands-on auth lessons (L5).
- **D2 (was Q2). Language for Phase 2:** **Python**, using the official MCP Python SDK (FastMCP API).
- **D3 (was Q3). Calendars:** **read** events from my main calendar; **write** all test and
  focus-block events to a dedicated **"MCP Test"** calendar.
- **D4 (was Q4). Version control:** git repo, pushed to a new GitHub repo (like worksheet_project).

## 9. Next specs (after this one is approved)

- `01-phase1-calendar-connect.md`: setup steps, prompts to try, what to observe
- `02-focus-planner-server.md`: tool/resource/prompt contracts, inputs/outputs, edge cases
- `03-integration.md`: the combined end-to-end flow and acceptance tests
