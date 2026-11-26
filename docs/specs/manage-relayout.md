# Manage relayout: the Access grammar

> **Status: done (2026-10-24), PR #62.** EXIT-3 not re-measured and EXIT-6 fix-first (see Acceptance criteria). Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/manage-relayout.md`.

## Outcome

Manage (`/manage`: Organization, Backup, Audit, Jobs, Updates & licensing, their dialogs, sheets and 390px layouts) uses the Access grammar: slim controls, 40px rows, label-left rows, quick filters with the Filters popover and chips, Advanced last, summary first, still pages from 1280px. Each account sees only the sections it can use. Code: `frontend/src/components/systems/manage/` (`domain/audit-rules.ts`, `domain/backup-rules.ts`, `domain/job-rules.ts`, `domain/updates-rules.ts`, `components/backup-panel.tsx`, `updates-panel.tsx`), section visibility in `frontend/src/components/workspace-navigation.ts`. Preserved: URLs and `?view=` values; exports and backup requests; server refusals as the source of truth; the look picker previews before Save.

## Layout direction

1. Every section: slim controls (`slim-ui`), still pages from 1280px, a title with one meta line, quiet actions with at most one primary.
2. Who sees what: Organization for every member (administrators edit, others read); Audit for administrators and for department managers on their departments (MD12); Jobs unchanged; Backup and Updates & licensing for the installation owner. A direct link to a hidden section shows a notice ("Backup is managed by the installation owner.") with no Retry and no refused request.
3. Organization: two panes, label-left Identity, Region and Look groups, a closed Profile block, a pinned footer.
4. Audit: Activity and Security events views; search, quick filters, Filters popover and chips; 40px sentence rows; system events folded; an event sheet with "What changed" for changed fields only; Export disabled with a reason above 10,000 rows.
5. Backup: a status summary first, then history as a list and a detail.
6. Jobs: 40px rows with a state dot and word, state quick filters, ink subjects, a row ⋯ menu only where Retry applies.
7. Updates & licensing: one summary panel of label-left rows.
8. Dialogs: pinned header and footer, a named close, a Save bar only after an edit.
9. Phones: the two-row header, details on their own screen, Filters as a bottom sheet, 44px targets.

## Decisions

| ID | Decision |
| --- | --- |
| MD1 | Manage carries `slim-ui`, and from 1280px its pages are still. |
| MD2 | The header is the title and one meta line. |
| MD3 | The navigation shows each section only to an account that can open it; a hidden section's link shows a notice. Related links show only places the account can open. |
| MD4 | Organization uses two panes, label-left groups, a closed optional Profile block, and a pinned footer. |
| MD5 | A reader sees Organization as plain text. |
| MD6 | Audit has quick filters, a Filters popover and chips, 40px sentence rows, system events folded, and an event sheet listing changes only. |
| MD7 | Audit Export is disabled with a reason above 10,000 rows. |
| MD8 | Backup shows a status summary first, then history as a list and a detail. The schedule dialog's Save bar appears only after an edit. |
| MD9 | Jobs has state quick filters, ink subjects, row menus only where they apply, and "—" for runs that have not happened. |
| MD10 | Updates & licensing is one summary of label-left rows. |
| MD11 | Security events use the Access glossary words. |
| MD12 | A department manager sees Audit for the departments they manage (`department_id`, a department picker for two or more); Security events and Export stay for administrators. |
| MD13 | Audit targets read as the record's name ("Quote Q-1042"); without one, the kind alone ("Test run"). The area word names the department or page. |
| MD14 | Phase 1: Backup and Updates show for `operator` with an administrator role; only `operator_required` leads to the owner notice; the breadcrumb names every section. |
| MD15 | Phase 2: Organization panes and groups as in MD4; Save says "No changes to save." at rest; readers see saved values with "Not set". |
| MD16 | Phase 3: Activity rows read "Changed Status, Sent on +3 · Quote Q-1042"; field names come from `GET /fields/{id}`; system events fold per page; quick filters show no counts; the sheet reads the list row; managers read with `department_id`; Security events take the same toolbar and a side sheet. |
| MD17 | Phase 4: the Backup Status panel (Schedule, Last good backup, Service, Queue) with Edit schedule and Back up now; history quick filters on the API states; actions disabled with a reason after an owner refusal. |
| MD18 | Phase 5: Jobs rows for the seven API states, the kind in the server's words, Retry only where `can_retry`, `TablePagination`; Updates is one "Installation" panel (Version, Release check, Latest release, License, Limits). Backup, Jobs and Audit share `StatusWord`. |
| MD19 | Phase 6: the dialog frame moved to `ui/dialog-frame.tsx`; Manage dialogs take it with named closes; event sheets stay sheets; the phone header holds one row of actions; below 1280px Jobs and Audit show list rows. |
| MD20 | Phase 8: every audited table has its own kind words; system values leave rows and What changed and stay in Advanced; references read as loaded names, else "Set", "Changed" or "Removed"; the Backup schedule asks before closing with unsaved changes; Organization Save reads "Saving…"; the Jobs retry result is a toast; row targets never show a short id (owner decision). |

Findings M-F1 to M-F16 (baseline critique 20/40): M-F1 (P1) owner-only sections refused administrators with a useless Retry; M-F2 (P1) managers saw admin sections with 403s; M-F3 Organization scroll and late Save; M-F4 boxed read-only fields; M-F5 77px Audit rows and read-receipt flood; M-F6 inline Audit filters; M-F7 raw diff; M-F8 old Security event words; M-F9 Export opening in an error state; M-F10 scattered Backup state; M-F11 repeated chips, sentences and banners; M-F12 Jobs noise; M-F13 Updates repetition; M-F14 unclear button names; M-F15 actions enabled after a refusal; M-F16 split table names as targets.

