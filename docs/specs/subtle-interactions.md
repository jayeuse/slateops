# Subtle interactions: fewer steps in daily record work

> **Status: done (2026-11-13), PR #110.** Build approved by APR-0003 (extension). Pull request 4 of the UX friction pass; it builds on `ux-friction-pass.md`. Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/subtle-interactions.md`.

## Outcome

Nine small interactions remove steps in daily record work: a Choice value menu, New record with the filter values, "Create and add another", "Me" first in person pickers, a change of many selected rows, dashboard figures that open their records, file drop and paste, quick card dates, and delete with Undo. No backend change, no migration, no new route. List changes use the existing `POST /api/records/batch-update` through `frontend/src/components/systems/openview/adapters/record-batch-api.ts`. Main code: `openview/domain/record-batch-change.ts`, `create-starting-values.ts`, `widget-records-link.ts`, `openview/components/record-selection-bar.tsx`, `frontend/src/lib/file-drop.ts`.

**Who.** The accounts of `ux-friction-pass.md` "Who". A **writer** here is anyone with Write on the open module. A **view manager** has the meaning of `ux-friction-pass.md`. Candidate numbers 1–9 are the ranks of the candidate file.

## Decisions

ID | Decision
--- | ---
OD6 | Changed (APR-0003 extension): the whole row opens the record, except a Choice list value, which opens its menu (SI-1.1). `openview-relayout.md` and `openview-department-pages.md` point here.
Delete question | Not a decision change: the OpenView record sheet deletes with Undo and no question. The Boards card sheet keeps its question.
Decisions needed | None. Requirements limit each unsafe or inexact case (SI-0.1, SI-1.5, SI-5.6, SI-6.2, SI-7.3, SI-9.4).

## Rules for every candidate

- SI-0.1 **Exact result only.** Only applied conditions count (UF-3.1). Candidates 1 and 6 act only with "All conditions" or no condition; a candidate 6 link may set "All conditions" when the widget has at most one condition. Candidate 2 acts with "All conditions" or exactly one condition.
- SI-0.2 **Undo.** A status names the change with Undo until the next action, with no timer. Undo writes back only what the change did; a record changed again is reported, not overwritten. For candidates 1 and 5, Undo is a second change (History and triggers run). For candidate 9, Undo is a Restore (no trigger, no notice).
- SI-0.3 **Access.** Write controls show only with Write on the module, never on a deleted record. The server checks Write per record.
- SI-0.4 **Reach.** Every control has a name, keyboard path, focus ring, and a 44 px target at 390 px. Nothing is gesture-only.
- G1 to G6 of `ux-friction-pass.md` apply.
- G7 **One status place per surface.** List changes report in the module page meta-line status (as DR-6.1); sheet changes in the record header meta line (as DR-2.5); dialog changes at the top of the dialog. From 640 px to 1279 px the list status stays in normal flow and may wrap, so Undo stays reachable.
- G8 **Undo lasts until the next action, with no timer** (SI-0.2, DR-2.6).

## Preserved behavior

- Readers and guests never get a change control. Guests stay capped at Read. Server refusal is the source of truth.
- Saved views stay shared and saved only by view managers (DA12, DA13).
- One record event per changed record, per change and per Undo; delete and Restore run none.
- `ux-friction-pass.md` "Preserved behavior", item 2 and item 6 stay.

## Acceptance criteria

"Met" means: in the stated scope of PR #110. Accounts are the Harbor testing accounts at 1440×900 unless stated.

