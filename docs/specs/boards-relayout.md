# Boards: the team space (relayout)

> **Status: done (2026-10-27), PR #69.** Approved by the owner 2026-10-26; the owner approved the live result 2026-10-27 (EXIT-11). Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/boards-relayout.md`.

## Outcome

Boards became the team space. Every board has the tabs Posts · Calendar · Kanban · Gantt in the slim grammar. My calendar combines the events of every board a person reads, plus record-date sources and card due dates. A department's board is its **Announcements**. Board widgets, the Overview and board portability were removed, and OpenView lost its Kanban, Calendar and Timeline layouts (their saved views were deleted by a migration). Code: `frontend/src/components/systems/boards/`, `frontend/src/components/boards-navigation-model.ts`, `backend/app/systems/boards/` (stages, cards, labels, occurrences, calendar sources). Migrations: `4e015d0fb2ab` (widgets removed), `b7e2c4a9d1f3` (Kanban), `c3f8d2e6a1b7` (calendar sources).

Preserved: `backend/app/systems/boards/access.py` stays the source of truth; posts, events, lifecycle and the live stream behave as before; OpenView Table, Grid and Gallery keep their saved views. URLs: `/boards` opens the Company board's Posts; `?board=<id>&section=posts&post=<id>` and `?board=<id>&section=calendar&event=<id>` still open the item; `section=overview` opens Posts; an OpenView address with `layout=kanban|calendar|timeline` opens Table.

Out of scope: comments on posts, new post or event features, card automations, and changing a record from Boards by drag (BR79).

## Data safety

Two migrations delete data; downgrades recreate the schema, never the rows. Caution: do not run them on an installation without a backup (`infra/supabase/RESTORE.md`).

**A. Board widgets and portability (BE1).** The `board_widgets` table and 9 operations on 7 paths were removed. Every widget row was deleted (Harbor 48, School 44). Labelled parts that tests cite:

- A2: the widget routes and the portability routes (configuration export, import, duplicate) are gone.
- A4: chart usage counts dashboard widgets only; usage loses `kind: "board"`.
- A5: board widgets no longer block a Sandbox purge.
- A6: audit department attribution no longer maps `BoardWidget`; past rows keep their stored department.
- A8: `board_widgets` left the reset lists.
- A9: sample runs no longer seed or count widgets.

Board Activity no longer lists past widget rows (BE5); Manage › Audit keeps them.

**B. OpenView's Kanban, Calendar and Timeline (BE6).** `ViewPresentation.layout` keeps `table`, `grid`, `gallery`. The migration deleted every saved view of the three layouts (Harbor 18 of 36, School 21 of 42) and stripped seven presentation keys from the rest. `/records/window-query`, `/records/grouped-query` and `/records/batch-update` stay.

**C. Kanban purge and reset (BE7).** A board purge deletes its stages, cards, labels, checklist items and card files and links. A record or module purge lists and removes the record cards that point at it and never blocks. Reset lists the new tables.

## Fix-now rows

| ID | Fix |
| --- | --- |
| FN1 | A bare `/boards` opens Posts with no widget, record or field request, for every role (the Overview 404s are gone). |
| FN2 | An empty current month points to the next event ("No events in October · Next: Mon, Nov 2"), using BE3. |

## Decisions

Findings BF-1 to BF-30 (Boards) and LF-1 to LF-5 (OpenView layouts) are in the full text; each maps to a decision below.

