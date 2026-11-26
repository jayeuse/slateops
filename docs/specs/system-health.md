# System health for the people who use Slate Operations

> **Status: done (2026-11-05), PR #87, #88, #89.** S1 to S6 and the still-page relayout (D23 to D34) are built. Client side only; the developer side is [Deferred](#deferred). Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/system-health.md`.

## Outcome

Every signed-in person opens **Manage → System health** (`/manage?view=health`) and reads whether Slate Operations works now, its version, and how to report a failure. Each role sees only the signals of its scope. When the server does not answer, the app shell shows its own banner. Main code: `backend/app/systems/manage/health/`, `frontend/src/components/systems/manage/components/system-health.tsx`, `frontend/src/components/systems/manage/domain/health-rules.ts`, `frontend/src/components/ui/error-reference.tsx`, `frontend/src/components/server-connection-banner.tsx`, `frontend/src/lib/server-connection.ts`.

## Rules

- **R1. Plain parts, not services.** The parts are "Saving and loading your data" (database), "Signing in" (auth), "Files and pictures" (storage) and "Email" (smtp), always in this order. No service name, host, port, SQL or stack trace shows anywhere.
- **R2. Status words, with an icon and the word.** Working, Not working, Not set up, Set up, and Slow (from S5). Never color alone.
- **R3. One headline sentence.** It answers "does Slate Operations work for me?" first, for example "Email is not working. Everything else works.", with the check time "Checked at 10:42".
- **R4. Scope never widens through this page.** Installation-wide figures go to the installation owner only. The readiness parts are shared by every organization, so everyone sees them.
- **R5. Every error message carries a reference.** "Reference 4f9c2e1a" (the last 8 characters of `request_id`) with a Copy button that copies the full ID, and a sentence on what to do with it (D6). Exception: a sign-in refused for wrong credentials (S1-C7).
- **R6. No raw diagnostics for non-owners.** Sentences and status words only; no graphs for anyone.

## Slices

| Slice | Delivers | PR |
|---|---|---|
| S1 Error references | `request_id` in every error JSON body; a reference in every error message and toast. | #87 |
| S2 Status now | `GET /api/system/status`, the System health page (blocks 1, 2, 5, 6), the Manage tab for everyone, the shell banner. | #87 |
| S3 Organization block | Block 3 for organization admins: backups, failed jobs, sign-in activity. | #88 |
| S4 Personal history | Own sign-in history in Settings → Sessions; record history for every reader, readable fields only. | #88 |
| S5 History and installation | Samples every minute (kept 30 days), the Slow word, the 30-day timeline, email send results, file storage, block 4. | #89 |
| S6 Diagnostics export | A JSON support file for the owner and for organization admins; the server error log. | #89 |

The page blocks: 1 headline (the band), 2 Parts of Slate Operations with Last 30 days, 3 Your organization (admins), 4 Installation (owner), 5 About this system, 6 When something goes wrong.

## Decisions

