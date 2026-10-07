# 01 — Phase 1 Spec: Connect Claude to Google Calendar over MCP

Status: **Draft — awaiting review**
Date: 2026-10-07
Owner: Sandipan
Parent: [00-goal.md](00-goal.md)

---

## 1. Purpose

Use an **existing** MCP server, on the consumer side, before building one. This phase is
about watching MCP work and writing down what happens, not about writing code.

| Covers | From 00-goal |
|---|---|
| Goals | G1, G2, G3 |
| Success criterion | S1 |
| Learning outcomes started here | L1 (host/client/server), L2 (tools), L4 (tool schemas), L5 (OAuth, hosted case), L6 (inspecting traffic) |

Decision in force: **D1**. Use the Google Calendar connector built into Claude (claude.ai).
**D3**. Read from the main calendar; write only to the **"MCP Test"** calendar.

## 2. Mental model to check against

```
 You ──► Claude Code (HOST)
            │  contains an MCP CLIENT per server
            ▼
         claude.ai Google Calendar connector (MCP SERVER, remote, hosted by Anthropic)
            │  holds the Google OAuth token
            ▼
         Google Calendar API
```

Things to confirm or correct during this phase:
- Claude Code never calls the Google API itself. It only calls MCP tools.
- The Google OAuth token sits with the hosted connector, not on this machine.
- The transport is remote (HTTP), unlike the local stdio server in Phase 2.

## 3. Prerequisites

- Claude Code running in WSL, logged in with the same claude.ai account that will own the connector.
- A personal Google account with Google Calendar.
- Current state (2026-10-07): the connector already appears in Claude Code as
  `claude.ai Google Calendar`, but it only offers `authenticate` and
  `complete_authentication`. It is **not signed in yet**.

## 4. Setup steps

| # | Step | Expected result |
|---|---|---|
| 1 | In Claude Code, run `/mcp` and find **claude.ai Google Calendar**. | Listed, status shows it needs authentication. |
| 2 | Authenticate, either from `/mcp` or by asking Claude to connect Google Calendar. Finish Google sign-in in the browser and grant calendar access. | Browser shows success; `/mcp` shows the server as connected. |
| 3 | Run `/mcp` again and open the server's tool list. | The real calendar tools appear, replacing `authenticate`. |
| 4 | Record every tool name and its input schema in §6 (Tool inventory). | Table filled in. |
| 5 | Create the **"MCP Test"** calendar. Ask Claude first. If no tool can create calendars, create it by hand in Google Calendar (Settings → Add calendar → Create new calendar). | "MCP Test" is visible in Google Calendar. Note which way worked. |
| 6 | Ask Claude to list my calendars. | Both the main calendar and "MCP Test" are returned, with their IDs. Record the "MCP Test" calendar ID. |

## 5. Exercises

Run these in order. For each one, fill in a row in the observation log (§7).

**Rules for every write:** the target is the **"MCP Test"** calendar only, and event titles
start with `[MCP]` so they're easy to find and clean up.

### E1. Read: today and tomorrow
- Prompt: *"What's on my calendar tomorrow?"*
- Expect: a correct list that matches Google Calendar for that day.
- Observe: which tool was called; how "tomorrow" was turned into a time range; which time zone was
  used; whether all-day events and declined events show up.

### E2. Read: this week
- Prompt: *"Summarize my week: how many meetings, and which day is busiest?"*
- Observe: one call over a date range, or several calls? Any paging? How much raw data came back
  compared with what Claude showed you?

### E3. Create
- Prompt: *"Create a 30-minute event '[MCP] test event' tomorrow at 10:00 on my MCP Test calendar."*
- Expect: the event appears in Google Calendar on "MCP Test", at the right local time.
- Observe: the exact arguments (calendar ID, start/end format, time zone field). Did Claude ask
  before writing, or just do it?

### E4. Move
- Prompt: *"Move '[MCP] test event' to 14:00."*
- Observe: how Claude found the event (a search, or a list then pick by title?), and that it
  used the event's ID in the update call.

