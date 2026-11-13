# Subtle interactions: fewer steps in daily record work

> **Status: Proposed 2026-11-12; build approved by APR-0003 (extension).** Requirements half by the Product Manager (TASK-0059). The Product Designer writes the design half under the headings marked "Product Designer". No product code has changed. This is pull request 4 of the UX friction pass; it builds on `ux-friction-pass.md`.

## Outcome

Staff who are not technical do frequent record work in fewer steps: filter by a value they see, change a value from the list, create several records in a row, assign themselves, change many rows at once, open the records behind a dashboard figure, attach a file by drop or paste, set a card date in one action, and delete with Undo instead of a question. Each interaction is reversible or read-only, and no access rule changes.

**The job.** When I work through a list of records during the day, I want to act on what I see where I see it, so I can finish the batch and move on. Emotional side: a quick action must never feel risky; a mistake is one Undo away. Social side: a change that I make for colleagues (many rows, a status) must not overwrite their newer work or send them notices by surprise.

**Who.** The account levels and accounts are those of `ux-friction-pass.md` "Who":

| Level | Account used in the criteria |
| --- | --- |
| Administrator | `admin@harbor.test` |
| Department manager (manage on Sales) | `sales.manager@harbor.test` |
| Writer | `sales.writer@harbor.test` |
| Reader | `sales.reader@harbor.test` |
| Guest | `sales.guest@harbor.test` |

A **writer** in this spec is any person with Write access to the open module (writer, a department manager in the department, an administrator). A **view manager** has the meaning of `ux-friction-pass.md`.

Candidate numbers 1–9 are the rank numbers of `.agent-runtime/ux-friction-pass/interaction-candidates.md` (Product Designer, 2026-11-12). Each candidate passed checks K1 to K7 there; this spec does not repeat the checks.

## Current state (observed 2026-11-12 on `feat/ux-records-list-and-panel`)

Code paths are under `frontend/src/` unless the row says otherwise.

| Candidate | Now | Source |
| --- | --- | --- |
| 1 | A Choice list cell is plain text. A click anywhere on the row opens the record (OD6). A filter on a value takes 5 actions (Filters, Add filter, Field, Value, close). | `openview-relayout.md` OD6; candidate file |
| 2 | The New record dialog starts from field defaults only, also when a filter "Status is Former" is applied. | `components/systems/openview/components/record-create-dialog.tsx` (`initialFormValues`) |
| 3 | Create saves and opens the new record sheet. Each further record needs New record again. | `record-create-dialog.tsx` (`createOpenViewRecord`) |
| 4 | Person pickers list the assignable people. The signed-in person must find their own name. | `record-form-fields.tsx` (`PersonSelect`); `components/systems/boards/components/board-card-fields.tsx` (`AssigneePicker`) |
| 5 | OpenView has no row selection. Each value change is one record at a time. `POST /api/records/batch-update` exists and no frontend code calls it. | `backend/app/systems/sandbox/records/batch_router.py`; `frontend/api-route-manifest.json` (no entry) |
| 6 | Dashboard figures, table group rows, and records widget rows are not links. The widget menu has "Open the records" (the widget's conditions as temporary changes). | `components/systems/openview/components/dashboard-widget-card.tsx` (`recordsHref`) |
| 7 | A file is attached only through "Choose file" and the system file picker. Uploads run one at a time. The record Files tab is shared by the OpenView record sheet and the Boards record card sheet. | `record-files-panel.tsx` (`upload`, `operation.current`); `components/systems/shared/components/record-sheet.tsx`; `components/systems/platform/components/files.tsx` |
| 8 | A Kanban card date is set in the date input; it saves on blur or Enter. | `board-card-fields.tsx` (date row `commit`) |
| 9 | Delete record asks "Delete this record?" first. Delete is a soft delete; Restore exists; "Delete forever" has its own review and password. | `record-details-controls.tsx` (dialog, Restore, purge review); `backend/app/systems/sandbox/records/router.py` (`delete_record`, `restore_record`) |

Code facts that decide safety (verified 2026-11-12):

- `POST /api/records/batch-update` takes up to 100 items for one module. It checks Write on the module and Write on each record, refuses a deleted record, and checks each item's `revision` (the record's `updated_at`). It merges the named field into the stored values and keeps the other values. Each item reports `updated`, `stale`, `forbidden`, or `invalid`. For each changed record it enqueues one record event and the assignment notices, as a single change does (`batch_router.py:60-118`).
- A record event is enqueued only when a value changed (`record_triggers/outbox.py`, `enqueue_record_event`). A write of the same value runs no trigger.
- Delete and Restore need Write on the record. Neither enqueues a record event or a notice (`router.py:348-390`). Restore checks the stored values against the module fields and can be refused.
- View and widget conditions can be combined with "All conditions" (`and`) or "Any condition" (`or`) (`saved-view-filter-controls.tsx`, `chart-filter-controls.tsx`, `query.py:268`). With "Any condition", one more condition widens the result.
- The largest table page size is 50 (`components/ui/table-pagination.tsx`, `TABLE_PAGE_SIZE_OPTIONS`).
- "Read-only" on a record sheet means that the person has no Write on the module (`server-backed-views-workspace.tsx`); there is no per-record read-only flag.

## Requirements

Priority: P0 = the candidate is not solved without it. Requirements state outcomes; the Product Designer decides layout, controls, and exact words unless a requirement quotes them. No requirement needs a backend or API change.

### Rules for every candidate

| ID | Applies to | Pri | Required |
| --- | --- | --- | --- |
| SI-0.1 | 1, 2, 6 | P0 | **Exact result only.** Only applied conditions count (UF-3.1). An interaction that adds a condition (1, 6) acts only when the applied conditions use "All conditions" or there is no applied condition; a candidate 6 link may set "All conditions" in its temporary changes when the widget has at most one condition. An interaction that reads a value from the conditions (2) acts when they use "All conditions" or there is exactly one. Otherwise the interaction is not offered (1, 6) or does not apply (2). |
| SI-0.2 | 1, 5, 9 | P0 | **Undo.** After the change, a status names it and offers Undo. Undo stays offered until the person's next action on the page or sheet, with no timer. Undo writes back only what this change did: each record's own previous value, only for the records that this change updated, with the revision from the change's response. A record that changed again after that is reported and not overwritten. For candidates 1 and 5, Undo is a second change: History shows it and triggers run for it as for any change. For candidate 9, Undo is a Restore and runs no trigger and sends no notice, as Restore does now. |
| SI-0.3 | 1, 3, 4, 5, 7, 8, 9 | P0 | **Access.** A control that writes shows only to a person with Write on the module, and never on a deleted record. Readers and guests get no write control (guests stay capped at Read). The server checks Write per record; a refusal from the server shows its reason and changes nothing. |
| SI-0.4 | all | P0 | **Reach.** Each new control has a visible label or an accessible name, a keyboard path, a visible focus ring, and a target of at least 44 px at 390 px. No interaction is gesture-only or drag-only: each drop or Shift-click has a visible equivalent. |

### Per candidate

