# OpenView: department pages and the slim identity (umbrella)

> **Status: done (2026-10-26), PR #68; EXIT-1 and EXIT-9 have no recorded result.** Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/openview-relayout.md`.

## Outcome

OpenView became the departments' own pages, in the slim grammar (DESIGN.md "Slim controls": 32px controls from 1280px, 40px rows, label-left rows, quick filters with the Filters popover and chips, still pages, one primary, framed dialogs, 44px phone targets). The owner's direction (2026-10-25): departments replace the OpenView item in the sidebar; each department has one dashboard on a 4×5 grid; charts are a builder dialog, not a page; reports are a tab in each module page. The work is in three parts:

| Part | Spec | Content |
| --- | --- | --- |
| A | `docs/specs/openview-department-pages.md` | Departments in the sidebar, module pages |
| B | `docs/specs/openview-dashboard.md` | The department dashboard, the chart builder, backend placement |
| C | `docs/specs/openview-reports-in-modules.md` | Reports inside module pages |

Preserved: every capability for every role; the URL parameters `?section=`, `?module=`, `?view=`, `?record=`, `?dashboard=`, `?report=`; server refusals stay the source of truth.

## Decisions

| ID | Decision |
| --- | --- |
| OD1 | One section header: title, one muted meta line ("Sales · 30 records"), pickers in the header row, quiet actions with at most one primary. No intro sentence or source card. |
| OD2 | ~~Keep four sections.~~ Replaced by the department-pages direction. |
| OD3 | The Views toolbar is one row: search, quick filter, Filters popover with chips, Sort, Columns, Layout. |
| OD4 | **Reversed (2026-10-27) by `docs/specs/boards-relayout.md` BR77:** the Layout menu lists Table, Grid and Gallery only. The layout is a select, not tabs. |
| OD5 | Save model: an "Unsaved changes" chip, then Save view (primary) and "Save as new view"; otherwise New record is the primary. Archived views, Copy link and Reset changes are in the menu. `docs/specs/ux-friction-pass.md` item 1 shows the chip and leave guard to view managers only. |
| OD6 | 40px one-line rows; the whole row opens the record; people as avatar and name in ink; one date format. `docs/specs/subtle-interactions.md` candidate 1: a Choice list value opens its menu. |
| OD7 | The record opens in a right sheet; `?record=` links are unchanged. |
| OD8 | **Reversed (2026-10-27) by `docs/specs/boards-relayout.md` BR77:** Kanban, Calendar and Timeline left OpenView, with their field-picker empty states. |
| OD9 | *(Replaced by part B: a chart-builder dialog.)* Charts in two panes with explicit Apply. |
| OD10 | *(Replaced by part B: the 4×5 grid.)* Dashboards with a header picker and compact widget pagers. |
| OD11 | *(Replaced by part C: Reports in module pages.)* Reports in list and detail panes. |
| OD12 | All OpenView dialogs use the shared dialog frame (`ui/dialog-frame.tsx`). |
| OD13 | One no-access state ("No records to show yet" with the reason); create actions only for those who can create. |
| OD14 | The Views quick filter uses the first choice field, with counts from the grouped-count read, cached per view. No choice field, no quick filter. |
| OD15 | Extract only the header, toolbar and record sheet from `server-backed-views-workspace.tsx`; state owners stay where they are. |

Part A adds DA1–DA22 (`openview-department-pages.md`, where DA11 and DA20 are superseded by BR77); part B adds BD1–BD25.

## Findings

The Phase 0 critique scored 17/40. Findings OV-F1 to OV-F13: OV-F1 (P0) records sat below four control bands; OV-F2 empty states ignored the role; OV-F3 an empty View actions menu; OV-F4 unframed dialogs; OV-F5 a meaningless default chart; OV-F6 chrome before content; OV-F7 pre-slim controls; OV-F8 six layout tabs; OV-F9 69px rows and mixed date formats; OV-F10 dashboard picker card and full pagers; OV-F11 report list buttons; OV-F12 jargon words; OV-F13 long phone scroll.

## Acceptance criteria

| ID | Criterion | Result |
| --- | --- | --- |
| EXIT-1 | Critique at least 28/40 with no P1. | not recorded |
| EXIT-2 | The landings do not scroll the document at 1280×720 and 1440×900. | built, PR #68 (no separate result) |
| EXIT-3 | The first record row is above y=300 at 1440 and on the first screen at 390. | built, PR #68 (no separate result) |
| EXIT-4 | From 1280px, controls are 32px and rows 40px. | built, PR #68 (no separate result) |
| EXIT-5 | Targets at least 44px at 390; no horizontal scroll. | built, PR #68 (no separate result) |
| EXIT-6 | Every capability and preserved URL still works for each role. | built, PR #68 (no separate result) |
| EXIT-7 | Each finding has a failing-first test or a reason; the budget holds. | built, PR #68 (no separate result) |
| EXIT-8 | A hands-on pass by role finds no blocking defect. | built, PR #68 (no separate result) |
| EXIT-9 | The owner reviews the live app and approves. | not recorded |

## Open items

- EXIT-1 and EXIT-9 have no recorded result.