| ID | Decision |
| --- | --- |
| BR1 | Each department group shows its board row after Dashboard, linking to `/boards?department=<id>`, read as Announcements. |
| BR2 | The Boards group: My calendar, Company, active project boards, All boards. |
| BR3 | All boards (`section=all`): search, Active · Archived, 40px rows with level chip; New project board for admins. |
| BR4 | Breadcrumbs: "Sales › Announcements", "Boards › Company", "Boards › My calendar". |
| BR5 | The rail's Boards button opens the sidebar with the group open. |
| BR6 | One `PageHeader`: title, department mark, level chip (Read, Post, Manager), Archived chip, one meta line, the tab's primary, Board settings for managers. |
| BR7 | Refresh follows the live stream; state shows in the meta line. |
| BR8 | From 1280px the page is still; only panels scroll. |
| BR9 | `section` is `posts` (default), `calendar`, `kanban`, `gantt`, `all` or `my-calendar`; `overview` opens Posts. |
| BR10 | Posts: list and reading pane from 1024px; writers see Published · Scheduled · Drafts (managers also Archived). |
| BR11 | Two-line list rows; pinned first; the whole row opens the post. |
| BR12 | Reading pane: title, meta line, Edit, More post actions; attachments only when present. |
| BR13 | The post editor uses the shared dialog frame; Publish with Schedule…. |
| BR14 | Archiving a published post confirms once; Restore acts at once with a toast. |
| BR15 | Empty states keep the layout and name the reason. |
| BR16 | One calendar toolbar row; Show: All · Created by me · Archived. |
| BR17 | Superseded by BR51–BR52. |
| BR18 | The empty month points forward (refined by BR43). |
| BR19 | Upcoming: from today, grouped by day; a series shows once per row. |
| BR20 | One event sheet for every view and for `?event=`. |
| BR21 | The event editor in the shared dialog frame, opening on Title. |
| BR22 | My calendar at `section=my-calendar` over every active board the person reads. |
| BR23 | Revised by BR53. |
| BR24 | A board whose events fail shows "not loaded · Retry" in the calendar list; the rest still show. |
| BR25 | New event from My calendar (BR35). |
| BR26 | Board settings is one sheet: Details · Access · Activity. |
| BR27 | Details: label-left rows; a department board's name is read-only; Archive asks once; Restore is neutral. |
| BR28 | Access: read-only summaries and Check a person. |
| BR29 | Activity: 40px audit sentence rows. |
| BR30 | New project board in the dialog frame; after Create, settings open on Access. |
| BR31 | Phone header: two short rows, then the tabs. |
| BR32 | Phone Posts: list or post, with Back. |
| BR33 | Revised by BR59. |
| BR34 | Module write on part of a department gives read on its board; the chip says "Posting needs write access to Sales." |
| BR35 | New event from My calendar shows only when the person can post on a board; the editor's first field is Board. |
| BR36 | No "Coming up" list beside Posts. |
| BR37 | Preview access becomes Check a person. |
| BR38 | Posts use slim controls; the message sits at the reading measure (at most 672px). |
| BR39 | Scope: every critique issue and analysis P1 and P2; P3 words land in P6. |
| BR40 | Superseded by BR50. |
| BR41 | A department board's address is `/boards?department=<id>`; a `?board=<id>` arrival is replaced with it. |
| BR42 | Superseded by BR55. |
| BR43 | The empty-month status sits at the center of the grid with "Next: <date>"; a search or hidden calendars that empty a period say so. |
| BR44 | "Created by me" filters in the browser; Archived is a list from the existing events read. |
| BR45 | The meta line says who reads and posts. |
| BR46 | Phones name the month short ("Nov 2026"). |
| BR47 | (Owner) The department row reads Announcements; page titles read "<owner> announcements". |
| BR48 | (Owner) Kanban, Calendar and Gantt are tabs beside Posts and are redesigned; only behavior moves. |
| BR49 | (Owner) The fourth tab is "Gantt" everywhere (`section=gantt`). |
| BR50 | Tabs sit under the title on every board; the tab's primary sits in the title row. |
| BR51 | (Owner) Month, Week, Upcoming on every Calendar tab and on My calendar (`view=`). |
| BR52 | A left rail (mini month and calendar list with checkboxes) from 1440px; below it, a Calendars popover. Hidden calendars are kept in browser storage. |
| BR53 | (Owner) An item takes its calendar's department mark; Company and project calendars are neutral ink; record sources and card due dates are outlined. Names stand beside colors outside month cells (recorded exception in DESIGN.md). |
| BR54 | Month anatomy: timed events are ink titles with a 3px color rule; all-day events are tinted pills; week number in Monday's cell. |
| BR55 | Titles take two lines while the day has room, legible at 1280. |
| BR56 | Week anatomy: hours 6 AM–9 PM, an all-day row, blocks by duration, a current-time line in ink. |
| BR57 | (Owner) Record-date sources: one module and one date field, up to 5 per board and 5 per person, saved on the server (BE8); a viewer sees only sources they can read. |
| BR58 | (Owner) Card due dates as a source: "Cards · Due" per board and "My cards · Due" on My calendar. |
| BR59 | Phones: Month is a compact grid with colored dots; Week is a day list; phones open on today's day list. |
| BR60 | (Owner) One Kanban per board, with stages and cards that belong to the board. |
| BR61 | Stages are managers only: rename, color, WIP limit, move, sort, archive. Over the limit the count reads "9 / 8" in warn. |
| BR62 | (Owner) Cards are objectives or record cards; writers add, edit, move and archive them; readers view. |
| BR63 | A record card shows module, name, up to two fields and a status chip. A viewer who cannot read the record sees a locked card with no name. |
| BR64 | An objective opens a card sheet; a record card opens the shared record sheet with an "On this board" tab first. |
| BR65 | A Kanban move saves at once with an Undo toast; Gantt drags are staged with Save changes. |
| BR66 | The Kanban surface reads the canvas tokens through its own skin place, `data-skin="board-surface"`. |
| BR67 | Kanban readability: stage header with dot, name, count; cards with no field labels; 25 cards then pages of 25; keyboard drag (WCAG 2.5.7). |
| BR68 | Kanban toolbar: search, people, Labels, Due, Group by (swimlanes); filters are in the URL. |
| BR69 | Stage and label colors use the chart series `--chart-1` to `--chart-5`. |
| BR70 | Labels are board-defined: managers edit them; writers apply them. |
| BR71 | Phone Kanban: one stage at a time with a stage switcher; no drag. |
| BR72 | (Owner) Gantt columns are dates: a month row and a week row; zoom Week, Month, Quarter (default Quarter). |
| BR73 | (Owner) Gantt rows are cards, grouped with a summary bar per group; no text inside card bars. |
| BR74 | (Owner) A bar takes its first label color; a darker leading segment shows checklist progress; every bar edge holds 3:1. |
| BR75 | Gantt behavior: today line, drag or keyboard to move and resize (staged), an Unscheduled list. |
| BR76 | Phone Gantt: the panel scrolls sideways inside; 120px sticky names; Month zoom; bars are not targets. |
| BR77 | (Owner) OpenView keeps Table, Grid, Gallery; `layout=kanban|calendar|timeline` opens Table. Supersedes DA11, DA20, OD4 and OD8. |
| BR78 | (Owner) Saved views of the removed layouts are deleted by a migration (data safety B). |
| BR79 | Boards never change a record by drag; a record card's stage and dates belong to the board. |
| BR80 | Every reader sees Kanban and Gantt; with no stages, managers see a setup state and others see "No stages yet". |
| BR81 | Card activity reads the audit log, not a new table. |
| BR82 | Board settings gains no Kanban or Gantt settings. |
| BR83 | The OpenView record sheet is shared, not copied (`frontend/src/components/systems/shared/components/record-sheet.tsx`). |
| D1 | (Owner, final review) Board groups save at once, with Undo on Remove. |
| D2 | (Owner, final review) One set of level words: Read, Post, Manager. |