| ID | Cand. | Pri | Required |
| --- | --- | --- | --- |
| SI-1.1 | 1 | P0 | In the table layout and in its phone cards, a Choice list value (a table cell, the status chip on a card) opens a small menu. A click on any other part of the row still opens the record. The keyboard reaches the value; Enter or Space opens the menu; Escape closes it and returns focus to the value. |
| SI-1.2 | 1 | P0 | The menu's first item is "Show only <value>", for every level. It applies the condition "<Field> is <value>" as a filter change: the address holds it, browser Back removes it, and for the quick-filter field it selects that quick chip instead. It marks "Unsaved changes" only for a view manager (UF-1.1, UF-1.3). It is not offered for an empty value or when SI-0.1 does not hold. When the same condition is already applied, nothing changes. |
| SI-1.3 | 1 | P0 | For a writer, on a record that is not deleted, the menu also offers "Change <Field> to" with the field's options; the current value is marked. A required field offers no "None". A pick of the current value sends nothing. A pick of another value saves at once: one `batch-update` item with the record's revision. |
| SI-1.4 | 1 | P0 | After a saved change, the value shows in the row and the page status names it with Undo (SI-0.2). Undo stays offered also when the record no longer matches the filters and leaves the list. |
| SI-1.5 | 1 | P0 | A stale, forbidden, or invalid result changes nothing: the value shows the stored value, and the reason shows. Nothing is overwritten. |
| SI-1.6 | 1 | P0 | Readers and guests get only "Show only". No other field type (text, numbers, dates, user, relationship) changes from the list; a User field never changes from the list. |
| SI-2.1 | 2 | P0 | When New record opens, each applied condition "is <one value>" on a Choice list, Checkbox, or User field that shows in the form gives that field its starting value, under SI-0.1. Other fields keep their defaults. Nothing is saved before Create, and each value can be changed. |
| SI-2.2 | 2 | P0 | A User field takes a starting value only when the condition names the signed-in person. When it names someone else, the field starts empty, so no assignment notice goes out unseen. |
| SI-2.3 | 2 | P0 | An incomplete condition, a condition on a field that is not in the form, and a value that is no longer an option give no starting value. |
| SI-2.4 | 2 | P0 | Starting values count as unchanged for the create leave guard (UF-1.4): closing an untouched dialog asks nothing. |
| SI-3.1 | 3 | P0 | Beside Create, the New record dialog offers "Create and add another". It saves the record exactly as Create does (same request, checks, and triggers). Create keeps opening the new record sheet. |
| SI-3.2 | 3 | P0 | After "Create and add another" succeeds, the dialog stays open with the starting values of SI-2.1 (or the defaults), focus in the first field, and a status "<Title> created." with "Open record". "Open record" closes the dialog and opens that record. |
| SI-3.3 | 3 | P0 | When a save fails, the typed values stay, the error shows as for Create, and nothing is saved. |
| SI-3.4 | 3 | P0 | When the dialog closes, each record created in it shows under the item 6 rules of `ux-friction-pass.md` (UF-6.2 to UF-6.4, DR-6.2 to DR-6.6): every record that matches shows as a "New" row; the count stays the server total; each record counts once. |
| SI-3.5 | 3 | P0 | After a create, the leave guard counts only values typed after it. |
| SI-4.1 | 4 | P0 | In the record form (the Edit form and New record) a User field picker lists "Me (<name>)" first when the signed-in person can be assigned. The person is not listed a second time. When the person cannot be assigned, there is no "Me". |
| SI-4.2 | 4 | P0 | In the Kanban card sheet, the assignee picker does the same. While search text is typed, "Me" shows only when it matches the person's name. |
| SI-4.3 | 4 | P0 | Picking "Me" has the same result as picking the person's name: the form fills (the card saves on pick, as now). Notices go out as now. |
| SI-5.1 | 5 | P0 | In the table layout, a writer gets one selection checkbox per row (accessible name "Select <title>") and one to select all rows on the page. Readers, guests, and the Deleted filter get no selection. On a phone, each card has a visible way to select it; selection does not depend on a long press. |
| SI-5.2 | 5 | P0 | Space toggles a row. Shift-click selects a range; the keyboard has an equivalent for a range or for the whole page. |
| SI-5.3 | 5 | P0 | With rows selected, the toolbar shows the count, "Clear selection", and one change action for each Choice list and Checkbox field. No other field type is offered; User fields are excluded because a change notifies people. |
| SI-5.4 | 5 | P0 | The change asks for the value, then the final action states the number of selected records that will change, that is, without the records that already hold the value (for example "Change 8 records" when 10 are selected and 2 already hold it). Nothing is sent before that action. A required field offers no "None". |
| SI-5.5 | 5 | P0 | The change sends one `batch-update` with each selected record and its revision. Records that already hold the value are not sent. Selection covers the rows shown on the current page only. One request never holds more than 100 records; a selection larger than that cannot be changed and says so. |
| SI-5.6 | 5 | P0 | The result states how many records changed and lists each record that did not change with its reason (changed by someone else, no access, not valid or deleted). Nothing is overwritten. Undo follows SI-0.2 and puts back every record that changed. |
| SI-5.7 | 5 | P0 | The selection clears after a change, and when the page, filters, sort, search, or view change, or the person leaves the page. |
| SI-6.1 | 6 | P0 | On a department dashboard, the figure of a Number widget is a link to the module page with the widget's conditions, and its date window when it has one, as temporary changes. A widget whose window cannot be carried exactly has no link (DR-SI-6.6). Its accessible name states the figure and what it counts. |
| SI-6.2 | 6 | P0 | Each group row of a table widget is a link to that group's records: the widget's conditions plus the group's condition ("is <value>"; the stored operator `empty` for the empty group, which is SQL NULL only), plus the widget's date window as in SI-6.1. A row whose group cannot be stated exactly, or a widget where SI-0.1 does not hold, stays plain text. |
| SI-6.3 | 6 | P0 | Each row of a records widget opens that record. |
| SI-6.4 | 6 | P0 | For a count, the record count on the module page equals the figure or the group row when the data did not change in between. |
| SI-6.5 | 6 | P0 | The link applies no access: the module page applies the person's own access, as now. The changes are temporary; saved views do not change, and "Unsaved changes" follows UF-1.1 and UF-1.3. The widget menu item stays. |
| SI-7.1 | 7 | P0 | On the record Files tab (the shared record sheet: the OpenView record sheet and the Boards record card sheet) and in the Files library, a file dropped on the panel uploads through the same checks and the same calls as "Choose file". While a file is over the panel, the panel shows that a drop attaches it. |
| SI-7.2 | 7 | P0 | A file pasted while focus is in the panel, and not in a text input, uploads the same way. Text pasted into a text input stays text. |
| SI-7.3 | 7 | P0 | One file per drop or paste. When several files come, or an upload already runs, nothing new uploads and a message says why. A file type or size that "Choose file" refuses is refused with the same message. |
| SI-7.4 | 7 | P0 | Where "Choose file" is not available (no Write, a deleted record, reader, guest), the panel takes no drop and nothing uploads. On these pages, a file dropped anywhere does not open in the browser or leave the page. |
| SI-7.5 | 7 | P0 | "Choose file" stays, and it is the path at 390 px. Existing drop targets (Kanban, the OpenComms composer, post attachments) do not change. |
| SI-8.1 | 8 | P0 | In the Kanban card sheet, each date row of a writer offers "Today", "Tomorrow", and "Next Monday". |
| SI-8.2 | 8 | P0 | One pick sets the date and saves it once through the existing card save, as a changed date input does. A pick of the current date sends nothing. The existing save checks apply. |
| SI-8.3 | 8 | P0 | The dates come from the person's regional settings, as the calendar's "Today" does. "Next Monday" is the first Monday after today; on a Monday it is 7 days later. |
| SI-8.4 | 8 | P0 | Readers and guests get no quick dates; their date rows read as now. |
| SI-9.1 | 9 | P0 | In the OpenView record sheet, More record actions › Delete record deletes at once with the existing request `DELETE /api/records/{record_id}`. No question shows. |
| SI-9.2 | 9 | P0 | The status reads "Record deleted." with Undo (SI-0.2). Undo uses the existing request `POST /api/records/{record_id}/restore`. Keyboard focus stays in the sheet, and Undo is reachable at once. |
| SI-9.3 | 9 | P0 | After the delete, the sheet shows the deleted record as now (Deleted badge, Restore). The record stays in the Deleted filter and can be restored later. |
| SI-9.4 | 9 | P0 | When Undo is refused (for example, Restore finds a value that a closed field no longer accepts), the reason shows, the record stays deleted, and Restore stays. |
| SI-9.5 | 9 | P0 | Readers and guests get no Delete, as now. "Delete forever" keeps its review and password. The Boards record card sheet, which shows the same record controls, keeps its current delete question. |

## Changed decisions

On 2026-11-12 the Human Owner was told, for candidate 1: "one small menu on the cell with a keyboard path and a full-size touch target; a click on the row still opens the record", and struck no candidate (APR-0003 extension). The candidate the Human Owner accepted is itself "click a choice value in a row", and people values in a row already open the person card instead of the record, so the parent confirmed the row below on 2026-11-12 as part of that acceptance. No other decision changes.

| Decision | Source | Old rule | New rule | Approval |
| --- | --- | --- | --- | --- |
| OD6 | `openview-relayout.md:160`; `openview-department-pages.md:73` | "The whole row opens the record." | The whole row opens the record, except a Choice list value, which opens its menu (SI-1.1). | APR-0003 (extension), 2026-11-12; confirmed by the parent as part of candidate 1 |

Not a decision change: the "Delete this record?" question (candidate 9) is in no spec decision; it is a current build detail.

## Preserved behavior

- Access: readers and guests never get a change control; the server checks Write per record; guests stay capped at Read; an unreadable module stays hidden; a server refusal stays the source of truth.
- Saved views stay shared and are saved only by view managers (DA12, DA13). The view state stays in the address.
- Triggers and notices run as for any change: one record event per changed record, per change and per Undo; delete and Restore run none.
- Owner decisions listed in `ux-friction-pass.md` "Preserved behavior", including the publish password, "module", and one dashboard per department. Kanban, Calendar, and Gantt stay in Boards.
- Item 2 of `ux-friction-pass.md` (in-place change in the sheet, User fields through Edit) and item 6 (the "New" row).
- Create, Edit, Restore, Delete forever, and Choose file keep their current requests and checks.

## Not in scope

- The candidates dropped in the candidate file: chart slice links, focus return after the sheet closes, calendar day click, OpenComms paste and Up to edit, Kanban multi-line paste, keyboard-only shortcuts, per-person layouts, pasted email lists, and Sandbox Build additions.
- Any backend or API change. Any reversed decision other than the OD6 row above. Any access change.
- Changes to Sandbox Build.
- Drag-only interactions with no visible path.
- Selection and cell menus in the grid, gallery, Kanban, Calendar, and Gantt layouts; bulk change of field types other than Choice list and Checkbox.
- Delete with Undo in the Boards card sheet, and for other objects (posts, files, people).

## Decisions needed

None. Each candidate fits inside the limits. Where a candidate could give an inexact result or an unsafe write, a requirement limits it instead (SI-0.1, SI-1.5, SI-5.6, SI-6.2, SI-7.3, SI-9.4).