| ID | Decision |
|---|---|
| Owner, 2026-11-02 | Admins see backup freshness only (word, time, result). Plan usage is dropped. |
| Owner, 2026-11-03 | Backups are late after the last due time plus 1 hour with no success. Block 3 is for organization admins only. Samples every minute, kept 30 days. No host disk figure. |
| DQ1 | Failed password sign-ins are attributed to the account (`subject_id` on `identity.sign_in_failure`); every attempt on an existing account writes its own event. |
| DQ2 | Readers get live, non-redacted fields only. |
| DQ3 | No index for the 8-character reference search (RLS blocks an expression index on `right()`). |
| J1 | Recovery requests record only an Auth 5xx as an email failure; successes come from invitations. |
| J2 | A diagnostics download writes no security event. |
| D5, D12, D21, D34 | Criteria maps: which design item covers which criterion. |
| D6 | Reference wording by role (D6-C1): members and guests "Give this reference to your administrator."; a non-owner admin "Give this reference to the person who runs your server."; the installation owner gets no second sentence. Block 6 follows the same rule. |
| D7 | Audit and Security events find an entry by the 8-character reference or the full ID (D7-C1). |
| D8 | Block 3 "Your organization": rows Backups, Failed jobs, Sign-in activity, File storage, from the same status request. |
| D9 | Your sign-in history: an `ol` under the active sessions in Settings, 10 rows, then "Show older" adds 10. D9.2: each row has an icon, a sentence ("Signed in", "Sign-in failed", "Session ended" and others) and a meta line "{device} · {address} · {time}". |
| D10 | Record history for readers: the History tab shows to everyone who can open the record; hidden fields and entries that only change them are left out. |
| D11, D20 | Contract values; D11 item 1 was not adopted. |
| D13, D22, D35 | Review answers, folded into the rules here. |
| D14 | Slow: icon `CircleGauge`, warn color; Not working always wins; Email is never Slow. The headline has up to three sentences: Not working, Slow, Not set up. |
| D15 | The last 30 days: inside block 2, one sentence per period ("Email did not work for 12 minutes on Tuesday."), 5 rows, then "Show older". Empty: "No problems in the last 30 days." |
| D16 | Email after S5: Working after a recent good send, Not working after failures, else Set up. |
| D17 | File storage in block 3: "Files use 1.2 GB" (decimal units). |
| D18 | Block 4 "Installation" (owner only): database size and each worker as Running, "Not seen since …" or "Not seen yet". |
| D19 | The support file: block 6 gains a paragraph and "Download support file" for admins and the owner. D19.3: page tab order is Check again, Copy reference, Show older, block 3 links, version link, Download support file. D19.4: a failed download shows its message and reference. |
| D23 | Still-page frame: from 1280px a full-width band (block 1) on top and panes under it that fill the height. The page never scrolls; each pane scrolls alone. |
| D24 | Panes by role: member or guest `parts`, `help`; admin `parts`, `details` (block 3), `help`; owner `parts`, `details` (blocks 3, 4), `help` (`data-health-pane`). |
| D25 | What scrolls: each pane alone; the band, page header and shell never scroll. Last 30 days has no scroller of its own. |
| D26 | The band: from 1280px the check line sits on the headline's row. |
| D27 | Label columns by card width (container query): 12rem, 7.5rem or stacked; block 5 takes 6rem from 1280px. |
| D28, D29 | Measured heights: no panel scroll at rest at 1440 × 900. |
| D30 | Below 1280px: one column, the page scrolls, cards fill the width; only the block 6 text keeps `max-w-2xl`. |
| D31 | Order: the DOM order stays blocks 1 to 6; no CSS `order`; panes have no `tabindex`. |
| D32 | States: an Alert or the server banner shortens the panes; the page does not start to scroll. |
| D33 | Older tests: only the Backups separator test changed. |

## Acceptance criteria

