# 03 — Phase 3 Spec: end-to-end "plan my day" across both servers

Status: **Draft — open questions in §10**
Date: 2026-10-08
Owner: Sandipan
Parent: [00-goal.md](00-goal.md) · Builds on: [01-phase1-calendar-connect.md](01-phase1-calendar-connect.md),
[02-focus-planner-server.md](02-focus-planner-server.md)

---

## 1. Purpose

Run the whole flow: one request makes Claude read my calendar (Calendar server), plan focus time
(`focus-planner`), and create the blocks (Calendar server). This phase is mostly about **observing two
servers working together**. There is little new code, and only if §10 decides it.

| Covers | From 00-goal |
|---|---|
| Goals | G6 (both servers in one request) |
| Success criterion | S3 |
| Learning outcomes | L1 (one host, two clients, two servers), L2 (who triggers each primitive), L6 (tracing a multi-server run) |

Decisions in force: **D3** (read main, write only to "MCP Test"), **D5** (preferences), and spec 02's
`plan_my_day` steps (show the plan, get a yes, write, read back).

## 2. The flow

```
 You ──► Claude Code (HOST)
   │  /mcp__focus-planner__plan_my_day tomorrow
   │       └─ prompts/get ──────────────► focus-planner   (user-triggered: a PROMPT)
   │                                         returns steps + my preferences
   │
   ├─ list_events (primary, full day) ────► Google Calendar  (model-triggered: TOOL)
   ├─ convert events (busy rules)            ← done by the model, no server involved
   ├─ find_focus_blocks(date, events) ─────► focus-planner   (model-triggered: TOOL)
   ├─ show plan, ask me ◄──── I say yes / no
   ├─ create_event × N (MCP Test, busy) ──► Google Calendar
   └─ list_events (MCP Test) ──────────────► Google Calendar  (read back, E3 lesson)
```

The two servers never talk to each other. Claude Code holds one MCP client per server, and the **model**
moves data between them. That's the composition lesson (00-goal §6): any mistake in the conversion step
is the model's, not a server's.

## 3. Prerequisites and pre-flight checks

| # | Check | Expected |
|---|---|---|
| P1 | Start `claude` from the repo root and run `/mcp`. | Both `claude.ai Google Calendar` and `focus-planner` connected. |
| P2 | Look for leftover `[MCP]` events from Phase 1 (E6.1–E6.3 created several) with `list_events` + `fullText "[MCP]"` on MCP Test **and** on primary. | None, or delete them first so they don't confuse the read-back. |
| P3 | **FOCUS_TIME on a secondary calendar.** Create one `[MCP] focus probe` event on MCP Test with `eventType FOCUS_TIME`, then `get_event` it. | Note what comes back: `eventType focusTime`, silently `default`, or an error. See §10 Q1. |
| P4 | Pick a test day with real events on it (a working day, ideally one with 2+ busy events and a free Task, like Fri Oct 9). | Noted in the run log. |

P3 matters because Google's Calendar API has historically allowed focus-time events only on a user's
**primary** calendar. If that holds here, spec 02 step 6 (`FOCUS_TIME` on MCP Test) can't work as written.
Unverified until P3 runs.

## 4. Runs

Run these in order. Fill in one row per run in §6. **Every write goes to MCP Test only.** If Claude ever
proposes `primary` (or no `calendarId`) for a write, answer **no** and log it.

### R1. Happy path, via the prompt
- Input: `/mcp__focus-planner__plan_my_day` with `date` = the P4 day.
- Expect: steps 1–7 of spec 02 §7 in order. The proposed blocks match what `find_focus_blocks` would give
  for that day's events (cross-check by hand or with the Inspector). After my yes, N events exist on MCP Test
  with the right times, title `[MCP] Focus block`, and the read-back reports them.
- Observe: the `list_events` arguments; how each event was converted (especially `busy` for Tasks and
  declined events); whether Claude passed **every** event, including free ones; the `create_event` arguments.

### R2. Decline at the confirmation step
- Input: same as R1 on another day (or after cleaning up R1), but answer **no**.
- Expect: no `create_event` calls; nothing new on MCP Test.

### R3. Natural language, no prompt
- Input, in a **fresh session**: *"Plan my day tomorrow and block focus time."*
- Prompts are user-triggered, so Claude can't load `plan_my_day` itself. It only has the tool descriptions
  (and can read `planner://preferences` if it chooses).
- Observe: does it find `find_focus_blocks` on its own? Does it read the preferences resource? Which calendar
  does it propose writing to? Does it still ask first? This is the E6.3 guardrail test, now with
  `focus-planner` in the picture. **Answer no** if it targets primary.

### R4. Nothing to plan
- Input: `plan_my_day` for a Saturday, then for a day packed with meetings (or `today` after 18:30).
- Expect: `working_day: false` / no blocks; Claude says so and makes **no** writes.

### R5. Running twice
- Input: R1 again for the same day, after R1's blocks were created.
- Today's design reads only `calendars.read` (primary), so it can't see the blocks on MCP Test and will
  likely propose the **same blocks again**, creating duplicates. Observe what happens and answer **no** at
  the confirmation. See §10 Q2.

## 5. What to look at (L6)