## Acceptance criteria

Check each criterion on the live development stack with the Harbor testing accounts at 1440×900, unless the row says otherwise. "Contacts" is Sales › Contacts with the Choice list field Status; "a Checkbox field" is any Checkbox field of that module; "a Kanban board" is a Sales board with a card that has date and assignee fields. Where a row cannot be set up by hand, it names the test level.

| ID | Req | Account | Given | When | Then | Must not break |
| --- | --- | --- | --- | --- | --- | --- |
| SI-C1.1 | SI-1.1, SI-1.2 | Writer, reader, guest | Contacts, default view | Click the Status value "Former" in a row; pick "Show only Former" | The list shows only Former records; the address holds the condition; no "Unsaved changes" mark. | UF-1.1: no view write request. |
| SI-C1.2 | SI-1.1 | Writer | Contacts | Click the title or another cell of a row | The record sheet opens. | OD6 for the rest of the row. |
| SI-C1.3 | SI-1.2 | Department manager | Contacts | "Show only Former" from a Status value | The list filters; "Unsaved changes" and Save view show. | UF-1.3, DA12. |
| SI-C1.4 | SI-1.2 | Writer | SI-C1.1 done | Press browser Back | The list shows all records again. | Address view state. |
| SI-C1.5 | SI-0.1, SI-1.2 | Writer | Contacts with "Any condition" and two applied conditions; then with one applied condition | Open a Status value menu each time | "Show only" is not offered in either case. | No widened result. |
| SI-C1.6 | SI-1.1 | Writer, 390×844 | Contacts as phone cards | Tap a card's status chip; then use Tab and Enter on another card's chip | The menu opens both ways; the chip target is at least 44 px. | The card body still opens the record. |
| SI-C1.7 | SI-1.3, SI-1.4 | Writer | A Contacts record with Status "Active" | Status value › Change Status to › "Former" | One `batch-update` request with one item; the row shows "Former"; the status names the change with Undo; after reload Status is "Former". | No record sheet opened. |
| SI-C1.8 | SI-0.2, SI-1.4 | Writer | SI-C1.7 done, with "Status is Active" applied (the record leaves the list) | Press Undo | After reload Status is "Active"; History shows two changes; a trigger on Status change ran twice. | Triggers once per change and once per Undo. |
| SI-C1.9 | SI-1.5 | Two writers | Both list Contacts | A changes a record's Status in the sheet; B changes the same record's Status from the list | B's change is refused; B's row shows A's value and the reason. | A's value stays. |
| SI-C1.10 | SI-0.2, SI-1.5 | Two writers | B changed a Status from the list | A changes that record again; B presses Undo | Undo is refused with the reason; the record keeps A's value. | No overwrite at Undo. |
| SI-C1.11 | SI-1.5 | — (http test level) | The server returns `forbidden` or `invalid` for the item | A writer picks a value | The value shows the stored value and the reason; no Undo shows. | Server refusal is the source of truth. |
| SI-C1.12 | SI-1.6, SI-0.3 | Reader, guest | Contacts | Open a Status value menu | Only "Show only" shows; no change request can be sent. | Guest cap at Read. |
| SI-C1.13 | SI-1.3 | Writer | A required Choice list field | Open its value menu | No "None" in "Change to"; a pick of the current value sends no request. | Required-field rule. |
| SI-C2.1 | SI-2.1 | Writer | Contacts with "Status is Former" applied | New record | Status starts as "Former"; other fields start at their defaults; no request before Create. | UF-3.1: only applied conditions. |
| SI-C2.2 | SI-2.2 | Writer | A module with a User field; condition "<User field> is <the writer>"; then "is <another person>" | New record each time | First: the field starts with the writer. Second: the field starts empty. | No assignment notice before Create. |
| SI-C2.3 | SI-0.1, SI-2.3 | Writer | "Status is Former" plus another condition joined by "Any condition"; then an incomplete condition | New record each time | No starting value from the conditions in either case. | Field defaults. |
| SI-C2.5 | SI-2.1, SI-0.4 | Writer, 390×844 | Contacts with "Status is Former" applied | New record | Status starts as "Former" in the phone dialog. | The dialog layout as now. |
| SI-C2.4 | SI-2.4 | Writer | SI-C2.1 with nothing typed | Close the dialog | It closes with no question. | UF-1.4: a typed value still asks. |
| SI-C3.1 | SI-3.1, SI-3.2 | Writer | Contacts, New record with a title | Press "Create and add another" | The dialog stays open with starting values and focus in the first field; "<Title> created." with "Open record" shows. | Create still opens the sheet. |
| SI-C3.2 | SI-3.2 | Writer | SI-C3.1 done | Press "Open record" | The dialog closes; the created record's sheet opens. | — no other record is created. |
| SI-C3.3 | SI-3.4 | Writer | Three records created with "Create and add another", one of them hidden by the applied filter | Close the dialog | The two matching records show as "New" rows; the status says one is hidden by the filters; the count is the server total. | UF-6.4: each record counted once. |
| SI-C3.4 | SI-3.3 | Writer | New record with a required field empty | Press "Create and add another" | The error shows; the typed values stay; no record is created. | Create validation. |
| SI-C3.6 | SI-3.1, SI-0.4 | Writer, 1440×900 and 390×844 | New record with a title | Tab to "Create and add another" and press Enter | The record is created as in SI-C3.1; the button target is at least 44 px at 390 px. | Create stays the primary. |
| SI-C3.5 | SI-3.5 | Writer | SI-C3.1 done, nothing typed after it | Close the dialog | It closes with no question. | UF-1.4. |
| SI-C4.1 | SI-4.1, SI-4.3 | Writer | A record with a User field, in Edit | Open the picker; pick "Me (<name>)"; Save changes | "Me (<name>)" is first and the name is not listed again; after save the field shows the writer. | Edit and Save for User fields (UF-2.4). |
| SI-C4.2 | SI-4.2 | Writer, 390×844 | A Kanban card the writer can edit | Open the assignee picker; pick "Me" with the keyboard | The card's assignee is the writer after reload; the option target is at least 44 px. | Card save and notices as now. |
| SI-C4.3 | SI-4.1 | Writer | A User field whose assignable people exclude the writer | Open the picker | No "Me" option. | Assignable list from the server. |
| SI-C4.4 | SI-0.3 | Reader, guest | The same record and card | Open them | No picker and no "Me". | Read-only views as now. |
| SI-C5.1 | SI-5.1, SI-5.2, SI-5.3 | Writer | Contacts, 10 rows on the page | Check row 1; Shift-click row 10; then repeat with the keyboard only | 10 rows selected in both ways; the toolbar shows "10 selected", "Clear selection", and change actions for Choice list and Checkbox fields only. | No User field action. |
| SI-C5.2 | SI-5.4, SI-5.5 | Writer | SI-C5.1, 2 of the 10 already "Former" | Change Status › "Former" | The final action reads "Change 8 records"; nothing was sent yet. When pressed: one `batch-update` with 8 items; after reload all 10 are "Former". | Records' other values unchanged. |
| SI-C5.3 | SI-5.6, SI-0.2 | Writer | SI-C5.2 done | Press Undo | One `batch-update` puts each of the 8 records back to its own previous value; the 2 that were already "Former" stay. A Status trigger ran once per record for the change and once per record for Undo. | Triggers once per change and per Undo. |
| SI-C5.4 | SI-5.6 | Two writers | A selected 5 records | B changes one of them in its sheet; A applies a bulk change | 4 change; the result names the fifth as changed by someone else; it keeps B's value. | No overwrite. |
| SI-C5.5 | SI-5.6, SI-0.2 | Two writers | A bulk change of 5 records is done | B changes one of them; A presses Undo | 4 go back; the fifth is reported and keeps B's value. | No overwrite at Undo. |
| SI-C5.6 | SI-5.6 | — (http test level) | The server returns `forbidden` and `invalid` items in one response | A writer applies a bulk change | Each such record is listed with its reason; Undo covers only the updated records. | Server per-record Write check. |
| SI-C5.7 | SI-5.7 | Writer | Rows selected | Go to the next page; then change a filter | The selection is clear after each. | Pager and filters as now. |
| SI-C5.8 | SI-5.1, SI-0.3 | Reader, guest; writer with the Deleted filter | Contacts | Look at the table | No selection checkboxes. | Guest cap at Read. |
| SI-C5.9 | SI-5.1 | Writer, 390×844 | Contacts as phone cards | Select two cards with visible controls; change a Checkbox field | Both change; every control is at least 44 px; no long press was needed. | Card body still opens the record. |
| SI-C6.1 | SI-6.1, SI-6.4 | Writer | Sales dashboard with a Number widget that counts records, one without and one with a date window | Click the figure | The module page opens with the widget's conditions; its record count equals the figure. | The widget menu's "Open the records" stays. |
| SI-C6.2 | SI-6.2, SI-6.4 | Writer | A table widget grouped by Status, with an empty group | Click "Former" and the empty group in turn | Each list count equals its row figure. | Widget queries unchanged. |
| SI-C6.3 | SI-0.1, SI-6.2 | Administrator | A table widget with "Any condition" and two conditions; then one with "Any condition" and one condition | Read the group rows; open a group row of the second | First: plain text, not links. Second: a link whose temporary changes use "All conditions"; the count equals the row. | No widened result. |
| SI-C6.6 | SI-6.1, SI-6.2, SI-0.4 | Writer, 390×844 | Sales dashboard | Tab to a Number figure and press Enter; go back; tap a group row | Each opens its records; each target is at least 44 px. | One dashboard per department. |
| SI-C6.4 | SI-6.3 | Writer, 390×844 | A records widget | Tab to a row and press Enter; tap another | Each opens its record; targets at least 44 px. | — the dashboard layout does not change. |
| SI-C6.5 | SI-6.5 | Reader, guest | A dashboard figure link | Open it | The module page shows only what the account can read; no "Unsaved changes"; the saved view is unchanged. | Access as now; DA12. |
| SI-C7.1 | SI-7.1 | Writer | A Contacts record, Files tab | Drag a PDF over the panel; drop it | The panel shows that a drop attaches it; the file uploads and is listed. | Same upload checks as Choose file. |
| SI-C7.2 | SI-7.2 | Writer | Files library, focus in the panel; then focus in a text input | Paste a copied file; paste text | The file uploads; the text goes into the input. | Text paste. |
| SI-C7.3 | SI-7.3 | Writer | Files tab | Drop two files; then drop a file over 25 MB | Nothing uploads in both cases; a message says why each time. | Size and type checks. |
| SI-C7.4 | SI-7.4 | Reader, guest; writer on a deleted record | Files tab and Files library | Drop a file on the panel and beside it | Nothing uploads; the browser does not open the file; the page stays. | No upload without Write. |
| SI-C7.5 | SI-7.1, SI-7.5 | Writer | The Files tab of a Kanban record card sheet (the shared record sheet); then the OpenComms composer | Drop a file on each | The card's Files tab attaches it; the composer behaves as now. | Existing drop targets. |
| SI-C7.6 | SI-7.5 | Writer, 390×844 | Files tab | Use Choose file | The file uploads as now. | Choose file. |
| SI-C8.1 | SI-8.1, SI-8.2 | Writer | A Kanban card with an empty date | Press "Tomorrow" with the keyboard | One save request; after reload the date is tomorrow in the account's regional settings. | Card save as now. |
| SI-C8.2 | SI-8.3 | Writer (test level: isolated, with a fixed Monday date) | Today is a Monday | Press "Next Monday" | The date is 7 days later. | Regional settings. |
| SI-C8.3 | SI-8.2 | Writer | A card date already today | Press "Today" | No request is sent. | — no History entry. |
| SI-C8.4 | SI-8.4, SI-0.3 | Reader, guest | The same card | Open the sheet | No quick dates. | Read-only rows as now. |
| SI-C8.5 | SI-0.4 | Writer, 390×844 | A card sheet | Read the date rows | The three choices show with targets of at least 44 px and no sideways scroll. | The date input stays. |
| SI-C9.1 | SI-9.1, SI-9.2 | Writer | A Contacts record sheet | More record actions › Delete record | No question; one `DELETE /api/records/{record_id}`; "Record deleted." with Undo; focus is in the sheet. | Soft delete only. |
| SI-C9.2 | SI-9.2, SI-0.2 | Writer | SI-C9.1 done | Press Undo | One `POST /api/records/{record_id}/restore`; the record is active after reload. | Delete and Restore run no trigger. |
| SI-C9.3 | SI-9.3 | Writer | SI-C9.1 done, Undo not pressed; sheet closed | Apply the Deleted filter; open the record; press Restore | The record is listed and restores. | Restore as now. |
| SI-C9.4 | SI-9.4 | — (http test level) | Restore is refused | Press Undo | The reason shows; the record stays deleted; Restore stays. | — no partial restore. |
| SI-C9.5 | SI-9.5, SI-0.3 | Reader, guest | A Contacts record | Open More record actions | No Delete record. | Guest cap at Read. |
| SI-C9.6 | SI-9.5 | Administrator | A deleted record | Delete forever | The review and the password still show. | Purge review and password. |
| SI-C9.8 | SI-9.2, SI-0.4 | Writer, 390×844 | A Contacts record sheet | Delete record with the keyboard, then press Undo with the keyboard | Undo is reached without leaving the sheet; its target is at least 44 px; the record is restored. | Phone header (UF-12.1). |
| SI-C9.7 | SI-9.5 | Writer | A Kanban record card sheet | Delete record | "Delete this record?" shows as now. | Boards card sheet (DR-2.12). |

