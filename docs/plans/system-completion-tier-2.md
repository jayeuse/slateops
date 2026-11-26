# System completion: Tier 2 plan

> **Status: done (2026-10-10), PR #34.** Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/plans/system-completion-tier-2.md`.

Base revision `9e732b84`, Alembic head `dfa5340b47ba`. The owner answered the Tier 2 questions on 2026-10-08. The owner owned final acceptance (S32, S33).

## Outcome

Tier 2 made every existing feature complete its full cycle before OpenComms: people save, analyze, export and edit data where they see it; screens stay current without a refresh, and an open editor never loses typed text; each person owns a profile; administrators read security events and job health in plain language; permanent delete works with one set of safeguards; the documentation describes the current system. It added no new product area. Main code: `/profile` and the person card, Manage › Jobs and the Audit security-events tab, the OpenView export (XlsxWriter), `POST /records/batch-update` with drag editing, the `charts` table with the shared chart editor and the dashboard grid, Board and Dashboard live updates, and the purge routes for reports and Board events.

This plan replaced three Tier 1 decisions: Tier 1 D4 (purge off) by D1; Tier 1 W2b ("do not add personal timezone or week start") by D14; Tier 1 D1 and S25 (security events in Access) by D17.

## Decisions

| ID | Decision |
|---|---|
| D1 | Permanent delete is on for new installations (`.env.example`, test defaults). `LIFECYCLE_PURGE_ENABLED` stays required; existing installations keep their value. |
| D2 | Every permanent delete needs the safeguards of W5b; report and Board event deletes moved to that rule. |
| D3 | Pinned posts sort first in the default order and keep the badge. |
| D4 | The Board widget `refresh` field is no longer written; it is accepted and ignored on import. |
| D5 | Analytics: full editors, saved charts, min, max and distinct count, week to year buckets. No pivot tables and no cross-relationship aggregation. |
| D6 | Chart and dashboard visibility follows module read access. No new sharing model. |
| D7 | Widget sizes S, M and L for Dashboards and Boards; Board `half` → M, `full` → L. |
| D8 | Live updates: Board events go to Board readers (`board_ids` on `EventViewer`); Dashboard events are opaque entity-only events to all authenticated people. |
| D9 | Lists update in place. An open editor keeps its text and shows "Changed by someone else — review latest". |
| D10 | Drag edits save through the existing `POST /records/batch-update`: at most 100 items, one revision check, savepoint and result per item. An opt-in item form merges up to two distinct field changes atomically. No new endpoint and no full-record replacement. |
| D11 | Drag editing: batch, then Save; partial success with per-card conflict flags; Kanban lanes for `select`, `user` and `boolean` only; Timeline move and end resize; `@dnd-kit/core`; a "Move to…" menu as the non-drag path. |
| D12 | Export: any module reader; CSV and Excel through XlsxWriter; each export is recorded; options for title and details, columns, accent, banded rows, totals and record ID (off). |
| D13 | The profile route is `/profile`; Account and Appearance redirect to it. |
| D14 | Personal regional settings are display only (rules below). |
| D15 | Person card: name, photo and title for everyone; email, phone and bio for members and admins; no department. |
| D16 | Job retry is admin only. It resets a failed `scheduled_work` row or queues a new backup run, starts a new set of 5 attempts, and is not offered for `source_unavailable`. |
| D17 | Security events live in Manage › Audit, in an admin-only tab; Access › Security links to it. |
| D18 | Sandbox version cap: a banner at 45 of 50; prune deletes the oldest checkpoint and imported versions down to 40, never published versions or the newest version. |
| D19 | Stale documents are rewritten as current state and remaining gaps; the seven reviews became `docs/reviews/known-gaps.md`. |
| D20 | The Harbor Small and School Small runs call the new routes through the same APIs as the UI. |
| D21 | Sample executors are written in the same slice that adds a frontend-called route; `DEFERRED_ROUTES` stays empty. |
| D22 | Paging extensions: `GET /access/groups` filters `without_access`, `without_members`, `member_id` and sort `member_count`; `GET /users` and `GET /member-candidates` accept `ids` (at most 100); `GET /boards/{board_id}/post-authors` accepts `ids`; `GET /sandbox/versions` accepts `search` and `kind`. Permissions and the paged response stay unchanged. |
| D23 | Dashboard refresh counts from the end of the previous fetch, pauses while the page is hidden or the draft is dirty, and uses TanStack Query `refetchInterval`. |
| D24 | `scheduled_work.last_attempt_started_at` and `finished_at` (nullable); old rows show "Not recorded". |
| D25 | An export with no columns returns 422 `export_no_columns`. |
| D26 | `min` and `max` take numeric fields only; temporal min and max come after Tier 2. |
| D27 | `GET /auth/me` adds nullable `phone`, `bio` and `avatar_file_id`; a person may read their own avatar without shared access. |

