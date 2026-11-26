# OpenView part A: department pages

> **Status: built, PR #68 (2026-10-26); EXIT-A7 and EXIT-A9 have no recorded result.** Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/openview-department-pages.md`. Part A of the umbrella `docs/specs/openview-relayout.md` (OD1–OD15).

## Outcome

Each department is a sidebar group, and each module is a page (Sales › Contacts) that shows its records at once, with no "data source" picker. The module page is the Views page for one module in the slim grammar. Code: `frontend/src/components/department-navigation-model.ts`, `department-navigation.tsx`. URLs are unchanged: `/openview?section=views&module=<id>`, saved views and `?record=`. No backend change.

## Decisions

| ID | Decision |
| --- | --- |
| DA1 | A Departments section sits above the tools, under a small muted label; the tools follow under "Tools". |
| DA2 | It lists only departments with a readable module, and only those modules. Departments follow the Sandbox order (`created_at`); modules follow their names. One cached read each of `/api/departments` and `/api/views/data-sources` (first 100, then "More…"). |
| DA3 | The current department is open, others closed; a toggled group stays so between pages, not across reloads. |
| DA4 | A module row links to its page and is current when the page shows that module. |
| DA5 | The OpenView item keeps Dashboards, Charts and Reports until parts B and C; Views goes. |
| DA6 | The collapsed rail has one Departments button that opens the sidebar. |
| DA7 | The phone drawer shows the same section, current department open. |
| DA8 | The breadcrumb reads "Sales › Contacts". |
| DA9 | No readable module: no Departments section. An administrator with nothing published also sees none; the landing offers the Sandbox (OD13). |
| DA10 | Each row starts with its `DepartmentMark` (`--dept-n`, Sandbox order). |
| DA11 | **Superseded in part by `docs/specs/boards-relayout.md` BR77:** the Layout menu ("Table ▾") keeps Table, Grid and Gallery, with "Layout settings…" at its foot; Kanban, Calendar and Timeline move to Boards. |
| DA12 | With unsaved changes a manager sees "Save view" and, on an editable saved view, "Save as new view". |
| DA13 | The view menu: Copy link, Reset changes, Archived views; for managers Save as new view…, Rename, Duplicate, Make or Clear default, Archive. |
| DA14 | Refreshes show in the header meta line, not as banners. |
| DA15 | A refused catalog read hides the Departments section and breadcrumb names until the next authorized read. |
| DA16 | The Filters popover holds filter rows label-left; chips read "Status: is Active". |
| DA17 | The quick filter (OD14) is an "is" filter on the first choice field, in the view URL, with counts from `aggregate-query`. |
| DA18 | The record sheet: name, meta line, Previous and Next, quiet Edit, "More record actions", named Close; accessible name "Record details". |
| DA19 | Edit stays in the sheet's Details tab; other dialogs use the shared dialog frame. |
| DA20 | **Superseded by `docs/specs/boards-relayout.md` BR77:** Kanban, Calendar and Timeline leave OpenView, so their empty states (OD8) go. |
| DA21 | No access: "No records to show yet" with the reason. An administrator with nothing published sees "Nothing published yet" and Open Sandbox. |
| DA22 | Phones: Export moves into the view menu so the picker, menu and New record share one line. |

Phases: A1 sidebar (DA1–DA9), A2 module page, A3 record sheet and dialogs, A4 no access and phones, A5 review.

## Acceptance criteria

| ID | Criterion | Result |
| --- | --- | --- |
| EXIT-A1 | Each role sees exactly its readable departments and modules; the current row is marked. | built, PR #68 (no separate result) |
| EXIT-A2 | A cold `/comms` load adds at most the two catalog reads; the Comms JS budget holds. | built, PR #68 (no separate result) |
| EXIT-A3 | A module published or renamed appears without a reload. | built, PR #68 (no separate result) |
| EXIT-A4 | No document scroll at 1280×720 or 1440×900; first row above y=300. | built, PR #68 (no separate result) |
| EXIT-A5 | From 1280px controls 32px, rows 40px; at 390 targets 44px. | built, PR #68 (no separate result) |
| EXIT-A6 | Every preserved URL and capability still works. | built, PR #68 (no separate result) |
| EXIT-A7 | Critique scores at least 28/40 with no P1. | not recorded |
| EXIT-A8 | Each finding has a failing-first test or a reason. | built, PR #68 (no separate result) |
| EXIT-A9 | The owner approves the live app. | not recorded |

## Open items

- EXIT-A7 and EXIT-A9 have no recorded result.
- Opening a record reads it through the list query, so the list behind the sheet narrows to that record.
- The mark index counts readable departments, so a partial reader can see a different color.