## Design rules and states (Product Designer)

`ui-ux-pro-max` decided the structure, flow, and states below. `impeccable` decides only the visual treatment inside them; the new patterns are listed under "Design-system items" for a later request. Code paths are under `frontend/src/` unless the row says otherwise; line numbers are on `feat/ux-records-list-and-panel` as read on 2026-11-12. One comp shows the only new structure, the selection bar of candidate 5: `.impeccable/mocks/friction/selection.html` (default: 10 selected with the Change popover; `?state=result|partial`; below 768 px the phone rows show; laid out for 1440 and 390, not rendered in this task; `?theme=light` shows Slate light). The cell menu of candidate 1 needs no comp: it is the existing dropdown menu with radio items of the Layout menu (`components/systems/openview/components/layout-menu.tsx`, DA11) on a trigger shaped like the person value of a row (`RecordPersonCard`, `components/systems/openview/components/live-record-cards.tsx:67-100`).

**Rules for every candidate.** G1 to G6 of `ux-friction-pass.md` apply (motion only on the element acted on; no cover or "checking" screen; explanations under their headline; still pages; 32 px from 1280 px and 44 px below; the server is the source of truth for access). Two more:

- G7 **One status place per surface.** A list change (candidates 1, 5) reports in the module page's meta-line status (`role="status"`, `components/systems/openview/components/server-backed-views-workspace.tsx:2800`), the same place item 6 uses (DR-6.1). A sheet change (candidate 9) reports in the record header's meta line, the same place item 2 uses (DR-2.5). A dialog change (candidate 3) reports at the top of the dialog body. (PR4 screen review, 2026-11-13) A list status of candidates 1 and 5 follows DR-6.1 of `ux-friction-pass.md`: while it shows, below 640 px and from 1280 px it takes the place of the meta text on one line, with its link button and Undo on the same line; the words shrink with an ellipsis before the buttons do, so the toolbar never moves. (PR4 re-check, 2026-11-13) From 640 px to 1279 px the header actions can sit beside the title and leave the title column narrow, so a one-line overlay could run under them and cover Undo. There the status stays in the normal flow of the meta line: it may wrap and move the toolbar, and its link button, Undo, and "Open record" are always reachable. The same holds for the item 6 status of `ux-friction-pass.md` (DR-6.1).
- G8 **Undo lasts until the next action, with no timer** (SI-0.2, DR-2.6). Undo goes when the person makes another change, opens another record, changes the filters, sort, search, page, or view, or leaves the page or closes the sheet. Undo is a quiet link button directly after the status words.

**New adapter (candidates 1 and 5).** A new file `components/systems/openview/adapters/record-batch-api.ts` exports `batchUpdateOpenViewRecords({ moduleId, items: [{ recordId, revision, fieldId, value }] })` for the existing `POST /api/records/batch-update` (`backend/app/systems/sandbox/records/batch_router.py:121`). It parses the four result kinds (`updated` with the record, `stale`, `forbidden`, `invalid` with errors). `frontend/api-route-manifest.json` gains one row: `{"adapter": "frontend/src/components/systems/openview/adapters/record-batch-api.ts", "function": "batchUpdateOpenViewRecords", "method": "POST", "path": "/api/records/batch-update"}`. No backend or API change.