## Rules that still govern

**One rule for every permanent delete (W5b, D2).** A permanent delete requires all of these: the person is an administrator; `LIFECYCLE_PURGE_ENABLED` is true; the item is archived first; a preview shows what will be deleted, with the date of the last successful backup; the person enters their password and types the item's name. The disabled-state text is "Permanent delete is turned off for this installation."

**Rules for personal regional settings (D14).** Personal timezone, date format, time format and first day of the week change display only. They never change record windowing, aggregation buckets, the workspace `today`, report run snapshots, backup schedules, trigger timezones, Board event timezones or export cell text (exports use the workspace timezone and state it). A surface that groups by workspace day shows "Workspace timezone: …". A personal first day of the week changes only where the calendar grid starts.

**Relationship lifecycle (W6a).** A published relationship is a `Field` of type `relationship`; the inspector offers Close, Reopen and Permanently delete through the field lifecycle routes, and the preview shows the record links that a close hides.

**Migrations (section 6).** Edit CHECK constraints by hand; Alembic does not compare them. Each route change regenerates `contracts/openapi.json`, updates `frontend/api-route-manifest.json` and the contract fixtures.

**Implementer decisions (section 11.8).** An implementer may settle validation of empty input, null display, names, test technique and derived values by the most conservative existing pattern, and records it. A new permission, a data deletion, an unlisted public shape change or work outside the workstream blocks the slice.

## Workstreams and slices

| ID | Workstream | Slices |
|---|---|---|
| W1 | Naming cleanup (W1a) and documentation update (W1b) | S01, S31 |
| W2 | Login error text (W2a), root redirect (W2b), Help panel (W2c) | S02, S23 |
| W3 | Server paging for every list; `loadAllAccessPages` deleted | S07, S08 |
| W4 | Live updates: backend delivery (W4a), Boards (W4b), Dashboards (W4c) | S10, S11, S12 |
| W5 | Purge on by default (W5a), one rule for every permanent delete (W5b), missing purge UI (W5c), route bundle: pin and expiry, unpublish, invitation reconcile, Sandbox export with history (W5d) | S03, S04, S05 |
| W6 | Sandbox relationship lifecycle (W6a), version cap (W6b), delete text (W6c) | S06 |
| W7 | Profile backend (W7a), `/profile` page (W7b), person card (W7c), email change (W7d) | S20, S21, S22, S24 |
| W8 | Security events in Manage › Audit, one sentence per event type | S09 |
| W9 | Export from OpenView: backend (W9a), dialog (W9b) | S15, S16 |
| W10 | Drag to edit: batch route (W10a), foundation (W10b), Kanban (W10c), Calendar and Timeline (W10d), results (W10e) | S17, S18, S19 |
| W11 | Jobs status: backend (W11a), UI (W11b) | S13, S14 |
| W12 | Analytics: aggregation (W12a), saved charts (W12b), widget size migration (W12c), shared chart editor (W12d), Charts page (W12e), dashboard grid (W12f), Board widget editor (W12g) | S25 to S30 |

S32 (owner): run the Harbor Small and School Small profiles with the new executors (D20, D21). S33 (owner): review the full branch diff, run the pre-push gate and write the final acceptance report.

## Open items

Deferred from Tier 2 to later plans, which own their state: OpenComms, then trigger actions beyond "Set field" and triggers that follow relationship links; notification preferences and digests; presence; conversation search; email delivery of reports; pivot tables and aggregation across relationships; min and max over date and datetime fields (D26); in-place backup restore. Bug 9 of the traces stays out of scope: a record whose assigned user lost access cannot be saved (422), and batch update reports it per item. A notification for failed post publishing and reminders is out of scope.