- The Claude Code transcript: each tool call with its server prefix (`mcp__claude_ai_Google_Calendar__…`
  vs `mcp__focus-planner__…`). Expand calls to see full arguments and results.
- `focus-planner`'s stderr log (`claude --debug`, or set `FOCUS_PLANNER_LOG=DEBUG`): one line per
  tool/prompt call with event counts, so you can check it got the number of events `list_events` returned.
- Google Calendar in the browser, as the final truth for what got written.

## 6. Run log

| Run | Input | Tool calls + key args (both servers) | Result | Surprises / notes |
|---|---|---|---|---|
| P3 (2026-10-08) | Probe on MCP Test, Sat Oct 10 10:00–10:30 | 1) `create_event`, `calendarId <MCP Test>`, `eventType FOCUS_TIME`, `notificationLevel NONE` → **error "Request contains an invalid argument."** 2) Control: same call without `eventType` → created (`eventType DEFAULT`, organizer MCP Test). 3) `delete_event` → `cancelled`; `list_events` `fullText "[MCP]"` on MCP Test for October → none | **FOCUS_TIME is rejected on MCP Test**, and only the event type differs between the two calls. Spec 02 step 6 can't work as written. | Fits Google's rule that focus time goes only on a primary calendar, but the error message doesn't say why. Not tried on primary (D3). Side findings: MCP Test has no leftover `[MCP]` events (P2 clean for that calendar). The connector's schema now says to pass `startTime`/`endTime` as **local time with no offset** (it fills in the zone), which differs from what Phase 1 recorded. |
| R1 | | | | |
| R2 | | | | |
| R3 | | | | |
| R4 | | | | |
| R5 | | | | |

## 7. Acceptance criteria (S3)

- [ ] C1. R1: one prompt produces calls to **both** servers in the order of §2, and the proposed blocks equal
      `find_focus_blocks`' output for the real events (no blocks lost, invented or moved by the model).
- [ ] C2. R1: the events Claude passed match `list_events` output: same count, `busy` set by the rules
      (free Tasks are `busy: false`).
- [ ] C3. R1: after a yes, the blocks exist on **MCP Test** with the right times and title, and the read-back
      reports what's really there.
- [ ] C4. R2 and R4: no writes happened.
- [ ] C5. No `[MCP]` event was ever written to primary (check with `list_events` + `fullText "[MCP]"` on primary).
- [ ] C6. R3 and R5 are logged, with their findings written up in §6, pass or fail. (They're observations,
      not pass/fail gates, unless §10 decides to fix them.)

## 8. Risks and cleanup

- **Writing to primary.** Mitigation: `plan_my_day` hard-codes the MCP Test ID; I check every proposed write
  and say no to anything else; C5 checks afterwards.
- **FOCUS_TIME rejected on MCP Test.** Mitigation: P3 finds out before any real run; §10 Q1 picks the fallback.
- **Duplicates on re-runs.** Mitigation: R5 is observe-only and answered no; §10 Q2.
- **The model mis-converts events** (e.g. treats a free Task as busy, drops an all-day event). Mitigation:
  C2 compares event counts and `busy` flags against the raw `list_events` output.
- **Cleanup:** at the end, delete all `[MCP]` events on MCP Test (`list_events` + `fullText "[MCP]"`, then
  `delete_event`, then read back). Keep the MCP Test calendar.

## 9. Notes to carry into `docs/learning-notes.md` (S4)

- **L1:** one host, two clients, two servers, and the model as the only thing that connects them.
- **L2:** who triggers each primitive: prompt = me (slash command), tools = the model, resource = the app or
  the model when asked. R1 vs R3 shows the difference.
- **L6:** how the run looked from the transcript, the stderr log and Google Calendar, and what none of them showed.

## 10. Open questions

- **Q1. If P3 shows FOCUS_TIME doesn't work on MCP Test**, which fallback?
  (a) Create normal events on MCP Test titled `[MCP] Focus block`, with `availability` busy. Keeps D3.
  (b) Create real FOCUS_TIME events on primary. Breaks D3, so it needs a new decision.
  **Resolved 2026-10-08: (a).** P3 showed FOCUS_TIME is rejected. Step 6 of `plan_my_day` now creates
  normal events with `availability AVAILABILITY_BUSY` and no `eventType` (spec 02 §7 updated).
- **Q2. Duplicates on re-run (R5).** Options:
  (a) Change `plan_my_day` to also `list_events` on `calendars.write` and pass those events as busy, so
      existing blocks count as taken. Small prompt change, no server change.
  (b) Add `already_planned` handling to `find_focus_blocks`. Server change; overkill for one user.
  (c) Accept it and rely on the confirmation step.
  *Recommendation: (a)*, after R5 confirms the problem.
- **Q3. Should R3's guardrail gap be closed?** If R3 targets primary, options are a project `CLAUDE.md`
  note with D3 and the MCP Test ID, or stronger wording in the `find_focus_blocks` description.
  *Recommendation: decide after R3; a `CLAUDE.md` note is the cheapest.*

## 11. Out of scope

- Planning several days at once, or recurring focus blocks.
- Moving or deleting existing meetings to make room.
- A self-hosted Calendar server (optional Phase 1b in spec 01).
- HTTP transport / remote hosting for `focus-planner`.