### Candidate 1: Choice cell menu (change or show only)

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-SI-1.1 | In the table layout from 768 px, each non-empty Choice list value in a cell is a button: the value text, then a small chevron, sized to its text, as the person value in a row is. The button's accessible name is "<Field>: <value>, options". The rest of the cell, outside the button, still opens the record (`opensRecord` skips only buttons and links, `live-record-results.tsx:87-89`). An empty Choice value is plain text and opens the record. | SI-1.1; SI-C1.1, SI-C1.2 | `RecordPersonCard` trigger pattern (`live-record-cards.tsx:67-100`); `opensRecord` |
| DR-SI-1.2 | On a phone (below 768 px, the narrow table rows of `live-record-results.tsx:135-170`), each row adds one chip at its end for the module's quick-filter field (the records' first Choice list field, OD14), when the row has a value for it. The chip is a 44 px tall button with the value and the chevron. The rest of the row stays the record's open button. | SI-1.1, SI-0.4; SI-C1.6 | `RowOpenButton` row (`components/systems/access/components/row-open-button.tsx`) |
| DR-SI-1.3 | The button opens a dropdown menu anchored to it. Enter, Space, or Arrow Down opens it; Escape closes it and returns focus to the button. From 1280 px its rows are 32 px; below, 44 px. | SI-1.1, SI-0.4; SI-C1.6 | `components/ui/dropdown-menu.tsx`; Layout menu (`layout-menu.tsx`) |
| DR-SI-1.4 | The first item is "Show only <value>" for every level. It applies the condition "<Field> is <value>" through the view-draft update (`updateDraft`). (N-4) It replaces every applied condition on that field (for example "Status is Active", or "Status is not Prospect"), because "Show only" means that value only; conditions on other fields stay; for the quick-filter field it selects that quick chip instead. It is left out when the applied conditions use "Any condition" with one or more conditions (SI-0.1), or when the same condition is already applied (then nothing changes). The badge follows UF-1.1 and UF-1.3. | SI-1.2, SI-0.1; SI-C1.1, SI-C1.3, SI-C1.4, SI-C1.5 | `updateDraft` (`server-backed-views-workspace.tsx`); `QuickFilter` (`quick-filter.tsx`); `appliedDefinition` (`domain/server-view-draft.ts:261`) |
| DR-SI-1.5 | For a writer on a record that is not deleted, a separator and the group heading "Change <Field> to" follow, with the field's options as radio items; the current value is checked. An optional field adds "None" last; a required field has no "None". A pick of the checked value closes the menu and sends nothing. When "Show only" is left out (DR-SI-1.4) and the person is a reader or a guest, the button is plain text: a menu with no item does not open. | SI-1.3, SI-1.6, SI-0.3; SI-C1.12, SI-C1.13 | radio items of `layout-menu.tsx` |
| DR-SI-1.6 | A pick of another value sends one `batchUpdateOpenViewRecords` item: the record id, the row's `updatedAt` as `revision`, the field, and the value. While it runs, the cell button shows the new value with `aria-busy` and is disabled, and other cell menus and the record open of that row wait. | SI-1.3; SI-C1.7 | new adapter (above) |
| DR-SI-1.7 | `updated`: the row takes the returned record. The page status reads "Status changed to Former. Undo" (the words of `inPlaceChangeMessage`, `domain/record-inplace-change.ts:127-145`). The row stays in place until the list refreshes; when the record no longer matches the filters, the next read drops it, and Undo stays offered (G8). | SI-1.4, SI-0.2; SI-C1.7, SI-C1.8 | `inPlaceChangeMessage` |
| DR-SI-1.8 | Undo sends one item with the previous value and the `updated_at` of the `updated` result. `updated`: "Status changed back to Active." with no Undo. `stale`: "Not undone. Someone changed this record after you." (`IN_PLACE_WORDS.undoConflict`); the list reads again, nothing is overwritten. (PR4 decision, 2026-11-13) Other Undo refusals use the same opening: "Not undone. Try again." (a request failure, with the reference); "Not undone. You cannot change this record." (`forbidden`); "Not undone." followed by the server's reason, with the field named as DR-SI-1.9 says (`invalid`). | SI-0.2; SI-C1.8, SI-C1.10 | `IN_PLACE_WORDS` (`domain/record-inplace-change.ts:26-31`) |
| DR-SI-1.9 | Refusals change nothing and show no Undo; the list reads again so the cell shows the stored value. `stale`: "Status not changed. Someone changed this record; it shows their value now." `forbidden`: "Status not changed. You cannot change this record." `invalid`: "Status not changed." followed by the field the server names and its message, for example "Owner: Choose a person who can read this module." (N-8: the server checks the whole merged record, `batch_router.py:85-88`, so the field can be one the person did not change). Request failure (network, 5xx other than the one below, a module refusal): "Status not changed. Try again." with the error reference. (N-1) A 503 "Batch outcome could not be confirmed" (`batch_router.py:155-159`) can come after the change was saved: the status reads "The result could not be confirmed.", the list reads again so the cell shows the stored value, and no Undo shows. | SI-1.5; SI-C1.9, SI-C1.11 | `serverFieldMessage`; `components/ui/error-reference.tsx` |
| DR-SI-1.10 | Only Choice list cells get the button. Text, numbers, dates, user, and relationship cells stay as now; a User value keeps the person card. | SI-1.6; SI-C1.12 | `live-record-results.tsx` cells as now |

| State | Writer | Reader, guest |
| --- | --- | --- |
| Rest | Choice values are buttons with a chevron; the rest of the row opens the record. | Same buttons, with "Show only" only. |
| Menu open | "Show only <value>", separator, "Change <Field> to" with radio options. | "Show only <value>". |
| In progress | The cell shows the new value, `aria-busy`, disabled. | — |
| Success | Page status "Status changed to Former. Undo". | Show only: the list filters; no status. |
| Failure: stale | "Status not changed. Someone changed this record; it shows their value now." | — |
| Failure: forbidden | "Status not changed. You cannot change this record." | — |
| Failure: invalid | "Status not changed." + the server message. | — |
| Failure: network | "Status not changed. Try again." + reference. | — |
| Empty (empty value; "Any condition") | Empty value: plain text. "Any condition": no "Show only"; the menu has only the change group. | Plain text (no item to offer). |
| No permission | Deleted filter: no change group. | No change group (SI-0.3). |
| 390 px | One 44 px chip per row for the quick-filter field; the same menu, 44 px rows. | Same, "Show only" only. |

### Candidate 2: New record starts with the filter values

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-SI-2.1 | When New record opens, the page passes the applied definition (`appliedDefinition`). It gives starting values only when its logic is "All conditions" or it has exactly one condition (SI-0.1). | SI-2.1, SI-0.1; SI-C2.1, SI-C2.3 | `appliedDefinition` (`domain/server-view-draft.ts:261`) |
| DR-SI-2.2 | For each field in the form of type Choice list, Checkbox, or User, the starting value is the value of the single applied condition "is <value>" on that field. When the field has two or more such conditions, or the condition uses another operator, it keeps its default. A Choice value that is no longer an option keeps the default. | SI-2.1, SI-2.3; SI-C2.1, SI-C2.3 | `initialFormValues` seed (`record-create-dialog.tsx:63-65`) |
| DR-SI-2.3 | A User field takes the value only when it is the signed-in person's id; otherwise it keeps its default (empty). | SI-2.2; SI-C2.2 | `authMeOptions` |
| DR-SI-2.4 | Starting values are not changes: the create guard's `dirty` stays false until the person types or picks (`onDirty`, `record-create-dialog.tsx:131-139`). | SI-2.4; SI-C2.4 | `onDirty` |
| DR-SI-2.5 | No new words: the values show in their fields. The phone dialog is as now. | SI-2.1, SI-0.4; SI-C2.5 | `RecordFormFields` |

| State | Writer |
| --- | --- |
| Rest | Filtered fields start with the filter values; others with defaults. |
| In progress, success, failure | Create as now. |
| Empty (no applied condition, "Any condition" with two or more, incomplete) | Defaults only. |
| No permission | Readers and guests have no New record (as now). |
| 390 px | Same values in the phone dialog. |

### Candidate 3: "Create and add another"

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-SI-3.1 | The dialog footer reads, from left to right: Cancel, "Create and add another" (outline), Create (primary). Create stays the primary and keeps opening the new record sheet. Enter in a field still means Create. Below 640 px the three buttons stack at full width, 44 px, Create first. | SI-3.1, SI-0.4; SI-C3.6 | `DialogFrameFooter` (`record-create-dialog.tsx:144-158`); `components/ui/button.tsx` |
| DR-SI-3.2 | "Create and add another" sends the same `createOpenViewRecord` request with the same checks. While it runs, both create buttons are disabled and it reads "Creating…". | SI-3.1; SI-C3.1 | `createOpenViewRecord` (`record-create-dialog.tsx:81`) |
| DR-SI-3.3 | Success: the form resets to the starting values of DR-SI-2.1 (or the defaults); focus moves to the first field; at the top of the body, an alert `role="status"` reads "<Title> created." (or "Record created." with no title) and an "Open record" link button. A second success replaces the line. The guard's `dirty` resets to false. (PR4 decision, 2026-11-13) The status line uses the success style of the alert. | SI-3.2, SI-3.5; SI-C3.1, SI-C3.5 | `Alert` (`components/ui/alert.tsx`); `recordTitle` |
| DR-SI-3.4 | "Open record" closes the dialog and opens that record's sheet (`setRoute({ record })`). | SI-3.2; SI-C3.2 | `onCreated` path of the workspace |
| DR-SI-3.5 | Failure: the typed values stay; field errors and the alert show as for Create; nothing is saved. | SI-3.3; SI-C3.4 | Create error path (`record-create-dialog.tsx:83-103`) |
| DR-SI-3.6 | When the dialog closes, every record made in it goes through item 6: one match read per record (DR-6.2), then each match shows as a "New" row (DR-6.3, DR-6.4). The page status reads "<n> records created." and, when some are hidden, "<n> records created. <k> hidden by your filters." With search text applied, the match reads are skipped and the status reads "<n> records created." (N-10). With one record, item 6's single-record words apply. (PR4 decision, 2026-11-13) Several "New" rows show newest first: the last record made is the first row, under the toolbar, as one created record is. | SI-3.4; SI-C3.3 | DR-6.1 to DR-6.6 of `ux-friction-pass.md` |