ID | Req | Criterion | Result
--- | --- | --- | ---
SI-C1.1 | SI-1.1, SI-1.2 | "Show only Former" from a Status value filters; no "Unsaved changes" for non-managers. | met
SI-C1.2 | SI-1.1 | The rest of the row opens the record. | met
SI-C1.3 | SI-1.2 | A manager sees "Unsaved changes" and Save view. | met
SI-C1.4 | SI-1.2 | Back removes the condition. | met
SI-C1.5 | SI-0.1, SI-1.2 | With "Any condition", "Show only" is not offered. | met
SI-C1.6 | SI-1.1 | Phone chip menu opens by tap and keyboard; 44 px. | met
SI-C1.7 | SI-1.3, SI-1.4 | "Change Status to" sends one `batch-update` item; status with Undo. | met
SI-C1.8 | SI-0.2, SI-1.4 | Undo restores the value; History shows two changes. | met
SI-C1.9 | SI-1.5 | A stale list change is refused; the row shows the newer value. | met
SI-C1.10 | SI-0.2, SI-1.5 | A stale Undo is refused; nothing is overwritten. | met
SI-C1.11 | SI-1.5 | `forbidden` or `invalid` shows the stored value and reason; no Undo. | met
SI-C1.12 | SI-1.6, SI-0.3 | Reader and guest get only "Show only". | met
SI-C1.13 | SI-1.3 | A required field has no "None"; the current value sends nothing. | met
SI-C2.1 | SI-2.1 | New record starts with the filter value. | met
SI-C2.2 | SI-2.2 | A User field starts with the signed-in person only. | met
SI-C2.3 | SI-0.1, SI-2.3 | "Any condition" or an incomplete condition gives no starting value. | met
SI-C2.4 | SI-2.4 | An untouched dialog closes with no question. | met
SI-C2.5 | SI-2.1, SI-0.4 | The phone dialog gets the starting value. | met
SI-C3.1 | SI-3.1, SI-3.2 | "Create and add another" keeps the dialog open with "<Title> created.". | met
SI-C3.2 | SI-3.2 | "Open record" opens the created record. | met
SI-C3.3 | SI-3.4 | Records made in the dialog show as "New" rows; hidden ones are counted in the status. | met
SI-C3.4 | SI-3.3 | A failed save keeps the typed values. | met
SI-C3.5 | SI-3.5 | No question after a create with nothing typed. | met
SI-C3.6 | SI-3.1, SI-0.4 | Keyboard path; 44 px at 390 px. | met
SI-C4.1 | SI-4.1, SI-4.3 | "Me (<name>)" is first and not listed twice. | met
SI-C4.2 | SI-4.2 | The Kanban assignee picker offers "Me". | met
SI-C4.3 | SI-4.1 | No "Me" when the person cannot be assigned. | met
SI-C4.4 | SI-0.3 | Reader and guest get no picker. | met
SI-C5.1 | SI-5.1, SI-5.2, SI-5.3 | Click, Shift-click and keyboard select rows; Choice list and Checkbox actions only. | met
SI-C5.2 | SI-5.4, SI-5.5 | The final action counts only records that change ("Change 8 records"); one batch. | met
SI-C5.3 | SI-5.6, SI-0.2 | Undo puts back each record's own value. | met
SI-C5.4 | SI-5.6 | A record changed by someone else is reported and kept. | met
SI-C5.5 | SI-5.6, SI-0.2 | Undo skips a record changed again. | met
SI-C5.6 | SI-5.6 | `forbidden` and `invalid` items are listed with reasons. | met
SI-C5.7 | SI-5.7 | The selection clears on page or filter change. | met
SI-C5.8 | SI-5.1, SI-0.3 | No selection for reader, guest, or the Deleted filter. | met
SI-C5.9 | SI-5.1 | Phone selection with visible 44 px controls. | met
SI-C6.1 | SI-6.1, SI-6.4 | A Number figure opens records whose count equals it. | met
SI-C6.2 | SI-6.2, SI-6.4 | A group row, the empty group included, opens its records. | met
SI-C6.3 | SI-0.1, SI-6.2 | "Any condition" with two conditions gives plain text. | met
SI-C6.4 | SI-6.3 | A records widget row opens its record. | met
SI-C6.5 | SI-6.5 | The link applies the person's own access; saved views unchanged. | met
SI-C6.6 | SI-6.1, SI-6.2, SI-0.4 | Keyboard and 44 px targets on a phone. | met
SI-C7.1 | SI-7.1 | A dropped file uploads on the Files tab. | met
SI-C7.2 | SI-7.2 | A pasted file uploads; pasted text stays text. | met
SI-C7.3 | SI-7.3 | Two files, or a file over 25 MB, upload nothing, with a reason. | met
SI-C7.4 | SI-7.4 | No upload without Write; the browser does not open the file. | met
SI-C7.5 | SI-7.1, SI-7.5 | The Kanban card Files tab takes a drop; the composer is unchanged. | met
SI-C7.6 | SI-7.5 | "Choose file" works at 390 px. | met
SI-C8.1 | SI-8.1, SI-8.2 | "Tomorrow" saves once. | met
SI-C8.2 | SI-8.3 | On a Monday, "Next Monday" is 7 days later. | met
SI-C8.3 | SI-8.2 | The current date sends nothing. | met
SI-C8.4 | SI-8.4, SI-0.3 | No quick dates for reader and guest. | met
SI-C8.5 | SI-0.4 | 44 px targets, no sideways scroll at 390 px. | met
SI-C9.1 | SI-9.1, SI-9.2 | Delete runs at once; "Record deleted." with Undo. | met
SI-C9.2 | SI-9.2, SI-0.2 | Undo calls restore. | met
SI-C9.3 | SI-9.3 | The record stays in the Deleted filter and restores. | met
SI-C9.4 | SI-9.4 | A refused Undo shows the reason; the record stays deleted. | met
SI-C9.5 | SI-9.5, SI-0.3 | No Delete for reader and guest. | met
SI-C9.6 | SI-9.5 | "Delete forever" keeps its review and password. | met
SI-C9.7 | SI-9.5 | The Kanban card sheet keeps "Delete this record?". | met
SI-C9.8 | SI-9.2, SI-0.4 | Phone keyboard delete and Undo stay in the sheet. | met