Result rule: "met" only where a merged test names the ID. All slices merged (PR #87 to #89).

| ID | Criterion | Result |
|---|---|---|
| S1-C1 | Every error JSON body has `request_id` equal to `X-Request-ID`. | not recorded |
| S1-C2 | Success bodies do not change. | not recorded |
| S1-C3 | `ApiError` keeps the ID: from the body, else the header. | met |
| S1-C4 | Each API error message and toast shows the reference, Copy and the R5 sentence. | met |
| S1-C5 | A failure with no response shows no reference. | met |
| S1-C6 | No stack trace, SQL, service name, host or port in a message. | met |
| S1-C7 | Wrong credentials show "Wrong email, username or password." with no reference. | not recorded |
| S2-C1 | The status read answers every member of the bound organization; no session gives 401. | not recorded |
| S2-C2 | One readiness probe per 30 seconds per process. | not recorded |
| S2-C3 | Email never reads Working. Superseded by S5-C5. | superseded |
| S2-C4 | No service names, hosts, ports or other organizations' data. | not recorded |
| S2-C5 | The System health tab shows for every role; Organization stays the default tab. | met |
| S2-C6 | Page order, no curtain, refresh every 60 seconds and on focus. | met |
| S2-C7 | The shell banner (D3) shows on a failure with no response and clears on the next response. | met |
| S2-C8 | `/api/health` and `/api/ready` do not change. | not recorded |
| S2-C9 | No horizontal scroll at 1440 and 390; keyboard works; words, not color. | met |
| S2-C10 | A status read writes no audit row or security event. | not recorded |
| S3-C1 | Admins get the `organization` part; others get null, never 403. | not recorded |
| S3-C2 | Backup state, last success and last result; no sizes, paths or codes. | not recorded |
| S3-C3 | Failed jobs in 7 days, kinds the admin sees. | not recorded |
| S3-C4 | Failed sign-ins and lockouts in 7 days, own organization. | not recorded |
| S3-C5 | Block 3 for admins only, with its links; no extra request. | met |
| S3-C6 | The organization part writes nothing. | not recorded |
| S4-C1 | Own sign-in history only, newest first, paged. | not recorded |
| S4-C2 | "Your sign-in history" in Settings → Sessions. | met |
| S4-C3 | Record history for anyone who can open the record. | not recorded |
| S4-C4 | A reader sees only readable fields. | met |
| S4-C5 | The history panel shows to everyone who can open the record. | met |
| S4-C6 | Audit detail, export and security events stay admin-only. | not recorded |
| D6-C1 | The reference sentence follows D6. | met |
| D7-C1 | Search by the 8-character reference or the full ID. | met |
| S5-C1 | One sample a minute per installation; no organization column. | not recorded |
| S5-C2 | Samples older than 30 days are deleted daily. | not recorded |
| S5-C3 | Everyone sees the 30-day timeline (D15). | met |
| S5-C4 | Slow after 3 samples over 1 second; Not working wins. | met |
| S5-C5 | Email follows real send results. | met |
| S5-C6 | Worker heartbeats and database size, owner only. | met |
| S5-C7 | Admins see file storage and "Storage limit: not set yet". | met |
| S5-C8 | Sampler, heartbeats and email outcomes write no audit rows. | not recorded |
| S6-C1 | Each 5xx is stored 30 days with ID, status, route and organization; no personal data. | met |
| S6-C2 | The owner downloads the installation file. | met |
| S6-C3 | An admin downloads their organization's file only. | met |
| S6-C4 | Members and guests cannot download. | met |
| SP-C1 | At 1280 × 720, 1440 × 900 and 1920 × 1080 the document and section do not scroll. | met |
| SP-C2 | Band and panes align with the section edges. | met |
| SP-C3 | The last card reaches the pane bottom. | met |
| SP-C4 | Panes match D24. | met |
| SP-C5 | No pane scrolls at 1440 × 900 with the longest backup line. | met |
| SP-C6 | "Show older" scrolls only the `parts` pane. | met |
| SP-C7 | SP-C1 holds with the banner or the block 1 Alert. | met |
| SP-C8 | No pane scrolls sideways. | met |
| SP-C9 | Label columns match D27. | met |
| SP-C10 | The check line shares the headline row; band under 72px. | met |
| SP-C11 | At 1024 × 768 and 390 × 844 one column; the document scrolls. | met |
| SP-C12 | Tab order equals D19.3; no pane `tabindex`. | met |
| SP-C13 | SP-C1 and SP-C2 hold in every look, light and dark. | met |

## API contract (S1, S2)

### S1: `request_id` in every error JSON body

Body: `{"detail": <unchanged>, "request_id": "<uuid7>"}`. Helper `error_content` in `backend/app/core/middleware/request_context.py`, plus two handlers in `main.py`.

### S2: `GET /api/system/status`

Any member of the bound organization (`get_current_user`). Response `{parts, version, checked_at, organization, installation}`; part keys `data`, `signing_in`, `files`, `email`. A 30-second per-process cache. `organization` is for admins (S3), `installation` for the owner (S5).

## API contract (S3, S4)

- S4: `GET /api/auth/sign-in-events` lists only the caller's events (signed in, session ended, sign-in failed, locked out), newest first, limit 1 to 100.
- S4: `GET /api/audit-logs` gains a reader path: with `entity_id` of a record the caller can open, it returns that record's history with readable fields only; otherwise an empty page.
- D7: `reference` (8 hex characters or a full UUID) on the audit and security-event lists.

## API contract (S5, S6)

### Sampler (S5-C1, S5-C2)

`SystemHealthWorker` in `manage/health/worker.py`: one sample per UTC minute across processes (advisory lock), table `system_health_samples`, hourly retention through `public.retain_system_health()`.

### Status response, periods read, storage, installation (S5-C3, C4, C6, C7)

`slow` joins the part statuses. `GET /api/system/health-periods` gives the timeline periods to everyone. `organization.storage_used_bytes` for admins; `installation` (database size, workers) for the owner.

### Server error log (S6-C1)

The request middleware stores each 5xx in `server_errors` (no body, header or personal data); capped and paused on write failure.

### Diagnostics downloads (S6-C2 to S6-C4)

`GET /api/system/diagnostics/installation` (owner) and `GET /api/system/diagnostics/organization` (admin), JSON attachments named `slateops-diagnostics-<installation|organization>-YYYYMMDD-HHMMZ.json`.

## Design (S1, S2)

### D1. Error references (S1)

- **D1.1** `ErrorReference` renders the reference from a full ID, and nothing at all with no ID. `apiErrorReference(error)` in `frontend/src/lib/api-errors.ts` gives the ID.
- **D1.2** Two lines after the message: "Reference 4f9c2e1a · Copy · Reference copied", then the D6 sentence.
- **D1.3** Copy is a ghost button named "Copy reference" that copies the full ID; a failed copy shows the full ID as selectable text.
- **D1.4** One reference per failed request, always the last part of the error container, after any action such as Retry. A field error never carries it; a form with only field errors shows one form-level line with the reference. Refusal notices, conflict notices with a way to recover, and empty states show no reference.
- **D1.5** Error toasts take an optional `reference`.
- **D1.6** Each caller keeps the message and the reference together (for example `{ message, reference }`) until the error renders.

### D2. System health page (S2)

- **D2.1** A Manage section: title "System health", the blocks as cards; block 3 renders nothing for non-admins.
- **D2.2** Block 1: status icon, the headline as `h2`, the check line, "Check again". For example "Slate Operations is working normally." or "Files and pictures are not working. Everything else works."
- **D2.3** Block 2: a `dl` with one row per part in R1 order, icon and word, and a cause line when a part does not work.
- **D2.4** "Check again" stays in place while busy (`aria-disabled`, `aria-busy`). The check line adds "This is the latest check" or "No change". Background refresh never extends an idle session.
- **D2.5** Block 5: Version, plus "Release notes" for the installation owner.
- **D2.6** Block 6: how to use a reference, and what to do when Slate Operations does not load.
- **D2.7** The frame renders at once; only data waits. A failed status read never becomes part statuses: it shows an Alert with the reference, and keeps the last result when there is one.
- **D2.8** Keyboard order follows the DOM; never color alone.
- **D2.9** The Manage tab "System health" is second, for every role; the URL is `/manage?view=health`.

### D3. Shell banner (S2)

- **D3.1** Text: "Slate Operations cannot reach its server. Changes you make now may not save. It tries again on its own."
- **D3.2** It shows when a fetch rejects (not an abort), or a response is 500, 502 or 504 with no `X-Request-ID`.
- **D3.3** It clears at the first response that carries `X-Request-ID`, of any status.
- **D3.4** While it shows, the shell requests `/api/health` after 5, 10 and 20 seconds, then every 30 seconds.
- **D3.5** `ServerConnectionBanner`, under the top bar, in the page flow; fixed-height pages get shorter by its height. Warn colors, no button.
- **D3.6** A `role="status"` region announces it.
- **D3.7** One connection message at a time: while the banner shows, "Reconnecting…" and the session verification alert stay hidden.

### D4. Answers

1. The URL is `/manage?view=health`.
2. The banner trigger of D3.2 is confirmed.
3. The retry reads the unauthenticated `/api/health`.
4. The release-notes link uses the owner-only `/api/version`.
5. (D4.5) An `ApiContractError` keeps the `X-Request-ID` of the rejected response and shows a reference.
6. The reference wording by role became D6.
7. The 8-character search became D7.
8. A part other than Email that is Not set up gets its own headline sentence and cause line.
9. (D4 answer 9) The help guide line for System health is the second `manage` entry in `frontend/src/components/help/page-guides.ts`.
10. A repeated announcement empties the span first.
11. Modals hold a hidden banner announcer.
12. A recoverable 409 conflict notice shows no reference.
13. The OpenComms error band sits in the flow.

## Deferred

Developer observability comes later: error tracking, an external uptime check on `/api/health`, `/metrics`, traces, and an error rate by organization from logs.

## Open items

None for the client side. The developer side is in [Deferred](#deferred).