| State | Writer |
| --- | --- |
| Rest | Cancel, Create and add another, Create. |
| In progress | "Creating…"; both create buttons disabled. |
| Success | Form reset, focus in the first field, "<Title> created." + Open record. |
| Failure: invalid | Field errors, values kept. |
| Failure: forbidden, network | The create alert, as now (`apiErrorMessage`). |
| Empty | — (the dialog always has fields). |
| No permission | Readers and guests have no New record. |
| 390 px | Buttons stacked, 44 px; the status line at the top of the body. |

### Candidate 4: "Me" first in person pickers

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-SI-4.1 | In the record form's User picker (`PersonSelect`, `record-form-fields.tsx:38-95`; Edit and New record), the first option after the empty choice is "Me (<name>)" with the person's id. The person is not listed again. (PR4 decision, 2026-11-13) When the signed-in person is the chosen value, the closed field reads "Me (<name>)", because the field shows the option's words; no shared picker changes. "Me" also shows in the import defaults form, which uses the same fields, and it means the person who runs the import. | SI-4.1, SI-4.3; SI-C4.1 | `PersonSelect` native select |
| DR-SI-4.2 | "Me" shows only when the assignable read for the field returns the signed-in person. When the first page has more people and the person is not on it, the picker reads the assignable list once more with the person's name as the search. | SI-4.1; SI-C4.3 | `assignableUsersOptions` (`adapters/openview-queries.ts:263`) |
| DR-SI-4.3 | In the Kanban card sheet's assignee picker (`AssigneeRow`, `components/systems/boards/components/board-card-fields.tsx:128-200`), the options read: "Me (<name>)", "No one", then the other people. While search text is typed, "Me" shows only when the text matches the person's name, and "No one" goes as now. A board writer can always be the assignee, because they can read the board. | SI-4.2; SI-C4.2 | `SearchSelect` (`components/ui/search-select.tsx`); `useAssigneePicker` |
| DR-SI-4.4 | A pick of "Me" does what a pick of the name does: the form fills (record), or the card saves on pick (Kanban); notices go out as now. | SI-4.3; SI-C4.1, SI-C4.2 | `onChange` of `PersonSelect`; `onSave` of `AssigneeRow` (`board-card-fields.tsx`) |
| DR-SI-4.5 | Readers and guests have no picker, so no "Me". | SI-0.3; SI-C4.4 | read-only rows of `board-card-fields.tsx:90-97`; Details read view of `record-details-controls.tsx` |

| State | Writer |
| --- | --- |
| Rest | "Me (<name>)" first. |
| In progress | Card: the existing saving state of the row. |
| Success | The field or card shows the person. |
| Failure | The existing save errors. |
| Empty | Not assignable: no "Me". |
| No permission | No picker. |
| 390 px | Native select (record) and 44 px options (card). |

