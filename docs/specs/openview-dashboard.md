# OpenView part B: the department dashboard

> **Status: B0–B4 built, PR #68 (2026-10-26); the B5 critique, EXIT-B7 and EXIT-B9 have no recorded result.** Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/openview-dashboard.md`. Part B of the umbrella `docs/specs/openview-relayout.md`; backend BE1–BE3 in B0 (`1f434798`).

## Outcome

Each department has one dashboard, its home, opened from the first row under the department in the sidebar. Managers arrange graphs on a fixed 4×5 grid, built from the department's modules and from linked modules in other departments. Everyone who reads the department sees the dashboard; each widget shows only what the viewer may read (`aggregate-snapshots` runs as the viewer on every request; no result is shared or cached between people). The chart-builder dialog replaces the Charts page. Code: `frontend/src/components/systems/openview/domain/dashboard-grid.ts`, `components/dashboard-layout.tsx`, `adapters/dashboards-api.ts`, `backend/app/systems/openview/dashboards/placement.py`.

## The grid

- **4 columns × 5 rows**, 12px gaps, filling the page under the header.
- **Minimum row height 112px.** On a window too short for five such rows, the grid panel scrolls; the page does not.
- A widget covers a rectangle of whole cells. Widgets never overlap and never leave the grid.

### Size rules (columns × rows)

| Widget | Smallest | Largest |
| --- | --- | --- |
| Number | 1 × 1 | 2 × 1 |
| Bar | 2 × 2 | 4 × 3 |
| Line | 2 × 2 | 4 × 3 |
| Pie | 2 × 2 | 3 × 3 |
| Table (group values) | 2 × 2 | 4 × 5 |
| Records (a list) | 2 × 2 | 4 × 5 |

### Presets

A preset places empty widget spaces of the right sizes; each space then asks for its chart. Presets apply to an empty dashboard, or replace the layout after a confirmation.

| Preset | Layout |
| --- | --- |
| Overview | Row 1: four numbers. Rows 2–3: a bar and a line, 2 × 2 each. Rows 4–5: a table and a records list, 2 × 2 each. |
| One big trend | Row 1: four numbers. Rows 2–4: one line, 4 × 3. Row 5: four numbers. |
| Lists first | Rows 1–2: a bar and a pie, 2 × 2 each. Rows 3–5: a records list, 4 × 3. |

## Decisions