### E5. Delete
- Prompt: *"Delete '[MCP] test event'."*
- Expect: gone from Google Calendar.
- Observe: whether Claude confirmed first; what the tool returned.

### E6. Edge cases (short)
- Ambiguous request: *"Move my test event to Friday"* when two `[MCP]` events exist. Does Claude ask which one?
- Conflict: create an `[MCP]` event that overlaps an existing one. Does anything warn about it?
- Guardrail check: ask it to create an event without naming a calendar. Where does it go?
  (This tells you how much of D3 the spec for Phase 2/3 must enforce in prompts.)

## 6. Tool inventory (fill in after step 3)

| Tool name | Purpose | Required inputs | Optional inputs | Read / write |
|---|---|---|---|---|
| | | | | |

Questions to answer from the schemas (feeds L4):
- How are times represented: RFC 3339 strings, separate date and time, time zone field?
- Which tool takes a calendar ID, and what is the default when none is given?
- Do the tool descriptions tell the model anything that changes its behavior (e.g. "ask before deleting")?

## 7. Observation log

One row per exercise. "Tool calls" means the name and key arguments. Claude Code shows each
tool call in the transcript; expand it (or use the verbose transcript view) to see the full
arguments and result.

| Exercise | Prompt | Tool call(s) + key args | Result summary | Surprises / notes |
|---|---|---|---|---|
| E1 | | | | |
| E2 | | | | |
| E3 | | | | |
| E4 | | | | |
| E5 | | | | |
| E6 | | | | |

## 8. Acceptance criteria (S1)

- [ ] A1. `/mcp` shows the Google Calendar connector as connected, with its calendar tools listed.
- [ ] A2. "What's on my calendar tomorrow?" returns an answer that matches Google Calendar.
- [ ] A3. A `[MCP]` event created from Claude Code appears on the **"MCP Test"** calendar at the right time.
- [ ] A4. The same event can be moved and then deleted from Claude Code.
- [ ] A5. §6 and §7 are filled in.
- [ ] A6. No test events were written to the main calendar (check by searching for `[MCP]`).

## 9. Notes to carry into `docs/learning-notes.md`

After this phase, write first drafts for:
- **L1:** who the host, client and server were in this setup.
- **L2/L4:** what the tool list and schemas looked like, and one example where a schema clearly
  shaped what Claude did.
- **L5 (hosted case):** what you saw of OAuth (the browser sign-in) and what you *didn't* see
  (token storage, refresh). That gap is the reason for the optional Phase 1b.
- **L6:** where you could see MCP traffic (transcript tool calls, `/mcp`) and what stayed hidden.

## 10. Optional Phase 1b: self-hosted Calendar server (later)

Out of scope for this spec. Only do it after A1–A6 pass. Outline:
1. Pick an open-source Google Calendar MCP server (stdio).
2. Create a Google Cloud project, enable the Calendar API, configure the OAuth consent screen,
   create a Desktop OAuth client.
3. Store the client secret and token files outside git (the `.gitignore` already covers
   `credentials*.json`, `token*.json` and `.env`).
4. Register it in Claude Code with `claude mcp add`, and repeat E1–E5.
5. Compare it with the hosted connector: where the token lives, what the consent screen showed,
   how the tools differ.

This would get its own spec (`01b-self-hosted-calendar.md`) if pursued.

## 11. Risks and cleanup

- **Writing to the wrong calendar.** Mitigation: name "MCP Test" in every write prompt; A6 checks it.
- **Time zone drift** (WSL, Google and Claude disagreeing). Mitigation: E1 and E3 record the time zone used.
- **Connector tools differ from what this spec assumes.** Mitigation: step 5 has a manual
  fallback; §6 records what really exists, and Phase 3 relies on that record.
- **Cleanup:** at the end, delete any leftover `[MCP]` events. Keep the "MCP Test" calendar for Phase 3.