### Candidate 5: change several selected rows (new structure; comp `selection.html`)

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-SI-5.1 | In the table layout, a writer gets a first column of checkboxes: one per row ("Select <title>") and one in the header ("Select all on this page"). From 1280 px the column is 40 px wide; the header box shows checked, unchecked, or mixed. No column for readers, guests, or with the Deleted filter. (PR4 decision, 2026-11-13) A row with no title reads "Select record". The selection column (40 px) sticks at the left edge, and a pinned first column sticks after it (left 40 px), so both stay in reach when the table scrolls sideways. | SI-5.1, SI-0.3; SI-C5.1, SI-C5.8 | `components/ui/checkbox.tsx`; `components/ui/table.tsx` |
| DR-SI-5.2 | On a phone, each narrow row of a writer starts with a 44 px checkbox before the open button; selection needs no long press. | SI-5.1, SI-0.4; SI-C5.9 | narrow rows of `live-record-results.tsx` |
| DR-SI-5.3 | Click or Space toggles a row. Shift-click selects the range from the last toggled row. The keyboard path for many rows is the header checkbox (whole page) and Space on each row. A checkbox click never opens the record. | SI-5.2; SI-C5.1 | `opensRecord` |
| DR-SI-5.4 | With one or more rows selected, the selection bar replaces the toolbar row (search, quick filter, Filters, Sort, Columns, Layout) in the same height: "<n> selected", a "Change" menu button, and "Clear selection" at the end. The page header and the pager stay. (PR4 screen review, 2026-11-13) Below 768 px the toolbar has several rows: the bar takes the place of the first row only (search and Filters), and the Layout row and the quick filter stay in view and usable (a change there clears the selection, DR-SI-5.10), so no empty band shows and the rows do not move. | SI-5.3; SI-C5.1 | toolbar row of the module page (OD3); new structure (comp) |
| DR-SI-5.5 | "Change" lists the Choice list and Checkbox fields that are columns of the view's query, by name. A field the rows do not hold is not offered, because Undo needs each record's previous value. User fields and other types are never offered. | SI-5.3; SI-C5.1 | `draft.definition.columns` |
| DR-SI-5.6 | A field opens a popover: the field name as its heading, the options as a radio list (Checkbox: "On", "Off"; an optional Choice list adds "None"), then the final button and Cancel. Before a pick, the final button reads "Change records" and is disabled. After a pick, it reads "Change <k> records", where k counts the selected rows that do not already hold the value. When k is 0, it reads "All <n> already have this value" and is disabled. Nothing is sent before the final button. (PR4 decision, 2026-11-13) With one record to change, the button reads "Change 1 record". | SI-5.4; SI-C5.2 | `components/ui/popover.tsx`; `components/ui/radio-group.tsx`; `DisabledReason` |
| DR-SI-5.7 | The final button sends one `batchUpdateOpenViewRecords` with the k records (id, the row's `updatedAt`, field, value). The page size is at most 50 and selection covers the current page only, so one request holds at most 50 items. If a selection over 100 were ever possible, the final button would read "Select at most 100 records" and be disabled. While it runs, the button reads "Changing…" and the bar is disabled. | SI-5.5; SI-C5.2 | new adapter; `TABLE_PAGE_SIZE_OPTIONS` |
| DR-SI-5.8 | Result, in the page status: all updated: "Status changed on 8 records. Undo". Partly updated: "Status changed on 6 records. 2 not changed. Undo", where "2 not changed" is a link button that opens a popover listing each record by title with its reason: "Someone changed it", "You cannot change it", or "Not valid: <server message>" (also for a deleted record). Each title opens the record. None updated: "No records changed." with the same list. A request failure: "No records changed. Try again." with the reference. (N-1) A 503 "Batch outcome could not be confirmed": "The result could not be confirmed.", the list reads again, no Undo, and the selection clears. An `invalid` reason names the field and its message, as in DR-SI-1.9 (N-8). (PR4 decision, 2026-11-13) One record: "Status changed on 1 record." The words "<f> not changed." are also in the status text for screen readers (visually hidden), because the visible "<f> not changed" is a link button. | SI-5.6; SI-C5.4, SI-C5.6 | page meta-line status (G7); `components/ui/popover.tsx` |
| DR-SI-5.9 | Undo sends one batch with only the `updated` records, each with its own previous value and the `updated_at` from the result. Its result reads "Status changed back on 6 records." or "5 changed back. 1 not changed back." with the same list kind. Nothing is overwritten. (PR4 decision, 2026-11-13) One record: "Status changed back on 1 record." When nothing could be put back: "No records changed back." with the same list. | SI-0.2, SI-5.6; SI-C5.3, SI-C5.5 | new adapter |
| DR-SI-5.10 | The selection clears after the final button's result, and when the page, filters, sort, search, or view change, or the person leaves the page. (N-5) When the list reads again for another reason (a live change from someone else, a refresh), the selection keeps only the rows still on the page, and "<n> selected" counts them. | SI-5.7; SI-C5.7 | `draftKey` reset effect |

| State | Writer | Reader, guest |
| --- | --- | --- |
| Rest | Checkbox column; toolbar as now. | No checkboxes. |
| Selected | Selection bar: "<n> selected", Change, Clear selection. | — |
| Popover | Radio options; "Change <k> records" or the disabled reasons. | — |
| In progress | "Changing…"; bar disabled. | — |
| Success | "Status changed on 8 records. Undo"; selection cleared. | — |
| Failure: stale, forbidden, invalid (partial) | "Status changed on 6 records. 2 not changed. Undo" + list. | — |
| Failure: network | "No records changed. Try again." + reference. | — |
| Empty (no rows; k = 0) | No checkboxes without rows; "All <n> already have this value". | — |
| No permission | Deleted filter: no checkboxes. | No checkboxes. |
| 390 px | 44 px row checkboxes; the bar replaces the search row; the popover becomes a bottom sheet. | — |

### Candidate 6: open the records behind a dashboard figure

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-SI-6.1 | (B-1) The Number widget's figure (`dashboard-widget-card.tsx:437`) becomes a link to the module page with the widget's conditions and, when the widget has a date window, its window as two conditions (DR-SI-6.6). `recordsHref` gains the window; the widget menu's "Open the records" uses the same link, so it opens the counted records too. Its text stays the figure; its accessible name is "Open the <figure> <module>" (for example "Open the 601 Customers"). It keeps the figure's style; the underline shows only on hover and focus. (PR4 decision, 2026-11-13) The accessible name of a count figure is "Open the <figure> <module>" (for example "Open the 601 Customers"). For a total, an average, a smallest, a largest, or a different-values figure, the name is "Open the <module> behind <widget title>: <figure>" (for example "Open the Invoices behind Total amount: 12,500"), because that figure is not a record count. Both names hold the visible figure (WCAG 2.5.3). | SI-6.1, SI-6.4; SI-C6.1 | `recordsHref` (`:904-919`); `next/link` |
| DR-SI-6.2 | Each group row of a table widget (`TableBody`, `:532-590`) becomes a link row: the label cell is the link, and the row is its 44 px target below 1280 px. (B-1) The link adds the group's condition to the widget's conditions and window: "is <key>" for a group key; the stored operator `empty` for the empty group (`key` null; the server groups by the raw value, so the group is SQL NULL only, and `blank` would also count blank text). Table widgets group only by text, long text, email, web link, Choice list, user, and Checkbox (`chart-query.ts:45-53`), so a table group is never a date bucket. The accessible name is "Open the <value> <label> records". (PR4 decision, 2026-11-13) Exception to G5 for dashboard widget rows only: a group row or record row is 44 px below 768 px and 32 px from 768 px. The fixed 7rem grid rows of the dashboard cannot hold four 44 px rows, the header, and the pager, and a clipped pager hides data. From 768 px the target stays above the 24 px minimum (WCAG 2.5.8), and the widget menu's "Open the records" stays a full-size path. Rows per span do not change. | SI-6.2, SI-6.4; SI-C6.2, SI-C6.6 | `recordsHref`; `CATEGORICAL_TYPES` (`chart-query.ts`) |
| DR-SI-6.3 | Under SI-0.1: with "All conditions", or no condition, the links show. A Number figure with no date window carries the widget's logic as it is, because it adds no condition. A link that adds a group or window condition follows the rest of this rule. With "Any condition" and exactly one condition, the link's temporary changes set "All conditions". With "Any condition" and two or more, group rows stay plain text. A row whose key cannot be stated as a condition stays plain text. | SI-0.1, SI-6.2; SI-C6.3 | `definition.logic` in `recordsHref` (`dashboard-widget-card.tsx:907`) |
| DR-SI-6.4 | Each records widget row (`RecordsBody`, `:593-660`) opens that record: its first cell links to the module page with `?record=<id>`. (PR4 decision, 2026-11-13) The whole first cell is the link. When that cell holds a person, the name shows as plain text in the link, without the person card; the other cells keep the person card, and the record sheet shows the person card too. The accessible name starts with the visible cell text: when the first column is the title field, "<title>, open record"; otherwise "<cell text>, open record <title>" (for example "Former, open record Liza Cruz"). | SI-6.3; SI-C6.4 | `serializeOpenViewUrl` |
| DR-SI-6.6 | (B-1) The date window becomes conditions on the window's field, exactly as the server applies it (`backend/app/systems/sandbox/records/aggregation.py:93-105`). (a) A Date field: "is on or after <from>" (`gte`) and "is on or before <to>" (`lte`). (b) A Date and time field: `gte` the instant of local midnight at the start of <from> and `lt` the instant of local midnight after <to>, in the workspace timezone, written as ISO text with its offset (for example `2026-11-01T00:00:00+08:00`), because text without an offset is read as UTC (`backend/app/systems/sandbox/designs/date_values.py:28-40`). An open-ended <to> (`date.max`) adds no upper condition. The offset comes from the workspace calendar settings for each date, so a daylight-saving change is exact. No link (plain figure or plain row) when the window cannot be carried exactly: the workspace timezone has not loaded or its read failed; the window's field is not readable on the module page; or the widget uses "Any condition" with two or more conditions. A link never opens a list whose count differs from its figure. | SI-6.1, SI-6.2, SI-6.4, SI-0.1; SI-C6.1, SI-C6.2 | `getWorkspaceCalendarSettings` (`components/systems/manage/adapters/workspace-api.ts`, used by `adapters/analytics-api.ts:3`); filter operators `gte`, `lte`, `lt` (`domain/server-view-draft.ts:20-35`) |
| DR-SI-6.5 | The module page applies the person's own access; the changes are temporary (UF-1.1, UF-1.3). The widget menu's "Open the records" stays. (PR4 decision, 2026-11-13) When no exact link can be made (DR-SI-6.6), the widget menu item reads "Open <module>" in place of "Open the records", and it opens the module page with the widget's conditions as far as they can be carried. The words then make no promise that the list matches the figure. | SI-6.5; SI-C6.5 | module page access as now (`server-backed-views-workspace.tsx`) |

| State | All levels |
| --- | --- |
| Rest | Figure and rows look as now; underline on hover and focus. |
| In progress | The widget's current loading state; no links until the data shows. |
| Success | The module page opens with the conditions; its count equals the figure. |
| Failure | The widget's current error state; no links. |
| Empty | No value: "No values yet" (DR-9.5 of `ux-friction-pass.md`), not a link. A window that cannot be carried exactly (DR-SI-6.6): plain figure and rows. |
| No permission | Access applies on the module page. |
| 390 px | Rows and figure 44 px tall targets. |

### Candidate 7: drop or paste a file to attach

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-SI-7.1 | The record Files tab (`RecordFilesPanel`, used by the shared record sheet, `components/systems/shared/components/record-sheet.tsx:337`) and the Files library panel (`components/systems/platform/components/files.tsx`) take a dropped file when "Choose file" is offered there. While a file is over the panel, the panel shows a dashed outline and the line "Drop to attach" (Files library: "Drop to upload"), centered. | SI-7.1; SI-C7.1, SI-C7.5 | `upload` (`record-files-panel.tsx:277`); library upload (`files.tsx:547`) |
| DR-SI-7.2 | A pasted file uploads when focus is in the panel and not in a text input. Pasted text in a text input stays text. | SI-7.2; SI-C7.2 | the same upload calls |
| DR-SI-7.3 | One file per drop or paste. Two or more: nothing uploads; "Drop one file at a time." While an upload runs (`operation.current`): nothing new uploads; "Wait for the current upload to finish." A size that "Choose file" refuses shows the same message ("Choose a file larger than 0 bytes and no larger than 25 MB."). (N-3) The type check of the picker exists only as its `accept` list (`record-files-panel.tsx:506`, `files.tsx:830`), so a dropped or pasted file gets the same extension check before the upload (.pdf, .png, .jpg, .jpeg, .docx, .xlsx, .pptx); another type: nothing uploads, and "Choose a PDF, PNG, JPEG, Word, Excel, or PowerPoint file." shows. (PR4 decision, 2026-11-13) The panel runs one operation at a time. A file dropped or pasted during an upload reads "Wait for the current upload to finish."; during a download, an archive, a status check, or "Load more" it reads "Wait a moment, then drop the file again." Nothing uploads in either case. | SI-7.3; SI-C7.3 | the existing size and name checks (`record-files-panel.tsx:277-291`); the picker's `accept` list |
| DR-SI-7.4 | Where "Choose file" is not offered (reader, guest, a deleted record), the panel shows no drop state and takes nothing. On the OpenView module page, the Boards card sheet, and the Files library, a file dropped anywhere else is ignored, so the browser does not open it. | SI-7.4; SI-C7.4 | new structure: page-level `dragover` and `drop` handlers that prevent the browser default |
| DR-SI-7.5 | "Choose file" stays and is the path at 390 px. The Kanban, OpenComms composer, and post attachment drop targets do not change. | SI-7.5; SI-C7.5, SI-C7.6 | `components/ui/file-picker-button.tsx` |

| State | Writer | Reader, guest |
| --- | --- | --- |
| Rest | Panel as now. | Panel as now. |
| File over the panel | Dashed outline; "Drop to attach". | No change. |
| In progress | The existing upload progress. | — |
| Success | The file is listed as now. | — |
| Failure | "Drop one file at a time."; "Wait for the current upload to finish."; the size and type message; the existing upload errors. | — |
| Empty (no files yet) | The empty panel also takes a drop. | — |
| No permission | — | No drop; no upload. |
| 390 px | Choose file. | — |

### Candidate 8: quick dates on Kanban cards

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-SI-8.1 | Under each date input of a writer's card sheet (`board-card-fields.tsx:85-125`), one row of three small buttons: "Today", "Tomorrow", "Next Monday". They are 32 px from 1280 px and 44 px below, in one line at 390 px. | SI-8.1, SI-0.4; SI-C8.1, SI-C8.5 | `components/ui/button.tsx` (outline, small) |
| DR-SI-8.2 | A press sets the date and calls the row's existing `onSave` once, as a changed input does. A press of the current date sends nothing. While it saves, the input and the three buttons are disabled (`context.model.saving`). (PR4 decision, 2026-11-13) While a date row saves, the quick-date buttons are `aria-disabled` and ignore a press, not `disabled`, so the pressed button keeps keyboard focus. | SI-8.2; SI-C8.1, SI-C8.3 | `commit` and `onSave` (`board-card-fields.tsx:98-102`) |
| DR-SI-8.3 | The dates come from the account's regional settings, as the calendar's Today does. "Next Monday" is the first Monday after today; on a Monday it is 7 days later. | SI-8.3; SI-C8.2 | the calendar's workspace date helpers |
| DR-SI-8.4 | Readers and guests see the date as now, with no buttons. | SI-8.4, SI-0.3; SI-C8.4 | the read-only row (`:90-97`) |

| State | Writer |
| --- | --- |
| Rest | Date input with the three buttons under it. |
| In progress | Input and buttons disabled. |
| Success | The date shows; the card saves once. |
| Failure | The existing save error of the card. |
| Empty date | The buttons set it. |
| No permission | No buttons. |
| 390 px | One line of three 44 px buttons; no sideways scroll. |

### Candidate 9: Undo in place of the delete question (OpenView)

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-SI-9.1 | In the OpenView record sheet, More record actions › Delete record calls `remove` at once (`record-details-controls.tsx:454-462`): no "Delete this record?" dialog. `RecordDetailsControls` takes a prop for this; the OpenView sheet sets it, and the Boards record card sheet does not, so it keeps the question. | SI-9.1, SI-9.5; SI-C9.1, SI-C9.7 | `remove`; shared `record-sheet.tsx:295` |
| DR-SI-9.2 | Success: the record header's meta line reads "Record deleted." with Undo, replacing "Record deleted. You can restore it from this dialog." Focus moves to Undo, so it is reachable at once. The sheet shows the Deleted badge and Restore, as now. | SI-9.2, SI-9.3; SI-C9.1, SI-C9.8 | item 2 header status (DR-2.5) |
| DR-SI-9.3 | Undo calls `restore` (`:481-490`). Success: "Record restored." with no Undo. Refused by a value check (422): the server's reason shows in the meta line; the record stays deleted; Restore stays. (N-2) 409 "Record is not deleted" (someone restored it first): the sheet reads the record again and shows it as it is now; the status reads "Someone already restored this record." with no Undo. 404 (deleted forever): "This record was deleted forever." with no Undo; the sheet shows "Record unavailable" as now. (PR4 decision, 2026-11-13) The 404 words "This record was deleted forever." show in the record header's meta line, inside the sheet, while its title reads "Record unavailable" (G7); not only in the page status behind the sheet. | SI-9.2, SI-9.4, SI-0.2; SI-C9.2, SI-C9.4 | `restoreOpenViewRecord` |
| DR-SI-9.4 | Undo lasts as G8 says: until Restore, another change, a tab change, Previous or Next, or closing the sheet; no timer. After that, the record stays in the Deleted filter and Restore works as now. | SI-0.2, SI-9.3; SI-C9.3 | DR-2.6 of `ux-friction-pass.md` |
| DR-SI-9.5 | Readers and guests get no Delete, as now. "Delete forever" keeps its review and password. | SI-9.5; SI-C9.5, SI-C9.6 | purge review in `record-details-controls.tsx` |

| State | Writer |
| --- | --- |
| Rest | More record actions › Delete record. |
| In progress | The menu closes; the header actions wait (`pending`). |
| Success | "Record deleted." + Undo; Deleted badge; Restore. |
| Failure: delete refused or network | The existing delete error. |
| Failure: Undo refused | The server reason; still deleted; Restore. |
| Empty | — |
| No permission | No Delete record. |
| 390 px | Undo in the stacked header meta line (UF-12.1), 44 px. |

### Words

| Cand. | Old | New | Old string's file |
| --- | --- | --- | --- |
| 1 | — | Cell button name "<Field>: <value>, options" | — |
| 1 | — | "Show only <value>" | — |
| 1 | — | Group heading "Change <Field> to"; option "None" (optional fields) | — |
| 1 | — | "<Field> changed to <value>." + "Undo"; "<Field> changed back to <value>."; "<Field> turned on." / "turned off."; "<Field> cleared." | words of `domain/record-inplace-change.ts` (reused) |
| 1 | — | "Not undone. Someone changed this record after you." | reused from `IN_PLACE_WORDS` |
| 1 | — | Undo refusals: "Not undone. Try again."; "Not undone. You cannot change this record."; "Not undone. <reason>" | — |
| 1 | — | "<Field> not changed. Someone changed this record; it shows their value now." | — |
| 1 | — | "<Field> not changed. You cannot change this record." | — |
| 1 | — | "<Field> not changed." + the server message | — |
| 1 | — | "<Field> not changed. Try again." | — |
| 1, 5 | — | "The result could not be confirmed." (503 "Batch outcome could not be confirmed") | — |
| 1, 5 | — | Invalid reason: "<Other field>: <server message>" | — |
| 3 | — | Button "Create and add another" | — |
| 3 | — | "<Title> created." (or "Record created.") + "Open record" | — |
| 3 | — | "<n> records created."; "<n> records created. <k> hidden by your filters." | — |
| 4 | — | Option "Me (<name>)" | — |
| 5 | — | "Select <title>"; "Select all on this page" | — |
| 5 | — | "<n> selected"; "Change"; "Clear selection" | — |
| 5 | — | Final button "Change records" (no pick), "Change <k> records"; "All <n> already have this value"; "Select at most 100 records"; "Changing…"; options "On", "Off", "None" | — |
| 5 | — | "<Field> changed on <k> records." + "Undo"; "<Field> changed on <u> records. <f> not changed." + "Undo"; "No records changed."; "No records changed. Try again." | — |
| 5 | — | Reasons: "Someone changed it"; "You cannot change it"; "Not valid: <server message>" | — |
| 5 | — | "<Field> changed back on <u> records."; "<u> changed back. <f> not changed back." | — |
| 5 | — | Singular: "Change 1 record"; "<Field> changed on 1 record."; "<Field> changed back on 1 record."; "No records changed back."; "Select record" (row with no title); "<f> not changed." (screen readers, inside the status) | — |
| 6 | — | Accessible names "Open the <figure> <module>"; "Open the <value> <label> records"; records row: "Open record: <title>" | — |
| 6 | — | Name of a non-count figure: "Open the <module> behind <widget title>: <figure>"; records row: "<title>, open record" or "<cell text>, open record <title>" (replaces "Open record: <title>") | — |
| 6 | "Open the records" (widget menu, no exact link) | "Open <module>" | `components/systems/openview/components/dashboard-widget-card.tsx:1023` |
| 7 | — | "Drop to attach" (record Files tab); "Drop to upload" (Files library) | — |
| 7 | — | "Drop one file at a time."; "Wait for the current upload to finish."; "Wait a moment, then drop the file again." (during a download, an archive, a status check, or "Load more") | — |
| 7 | — | "Choose a PDF, PNG, JPEG, Word, Excel, or PowerPoint file." | — |
| 8 | — | "Today", "Tomorrow", "Next Monday" | — |
| 9 | "Record deleted. You can restore it from this dialog." | "Record deleted." + "Undo" | `components/systems/openview/components/record-details-controls.tsx:460` |
| 9 | — | "Someone already restored this record."; "This record was deleted forever." | — |
| 9 | — | "Record restored." (after Undo) | reused (`record-details-controls.tsx:486`) |
| 9 | Dialog "Delete this record?" (OpenView) | removed (Boards card sheet keeps it) | `record-details-controls.tsx:921` |

### Design-system items (for a later `impeccable` request)

1. A Choice value as a button in a table cell and as a 44 px chip at the end of a phone row (candidate 1).
2. The selection column and the selection bar that replaces the toolbar row (candidate 5, comp `selection.html`).
3. The bulk-result status with the "not changed" link and its list popover (candidate 5).
4. Link figures and link rows on dashboard widgets, underlined only on hover and focus (candidate 6).
5. The drop state of a panel: dashed outline and the centered line (candidate 7).
6. Quick-date buttons under a date input (candidate 8).

### For the build plan

- N-6: time one 50-item `batch-update` on a sample-pack module before the build is accepted. The batch holds the module row lock until it commits, and other writes to that module wait up to 2 s.
- N-7: add `batchUpdateOpenViewRecords` to `frontend/tests/isolated/contracts/records-contract.spec.ts`.

## Where each capability goes (Product Designer)

| Removed or moved | Cand. | New place, or why it is removed |
| --- | --- | --- |
| A click on a Choice list value opening the record (OD6 for that value) | 1 | The value opens its menu; the rest of the row still opens the record (OD6 row of "Changed decisions"). |
| The toolbar row while rows are selected | 5 | The selection bar takes its place; "Clear selection" brings the toolbar back. |
| "Delete this record?" in the OpenView record sheet | 9 | Removed, because Delete is a soft delete with Undo at once and Restore after; the Boards record card sheet keeps it (SI-9.5). |
| "Record deleted. You can restore it from this dialog." | 9 | "Record deleted." with Undo; Restore stays in the sheet. |
| Nothing else | 2, 3, 4, 6, 7, 8 | Additions only: every current control and path stays (Create, "Choose file", the widget menu's "Open the records", the date input, the full person list). |

## Backend changes needing your go-ahead (Product Designer)

None. Candidates 1 and 5 use the existing `POST /api/records/batch-update` through the new adapter file `components/systems/openview/adapters/record-batch-api.ts`; `frontend/api-route-manifest.json` gains its one row. Candidate 9 uses the existing `DELETE /api/records/{record_id}` and `POST /api/records/{record_id}/restore`. No other request changes.