| ID | Decision |
| --- | --- |
| BD1 | Each department group starts with a Dashboard row, then its module pages. The OpenView group loses Dashboards and Charts. |
| BD2 | Header: the dashboard name (default "<Department> dashboard"), a meta line (refresh time and cadence), a quiet Refresh, a "More dashboard actions" menu (Settings, Archive), and for managers one primary, Edit layout. |
| BD3 | One dashboard per department: the first active one by position is the home. Other dashboards stay read-only under "Other dashboards" until archived; nothing is deleted. No dashboard: managers see "Set up the Sales dashboard" with presets, readers "No dashboard yet". |
| BD4 | View mode: each widget is a card with a 36px head (title, linked department name, menu). No sentence, no size kicker. Tables page with a compact "1–4 of 12". |
| BD5 | Widget menu: Open the records, Download data (CSV), and for managers Edit chart and Remove. |
| BD6 | A widget on an unreadable module is a locked card; the other widgets load (one read per module). |
| BD7 | Edit mode (managers, from 1024px): grid lines, "Add" in empty cells, a drag handle and a corner handle per widget (`@dnd-kit/core`). Resizing snaps to cells and stops at the size rules. |
| BD8 | Non-drag way (WCAG 2.5.7): the edit-mode widget menu lists allowed sizes (others disabled with a reason) and Move left, right, up, down; arrow keys move and Shift+arrows resize on the focused handle. |
| BD9 | Edit mode shows one pinned bar: hint, Presets, Add widget, Cancel, Save layout (only primary). Save sends one update with the revision; a conflict keeps the edit and offers reload; leaving asks first. |
| BD10 | The chart builder is a large framed dialog: Setup (Show as, Records, Group by, Show, Filters, Dates, Order, Title, Size) and Preview (explicit Update preview). It opens from an empty cell (size preselected; types that do not fit are disabled with a reason) or from Edit chart. Footer: "Use a saved chart instead", Cancel, Add to dashboard. |
| BD11 | The Records picker lists the department's modules, then linked modules under "Linked departments" ("Finance › Invoices"). |
| BD12 | Phones: widgets stack in reading order, full width. Edit layout says "Edit the layout on a larger screen." |
| BD13 | Address: `/openview?section=dashboards&department=<id>`, plus `&dashboard=<id>` for another dashboard. An old `&dashboard=<id>` link gains its department. `?section=charts` opens the first department's dashboard with `&builder=saved`. |
| BD14 | Inline widgets are read in one `aggregate-snapshots` batch per module (at most 12 queries), each saved chart on its own. A 404 or unavailable chart locks only its widgets; a 401 or 403 sets the OpenView refusal latch. |
| BD15 | The locked card says "No access to these records" (the viewer cannot read the module's name). |
| BD16 | Widgets store no title or group order; the title comes from the query, a saved chart shows its name. The Order row is for records lists only. `docs/specs/ux-friction-pass.md` item 9 makes the titles plain words. |
| BD17 | Preset spaces live in the layout draft only; unfilled spaces are not saved. |
| BD18 | Edit chart and Remove from a view-mode menu open edit mode with that change; Save layout saves it. |
| BD19 | Download data (CSV) is on numbers, charts and tables; a records list offers Open the records instead. |
| BD20 | The saved-chart list reads a chart's usage when the chart is opened, not per row. Archive and Restore are in the row menu, Restore under "Archived charts". |
| BD21 | Edit chart on a saved-chart widget changes a copy here unless "Change … everywhere" is ticked. |
| BD22 | A Number shows one figure across groups (count, sum, smallest, largest); average and distinct are not offered for a Number. |
| BD23 | A card moves by pointer from its handle or body (5px threshold), resizes from its corner, and moves or resizes by keyboard (announced). Unplaced widgets (BE1m) show under "Not on the grid" with Place it and Remove; Save layout waits until each is placed or removed. From 768px to 1023px the grid shows with 112px rows and the page scrolls. |
| BD24 | Widget schemas live in `adapters/dashboard-widget-config.ts`, so the shell does not load the dashboard reads (cold Comms budget). |
| BD25 | A department with only archived dashboards shows its managers "Archived dashboards…" with Restore; the restored one becomes the home. |

### Where each Charts and Dashboards capability goes

| Capability | In part B |
| --- | --- |
| Create a chart | The builder, from Add widget or an empty cell |
| Open a saved chart | "Use a saved chart instead" in the builder |
| Save a chart for reuse | "Save for reuse" in the builder footer |
| Usage of a saved chart | Each saved-chart row names the dashboards that use it |
| Archive and restore a saved chart | Row menu (Archive) and an Archived filter (Restore) |
| Edit a saved chart | Edit chart: "Change it everywhere" or "Use a copy here" |
| Chart data as CSV | Download data in the widget menu |
| Create, rename, archive, restore a dashboard | BD3, and Settings and Archive in the dashboard menu |
| Refresh and cadence | The header Refresh, and Settings |
| A quick question | The module page: quick filter and Filters |

## Backend changes

| ID | Change |
| --- | --- |
| BE1 | Widget placement: `grid_column` (0–3), `grid_row` (0–4), `column_span` (1–4), `row_span` (1–5). The server refuses overlap, out-of-grid placement and sizes outside the size rules. `size` and the 12-widget limit go. |
| BE1m | Migration: existing widgets are placed in `position` order at the first free space (number S → 1 × 1, M or L → 2 × 1; other types S or M → 2 × 2, L → 4 × 2; pie L → 3 × 3 or 2 × 2). A widget that does not fit stays unplaced. |
| BE2 | Linked sources: a widget may use a module of the department or one linked to it by a relationship. The saving manager must read it; every read is still checked as the viewer (SEC-R6). |
| BE3 | One home per department: `is_home`, one active home per department (partial unique index); archiving the home moves it to the next active dashboard. |

Phases: B0 backend, B1 sidebar row, view mode and locked cards (BD1–BD6), B2 edit mode (BD7–BD9), B3 chart builder and saved charts (BD10, BD11), B4 phones and empty states, B5 review.

## Acceptance criteria

| ID | Criterion | Result |
| --- | --- | --- |
| EXIT-B1 | Each Dashboard row opens its home dashboard; the OpenView group holds Reports only. | built, PR #68 (no separate result) |
| EXIT-B2 | At 1440×900 the dashboard does not scroll; below 112px rows only the grid panel scrolls. | built, PR #68 (no separate result) |
| EXIT-B3 | A manager arranges by mouse and by keyboard; the server refuses overlap and bad sizes. | built, PR #68 (no separate result) |
| EXIT-B4 | A linked-module widget shows to readers who can read it and is locked for the others. | built, PR #68 (no separate result) |
| EXIT-B5 | Every capability in the map is reachable; existing dashboards and saved charts work after the migration. | built, PR #68 (no separate result) |
| EXIT-B6 | At 390, targets are 44px and widgets stack in reading order. | built, PR #68 (no separate result) |
| EXIT-B7 | A critique scores at least 28/40 with no P1. | not recorded |
| EXIT-B8 | Each finding has a failing-first test or a reason. | built, PR #68 (no separate result) |
| EXIT-B9 | The owner reviews the live app and approves. | not recorded |

## Open items

- The B5 critique, EXIT-B7 and EXIT-B9 have no recorded result.
- A free widget title and group order need a backend field (BD16 follow-up).
- Never cache dashboard results: BE2 is safe only because every read is checked as the viewer.
