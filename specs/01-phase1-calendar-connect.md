# 01 — Phase 1 Spec: Connect Claude to Google Calendar over MCP

Status: **Done — exercises E1–E6 complete, acceptance A1–A6 pass (2026-10-07)**
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
         claude.ai connector proxy ("claudeai-proxy", sign-in via /mcp)
            │
            ▼
         Google's Calendar MCP server (MCP SERVER, remote: https://calendarmcp.googleapis.com)
            │
            ▼
         Google Calendar data
```

Things to confirm or correct during this phase:
- Claude Code never calls the Google API itself. It only calls MCP tools.
- The Google OAuth token sits with claude.ai's connector proxy, not on this machine. (Unconfirmed:
  where exactly it's stored and how it's refreshed isn't visible from here.)
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

### Setup results (2026-10-07)

| Calendar | ID | Time zone | Use |
|---|---|---|---|
| Main (primary) | `<primary>` (my Gmail address) | Asia/Kolkata | **Read only** (D3) |
| MCP Test | `beb30fefd017ae45273926ebd94225b07caa9f06e682c801991ef0be02384faa@group.calendar.google.com` | Asia/Kolkata | **All writes** (D3) |
| Holidays in India | `en.indian#holiday@group.v.calendar.google.com` | Asia/Kolkata | Ignored |

Notes:
- Step 5: no tool can create a calendar, so "MCP Test" was created by hand in Google Calendar.
- Gotcha: the first attempt created an *event* ("MCP-3") on the main calendar instead of a *calendar*.
  It was deleted with `delete_event` (returned `status: cancelled`). It's a preview of E5.

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

Recorded 2026-10-07, right after sign-in. Claude Code names them `mcp__claude_ai_Google_Calendar__<tool>`.

| Tool name | Purpose | Required inputs | Notable optional inputs | Read / write |
|---|---|---|---|---|
| `list_calendars` | Calendars I can access, with IDs | none | `pageSize`, `pageToken` | Read |
| `list_events` | Events on one calendar | none | `calendarId`, `startTime`, `endTime`, `fullText`, `eventType`, `orderBy`, `timeZone`, `pageSize`, `pageToken` | Read |
| `search_events` | Semantic search, **primary calendar only** | `query` | `pageSize`, `pageToken` | Read |
| `get_event` | One event by ID | `eventId` | `calendarId` | Read |
| `suggest_time` | Free slots across attendees' calendars | `attendeeEmails`, `startTime`, `endTime` | `durationMinutes`, `preferences` (`startHour`, `endHour`, `excludeWeekends`), `timeZone` | Read |
| `create_event` | Create an event | `summary`, `startTime`, `endTime` | `calendarId`, `timeZone`, `eventType` (incl. `FOCUS_TIME`), `availability`, `attendees`, `recurrenceData`, `notificationLevel` | Write |
| `update_event` | Change an event; unset fields stay as they are | `eventId` | `calendarId`, `startTime`, `endTime`, `summary`, `notificationLevel` | Write |
| `delete_event` | Delete an event | `eventId` | `calendarId`, `notificationLevel` | Write |
| `respond_to_event` | Accept, decline or mark tentative | `eventId`, `responseStatus` | `calendarId`, `responseComment` | Write |

Answers from the schemas (feeds L4):
- **Times** are ISO 8601 strings with an offset (e.g. `2026-04-30T10:00:00+08:00`). A separate
  `timeZone` (IANA name) overrides the offsets. The default is my primary calendar's time zone.
- **Calendar ID:** every per-calendar tool has an optional `calendarId` that **defaults to the
  primary calendar**. So D3 depends on Claude passing the "MCP Test" ID on every write;
  nothing in the server enforces it. E6's guardrail check tests exactly this.
- **There is no tool to create a calendar**, so step 5 uses the manual fallback.
- **Descriptions do steer the model.** For example, `list_events` says time limits "should not
  be specified unless requested by the user" and to use `search_events` for keyword searches
  on the primary calendar. Nothing says "ask before deleting"; that comes from Claude Code, not the server.
- **Relevant to Phase 2/3:**
  - `create_event` supports `eventType: FOCUS_TIME`, a real Google Focus Time block.
  - `suggest_time` already finds free slots, which overlaps with `find_focus_blocks`.
    Spec 02 should say what `focus-planner` adds on top (preferences, no-meeting days, focus length).
  - `search_events` can't search "MCP Test". Finding `[MCP]` events there needs
    `list_events` with `calendarId` + `fullText`.

## 7. Observation log

One row per exercise. "Tool calls" means the name and key arguments. Claude Code shows each
tool call in the transcript; expand it (or use the verbose transcript view) to see the full
arguments and result.