## Phases

Phase 0 discovery; Phase 1 MD1, MD2, MD3; Phase 2 Organization (MD4, MD5); Phase 3 Audit (MD6, MD7, MD11); Phase 4 Backup (MD8); Phase 5 Jobs and Updates (MD9, MD10); Phase 6 dialogs and phone; Phase 7 plain words; Phase 8 sweep, critique and hands-on pass.

## Phase 7 glossary (decided under the owner's delegation, 2026-10-24)

Display words only; stored values, API fields and URLs are unchanged. `frontend/tests/http/manage-plain-words.spec.ts` guards that no Manage state shows Binding, Operator, Reconciliation, Policy, "authentication" or "membership".

| # | Now |
| --- | --- |
| MG1 | "Backup policy" becomes "backup schedule" in every message. |
| MG2 | Schedule dialog: "Keep backups for", Save schedule. |
| MG3 | Backup detail "Server restart": "Recorded · <time>", "Needs recovery on the server", or "—". |
| MG4 | "Schedule then". |
| MG5 | Source: "Manual" and "Automatic"; the filter is "Source". |
| MG6 | "Needs recovery on the server" and "Needs confirmation after a restore", each with one line on what to do. |
| MG7 | Audit kinds "Live item link", "Published change", "Organization member", "Report result". |
| MG8 | Refusals name "the installation owner" ("Only the installation owner can request a backup."). |
| MG9 | "The retry could not be confirmed. Reload Jobs to see its state.", "Retry requested." |
| MG10 | "Cleanup is not finished. Try again when the current task ends." |
| MG11 | "The release check is out of date", "… is not available", "The versions could not be compared". |
| MG12 | "—" for empty label-left values; "No earlier value" and "No new value" for raw values. |
| MG13 | "OpenComms export", "Scheduled OpenComms message"; "Event type". |
| MG14 | Five Help entries, one per section. |
| MG15 | Work on the server names "the person who runs your server"; "installation owner" names only the in-app account. |
| MG16 | "<name> is queued. The backup service on the server runs it." |
| MG17 | Export reasons "This backup is still running." and "This backup needs recovery on the server first."; plain failure words. |
| MG18 | "Organization" replaces "Workspace" for the organization. |
| MG19 | "The logo upload could not be confirmed. Choose the logo again."; "Permanent delete is turned off on this server." |
| MG20 | "No backups yet"; "Jobs could not be loaded. You do not have access." |
| MG21 | Restore caveat (later removed by MG31). |
| MG22 | "Sign-in enabled", "Sign-in disabled", "Sign-in restored". |
| MG23 | "Record summary authorization"; OpenView still says "aggregate snapshot" (follow-up). |
| MG24 | Unchanged technical names: Snapshot ID, Checksum, CSV, Event ID, Request ID, Reference. |
| MG25 | Unchanged: "Installation", Refresh release status, "Account policy change". |
| MG26 | Every audited kind has its own words ("Posts · Boards"); an unknown table reads "Unknown tables · Other". |
| MG27 | "Changed Description · Organization <name>"; system values only in Advanced; "Changed settings · …" when only they changed. |
| MG28 | Organization preview title "Preview". |
| MG29 | The Security events Person ID mode is gone; Person is the directory picker. |
| MG30 | One schedule dialog description: "Old backups are removed only after a newer backup is checked." |
| MG31 | The backup detail restore caveat is gone; the Backup meta line says who restores. |
| MG32 | "Showing the first 10 of 123 entries." |
| MG33 | Save reads "Saving…"; the footer chip "Saved" confirms. |
| MG34 | New: "Needs confirmation after a restore." on Edit schedule; "Discard unsaved changes?"; "Department: Sales"; "Retry requested." |
| MG35 | Retired OpenComms tables read "Join requests · OpenComms", "Conversation group access · OpenComms". |
| MG36 | References read as their loaded names, else "Set", "Changed" or "Removed"; select values read their option labels. |
| MG37 | Row targets use a name from the event ("Group member HO Manager"). |
| MG38 | A Person chip outside the directory reads "Person 3f2a1b9c". |
| MG39 | Row targets with no name show the kind alone ("Created · Test run"); the id is "Record ID" in the sheet's Advanced (owner decision). |

## Acceptance criteria

| ID | Criterion | Result |
| --- | --- | --- |
| EXIT-1 | A new critique finds no P1; heuristics 4 and 8 score 3 or more. | met (20 → 29 of 40) |
| EXIT-2 | Every data-changing action gives feedback before, during and after. | met |
| EXIT-3 | Helper words and default-visible controls do not rise above the baseline, unless recorded. | not recorded (the owner waived the sweep; additions in MD15–MD20) |
| EXIT-4 | M-F1 to M-F14 have a failing-first test or a reason. | met |
| EXIT-5 | Manage isolated and HTTP tests, budget specs and static checks pass. | met (focused batches) |
| EXIT-6 | `ui-reviewer` returns "ship". | not met as written: fix-first, fixes checked in the hands-on retest |
| EXIT-7 | A hands-on pass as `ho-admin`, `ho-manager` and the installation owner finds no open defect. | met |
| EXIT-8 | No page scroll from 1280px; no sideways scroll below. | met |
| EXIT-9 | Field edges at least 3:1; targets at least 44px at 390. | targets met; edges covered by theme parity only |
| EXIT-10 | The owner approves the 390px sweep. | met (2026-10-24) |

## Open items

- Server-sent words: the audit CSV header and kind values ("Entity", "Sandbox Bindings"), Jobs `failure_label` texts, "Scheduled Comms retention".
- OpenView "aggregate snapshot" (MG23).
