# Sample packs: natural data and the remaining packs

> **Status: done (2026-10-31), PR #70, #71, #73.** P0 in PR #70; P1–P4 and the concurrency fixes in PR #71; P5 (all seven Large packs as permanent development data, and one-pack removal) in PR #73. Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/sample-pack-realism.md`.

## Outcome

Every sample pack produces data that looks like a real organization after a year of use: skewed statuses, long-tailed amounts, clustered dates, uneven workload and links, and small human mistakes. Seven packs exist: Harbor, School, Clinic, Nonprofit, Local government, FMCG distributor and Manufacturer, each populated once at Large into its `sample-<pack>` organization in the development database. Shared helpers live in `backend/operations/sample/`; each pack's weights, seasons, holidays, dashboards and Kanban stages live in its own `realism.py` and data files. `seed_sample_data.py remove --organization <pack>` removes and repopulates one pack. API smoke runs use disposable stacks only. No new routes, bulk endpoints or schema changes; no OpenComms population.

## Phases

P0 make the base current and run Harbor and School Small live (PR #70); P1 shared realism module, offline checks and one administrator per pack organization; P2 R1–R5, R8 and R9 for Harbor and School; P3 R6 and R7 for Harbor and School; P4 the five new packs (PR #71); P5 the Large runs, one at a time, with a backup after each (PR #73).

## Rules

All rules use the run's seed, so a run stays reproducible. Pinned business cases (records below index 10) keep their values.

### R1. Statuses and choices are skewed

Most records sit in the module's normal end state (60–75%); the other statuses form a long tail.

### R2. Amounts have a long tail

Log-normal amounts around a per-module median, with round numbers, cents and 1–2% outliers.

### R3. Dates and times cluster

Weekdays hold at least 85% of records; Mondays and month-end are denser; pack holidays have gaps; each module has seasons; entry times cluster at 9–11 and 14–16.

### R4. Workload follows a Pareto shape

In each department, one or two people write 40% or more of the records.

### R5. Links are uneven

5–10% of parents have no children, and a few have many.

### R6. Text has dirt that the server accepts

Extra spaces, ALL CAPS, mixed abbreviations, near-duplicates, "n/a" notes, mixed phone formats. Email and URL values stay valid. Dirt applies from index 10.

### R7. Record states are messy

Quick entries with blanks, old drafts, cancelled-then-recreated pairs, and records owned by a disabled person.

### R8. Each pack writes its own department dashboards

Each department dashboard follows `docs/specs/openview-dashboard.md` with 7 widgets in the Overview shape (four numbers, a monthly trend, workload by owner, open records), including a `sum` or `average` and a `date_series`.

### R9. Boards content grows with the profile and fills every Board tab

Every department board has a Kanban with the department's stages and cards with `start_on` and `due_on`; cards per board are 12, 24 and 60 for Small, Standard and Large. Each board has one or two calendar sources.

## Decisions

| ID | Decision |
| --- | --- |
| Admin | Each pack organization has its own administrator, invited by the operator through Mailpit. The operator stays the owner and an admin member of each pack and partner organization and runs only the operator steps (backups, installation fields, account restore) as a separate `operator` actor (2026-10-28). |
| Layers | Offline plan checks after each change; one disposable stack for live pack runs; the release smoke in a disposable stack with Caddy; permanent Large data in the development stack only. |

## Acceptance criteria

| ID | Criterion | Result |
| --- | --- | --- |
| 1 | In modules with 4 or more statuses, the top status holds 50% or more and at least twice the second. | not recorded separately; the P4 offline realism suite passed for all seven packs |
| 2 | Typed amounts: p99/p50 at least 5 and 5% or more round numbers. | not recorded separately; P4 realism suite passed |
| 3 | Weekdays hold 85% or more on each main business date; holidays are empty or nearly empty. | not recorded separately; P4 realism suite passed |
| 4 | The top two writers hold 40% or more of a department's writes. | not recorded separately; P4 realism suite passed |
| 5 | 5% or more of parents have no children on non-structural one-to-many links. | not recorded separately; P4 realism suite passed |
| 6 | Every dashboard has 6 or more widgets, a `sum` or `average`, and a `date_series`. | not recorded separately; R8 delivered with 7 widgets per dashboard |
| 7 | Every department board has a Kanban with dated cards and one or more calendar sources. | not recorded separately; R9 delivered |
| 8 | The Step 4a preflight passes; a live Small run has no unplanned 4xx. | partly recorded: all seven packs passed a live Small run with no 5xx; 4xx counts not recorded |
| 9 | Pinned business cases and refusals are unchanged in the golden-master comparison. | not recorded |

## Server findings for a later session

Findings from live runs, with their fix and test in the full text.

| # | Finding |
| --- | --- |
| F1 | Measured (C8): `API_WORKERS` sets API processes; production keeps 1. |
| F2 | Measured (4.2): record create and edit read readers and fields once; statement budgets tested. |
| F3 | Open: about 42% of a Small run is outside the API (fixed 2 s job polls, client work). |
| F4 | Fixed (C9): ending all sessions keeps people of other organizations. |
| F5 | Fixed in P0: the release smoke seeds the pack's own organization. |
| F6 | Fixed: Kanban card file downloads get a transfer lease. |
| F7 | Fixed: the MFA-reset control refreshes idle clients. |
| F8 | Fixed: the host-delivery control refreshes before each request (not yet verified by a host-acceptance run). |
| F9 | Fixed: the release smoke registers its administrator as the operator. |
| F10 | Fixed: the Comms structure control reads every page. |
| F11 | Fixed: a stale Comms export refusal step was removed. |
| F12 | Fixed: Comms control evidence accepts planned members and refusals. |
| F13 | Fixed: a Comms purge cleans up exports in its own file slot. |
| F14 | Fixed: token `iat` and `nbf` admit 5 s of clock skew. |
| F15 | Fixed (C3): file requests use a memory budget and processing slots, 503 `files_busy` with `Retry-After: 1`. |
| F16 | Fixed (C7): one invalidation publisher thread per process; a lost update becomes a `resync`. |
| F17 | Fixed (C1): two confirmations by one administrator never deadlock. |
| F18 | Fixed (C2): a short Auth outage keeps the session (503 with `Retry-After`). |
| F19 | Fixed (C4): `TRIGGER_WORKERS` lanes run trigger events, keeping per-record order. |
| F20 | Fixed (C10): rate-limit bucket cleanup uses `SKIP LOCKED`. |
| F21 | Fixed (T3, tooling): session security event readback is bounded by the end of population. |
| F22 | Fixed (T4, tooling): the Chart control check allows a planned archive and restore. |
| F23 | Fixed (C11): a security save that changes the session timeout locks sessions in a fixed order with a normal wait instead of `NOWAIT`, so it waits for held sessions instead of failing. |
| F24 | Fixed (T6, tooling): phases never disable or end sessions of a partner member. |
| F25 | Fixed (C12): idle upstream connections close on the client side first (Caddy `keepalive 3s`, sample client 2 s). |
| — | Withdrawn (C5): scheduled Report attempts that end in `http_409` after a source is archived are the designed Jobs retry flow; no change. |

## Open items

- F3: job polls and client work still take about 42% of a Small run.
- F8 is not verified by a host-acceptance run.
- F23: `lock_policy_users` still refuses a held membership at once, and the local recovery command locks the organization row before sessions, so it can deadlock with a deadline save in the same organization.
- Known limits: pack keys must be Python package names; link rules get no seed or anchor date; the realism date check reads Date fields only; generic writer weights are not Pareto, so writer teams stay at four people or fewer.