| Exercise | Prompt | Tool call(s) + key args | Result summary | Surprises / notes |
|---|---|---|---|---|
| E1 | What's on my calendar tomorrow? | `list_events` (no `calendarId` → primary), `startTime 2026-10-08T00:00+05:30`, `endTime 2026-10-09T00:00+05:30`, `orderBy startTime` | 2 items: one event plus one Google Task. Matches Google Calendar. | Claude turned "tomorrow" into midnight-to-midnight IST. The Task arrives as `eventType FOCUS_TIME` with `transparency transparent` (doesn't block time). About 15 fields per event came back, 3 were shown. |
| E2 | Summarize my week: how many meetings, and which day is busiest? | One `list_events`, Mon 2026-10-05 → Mon 2026-10-12 (+05:30), `pageSize 100` | 5 items (3 busy events, 2 free Tasks). Busiest day: Fri Oct 9. | "Week" read as Mon–Sun, while the tool default is the next 7 days. "Meeting" isn't in the data, so the model had to define it (busy vs free, attendees). No paging needed. |
| (extra) | Add a 1-hour "travel to SSB" event on Friday | Claude **asked** for the time and calendar first, then `create_event` with `calendarId "primary"`, 09:00–10:00 +05:30, `timeZone Asia/Kolkata` | Created on the main calendar (user's choice: a real event, not a test). | `"primary"` is accepted as a calendar ID even though the schema says "email address", so prompts never need the Gmail address. A request missing details → ask before writing. |
| E3 | Create a 30-minute event '[MCP] test event' tomorrow at 10:00 on my MCP Test calendar. | `create_event`, `calendarId <MCP Test ID>`, `startTime 2026-10-08T10:00+05:30`, `endTime 10:30+05:30`, `timeZone Asia/Kolkata` | Created, id `3c2abqj50g0d9gpr9cs7db5sfg`. The reply's `organizer` is "MCP Test". | No confirmation asked: the prompt gave title, time, length and calendar. Claude mapped the name "MCP Test" to its ID from the earlier `list_calendars` result. The reply's `organizer` field is a quick way to check which calendar an event landed on. **Gotcha:** the first copy disappeared about 41s after creation (most likely removed from the Calendar page). Found with `list_events` plus `get_event` ("not found or has been deleted"), then recreated as id `ed0noajfmhpgploboc8jjhaajk`. A successful write reply doesn't prove the event still exists, so read it back. |
| E4 | Move '[MCP] test event' to 14:00. | 1) `list_events`, `calendarId <MCP Test>`, `fullText "[MCP] test event"` → 1 match. 2) `update_event`, `eventId ed0noajfmhpgploboc8jjhaajk`, `startTime 14:00+05:30`, `endTime 14:30+05:30`, `notificationLevel NONE` | Moved to Thu Oct 8, 14:00–14:30. Same event ID. | Two calls: find, then update. `search_events` couldn't be used (primary calendar only), so `list_events` + `fullText` did the search. Exactly one match, so no need to ask. Both start and end were sent to keep it 30 min, although the schema says start alone keeps the length. |
| E5 | Delete '[MCP] test event'. | `delete_event`, `calendarId <MCP Test>`, `eventId ed0noajfmhpgploboc8jjhaajk`, `notificationLevel NONE`, then read back with `list_events` `fullText "[MCP]"` on MCP Test and on the main calendar | Returned `status: cancelled`. No `[MCP]` events left on either calendar. | No lookup needed: the event ID was already known from E4. No extra confirmation, because the prompt named one specific test event on the test calendar. Delete is a soft "cancelled" status in Google's model, not an error-free disappearance. The read-back confirms it. |
| E6.1 ambiguity | Move my test event to Friday. | `list_events`, `calendarId <MCP Test>`, `fullText "test event"` → **2 matches** (same title, Thu 11:00 and 16:00). Claude **asked** which one. Then `update_event` on `eokotr09ovlembhmcvh89aoi44`, Fri 11:00–11:30 +05:30, `notificationLevel NONE` | The 11:00 one moved to Fri Oct 9, 11:00–11:30. The 16:00 one is unchanged. | Correct behavior: several matches → ask, don't guess. The server does nothing to prevent ambiguity; the IDs are unique but titles aren't, so this is purely the model's job. "To Friday" also had no time, so Claude kept the original time (said so in the question). The search covered MCP Test only, because Claude knows D3 from this session; in a fresh session it might have searched the main calendar. |
| E6.2 conflict | Create a 30-minute event '[MCP] overlap test' tomorrow at 16:15 on my MCP Test calendar. | `create_event`, `calendarId <MCP Test>`, Thu 16:15–16:45 +05:30. No availability check before the call | Created, id `are01mtfmeniaeqj2cil1cod0k`. It overlaps `[MCP] test event` (16:00–16:30) by 15 min. | **The server gave no warning**; the reply has no conflict field. Google allows overlapping events. Claude only noticed because the 16:00 event was already in its context. Without that it would have had to call `list_events` (or `suggest_time`) first. Detecting conflicts is the client's/model's job, which is the core reason `find_focus_blocks` exists in Phase 2. |
| E6.3 guardrail | Create an event '[MCP] guardrail' tomorrow at 11:00. | `create_event`, `calendarId <MCP Test>` (**chosen by Claude**, not by the prompt), Thu 11:00–11:30 +05:30 | Created on MCP Test, id `lc9g19g2kd90q3rsc0bfat2flk`. | No calendar and no length given. Claude picked MCP Test because of the `[MCP]` prefix + D3 from this session, and 30 min to match the earlier tests. Both are **conversation memory, not server rules**. Leaving out `calendarId` would have put it on the **main** calendar (schema default: primary). In a fresh session with no D3 context, that's what you should expect. To make D3 durable, put it somewhere persistent: a CLAUDE.md note, the Phase 2 `plan_my_day` prompt, or the `planner://preferences` resource. |

## 8. Acceptance criteria (S1)

- [x] A1. `/mcp` shows the Google Calendar connector as connected, with its calendar tools listed.
- [x] A2. "What's on my calendar tomorrow?" returns an answer that matches Google Calendar.
- [x] A3. A `[MCP]` event created from Claude Code appears on the **"MCP Test"** calendar at the right time.
- [x] A4. The same event can be moved and then deleted from Claude Code.
- [x] A5. §6 and §7 are filled in.
- [x] A6. No test events were written to the main calendar (check by searching for `[MCP]`).

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