## Backend changes (approved)

| ID | Change |
| --- | --- |
| BE1 | Remove board widgets and portability end to end (data safety A). |
| BE2 | `GET /api/boards/occurrences` across the boards a person reads, with per-board limits; pages at 100. |
| BE3 | `next_occurrence` on the per-board occurrences read and in BE2 (366-day lookahead). |
| BE4 | No change needed: the board list already filters by department. |
| BE5 | Consequence: board Activity lists no past widget rows; Manage › Audit keeps them. |
| BE6 | Remove OpenView's Kanban, Calendar, Timeline and delete their saved views (data safety B). |
| BE7 | The board Kanban: `board_stages`, `board_cards`, `board_labels`, `board_card_labels`, `board_card_checklist_items`, card targets on attachments and record links, and their routes. Record card summaries are computed per viewer at read time. |
| BE8 | Record-date sources: `board_calendar_sources` with `/api/boards/{board_id}/calendar-sources` and `/api/me/calendar-sources`. |

## Phases

| Phase | Content |
| --- | --- |
| P0 | Backend: BE1 with FN1, BE2, BE3, BE7, BE8 |
| P1 | Sidebar and header: BR1–BR5, BR6, BR7, BR9, BR41, BR47, BR50, BF-7, All boards; cold Comms budget 548,000 |
| P2 | Posts: BR10–BR15, BR38 |
| P3 | Calendar and My calendar: BR16, BR19–BR22, BR35, BR43, BR44, BR51–BR59, FN2 |
| P4 | Kanban and Gantt (BR60–BR76, BR79–BR83) and the OpenView removal (BE6, BR77, BR78), in sub-phases P4a, P4b, P4c, P4d |
| P5 | Board settings: BR26–BR30, BR34, BR37, BR82 |
| P6 | Phones, words, review |

## Acceptance criteria

| ID | Criterion | Result |
| --- | --- | --- |
| EXIT-1 | No document scroll at 1280×720 or 1440×900 on any tab, My calendar or All boards. | not recorded |
| EXIT-2 | Slim controls from 1280px (four named exceptions); 44px targets and no page sideways scroll at 390. | not recorded |
| EXIT-3 | No request to a removed route; FN1 holds for every role. | not recorded |
| EXIT-4 | Every removed capability has a home or a recorded removal; every preserved URL works. | not recorded |
| EXIT-5 | Cold Comms JavaScript under 548,000 gzip bytes locally and in CI. | not recorded |
| EXIT-6 | OpenView lists three layouts; the migration test shows no saved view of the removed layouts. | not recorded |
| EXIT-7 | Readability of Month, Kanban and Gantt as specified. | not recorded |
| EXIT-8 | A critique scores at least 28/40 with no P1. | met (30/40, no P1) |
| EXIT-9 | Each finding has a failing-first test or a recorded reason; focused batches pass. | not recorded |
| EXIT-10 | A release smoke pass on a fresh organization and on Harbor finds no blocking defect. | not recorded (smoke-pass decisions of 2026-10-27 are in the full text) |
| EXIT-11 | The owner approves the result in the live app. | met (2026-10-27) |

## Open items

Deferred after the final critique (2026-10-27):

- Upcoming facts column and heading polish; weekend and all-day tints in dark looks; the project meta line is a constant, not the group count (BR45).
- Skeleton layout, Activity row alignment on phones, setup primary position.
- No people filter in the phone Kanban Filters sheet.
- Find a record finds nothing in a module with no title field.
- The glossary, DESIGN.md and the shared purge review still say "permanently delete"; Boards says "Delete forever" (owner decision, separate change).
- A sticky phone save bar for a long Gantt (BR76) is a later decision.
