# OpenView part C: Reports inside module pages

> **Status: built, PR #68 (2026-10-26); EXIT-C6 and EXIT-C8 have no recorded result.** Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/openview-reports-in-modules.md`. Part C of the umbrella `docs/specs/openview-relayout.md`.

## What a report is

A report is a saved recipe for one module: columns, up to 10 filters, up to 3 sorts, an optional grouping and row count. People run it now or on a schedule (daily, weekly or monthly at a local time). Each run saves a **copy**: the rows as they were then, which can be opened, printed or downloaded as CSV later.

## Outcome

A module's reports live on its page, in a Reports view beside Records. The detail reads as three steps (what it lists → when it runs → what you keep), with the latest copy under them. A manager can turn the current view into a report in one step. The Reports page and the OpenView sidebar item are gone. No backend change: part C uses the existing report, run, schedule and purge routes. Preserved: readers see reports and copies; non-guest readers run; module managers create, edit, schedule, archive and restore; a copy read re-checks module read (`eligibility.py`); old links `/openview?section=reports&report=<id>&run=<id>` still work.

## Decisions

| ID | Decision |
| --- | --- |
| DC1 | The module page has Records and Reports as a segmented control with counts. The URL adds `tab=reports`, `report=<id>` and `copy=<runId>`. |
| DC2 | The Reports view is a list and a detail. Rows: name, schedule state (dot and word), and "Every Monday · 12 copies". New report in the list head for managers; archived reports are a list filter. |
| DC3 | Detail head: name, "More report actions" (Duplicate, Archive; Restore and Delete forever for archived), and the primary "Make a copy now". |
| DC4 | The three steps as linked cards: 1 · What it lists, 2 · When it runs, 3 · What you keep. Managers get Change on steps 1 and 2. |
| DC5 | The latest copy shows under the steps: a bar ("Copy of Mon, Oct 20 at 08:00 · 142 rows · as they were then"), an "Older copies" picker, Print, CSV, then the rows. |
| DC6 | New report and Edit use the shared dialog frame, with the page's module and no module picker. |
| DC7 | "Make a report from this view" in the Records view menu (managers) prefills New report from the view. |
| DC8 | An old report link reads the report, then replaces the URL with its module page's Reports view, report selected and copy open. |
| DC9 | The OpenView item leaves the sidebar. `?section=reports` without a report opens the first readable module's Reports view. |
| DC10 | No cross-module list of copies; scheduled copies still arrive as notifications. |
| DC11 | The empty state shows the same three steps as dashed cards, with "Make a report from the current view" and "Start from scratch" for managers. |
| DC12 | Phones: the list opens the detail as its own screen with Back; a copy opens full screen. |
| DC13 | A gone or unreadable report keeps its id in the address of the first readable module's Reports view, which shows "This report is not available." above the list. |
| DC14 | Step 2's Change opens the schedule in place (`aria-expanded`): Repeat (Off, Daily, Weekly, Monthly), Day, Time, Time zone (IANA list), Next copy, Last run; Save schedule is enabled only with a change. |
| DC15 | A copy shows its rows by reading its CSV once; the first 500 rows with "500 of N rows · CSV has all". |
| DC16 | Older copies list date and row count, newest first, 25 at a time. How a copy was made is not recorded by the API (gap). |
| DC17 | A module's reports load as one page of up to 100; each row reads its schedule and copy count (cached). |
| DC18 | Archive acts at once with "Report archived." and Undo; an archived report offers Restore and Delete forever. |
| DC19 | A failed last scheduled copy shows in step 2 for every reader. |
| DC20 | A guest sees Make a copy now disabled with "Guests cannot make copies." |
| DC21 | The breadcrumb stays "Sales › Quotes" on both views (no third crumb, for the cold JS budget). |
| DC22 | The report dialog owns its draft: Close or Cancel asks "Discard your report changes?"; a conflict offers Reload latest. |
| DC23 | Make a report from this view takes the visible columns, finished filters, first three sorts and grouping; the view name becomes the report name. |
| DC24 | Step 1 says what the report lists in words ("Quotes that match 2 filters, grouped by Status"). |
| DC25 | The Records view stays mounted, hidden, under Reports, so drafts and the record sheet survive a switch. |
| DC26 | An address with an unreadable module moves to the module the page shows, keeping report and copy. |
| DC27 | The dialog lists chosen columns first in report order; moves are announced; Save and Create say why they wait. |
| DC28 | A changeable step is one button named by its facts, then "Change what it lists". |
| DC29 | Copy cells wrap to two lines; on a phone each row shows as label and value lines; Print lays the copy out as a table. |

### Where each Reports page capability goes

| Capability | In part C |
| --- | --- |
| List and create reports | The module's Reports view; New report or Make a report from this view |
| Edit recipe; schedule | Step 1; step 2 |
| Duplicate, Archive, Restore, Delete forever | Detail menu; archived list filter |
| Run now | "Make a copy now" |
| Saved outputs | The latest copy, Older copies, Print and CSV |
| Available outputs (shared copies) | Each module's copies and the notification links |
| Notification and old links | DC8 |

Phases: C1 views, steps, copy and schedule; C2 dialog and Make a report from this view; C3 old links, OpenView item removed; C4 phones; C5 review.

## Acceptance criteria

| ID | Criterion | Result |
| --- | --- | --- |
| EXIT-C1 | Every capability in the map is reachable for each role that has it. | built, PR #68 (no separate result) |
| EXIT-C2 | Every old report and notification link opens the right report and copy, or the notice. | built, PR #68 (no separate result) |
| EXIT-C3 | No OpenView item; `?section=reports` and `?section=charts` still land on a working page. | built, PR #68 (no separate result) |
| EXIT-C4 | The Reports view does not scroll the document at 1280×720 or 1440×900. | built, PR #68 (no separate result) |
| EXIT-C5 | At 390, targets are 44px and nothing scrolls sideways. | built, PR #68 (no separate result) |
| EXIT-C6 | A critique scores at least 28/40 with no P1. | not recorded |
| EXIT-C7 | Each finding has a failing-first test or a reason. | built, PR #68 (no separate result) |
| EXIT-C8 | The owner reviews the live app and approves. | not recorded |

## Open items

- EXIT-C6 and EXIT-C8 have no recorded result.
- DC16: the API does not record whether a copy was made by hand or by schedule.