### Candidate 1: Choice cell menu (change or show only)

SI-1.1 to SI-1.6.

- DR-SI-1.1 From 768 px, a non-empty Choice list value in a cell is a button ("<Field>: <value>, options"); the rest of the row opens the record. An empty value is plain text.
- DR-SI-1.2 On a phone, each row adds one 44 px chip for the quick-filter field.
- DR-SI-1.3 The button opens a dropdown menu (Enter, Space, Arrow Down); Escape returns focus. Rows are 32 px from 1280 px, 44 px below.
- DR-SI-1.4 "Show only <value>" replaces every applied condition on that field and keeps the rest; for the quick-filter field it selects the chip. Left out under "Any condition" (SI-0.1).
- DR-SI-1.5 For a writer: "Change <Field> to" with radio options; "None" only for an optional field; the checked value sends nothing. With no item, the value is plain text.
- DR-SI-1.6 A pick sends one `batchUpdateOpenViewRecords` item with the row's `updatedAt` as revision; the row waits while it runs.
- DR-SI-1.7 `updated`: the row takes the returned record; the status reads "Status changed to Former." with Undo, also when the record leaves the list.
- DR-SI-1.8 Undo sends the previous value with the returned `updated_at`; a stale Undo reads "Not undone. Someone changed this record after you."
- DR-SI-1.9 Refusals change nothing and offer no Undo: `stale`, `forbidden`, `invalid` (names the server's field), and request failure each have their words.
- DR-SI-1.10 Only Choice list cells get the button; a User value keeps the person card.

### Candidate 2: New record starts with the filter values

SI-2.1 to SI-2.4.

- DR-SI-2.1 New record gets the applied definition; values apply only under "All conditions" or exactly one condition.
- DR-SI-2.2 A Choice list, Checkbox or User field takes the value of its single applied "is" condition; otherwise its default.
- DR-SI-2.3 A User field takes the value only when it is the signed-in person.
- DR-SI-2.4 Starting values are not changes for the create guard.
- DR-SI-2.5 No new words; the phone dialog is unchanged.

### Candidate 3: "Create and add another"

SI-3.1 to SI-3.5.

- DR-SI-3.1 Footer: Cancel, "Create and add another" (outline), Create (primary). Below 640 px they stack at full width, Create first.
- DR-SI-3.2 Same `createOpenViewRecord` request; both buttons disabled while it runs ("Creating…").
- DR-SI-3.3 Success resets the form to the starting values, focuses the first field, and shows "<Title> created." with "Open record".
- DR-SI-3.4 "Open record" closes the dialog and opens that record.
- DR-SI-3.5 Failure keeps the typed values; nothing is saved.
- DR-SI-3.6 On close, every record made goes through item 6 of `ux-friction-pass.md` (UF-6.2 to UF-6.4, DR-6.2 to DR-6.6); the status reads "<n> records created." and names how many are hidden.

### Candidate 4: "Me" first in person pickers

SI-4.1 to SI-4.3.

- DR-SI-4.1 In the record form User picker (Edit and New record), "Me (<name>)" is first after the empty choice; the person is not listed again.
- DR-SI-4.2 "Me" shows only when the assignable read returns the signed-in person.
- DR-SI-4.3 The Kanban assignee picker reads "Me (<name>)", "No one", then others; with search text, "Me" shows only when it matches.
- DR-SI-4.4 A pick of "Me" does what a pick of the name does; notices as before.
- DR-SI-4.5 Readers and guests have no picker.

### Candidate 5: change several selected rows (new structure; comp `selection.html`)

SI-5.1 to SI-5.7.

- DR-SI-5.1 A writer gets a checkbox column ("Select <title>", or "Select record") and a header box for the page. None for readers, guests or the Deleted filter.
- DR-SI-5.2 On a phone, each writer row starts with a 44 px checkbox; no long press.
- DR-SI-5.3 Click or Space toggles; Shift-click selects a range; a checkbox click never opens the record.
- DR-SI-5.4 With rows selected, the selection bar ("<n> selected", "Change", "Clear selection") takes the toolbar row's place in the same height; the rows do not move.
- DR-SI-5.5 "Change" lists the Choice list and Checkbox fields that are columns of the view's query.
- DR-SI-5.6 A field opens a popover with its values; the final button reads "Change <k> records", where k excludes rows that already hold the value. Nothing is sent before it.
- DR-SI-5.7 The final button sends one batch; selection covers the current page (at most 50), and over 100 is refused.
- DR-SI-5.8 The result names how many changed and lists each record that did not, with its reason.
- DR-SI-5.9 Undo sends only the `updated` records with their previous values; nothing is overwritten.
- DR-SI-5.10 The selection clears after a result and at a page, filter, sort, search or view change; a re-read keeps only rows still on the page.

### Candidate 6: open the records behind a dashboard figure

SI-6.1 to SI-6.5.

- DR-SI-6.1 A Number figure links to the module page with the widget's conditions and date window; its name is "Open the <figure> <module>".
- DR-SI-6.2 Each table group row links with the group's condition ("is <key>", or stored `empty` for the empty group).
- DR-SI-6.3 Links follow SI-0.1; with "Any condition" and one condition, the link sets "All conditions"; with two or more, rows stay plain text.
- DR-SI-6.4 A records widget row opens that record; its name starts with the visible cell text.
- DR-SI-6.5 The module page applies the person's own access; with no exact link, the menu reads "Open <module>".
- DR-SI-6.6 The date window becomes exact conditions in the workspace timezone (`gte`/`lte` for Date; local midnight bounds with offset for Date and time). No exact window, no link.

### Candidate 7: drop or paste a file to attach

SI-7.1 to SI-7.5.

- DR-SI-7.1 The record Files tab (shared record sheet) and the Files library take a dropped file where "Choose file" is offered, through the same checks and calls.
- DR-SI-7.2 A pasted file uploads when focus is in the panel, not in a text input.
- DR-SI-7.3 One file per drop or paste; nothing new uploads while an upload runs; size refusals match "Choose file".
- DR-SI-7.4 Without "Choose file" (reader, guest, deleted record) the panel takes nothing; a file dropped elsewhere on these pages is ignored.
- DR-SI-7.5 "Choose file" stays and is the phone path. Kanban, OpenComms composer and post drop targets do not change.

### Candidate 8: quick dates on Kanban cards

SI-8.1 to SI-8.4. DR-SI-8.1 "Today", "Tomorrow", "Next Monday" under each writer date input. DR-SI-8.2 One save through the existing `onSave`; the current date sends nothing. DR-SI-8.3 Dates follow the regional settings; on a Monday, "Next Monday" is 7 days later. DR-SI-8.4 None for readers and guests.

### Candidate 9: Undo in place of the delete question (OpenView)

SI-9.1 to SI-9.5.

- DR-SI-9.1 More record actions › Delete record deletes at once (`DELETE /api/records/{record_id}`) in the OpenView sheet. A prop sets this; the Boards card sheet keeps the question.
- DR-SI-9.2 The header meta line reads "Record deleted." with Undo, and focus moves to Undo.
- DR-SI-9.3 Undo calls `POST /api/records/{record_id}/restore`; a refusal shows the reason and the record stays deleted.
- DR-SI-9.4 Undo lasts as G8 says; then Restore works as before.
- DR-SI-9.5 Readers and guests get no Delete. "Delete forever" keeps its review and password.

## Open items

- Known limits from PR #110: from 640 px to 1279 px a list status can wrap; Forward after Back does not re-apply "Show only"; a file from 10 MiB to 25 MB passes the browser check and is refused by the server.
- Not in scope: selection and cell menus in grid, gallery, Kanban, Calendar and Gantt; Delete with Undo in the Boards card sheet.
