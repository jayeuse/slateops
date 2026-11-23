# Sheets

> **Status: Draft for owner review (2026-11-24): spec, screens and data/API merged; comp at `.impeccable/mocks/openview/sheets.html`; decisions 1–18 settled (DEC-0045); module sheets, the "From another sheet" column and per-cell saves added (DEC-0046).** Source: owner decisions DEC-0043 and DEC-0044 and request REQ-0025 (company records), written under APR-0015. Screens come from TASK-0099 (Product Designer) and Data and API from TASK-0100 (Software Architect). Nothing here changes the verified architecture documents.

## Outcome

A person opens a record, adds a sheet to it, and keeps their own working data there in rows and columns. Example: Teacher A opens their own record in Faculty Members and keeps one sheet per class, with a Student column that links to Student List. Nobody else sees those sheets until Teacher A shares them.

The Sandbox lets an organization shape its structure. Sheets let its people organize their own data in that structure. The line between the two:

- **A record** holds shared and official data. Several people look it up, rules, reports or approvals use it, or two places need it.
- **A sheet** holds working data that one person owns. Everything else can be a sheet.

Job: when I keep data about the records I work with that the organization does not track, I want it next to those records and linked to them, so I stop keeping a separate spreadsheet that nobody can find when I leave.

Repository evidence for the need:

- The School pack leaves per-student scores out of modules on purpose (about 37,000 rows per grading period) and keeps the roster and class sections as modules (`docs/plans/sample-organization-research/school.md:6`).
- The Manufacturer pack defers BOM Lines and puts the formula in a long-text field (`docs/plans/sample-organization-packs.md:304`).
- Harbor shows the other side of the line. Its purchase lines stay a module, because receipts and stock depend on them (`backend/operations/sample/packs/harbor/catalog.py:295`).
- There are no formula fields and no record-level access (`docs/reviews/known-gaps.md`).

### Labels

Each rule carries one label.

| Label | Meaning |
| --- | --- |
| **Decided** | Human Owner decision (DEC-0043 or DEC-0044). Do not change it without the owner. |
| **Assumption** | Stated in DEC-0043 or DEC-0044 as an assumption until the owner says otherwise. |
| **Proposed (parent)** | A parent decision for this spec. It waits for owner approval of the spec. |
| **Proposed (PM)** | Added by the Product Manager to close a gap. It waits for owner approval of the spec. |
| **Proposed (Screens)** or **Proposed (D-n)** | Set by the Screens section or by a Data and API section. It waits for owner approval of the spec. |
| **Proposed (REQ-0025 item N)** | A proposal in the request record that no owner decision has settled yet. It waits for owner approval of the spec. |
| **Open** | Not settled. See Decisions. |

## Current state

These facts were checked in code at `8c8d2b02`.

- The record panel (the record sheet) is a 540px right-hand panel (`.impeccable/mocks/openview/openview.css:148`). Its tabs are an optional leading tab that the caller supplies, Details, Linked records, Files, and History when the person can read history (`frontend/src/components/systems/shared/components/record-sheet.tsx`, lines 259 to 278).
- `Record.data` is JSONB keyed by field ID (`backend/app/systems/sandbox/records/models.py`). Records delete softly and restore (`records/router.py`, `delete_record` and `restore_record`). Sandbox lifecycle purges remove them permanently and write `lifecycle.record_purge` (`sandbox/lifecycle/execution.py`).
- Field types: `text`, `long_text`, `email`, `url`, `number`, `decimal`, `int`, `boolean`, `date`, `datetime`, `select`, `user`, `relationship` (`sandbox/fields/models.py`, `FieldType`). There is no currency type.
- A `RelationshipEdge` needs a Sandbox field: `field_id` is not nullable and has a foreign key to `fields` (`sandbox/relationships/models.py`). A link shows only when the person can read both ends (`sandbox/relationships/access.py`).
- Departments, modules and fields have only `GET` routes. The Sandbox publish is the only way to change them (`backend/AGENTS.md`).
- Record export writes `records.export.authorized` (`sandbox/records/export.py:330`). Excel export uses `xlsxwriter` (`records/export_xlsx.py`), the only spreadsheet library in `backend/pyproject.toml`, so there is no Excel reader. Record import is an administrator CSV batch with a preview (`records/import_router.py`). A sheet import by any sheet editor is therefore new for non-administrators.
- The Sandbox design document has a versioned format (`schemaVersion`, `sandbox/designs/schemas.py:285`).
- Audit rows can hide values. A model lists the fields in `__audit_redacted_fields__` (`core/base_model.py:21`). OpenComms hides message `body` (`comms/messages/models.py:176`), and saved views hide `definition` and `presentation`.
- Formats come from the organization profile: `locale`, `currency`, `timezone`, `week_start` (`manage/workspace/models.py`, `WorkspaceProfile`). A person can override the date format, time format and week start. The value `organization` keeps the organization's choice (`access/users/models.py`, `ck_users_appearance`).
- A guest is capped at `read` (`access/policy/scope.py`, rule 5).
- An admin does not read private conversations they are not part of. They get 404 (OpenComms D43, `docs/plans/opencomms.md`).
- A person leaves an organization in one of these ways (`access/users/account_operations.py`). All are admin actions.
  - Disable in this organization: `_change_membership_status` to `disabled`.
  - Disable the account: `_disable_user`.
  - Remove from this organization: `_remove_membership`.
  - Delete the account: `delete_user`.
- A person comes back in one of these ways:
  - Re-enable: `_change_membership_status` to `active`, or `_activate_user`.
  - Restore: `restore_user`. It undoes a membership removal, and it also undoes an account delete. Only the installation owner can restore a deleted account.
  - A new invitation after removal. It reuses the removed membership row (`access/users/service.py:207-243`, checked in TASK-0100).
- `_disable_user` and `delete_user` act on the account, so they reach every organization of the person (`access/users/coordination.py:176-195`, checked in TASK-0100).
- The Sandbox shows `decimal` as "Number" and `int` as "Whole number", and does not offer `number` (`frontend/src/lib/sandbox/model.ts:72-83`).

## Scope

**In scope.**

- Sheets on records:
  - create, rename and delete;
  - columns of the existing types, link columns, lookup columns, computed columns, column groups and a totals row;
  - row editing with per-row revisions and live refresh.
- The record panel's Sheets tab, the full-width sheet page, My sheets, and the phone layout.
- Sharing (View or Edit, per person or group), and the leave event.
- Appears in on linked records.
- Export and import:
  - data as CSV or Excel;
  - templates as versioned JSON;
  - "New sheet from this structure";
  - "Make a copy" of an open sheet.
- Sheet history, admin audit with redaction, and security events.
- Sheets in two sample packs, as proof that sheets are organization-agnostic.

**Out of scope (not in this version).**

- Real-time co-editing beyond per-cell saves (F4), live refresh and presence (PR1–PR6). There is no character-by-character typing.
- Triggers, charts, reports, dashboards, Boards or Platform search that read sheet data.
- Free-form formulas across sheets, cell references such as `B2`, and links from a sheet row to a row of another sheet. A sheet reads another sheet only through a "From another sheet" column (K9).
- Automatic write-back from a sheet into record fields.
- Moving a sheet to another record. REQ-0025 names this upgrade path ("move the class sheets onto those records"). In this version a person uses "New sheet from this structure" on the new record, then exports the data and imports it there.
- Filters and saved views inside a sheet. Sort by one column and search are in scope.
- Notifications about sheets, including a notification when a sheet is shared. The recipient finds the sheet in My sheets (Proposed (PM)).
- An admin export of private sheets, like the OpenComms purpose-authorized export (D31). No such route exists for sheets.
- Changes to departments, modules or fields. Sheets never create or change them.

**Preserved behavior.**

- The record panel keeps its width, its tabs, their order and their behavior. The Sheets tab is added after History.
- A sheet never changes its record. The record's fields, revision, history, links, files and audit rows are the same before and after any sheet action.
- Saved views, record list counts, record export (CSV and Excel), record import (CSV), Charts, Reports and Dashboards return the same results with or without sheets.
- The Sandbox publish stays the only way to change departments, modules and fields.
- Guests stay capped at `read`. No sheet action gives a guest `write` on anything.
- Module access stays the only access level for records. A sheet share gives no access to the record or to any linked record.
- Every OpenView URL that works today opens the same thing.
- Audit covers every application ORM mutation through `AuditSession`. Sheets add redacted fields. They add no exception to audit.

## Rules and states

### Placement

| ID | Rule | Label |
| --- | --- | --- |
| P1 | Sheets are part of OpenView (Views), not the Sandbox. Sheets are stored as JSONB rows. A sheet sits on a record (a **record sheet**) or on a module (a **module sheet**), the way a record connects to its module. Use a record sheet for data about one record, and a module sheet for a working list across many records of the module. A list that is only records filtered by a field stays a saved view. | Decided (REQ-0025 direction, DEC-0043) |
| P2 | The module page lists its module sheets that the viewer can see, with **New sheet**. The record panel gets a **Sheets** tab. It lists the sheets that the viewer can see on that record and shows **New sheet** to people who can create one. With no visible sheets, it shows an empty state with the same structure. It is the last record tab, after History, or after Files when History is hidden. Its count is the number of items it lists. | Proposed (parent); position Proposed (Screens) |
| P3 | A sheet opens as its own full-width OpenView page. A header sits over one grid pane that fills the window and scrolls alone. The document does not scroll. A grid does not fit the 540px record panel. | Proposed (parent) |
| P4 | **My sheets** lists the sheets that a person owns and the sheets shared with them, directly or through a group. It is each person's entry point, because no account is tied to a record. It does not list sheets whose record the person cannot read now, nor open sheets that were never shared with the person (those show only in the record's Sheets tab). It sits at the foot of the sidebar, and every account sees it. | Proposed (parent); location Proposed (Screens); open sheets Proposed (D2) |
| P5 | On a phone (390px), the grid scrolls sideways with the first column pinned. Tapping a row opens that row as a form in a bottom panel for editing. The sheet page does not scroll at any width, the phone included; this is a stated exception to "phones scroll the page" in `DESIGN.md`. | Proposed (parent); still page Proposed (Screens) |
| P6 | Each sheet has its own link. A person who cannot see the sheet gets the same "not found" as for a sheet that does not exist. | Proposed (PM) |
| P7 | Users see "Sheets" and "sheet". Code uses `Worksheet`, because "sheet" already means a side panel in code and in the glossary. | Proposed (parent), from REQ-0025 item 8 |
| P8 | The line: a record holds shared and official data, and a sheet holds working data that one person owns. Sheets therefore never stand in for a module. Nothing reads sheet data except the sheet's own screens, Appears in, and its exports. | Proposed (REQ-0025 item 1) |
| P9 | The grid keeps the frontend commitments in `PRODUCT.md`: semantic grid roles, keyboard movement between cells, visible focus, sufficient contrast, and reduced-motion support. | Proposed (PM), from `PRODUCT.md` Accessibility & Inclusion |

### Create

| ID | Rule | Label |
| --- | --- | --- |
| C1 | A member with `read`, `write` or `manage` on a module can create a sheet on any record of that module that the member can read, or a module sheet on the module itself. | Decided (DEC-0043 1) |
| C2 | A sheet never changes its record. | Decided (DEC-0043 1) |
| C3 | Guests cannot create sheets. | Assumption (DEC-0043 1) |
| C4 | A sheet cannot be created on a deleted record, a closed module, a record of a closed module, or a record or module that the person cannot read. The refusal for an unreadable record is the same "not found" as for a missing record. | Proposed (PM) |
| C5 | The creator is the owner. Only the owner renames the sheet. | Proposed (PM), extends DEC-0044 3 assumption |

### Visibility and sharing

| ID | Rule | Label |
| --- | --- | --- |
| V1 | A new sheet is visible only to its creator. | Decided (DEC-0043 2) |
| V2 | The creator gives **View** or **Edit** to each person or group. | Decided (DEC-0044 3) |
| V3 | No one but the creator and the people the creator allows sees a private sheet. This includes module managers and admins. They do not learn that it exists, as with OpenComms D43. | Decided (DEC-0044 1) |
| V4 | A sheet is never visible to a person who cannot read its record (for a module sheet: its module), even when it is shared with them. When read returns, the share works again. | Decided (DEC-0043 2, DEC-0044 3); the return is Proposed (PM) |
| V5 | Edit changes rows and columns. Only the creator shares, changes visibility, or deletes the sheet. | Assumption (DEC-0044 3) |
| V6 | A group share follows the group's members. A person who joins the group gets the share, and a person who leaves the group loses it, unless they also have a direct share. When a person has both, the higher level applies. | Proposed (PM) |
| V7 | "Does not learn that it exists" covers every surface. A sheet that a person cannot see is absent from the following, with no count, title or placeholder: the Sheets tab and its count, My sheets, Appears in, Platform search, notifications, the record's History tab, record export, live-refresh events, and every API response. A request for it gets the same 404 as a missing sheet. | Decided (DEC-0044 1), surface list Proposed (PM) |
| V8 | The share dialog tells the creator that the sheet opens read-only to everyone who can read the record when the creator leaves. | Assumption (DEC-0044 2) |
| V9 | Whether a guest can receive a share, and at which level, is settled in Decisions. See Decisions, item 3. Data and API (D2) and Screens are built for option a (View only, no copy). | Settled (DEC-0045) |

### The leave event

| ID | Rule | Label |
| --- | --- | --- |
| L0 | The open state is not stored. A sheet is open when its owner is not present in the sheet's organization: the owner's account or membership is disabled, deleted or expired, or a release cutoff (D1.6) is later than the sheet's creation. Shares are never changed by a leave. | Proposed (D0); see Decisions, item 8 |
| L1 | The leave event is the creator's removal from the organization or the disable of the creator's account in that organization. In code it is one of: membership disabled (`_change_membership_status`), account disabled (`_disable_user`), membership removed (`_remove_membership`), or account deleted (`delete_user`). All are admin actions. | Decided (DEC-0044 2), code paths Proposed (PM) |
| L2 | At the leave event, each sheet that the creator owns becomes **open**. Everyone who can read the sheet's record (for a module sheet: its module) can read it, never wider. Nobody can edit it. People who had Edit keep only View. | Decided (DEC-0044 2) |
| L3 | The change happens in the same transaction as the leave action. There is no moment when the sheet is closed to everyone, or editable after the leave. L0 meets this by construction: the leave action's own write to the user or membership row is the change. A sheet write that races the leave locks the owner's user row first, so it either commits before the leave or is refused (D3.3). For account-wide paths, the sheets of the person's other organizations open too, but the security event covers only the organization of the request (D3.4). | Proposed (PM); mechanism Proposed (D0, D3.3, D3.4) |
| L4 | A re-enabled creator gets the sheets back. They become private again, with their earlier shares and levels (Edit included). Under L0 this is automatic, because the leave never changed the shares. | Assumption (DEC-0044 2); mechanism Proposed (D0) |
| L5 | The disable and remove confirmations show how many private sheets will open. They show a count only, never titles or records. The count comes from an admin-only route, `GET /api/users/{user_id}/worksheet-impact` (D3.2). | Assumption (DEC-0044 2); route Proposed (D3.2) |
| L6 | A person who can read an open sheet can **Make a copy**. The copy is a new private sheet that they own, on the same record. It has the same columns, rows and links, and no shares. Whether a guest can copy is settled in Decisions: DEC-0044 2 lets any reader copy, and DEC-0043 1 lets no guest create. See Decisions, item 3. | Assumption (DEC-0044 2); copy content Proposed (PM); guests settled (DEC-0045) |
| L7 | An open sheet cannot be deleted, renamed or shared by anyone while it is open (409 `worksheet_open`). Whether an admin may delete an open sheet is settled in Decisions. See Decisions, item 9. | Proposed (PM) |
| L8 | L4 names re-enable only. A restore (`restore_user`, after a removal or an account delete) and a new invitation after a removal are not covered. Under L0 a restore returns the sheets automatically. Keeping them open after a new invitation needs the `memberships.worksheets_released_at` cutoff (D1.6). See Decisions, items 6 and 7. | Settled (DEC-0045) |
| L9 | A creator who loses read on the module but stays an active member does not trigger the leave event. The sheets stay private and owned. The creator cannot open them until read returns (V4). Recipients who can still read the record keep their shares. | Proposed (parent); the recipient clause is Proposed (PM) |
| L10 | The open-sheet line names the owner and says that the sheet is now read-only to every reader of the record. Its wording ("left" or "no longer has access") and whether it shows a date are settled in Decisions. L0 stores no leave time. See Decisions, item 10. | Settled (DEC-0045) |

### Columns, computed columns and totals

| ID | Rule | Label |
| --- | --- | --- |
| K1 | Columns use the existing field types. The structure stores the field-type names (D1.7). The Add column list shows the Sandbox's names (Screens): Text, Long text, Number, Whole number, Checkbox, Date, Date and time, Choice list, User, Email and Web link, then Link to records, Lookup and Computed. `relationship` is not a column type, because it needs a Sandbox field. The link column (N1) takes its place (422 when sent). Which stored type "Number" uses, and whether `number` is offered, is settled in Decisions. See Decisions, item 16. | Decided (DEC-0043 3); list Proposed (Screens); mapping settled (DEC-0045) |
| K2 | Currency is a display option of a `decimal` column (`decimal.currency` in D1.7). It uses the organization's currency. It is not a new type. It depends on Decisions, item 16. | Proposed (PM) |
| K3 | A computed column uses same-row arithmetic with column names in braces, for example `{Quiz 1} + {Quiz 2}`. It also supports `ROUND`, `MIN`, `MAX`, `AVERAGE` and `SUM` over listed columns of the same row. There are no cell references such as `B2` and no references to other rows or sheets. | Proposed (parent) |
| K4 | A computed column reads numeric columns (`number`, `decimal`, `int`, numeric lookups, and other computed columns). A reference loop is refused when the column is saved, and the reason names the columns in it. Expressions store column keys, so a renamed column keeps working in every expression that uses it. The grammar and its limits are in D7.1. | Proposed (PM); detail Proposed (D7.1, D7.4) |
| K5 | `SUM`, `AVERAGE`, `MIN` and `MAX` skip blank cells. Arithmetic with a blank operand gives a blank result. Division by zero gives an error mark in that cell, and in each computed cell of the same row that reads it. | Proposed (PM); propagation Proposed (D7.2) |
| K6 | The server computes the results for each request and never stores them. The grid, the sort, the totals and the export show the same value. A computed cell that reads a lookup the viewer cannot read shows "No access". Sort, search and totals use only the values the viewer can read; totals report how many cells were hidden. | Proposed (PM); masking Proposed (D7.3) |
| K7 | A totals row gives each column one of these: sum, average, min, max or count. Count works for every type and counts non-empty cells. The others work for numeric columns only. Totals cover every row of the sheet. | Proposed (parent); scope Proposed (PM) |
| K8 | A column group is a named band over adjacent columns, for example one band for each grading period. Grading periods are column groups in one sheet, not separate sheets. | Proposed (REQ-0025 item 7) |
| K9 | A **From another sheet** column shows a column of another sheet for the same linked record. Example: a summary sheet with a Student column takes "Final grade" from Class 1A for each student. Rows match through the record that both link columns point to, never through cell positions. The column is read-only, and computed columns can use it. A viewer who cannot see the source sheet gets "No access" in the column. A removed source column shows "Column removed". A record that links to two rows of the source shows "2 matches". A renamed source column keeps working. | Decided (DEC-0046); detail Proposed (parent) |

### Links and Appears in

| ID | Rule | Label |
| --- | --- | --- |
| N1 | A link column targets one module that the creator chooses. Any module of the organization that the person can read can be the target. Each cell links to one record of that module. | Decided (DEC-0043 3); rule Proposed (REQ-0025 item 4) |
| N2 | A lookup column shows a field of the linked record, as its current value. It is read-only in the sheet. It is not a typed copy. | Proposed (REQ-0025 item 4) |
| N3 | A person can set a link only to a record that they can read. | Proposed (PM) |
| N4 | A link cell whose record the viewer cannot read shows "No access", with no name and no lookup values. This is the same both-ends rule as record links (`relationships/access.py`). Access is set per module, so for one viewer this holds for a whole link column, not for single cells. See Decisions, item 4. | Proposed (PM); per column Proposed (Screens) |
| N5 | A linked record shows every row that links to it under **Appears in**. Appears in is read-only and shows only rows of sheets that the viewer can see. It therefore differs from person to person. It is a view and is not stored. | Proposed (REQ-0025 items 3 and 4) |
| N6 | A linked record that is deleted shows "Deleted record" in the cell, and a restore brings the link back. A linked record that is purged shows "Removed record", and the link does not come back. The row stays in both cases. What a lookup cell beside such a link shows is settled in Decisions. See Decisions, item 17. | Proposed (parent) for delete; Proposed (PM) for purge |
| N7 | A lookup column whose field a Sandbox publish removes shows "Field removed" until someone removes the column. | Proposed (PM) |
| N8 | A link column whose target module is closed shows its cells as "Unavailable". So does a link whose target record a lifecycle close hid. The links come back when the module reopens. | Proposed (PM); detail Proposed (D4) |

### Import and export

| ID | Rule | Label |
| --- | --- | --- |
| X1 | A sheet exports and imports two file kinds. **Data** is CSV or Excel. A **template** is the structure only, as versioned JSON. | Decided (DEC-0044 4) |
| X2 | Anyone who can see a sheet can export it. This includes recipients with View and readers of an open sheet. | Decided (DEC-0044 4) |
| X3 | Each export writes a security event like `records.export.authorized`. The event is `worksheets.export.authorized`, for data and template exports. | Decided (DEC-0044 4); name Proposed (D5.4) |
| X4 | Data export uses the record export rules, with formula-safe cells. Computed and lookup columns export as values. A link cell exports as the linked record's display name, or as "No access". | Proposed (REQ-0025 item 10) |
| X5 | A template has a `schemaVersion`. It holds the columns, types, choice lists, column groups, computed columns, totals and link columns. It holds no data, no shares, and no organization, module, record or person IDs. | Proposed (REQ-0025 item 10) |
| X6 | On template import, each link column is mapped to a module of the importing organization. The mapping is suggested by name. With no match, the column becomes a text column. A lookup whose field name is not in the mapped module also becomes a text column. A template with an unknown `schemaVersion` is refused, and nothing is created. | Proposed (REQ-0025 item 10); refusal Proposed (PM); lookup Proposed (D9.2) |
| X7 | **New sheet from this structure** copies a sheet's template into a new private sheet on a record that the person chooses, without data. Anyone who can see the sheet and can create on the target record can use it. | Proposed (REQ-0025 item 10); rights Proposed (PM) |
| X8 | Data import matches rows to records by a key column, for example an ID number. Matching uses only records that the importer can read. A preview shows three counts: matched, not matched, and matched more than once. The person keeps the unmatched rows as unlinked text or skips them. Nothing is written until the person confirms. How rows matched more than once are handled is settled in Decisions. See Decisions, item 13. | Proposed (REQ-0025 item 10); readable-only Proposed (PM) |
| X9 | Data import adds rows to a sheet that the importer can edit (owner or Edit), or creates a new sheet from the file. The file's header row maps to the columns. How a new sheet from a data file gets its column types is settled in Decisions, item 14. Whether an import into an existing sheet also updates matched rows is settled in Decisions, item 15. | Proposed (PM) |
| X10 | Excel import is new and has these rules: <br>• a size limit and a zip-expansion limit; <br>• values only, so a formula cell imports its saved result, and a formula without a saved result imports as empty and counts in the preview; <br>• macro-enabled files are refused; <br>• one tab per import; <br>• the person chooses the header row. <br>Values (D8, D9.3): `.xlsx` only, at most 10 MiB, each part at most 10 MiB uncompressed, the existing OOXML bounds, at most 10,000 rows and 100 columns. CSV is read in the browser and is the path for large sheets. | Proposed (REQ-0025 item 10); formula cells Proposed (PM); values Proposed (D8, D9) |
| X11 | Imported or pasted text that starts like a formula (`=`, `+`, `-`, `@`) is stored as text and is never evaluated. | Proposed (PM) |

### Lifecycle

| ID | Rule | Label |
| --- | --- | --- |
| F1 | When a record is deleted, its sheets are hidden with it. A restore brings them back with their shares. When the record is purged, its sheets are purged with it. Module sheets follow their module in the same way: a module close hides them, a reopen brings them back, and a purge removes them. | Proposed (parent) |
| F2 | A purge preview shows how many sheets the purge removes. It shows a count, never titles. | Proposed (parent) |
| F3 | When the creator deletes a sheet, it disappears for everyone, and its rows leave Appears in. The creator can restore it from My sheets while its record or module is live. Data and API keeps a deleted sheet until its record is purged (D4). See Decisions, item 12. | Proposed (PM); retention Proposed (D4) |
| F4 | Saves are checked per cell. A save is refused only when another person changed one of the same cells since the person loaded them (412 `cell_changed`, with the current row), and the person sees the newer values. Changes to other cells of the same row save normally. Other people's changes appear without a reload. Each column change has a sheet revision, with the same rule. | Proposed (parent) |
| F5 | Live-refresh events are opaque invalidations, as on other OpenView pages. They go only to people who can see the sheet, administrators included. A person who gains access sees live changes after at most 15 seconds. This changes `_can_receive`, a protected control (SEC-R6), so a Security Engineer review is needed before build. | Proposed (PM); mechanism Proposed (D6) |
| F6 | Limits (D8): 100 columns, 10,000 rows, 4,000 characters in a text cell, 32 KiB in a row and 8 MiB in a sheet. A change past a limit is refused with a message that names the limit (422 `worksheet_limit`). | Proposed (PM); values Proposed (D8) |
| F7 | A person who can see a sheet can sort it by one column and search its text. The sort and search are not saved and change nothing for other people. | Proposed (PM) |

### Presence

| ID | Rule | Label |
| --- | --- | --- |
| PR1 | The sheet header shows an avatar for each person who has the sheet open now. Hovering or focusing an avatar shows the name. More than four avatars collapse into "+N". | Proposed (parent) |
| PR2 | Each person's current cell has an outline in the colour of their avatar. Presence carries the cell position only, never a value or a typed character. | Proposed (parent) |
| PR3 | Only people who can see the sheet (V1–V7, L0–L2) can join its presence channel. FastAPI checks this when it issues the presence token (D13). A hidden sheet is refused like a missing sheet. Module managers and admins join only when they can see the sheet. | Proposed (parent) |
| PR4 | Everyone who can see a sheet reads the same module, so the people directory already lets them see each other (`visible_person_ids` includes module readers). Presence shows no one else. | Proposed (parent) |
| PR5 | A person who loses access to the sheet or its record stops sending and receiving presence within 60 seconds. The presence token lasts 60 seconds, and each refresh checks access again. | Proposed (parent) |
| PR6 | Presence keeps no history. It lives only in the Realtime channel: nothing is written to the database or audited, and it ends when the person leaves the channel. | Proposed (parent) |

### History and audit

| ID | Rule | Label |
| --- | --- | --- |
| H1 | Sheet and row changes go through `AuditSession`. | Proposed (parent) |
| H2 | Admin-readable audit entries record who changed which sheet row, and when. Values are redacted with `__audit_redacted_fields__`. The sheet title, row values and column definitions are redacted fields, and so are the anchor record, share recipients and link targets (D5.1). Sheet audit rows carry no department, so only administrators see them (D5.2). | Proposed (parent); title and columns Proposed (PM); detail Proposed (D5) |
| H3 | A sheet has its own row history with values. Only people who can see the sheet can read it. | Proposed (parent) |
| H4 | The record's History tab shows no sheet events. | Proposed (PM), follows V7 |
| H5 | Security events: one for each export (X3), and one for each leave event that opens sheets (`worksheets.opened_on_leave`, with the count and the leave path). For account-wide paths the event is written only in the organization of the request (D3.4). | Proposed (PM); names Proposed (D5.4) |
| H6 | Each Excel parse writes `worksheets.import.file_parsed` with its outcome and reason, and no file content. A CSV import is read in the browser and writes no file event. | Proposed (D5.4) |

H2, L5, F2, H5 and H6 give admins a trace that private sheets exist: an ID, a time or a count, never content. Decisions, item 1, asks the owner whether this fits DEC-0044 1.

### Organization-agnostic

| ID | Rule | Label |
| --- | --- | --- |
| O1 | Sheets carry no industry or region concept. There are no built-in columns, words or templates for one kind of organization. | Decided (DEC-0043 3) |
| O2 | Templates belong to each organization. | Decided (DEC-0043 3) |
| O3 | Number, date and currency display follow the organization's settings (`locale`, `currency`, `timezone`, `week_start`). A person's own date format, time format and week start apply where they already apply to records today. | Decided (DEC-0043 3); the personal override is current behavior |
| O4 | Pasted and imported numbers use the decimal separator of the organization's `locale`. | Decided (REQ-0025 item 9, DEC-0043 3) |
| O5 | Two sample packs prove the rule with real sheets: School (class sheets with a Student link column) and Manufacturer (bill-of-materials lines with an item link column). | Proposed (REQ-0025 item 9) |

## Acceptance criteria

Each criterion names its rules. "Not found" means the same response as for a sheet or record that does not exist.

| ID | Criterion | Rules |
| --- | --- | --- |
| SH-1 | A member with `read` only on a module opens a readable record and creates a sheet. The sheet appears in that record's Sheets tab and in their My sheets. | C1, P2, P4 |
| SH-2 | The same is true for members with `write` and with `manage`. | C1 |
| SH-3 | A guest who can read the record sees no New sheet. A direct API create by the guest is refused. | C3 |
| SH-4 | A create on a deleted record, on a record of a closed module, or on a record of a module the person cannot read is refused. The last case returns "not found". | C4 |
| SH-5 | After any sheet action of the slice under test (in S1: create, edit, share, export, delete; S2 adds import and copy), the record's fields, revision, links, files, History tab and audit rows are unchanged. | C2, H4 |
| SH-6 | Teacher B has the same module access as Teacher A. Teacher B sees none of Teacher A's private sheets: no row in the Sheets tab, no count, no My sheets row, no Appears in row, no search hit, no event, and "not found" from the sheet link and every sheet API route. | V1, V3, V7, P6 |
| SH-7 | A module manager and an organization admin get the same result as SH-6 for a private sheet that is not shared with them. | V3, V7 |
| SH-8 | The creator gives Person X View. X sees the sheet in My sheets and in the Sheets tab, can read and export it, and cannot change rows or columns. The API refuses X's writes. | V2, X2 |
| SH-9 | The creator gives Person Y Edit. Y can add, change and delete rows and columns. Y cannot rename, share, change visibility or delete the sheet, and the API refuses those actions. | V2, V5, C5 |
| SH-10 | The creator gives Group G View. A person who joins G gets the sheet, and a person who leaves G loses it, unless they also have a direct share. A person with View through G and Edit directly has Edit. | V6 |
| SH-11 | A recipient who loses read on the record no longer sees the sheet anywhere, and gets "not found". When read returns, the share works again without any action by the creator. | V4 |
| SH-12 | The share dialog shows the sentence that the sheet opens read-only to record readers when the creator leaves. | V8 |
| SH-13 | An admin disables the creator in the organization. From the commit of that action, with no sheet write, every sheet that the creator owns reads as open: readable by every reader of its record and by nobody else. No one can edit it, and former Edit recipients can only view. The same holds for each of the other three leave paths in L1. | L0, L1, L2, L3 |
| SH-14 | After SH-13, a person who cannot read the sheet's record still gets "not found". | L2, V4 |
| SH-15 | Before the admin confirms a disable or a removal, the confirmation shows the number of private sheets that will open, from the `worksheet-impact` route (SH-55). It shows no titles and no records. With zero sheets, the line does not show. | L5 |
| SH-16 | The admin re-enables the creator. Each sheet is private again, with its earlier shares and levels, Edit included. No share row changed during the leave. | L0, L4 |
| SH-17 | A member who can read an open sheet uses Make a copy. They own a new private sheet on the same record, with the same columns, rows and links and no shares. The guest case follows the answer to Decisions, item 3. | L6 |
| SH-18 | Nobody can delete, rename or share an open sheet. The API refuses these actions. | L7 |
| SH-19 | A creator who loses read on the module but stays active cannot open their sheets ("not found"). The sheets do not open to record readers. Recipients who still read the record keep their shares. When read returns, the creator has the sheets as before. | L9 |
| SH-20 | A sheet can have columns of each type in K1. A `relationship` column type is refused. A `decimal` column with the currency option shows the organization's currency. | K1, K2 |
| SH-21 | A computed column `{Quiz 1} + {Quiz 2}` shows the sum for each row. `ROUND`, `MIN`, `MAX`, `AVERAGE` and `SUM` over listed columns of the same row give the expected values. An expression with a cell reference such as `B2`, an unknown column, a non-numeric column or a loop is refused when saved, with the reason. | K3, K4 |
| SH-22 | When Quiz 1 is renamed, the computed column still works and shows the new name. | K4 |
| SH-23 | Blank cells are skipped by the functions and give a blank result in arithmetic. A division by zero marks only that cell. A computed value is the same in the grid, the sort, the totals and the export. | K5, K6 |
| SH-24 | The totals row shows the chosen sum, average, min, max or count for each column over all rows. Count is offered for every type, and the others for numeric columns only. | K7 |
| SH-25 | Columns can be put in a named column group. The group shows as a band over its columns, and a computed column can use columns from several groups. | K8 |
| SH-26 | A link column targeting Student List lets a writer pick only Student List records that they can read. A lookup column shows the linked record's current field value and changes when the record changes. The lookup cell cannot be edited. | N1, N2, N3 |
| SH-27 | A viewer who can see the sheet but cannot read a linked record sees "No access" in that cell, with no name and no lookup values. The same holds in the export. | N4, X4 |
| SH-28 | Student A's record shows Appears in with every row that links to Student A in sheets that the viewer can see, and only those. Two people with different shares see different lists. Appears in is read-only. | N5, V7 |
| SH-29 | When the linked record is deleted, the cell shows "Deleted record", and a restore brings the link back. When it is purged, the cell shows "Removed record". The row stays in both cases. | N6 |
| SH-30 | When a Sandbox publish removes a field used by a lookup column, the column shows "Field removed". When the link column's target module closes, its cells show as unavailable and come back on reopen. | N7, N8 |
| SH-31 | A person who can see a sheet exports it as CSV and as Excel. The file has all rows and columns, with lookup values as values and formula-safe cells. Each export writes one security event. | X2, X3, X4 |
| SH-32 | A template export is valid JSON with `schemaVersion`. It contains no row data, no shares, and no organization, module, record or person IDs. | X5 |
| SH-33 | A template import in another organization suggests a module for each link column by name, lets the person change it, and makes an unmatched link column a text column. An unknown `schemaVersion` is refused, and nothing is created. | X6, O2 |
| SH-34 | New sheet from this structure creates a private sheet with the same columns, groups, computed columns and totals, and no rows and no shares. | X7 |
| SH-35 | A data import with a key column shows the counts matched, not matched, and matched more than once before anything is written. Records that the importer cannot read count as not matched. The person keeps the unmatched rows as text or skips them. Cancel writes nothing. | X8, X9 |
| SH-36 | Excel import reads one chosen tab with a chosen header row. A file over the size limit or the zip-expansion limit is refused, and so is a macro-enabled file. A formula cell imports its saved result. A formula with no saved result imports empty and is counted in the preview. | X10 |
| SH-37 | Text that starts with `=`, `+`, `-` or `@`, imported or pasted, is stored as text and exports formula-safe. | X11, X4 |
| SH-38 | Numbers typed, pasted or imported use the organization's decimal separator. Dates and numbers show in the organization's formats, or in the person's own formats where those apply today. | O3, O4 |
| SH-39 | The product code holds no industry words for sheets. The School and Manufacturer sample packs create sheets through the real APIs (class sheets linked to students; BOM lines linked to items). | O1, O5 |
| SH-40 | When a record is deleted, its sheets disappear everywhere, including My sheets and Appears in, and a restore brings them back with their shares. A purge removes them. The purge preview shows the number of sheets and no titles. | F1, F2 |
| SH-41 | The creator deletes a sheet. It disappears for every recipient and from Appears in. The creator can restore it from My sheets. | F3 |
| SH-42 | Two editors change different cells of the same row: both saves succeed. Two editors change the same cell: the second save is refused and shows the newer value. A change by one editor appears for the other without a reload. | F4 |
| SH-43 | Live-refresh events for a sheet reach only people who can see it, administrators included, and they carry no row values. | F5, V7 |
| SH-44 | A change past each limit in F6 (columns, rows, text cell, row size, sheet size) is refused with 422 `worksheet_limit` and a message that names the limit. | F6 |
| SH-45 | Each sheet and row change writes an audit row. In the admin audit log, the row shows actor, time, sheet ID and row ID, with the title, values and columns redacted. | H1, H2 |
| SH-46 | A person who can see the sheet opens its history and sees each row change with values, author and time. A person who cannot see the sheet gets "not found". | H3 |
| SH-47 | A leave event that opens sheets writes a security event with the count. | H5 |
| SH-48 | The record panel shows a Sheets tab, in the position that Screens sets. The other tabs, their order and the panel width do not change. With no visible sheets, the tab shows its empty state, with New sheet for people who can create. | P2, Preserved behavior |
| SH-49 | A sheet opens as a full-width page. At 1280×720 and 1440×900 the document does not scroll, and only the grid pane scrolls. | P3 |
| SH-50 | At 390px the grid scrolls sideways with the first column pinned, nothing else scrolls sideways, and targets are at least 44px. Tapping a row opens it as a form in a bottom panel. Saving the form saves the row under F4. | P5 |
| SH-51 | Saved views, record list counts, record export and import, Charts, Reports and Dashboards return the same results before and after sheets exist on their records. | P8, Preserved behavior |
| SH-52 | Every visible label says "Sheets", "sheet" or "New sheet". No screen, message or export shows the word "Worksheet". | P7 |
| SH-53 | A viewer sorts a sheet by one column and searches it. Only matching rows show, in the chosen order. After a reload, and for every other person, the sheet shows in its saved order with no search. | F7 |
| SH-54 | A keyboard-only person moves between cells with the arrow keys, edits a cell, and leaves it, with visible focus at each step. A screen reader announces the column name and value of the focused cell. With reduced motion, the grid has no motion. | P9 |
| SH-55 | `GET /api/users/{user_id}/worksheet-impact` answers an admin with `{"opening_count": n}`, where n is the number of sheets that the leave would open in this organization. It carries no titles and no records. A non-admin gets 403. The count is taken before the change, so it is not 0 after the leave starts. | L5, D3.1, D3.2 |
| SH-56 | A sheet is created on a record after an admin opens the purge preview. The purge is then refused with "Lifecycle impact changed after planning", and nothing is removed. The preview response has `worksheet_count`. | F1, F2, D4 |
| SH-57 | An Edit recipient saves a row while an admin disables the owner. Either the save commits before the disable, or it is refused because the sheet is open. No save commits after the sheet reads as open. | L3, D3.3 |
| SH-58 | A viewer who cannot read a lookup's module sees "No access" in the lookup and in each computed cell that reads it. Sorting and searching on those columns place and match those cells as blank. Totals skip them and report the number hidden. The export writes "No access". | K6, N4, D7.3 |
| SH-59 | Each Excel parse, accepted or refused, writes one `worksheets.import.file_parsed` event with its outcome and reason, and no file content. A CSV import writes none. | H6 |
| SH-60 | An installation owner disables an account that belongs to two organizations. The person's sheets in both organizations read as open. The `worksheets.opened_on_leave` event is written only in the organization of the request. | L0, L3, H5, D3.4 |
| SH-61 | After a restore (`restore_user`), the person's sheets are private again, with their earlier shares. After a new invitation following a removal, the outcome follows Decisions, items 6 and 7. | L8 |
| SH-62 | Every account, including one with no department access, sees My sheets in the sidebar. An open sheet that was never shared with the person does not show in their My sheets but shows in the record's Sheets tab. | P4 |
| SH-63 | Two people who can see a sheet open it. Each sees the other's avatar in the header and the other's current cell outlined. When one closes the sheet, the avatar is gone within 60 seconds. | PR1, PR2, PR6 |
| SH-64 | A peer with the same module access, a module manager and an admin who cannot see a private sheet are refused a presence token, cannot join its channel, and never appear in its presence. | PR3 |
| SH-65 | A present person who loses the share, or read on the record, stops receiving presence, and disappears from every other viewer's presence, within 60 seconds. | PR5 |
| SH-66 | Presence messages carry only the person's ID and cell position, never a cell value. No presence row reaches the database or the audit log. | PR2, PR6 |
| SH-67 | A member with `read` on a module creates a module sheet from the module page. It is private until shared, its rows can link to records, and it shows in the module page list and My sheets. A person who cannot read the module gets "not found". | P1, P2, C1, V4 |
| SH-68 | When the owner of a module sheet leaves, everyone who can read the module can read it, read-only. A module close hides it, a reopen returns it, and a purge removes it. | L2, F1 |
| SH-70 | A View recipient and a reader of an open sheet who cannot read a linked module or see a source sheet get no source sheet ID and no module, department or field names from the sheet, its 412 body or its template export. The owner gets everything. Saving with a hidden source and with a missing source gives identical 422 bodies. | D14 |
| SH-71 | The presence token joins only its own sheet topic; the OpenComms token is refused on a sheet topic even with a live grant; a presence token is refused on a conversation topic, on another sheet's topic and with another organization's prefix; a broadcast on a sheet topic is refused. | D13 |
| SH-72 | A computed-column chain whose expanded size exceeds the budget is refused at save in under 1 second; 1,000 characters of nested brackets give 422. | D7.1 |
| SH-69 | A From another sheet column shows the source value for each linked record. A viewer who cannot see the source sheet sees "No access". A removed source column shows "Column removed", and two matching source rows show "2 matches". A computed column that reads it uses the same values. | K9 |

## Screens

From TASK-0099 (Product Designer). Its decisions are in Decisions, items 4, 10, 13 to 17.

> Comp: `.impeccable/mocks/openview/sheets.html` (ignored by Git), base `8c8d2b02`. The data is fictional: Larkspur College, College of Computer Studies (CCS). Serve the folder over HTTP and open `sheets.html?screen=<state>`; states: `tab`, `tab-empty`, `tab-shared`, `new`, `sheet`, `share`, `open`, `appears`, `my`, `import`; extras `&col=pick|link|lookup|calc|calcerr|fg`, `&pop=export|more`, `&conflict=1`, `&row=4`, `&theme=light`, `&phone=1`, `&bare=1`.

**Layout rules for every screen**
- The **Sheets** tab is the last record tab, after History. When History is hidden, it follows Files. The tab count is the number of sheets on the record that the viewer can see; at 0 it shows no count. Appears in keeps its own count. A sheet the viewer cannot see adds nothing.
- **My sheets** sits in the sidebar foot, above OpenComms. Every account sees it, whatever its department access.
- The **sheet page stays still at every width, the phone included**. The header sits over one grid pane that scrolls alone, so the column headers, the first column and the totals row can stay fixed. This is a stated exception to "phones scroll the page" (DESIGN.md).
- At 390px, the record panel's five tabs scroll sideways in their own row. The page does not.

**1. Record panel, Sheets tab** (SH-48; SH-1 entry point; SH-6 and SH-7 for this surface; SH-52)
- The record panel keeps its 540px width. The Sheets tab has two sections.
- **On this record:**
  - A header with the count and a **New sheet** button. The button is hidden for guests (C3).
  - One row per visible sheet: title, "15 rows · changed Nov 21 by you", and the access on the right ("Shared", "Only you", "Edit", "View").
  - Empty state, same frame with a dashed border: "No sheets on this record yet" / "A new sheet is visible only to you until you share it."
- **Appears in** follows (screen 6). Empty: "No rows link here" / "Rows of sheets you can see that link to this record show here."
- The record panel shows no Edit action for a member with read only. A member with read only can still create a sheet (C1).
- States:
  - `tab`: Andrea Villamor's record, 3 sheets.
  - `tab-shared`: Bernard Ocampo's record. Only the 2 sheets he shared with Andrea show.
  - `tab-empty`: a record with no visible sheet. There is no count and no placeholder (V7).

**2. New sheet and columns** (SH-20 partial, SH-21 partial, SH-24, SH-25, SH-26, SH-33 partial)
- **The New sheet dialog** opens from the Sheets tab.
  - Its subtitle is the record: "On Andrea Villamor · Faculty Members". It has a Name field.
  - **Start with** offers three choices: **Blank sheet**, **Template file** (.json) and **Data file** (CSV or Excel).
  - The bottom line says "Only you can see it until you share it."
- **Template file:**
  - It shows the file summary ("14 columns · 3 column groups · 1 computed column · totals") and maps each link column to a module: "Student → Student List" with "Suggested: same name."
  - A link column with no matching module becomes text: "No module named Section. It becomes a text column."
  - An unknown version is refused: "This template has a version that this installation cannot read. Nothing was created." Create sheet is disabled.
- **Data file:** the primary button is **Check the rows**, which opens screen 8. Buttons: Cancel, and **Create sheet** or **Check the rows**.
- **Add column** is a popover on the "+" column header, with fields Name, Type, Column group and Total.
  - Type list, values: Text, Long text, Number, Whole number, Checkbox, Date, Date and time, Choice list, User, Email, Web link.
  - Type list, from other data: Link to records, Lookup, From another sheet, Computed.
  - **Link:** "Links to" a module; "Each cell links to one record that you can read."
  - **Lookup:** "From" a link column, and "Shows" a field; "Read-only. It shows the record's current value."
  - **Computed:** an expression in code type, buttons that insert `{column}` names and functions, and a live result for row 1.
  - **Error:** the unknown name is marked, with "{Quiz 7} is not a column of this sheet." Add column is disabled.
  - Total: Count for any column; Sum, Average, Min, Max for numeric columns. Clicking the Final grade header opens the same popover as **Column settings**, with its expression.

**3. Sheet page** (SH-8, SH-9, SH-23 partial, SH-24, SH-25, SH-26, SH-27, SH-29, SH-31, SH-32, SH-34, SH-41, SH-42, SH-49, SH-52, SH-53, SH-54)
- **Breadcrumb:** department › module › **record** › sheet. The record crumb opens the record panel.
- **Header:**
  - The title, with an access chip: "Shared with 2 people and 1 group", "You can view · shared by …" or "You can edit · shared by …".
  - Under the title: "On Andrea Villamor · Faculty Members · 15 rows · Owner: you".
  - Actions for the owner: **Import**, **Export ▾**, **Share** (primary), **More**.
  - The Edit recipient has no Share. The View recipient has only Export and More.
- **Export menu:**
  - Download CSV: "All rows. Computed and lookup columns as values."
  - Download Excel.
  - Download template: "Columns and settings only, no rows (.json)."
- **More menu:**
  - Rename (owner only).
  - Sheet history.
  - New sheet from this structure: "Same columns, on a record you choose. No rows."
  - Delete sheet (owner only).
- **Toolbar:**
  - "Search this sheet" and one **Sort** button, then "Saved".
  - When used: the typed text with a clear button, "Final grade, high to low", and "9 of 15 rows". Neither is saved.
- **Grid:**
  - Band and header rows are fixed at the top. The first column (row number + Student) is fixed at the left. The totals row is fixed at the bottom.
  - Column group bands: Prelim, Midterm, Finals.
  - Type icon in each header. Lookup and computed cells have a light shaded background and accept no edit.
  - Link cells:
    - The name as a link.
    - **"Deleted record"**, with a trash icon.
    - **"Removed record"**.
    - **"No access"**, with a lock icon, no name and no lookup values.
  - A blank Finals exam gives a blank Final grade. The Final grade expression is `ROUND({Prelim exam} * 0.3 + {Midterm exam} * 0.3 + {Finals exam} * 0.4, 2)`.
  - **Totals** show a small label over each value ("Count", "Average"). During a search, the first totals cell reads "Count · all 15 rows".
  - "Add row" is the last row and "+" is the last column. Both are hidden when the viewer cannot edit.
- **Cell in edit:** a 2px action-colour outline and the typed value. Arrow keys move between cells, Enter edits, Escape leaves the cell.
- **Row conflict:** the row is tinted with the warning colour and the changed cell is outlined. A line under the row says: "**Diego Navarro changed this row while you were editing it.** It now shows the newer values. Your Quiz 4 (18) was not saved." Buttons: **Edit Quiz 4 again**, **Dismiss**.

**4. Share** (SH-10, SH-11, SH-12; SH-8 and SH-9 levels)
- Dialog "Share Class 1A", subtitle "View reads and exports. Edit also changes rows and columns."
- Top row: "Add people or groups", a level (View or Edit), and **Share**.
- List: the owner ("Owner"), each person and group with a level control and Remove. A group shows "Group · 12 people". Guests are offered at View only (V9; Decisions, item 3). The picker lists the people the owner can see in the bound organization and the groups the owner belongs to (route 25).
- Two lines at the bottom:
  - "People see this sheet only while they can read Andrea Villamor's record."
  - "If you leave Larkspur College, this sheet opens read-only to everyone who can read Andrea Villamor's record."
- Footer: **Done**.

**5. Open sheet after the owner left** (SH-13, SH-17, SH-18, SH-31; UI side only)
- The viewer is a reader of the record. Chip: **Read-only**.
- Directly under the title: "Andrea Villamor left Larkspur College on Nov 22. Everyone who can read Andrea Villamor's record can read this sheet. Nobody can change it."
- Actions: only **Export ▾** and **Make a copy** (primary). There is no Share, Import, More, Add row or "+".
- **Make a copy** opens a dialog:
  - Name: "Class 1A (copy)", with "On Andrea Villamor · Faculty Members, the same record."
  - Line: "You get the same columns, rows and links. Only you can see the copy until you share it."

**6. Appears in** (SH-28)
- Student List record "Alyssa Mercado", Sheets tab. **On this record** is empty, with New sheet. **Appears in** has one row per linking sheet row.
- Each row shows the sheet title and "owner · row N". Opening a row shows the whole row as read-only label and value pairs, then the link "Open the sheet at this row", which opens the sheet with that row highlighted.
- Only rows of sheets that the viewer can see are listed.

**7. My sheets** (SH-1, SH-8, SH-10, SH-41)
- A still page. Title "My sheets", with "Sheets you own and sheets shared with you · 5 sheets" under it.
- Toolbar: search, then a selector All / Owned by me / Shared with me / Deleted, with counts.
- Table: Sheet, On record, Owner, Your access, Rows, Last change. Access examples: "Owner · shared", "Owner · only you", "Edit", "View · CCS Faculty".
- **Deleted:** Sheet, On record, Deleted, and a **Restore** button (owner only).
- **Empty:** "No sheets yet. Open a record and use New sheet in its Sheets tab."
- Phone: each row shows the name, the access and a line under them with the details.

**8. Import preview** (SH-35; SH-36 partial)
- A wide dialog: "New sheet Class 4D from a file", or "Add rows to Class 1A from a file". Three numbered steps in reading order:
  1. **File:** the file, plus Tab and Header row choices.
  2. **Columns:** each file column → a sheet column, or "Not added".
  3. **Match the Student column:**
     - "Find each row's student by [Full name] = [Name in Student List]", with "Only records you can read count as matches."
     - Count filters: Matched 12 · Not matched 2 · Matched more than once 1.
     - A row preview with each row's result.
     - "The 3 rows without one match": **Keep them, with the name as unlinked text** or **Skip them**.
     - Warning: "1 cell in Prelim has a formula with no saved result. It is added empty."
- Footer: "Nothing is added until you confirm." Buttons: Cancel, and **Create Class 4D with 15 rows** or **Add 15 rows to Class 1A**.

**9. Phone, 390×844** (SH-50)
- The header wraps: title, access chip, meta, then one row of 44px actions (primary stretched).
- Search fills the toolbar, with a 44px sort button.
- The grid pane fills the rest. The first column (160px) stays fixed while the rest scrolls sideways. Cells are 44px tall.
- Tapping a row, or the student name, opens the **row form in a bottom panel**:
  - Header: the student name, "Row 5 of 15 · Class 1A", previous and next row, and close.
  - Fields: Student (picker, with "Open … 's record"), then Student number (read-only, "Lookup from Student List. Read-only.").
  - Groups Prelim, Midterm and Finals, each with two quizzes and the exam as 44px number fields.
  - Final grade (read-only, with its expression), then Remarks.
  - Buttons: Cancel and **Save row**. A read-only viewer gets **Close** only.

**Not shown in the comp** (UI-bearing):
- SH-3: guest state (the rule is stated above).
- SH-14 and SH-6: the "not found" page.
- SH-15: the disable and remove confirmation count, in Access.
- SH-16 and SH-19: return and lost-access states.
- SH-22: rename.
- SH-23: the division-by-zero mark.
- SH-30: "Field removed" and the closed-module cell.
- SH-36: the size, zip and macro refusals.
- SH-37 and SH-38: formula text and formats.
- SH-40: the purge preview count.
- SH-44: the limit message.
- SH-46: the sheet history panel.
- SH-63 to SH-66: presence avatars in the header and cell outlines.
- SH-67 and SH-68: module sheets on the module page.
- SH-69: the From another sheet column.

## Data and API

From TASK-0100 (Software Architect). References to "Decisions, item N" and "Decision N" use the numbers of the merged list below.

> Source: TASK-0100 (Software Architect), 2026-11-24. Code facts were checked at `8c8d2b02`. **Current** marks a code fact, with its source. **Proposed** marks this design. Nothing here is approved: every schema, API and dependency change below is on the backend go-ahead list.

### D0. The main choice: the open state is derived, not stored

**Proposed.** A sheet has no stored `state` column, and a share keeps no "level before the leave". The open state is calculated on every read from rows that the leave paths already change:

- A sheet is **open** when its owner is **not present** in the sheet's organization.
- The owner is **present** when the owner's account and membership pass `active_account_clause` (`access/policy/readers.py:21-30`: user `active` and not deleted, membership `active` and not deleted, not expired, invitation accepted), and the membership has no release cutoff after the sheet's `created_at` (D1.6).

Why derived:

1. **Account-wide leave paths.** `_disable_user` sets `users.status` and `delete_user` sets `users.is_deleted` (`access/users/account_operations.py:334`, `:391-394`). Both reach every organization of the person (`access/users/coordination.py:176-195`). Each request transaction is bound to one organization, and RLS on `slateops.org_id` stops writes to the sheets of the other organizations (`docs/architecture/06-data-architecture.md`, "Organizations and row-level security"). A stored state could not change in the same transaction (L3) for those organizations. A derived state changes with the user row.
2. **L3 by construction.** The state changes in the leave transaction, because it is the leave transaction's own write.
3. **L4 by construction.** Shares are never changed by the leave, so re-enable and restore bring back the earlier shares and levels, Edit included.
4. **No missed path.** A future way to disable or remove a person changes sheet state with no new hook.

What it costs: every sheet read joins the owner's `users` and `memberships` rows (unique `(org_id, user_id)`, `access/users/models.py:126`). Admins see no audit row for "sheet opened" (the security event in D5.4 records the count instead).

This deviated from the first draft of the go-ahead list ("state (private or open)", "the level before the leave event", "change sheet state in the same transaction"). The go-ahead list below now follows D0. See Decisions, item 8.

### D1. Tables

All five tables live in `backend/app/systems/openview/worksheets/models.py`, because sheets are part of OpenView (P1). They follow the organization-table rules (`backend/migrations/AGENTS.md`, "Hard rules"):

- inherit `BaseModel` (UUIDv7 `id`, `created_at`, `updated_at`, `is_deleted`, `deleted_at`, `performed_by`; `core/base_model.py:17-52`);
- `org_id NOT NULL` with a foreign key to `organizations` (`ON DELETE RESTRICT`), `UniqueConstraint("org_id", "id")`, and composite `(org_id, <ref>_id)` foreign keys with `ON DELETE RESTRICT` (D09; pattern `sandbox/records/models.py:18-28`);
- an RLS policy for `slateops_app` on `slateops.org_id`, added on purpose in the generated revision, as in the `POLICIES` of root `e46611902f25`;
- registration in `core/database/model_registry.py`. The revision is generated from the models and reviewed operation by operation.

Column IDs are **sheet-local keys**, `^c[0-9a-z]{1,8}$` (for example `c1`, `c2`), and are never reused in a sheet. They are not UUIDs as in `Record.data`. Reason: a UUID key adds about 40 bytes to each cell, and the sheet size cap (D8) would then hold about 4 times fewer cells.

#### D1.1 `worksheets`

| Column | Type and rule |
| --- | --- |
| `record_id` | `uuid NULL`; FK `(org_id, record_id)` to `records (org_id, id)`, `RESTRICT` (`fk_worksheets_record_id_records`). Pattern: records to modules (`records/models.py:20-23`). |
| `module_id` | `uuid NULL`; FK `(org_id, module_id)` to `modules (org_id, id)`, `RESTRICT`. Set for a module sheet. `CHECK ((record_id IS NULL) <> (module_id IS NULL))`: a sheet has exactly one anchor. Index `(org_id, module_id)`. |
| `owner_id` | `uuid NOT NULL`; FK `users.id`, `RESTRICT`. Pattern: `comms_conversations.created_by` (`comms/conversations/models.py`). Never changes. |
| `title` | `text NOT NULL`; `CHECK (btrim(title) <> '' AND char_length(title) <= 200)`. Pattern: `ck_groups_name_not_blank` (`access/policy/models.py:32`). |
| `structure` | `jsonb NOT NULL`: columns, column groups and totals (D1.7). It is validated by a Pydantic model on each write. |
| `revision` | `integer NOT NULL DEFAULT 1`, `CHECK (revision > 0)`. It goes up on each title or structure change. Pattern: `saved_views.revision` (`openview/views/models.py:37`, `:54`). |
| `live_row_count` | `integer NOT NULL DEFAULT 0`, `CHECK (live_row_count BETWEEN 0 AND 10000)`. |
| `data_bytes` | `bigint NOT NULL DEFAULT 0`, `CHECK (data_bytes BETWEEN 0 AND 8388608)`. |

- The two counters are changed in each row write, under the sheet lock (D3.3). The CHECKs enforce the row and size limits in the database (postgres-patterns rule 2).
- Indexes: `ix_worksheets_record (org_id, record_id)` serves the Sheets tab, the purge scope and the record FK check. The FK check covers deleted rows, so the index has no filter (the reason in `relationships/models.py:57-60`). `ix_worksheets_owner (owner_id, org_id)` serves My sheets and the leave count.
- Soft delete: the owner's delete (F3) sets `is_deleted`. Record delete writes nothing here (D4).
- `__audit_redacted_fields__ = {"title", "structure", "record_id", "module_id"}`.

#### D1.2 `worksheet_rows`

| Column | Type and rule |
| --- | --- |
| `worksheet_id` | `uuid NOT NULL`; FK `(org_id, worksheet_id)` to `worksheets`, `RESTRICT`. |
| `position` | `bigint NOT NULL`. It sets the saved order (F7), with a gap of 1024 between rows. A full gap renumbers the sheet's rows under the sheet lock. Pattern: `comms_conversations.position` (`BigInteger`). |
| `data` | `jsonb NOT NULL DEFAULT '{}'`, keyed by column key; `CHECK (jsonb_typeof(data) = 'object')`. |
| `data_bytes` | `integer NOT NULL`, `CHECK (data_bytes BETWEEN 0 AND 32768)`. It holds the serialized size of `data`, which feeds `worksheets.data_bytes`. |
| `revision` | `integer NOT NULL DEFAULT 1`, `CHECK (revision > 0)`. |

- `UniqueConstraint("org_id", "worksheet_id", "id")`. This is the target of the row-link foreign key, so a link cannot point into another sheet. Pattern: `uq_saved_views_id_module` (`openview/views/models.py:38`).
- Indexes: `ix_worksheet_rows_order (worksheet_id, position, id) WHERE is_deleted IS FALSE` for the grid. The unique `(org_id, worksheet_id, id)` serves the FK check and the purge.
- Soft delete is a row delete. A removed column's key stays in `data` until the row's next save, which drops it. Reason: a column removal does not rewrite up to 10,000 rows. Pattern: a record keeps the values of closed fields (`records/router.py:381-384`).
- `__audit_redacted_fields__ = {"data"}`.

#### D1.3 `worksheet_shares`

This table copies `comms_channel_access` (`comms/conversations/models.py`, class `CommsChannelAccess`).

| Column | Type and rule |
| --- | --- |
| `worksheet_id` | `uuid NOT NULL`; FK to `worksheets`, `RESTRICT`. |
| `subject` | `text NOT NULL`, `user` or `group`. |
| `user_id` | `uuid NULL`; FK `users.id`, `RESTRICT`. |
| `group_id` | `uuid NULL`; FK `(org_id, group_id)` to `groups`, `RESTRICT`. |
| `level` | `text NOT NULL`, `CHECK (level IN ('view', 'edit'))`. This is the level kept for the leave event: the leave never changes it (D0), and the access rule reads it as `view` while the sheet is open. |
| `created_by` | `uuid NOT NULL`; FK `users.id`, `RESTRICT`. |

- `CHECK ((subject = 'user' AND user_id IS NOT NULL AND group_id IS NULL) OR (subject = 'group' AND group_id IS NOT NULL AND user_id IS NULL))`.
- Partial unique index `uq_worksheet_shares_active (org_id, worksheet_id, subject, user_id, group_id) NULLS NOT DISTINCT WHERE is_deleted IS FALSE`.
- Indexes `(org_id, worksheet_id)`, `(org_id, user_id)`, `(org_id, group_id)`.
- Soft delete removes a share. A share to a deleted group matches no one, because the reader joins only live `groups` and `group_members`.
- `__audit_redacted_fields__ = {"user_id", "group_id"}`. Who a sheet is shared with is sheet content.

#### D1.4 `worksheet_row_links`

This table copies the `RelationshipEdge` behavior (`sandbox/relationships/models.py:21-80`): restricting record foreign keys, soft delete, a partial unique index, a target index, and visibility only when both ends are readable (`relationships/access.py`).

| Column | Type and rule |
| --- | --- |
| `worksheet_id`, `row_id` | `uuid NOT NULL`; FK `(org_id, worksheet_id, row_id)` to `worksheet_rows (org_id, worksheet_id, id)`, `RESTRICT`. |
| `column_key` | `text NOT NULL`, `CHECK (column_key ~ '^c[0-9a-z]{1,8}$')`. |
| `target_record_id` | `uuid NULL`; FK `(org_id, target_record_id)` to `records`, `RESTRICT`. |
| `target_removed` | `boolean NOT NULL DEFAULT false`. |

- `CHECK ((target_record_id IS NULL) = target_removed)` (`ck_worksheet_row_links_target`). A purge sets the target to NULL and `target_removed` to true, so the cell shows "Removed record" (N6).
- Partial unique index `uq_worksheet_row_links_cell (row_id, column_key) WHERE is_deleted IS FALSE`: one link per cell (N1).
- `ix_worksheet_row_links_target (target_record_id) WHERE is_deleted IS FALSE AND target_record_id IS NOT NULL` for Appears in. `ix_worksheet_row_links_target_fk (org_id, target_record_id)`, with no filter, for the record FK check. `(org_id, worksheet_id)` for copy and purge.
- The link column's target module is in `structure`, so the database cannot check it. The write checks it under the target record lock (D3.3).
- `__audit_redacted_fields__ = {"target_record_id", "column_key"}`. A link target is a cell value.

#### D1.5 `worksheet_row_revisions` (sheet history, H3)

This table copies `CommsMessageRevision` (`comms/messages/models.py:172-176`): an audited, insert-only revision row with a redacted body.

| Column | Type and rule |
| --- | --- |
| `worksheet_id`, `row_id` | FK `(org_id, worksheet_id, row_id)` to `worksheet_rows`, `RESTRICT`. |
| `revision` | `integer NOT NULL`, `CHECK (revision > 0)`; unique `(row_id, revision)`. |
| `action` | `text NOT NULL`, `CHECK (action IN ('create', 'update', 'delete', 'restore'))`. |
| `data` | `jsonb NOT NULL`: the row's stored cells after the change, with the link targets. |
| `changed_keys` | `jsonb NOT NULL`: an array of column keys. |

- The author is `performed_by`. The index `(org_id, worksheet_id, created_at, id)` serves the history list.
- The reviewed migration revokes `UPDATE` from the runtime role, as the Comms revision comment asks. `DELETE` stays for the purge.
- `__audit_redacted_fields__ = {"data", "changed_keys"}`.

#### D1.6 One new column on `memberships` (Decision 6 support)

`memberships.worksheets_released_at timestamptz NULL`. An invitation of a removed person sets it to `now()` in the same transaction, because the invitation reuses the removed membership row (`access/users/service.py:207-243`, `removed or Membership(...)`). The sheets that person owns in that organization, with `created_at` before the cutoff, then stay open for good (Decision 6, recommended b for a new invitation). `restore_user` does not touch it, so a restore returns the sheets (recommended a for a restore). `memberships` has no RLS (06, "Organizations and row-level security"). This is a change to an existing access table. It is the only one in this design.

#### D1.7 `structure` JSON

```json
{
  "structureVersion": 1,
  "nextColumnSeq": 8,
  "columns": [
    {"key": "c1", "name": "Student", "type": "link", "link": {"moduleId": "<uuid>"}},
    {"key": "c2", "name": "Student no.", "type": "lookup", "lookup": {"linkKey": "c1", "fieldId": "<uuid>"}},
    {"key": "c3", "name": "Quiz 1", "type": "decimal", "decimal": {"places": 2, "currency": false}},
    {"key": "c4", "name": "Quiz 2", "type": "decimal", "decimal": {"places": 2, "currency": false}},
    {"key": "c5", "name": "Total", "type": "computed", "computed": {"expression": "{c3} + {c4}", "places": 2}},
    {"key": "c6", "name": "Grade", "type": "select", "select": {"options": [{"id": "o1", "label": "Pass"}]}}
  ],
  "groups": [{"name": "Period 1", "keys": ["c3", "c4", "c5"]}],
  "totals": {"c5": "average", "c1": "count"}
}
```

- Types: K1's twelve field types, plus `link`, `lookup`, `computed` and `sheet_lookup` (K9; payload `{"sourceWorksheetId", "sourceColumnKey", "linkKey", "sourceLinkKey"}`, D7.3a). `relationship` is refused (422). Cell values are checked by the existing field validators (`sandbox/fields/validation.py`: decimal digits `:15-31`, option labels `:149-153`, min and max length `:288-290`) and the import converter (`sandbox/records/importing.py`, `_converted_cell`) with the organization's `locale` (O4).
- Column names are unique in a sheet, case-insensitive. Expressions resolve names in braces. A link cell holds either a row link (D1.4) or unlinked text, `{"unlinked": "<text>"}`, for import rows that the person keeps unmatched (X8).
- Groups hold adjacent keys and do not overlap (K8).

### D2. The access rule

**Proposed.** The rule lives in a new module, `openview/worksheets/access.py`. It builds on `effective_levels` and `module_filter` (`access/policy/scope.py:180-201`, `access/policy/checks.py:61-71`) and does not change `scope.py`. Pattern: object rules that build on the one access function beside their object: `boards/access.py` (`readable_board_ids`, `:120-136`), `comms/access.py`, and `sandbox/relationships/access.py`. See Decisions, item 5.

```text
base(S, U)    = S.is_deleted = false
                AND ( record sheet: record R = S.record_id, R.is_deleted = false,
                                    R.module_id readable by U    -- module_filter(db, U, READ, Record.module_id)
                    | module sheet: module M = S.module_id, M.is_deleted = false,
                                    M.id readable by U )
present(S)    = EXISTS owner user + membership in S.org passing active_account_clause()
                AND (membership.worksheets_released_at IS NULL
                     OR membership.worksheets_released_at <= S.created_at)
shared(S, U)  = EXISTS live share on S to U, or to a live group with U as a live member
visible(S, U) = base(S, U) AND (NOT present(S) OR S.owner_id = U.id OR shared(S, U))
level(S, U)   = none   when not visible
                view   when NOT present(S)                    -- open (L2)
                owner  when S.owner_id = U.id
                max(direct share, group shares), capped at view when U is a guest
```

- **One SQL clause** (`visible_worksheet_clause(db, user)`) feeds every list, count and SSE set. One Python function (`worksheet_level(db, user, worksheet)`) feeds every route.
- **No admin override.** An administrator's `module_filter` is `true()`, so an admin passes `base`, but must still be the owner, a share recipient, or a reader of an open sheet (V3). Pattern: Comms gives an admin no access to member-scoped conversations they are not part of (`comms/access.py:132-141`).
- **Guest cap.** `EffectiveAccess` has no guest flag. The rule reads the role from `current_membership(db, user).role`, as `readable_board_ids` does (`boards/access.py:123-127`). Guests cannot create or copy (C3). A share to a guest is View only (Decision 3a).
- **Identical 404.** Every route loads a sheet through one helper that returns `None` for a missing, deleted or hidden sheet. Each case answers 404 `{"detail": {"code": "worksheet_not_found", "message": "Sheet not found"}}`. A row, share or history ID of a hidden sheet answers the same way. Pattern: `record_access` (`sandbox/records/access.py:13-23`) and `require_readable_link` (`relationships/access.py:37-41`). A sheet that the person can see but not change answers 403 `worksheet_read_only`.
- **Create (C1, C3, C4).** A non-guest with `read` on the record's module. An unreadable record answers 404 `record_not_found`. A deleted record, or a record of a closed module, answers 409 `record_not_active`. A lifecycle close sets `is_deleted` and `lifecycle_close_operation_id` on every row of its plan, records included (`lifecycle/execution.py:385-397`; the plan scope holds the records, `lifecycle/planning_scope.py:36-52`).
- **L9.** An owner who loses module read fails `base` and gets 404. Recipients who still read the record pass `base` and keep their shares. The sheet does not open, because the owner is still present.

How each V7 surface applies the rule:

| Surface | Rule |
| --- | --- |
| Sheets tab and its count | `visible` with `record_id = R`. The count is the list `total` of the same query. A record that the person cannot read answers 404. |
| My sheets | `visible` AND (owner, or a live share to the person or their group). Open sheets that were never shared with the person show only in the Sheets tab. `deleted=only` lists the person's own deleted sheets for restore. |
| Appears in | live links with `target_record_id = T`, live rows, and `visible` on their sheet. `T` must be readable, or the answer is 404. |
| Platform search | No sheet kind is added to `GET /api/search` (07, line 26). This is absent by construction. |
| Notifications | None (spec Scope). |
| Record History tab | Record history reads only `entity_type = 'records'` rows (`manage/audit/reader.py:77`). Sheet audit rows never match. |
| Record export, lists, Charts, Reports | They do not join sheet tables. They are unchanged (SH-51). |
| SSE | `EventViewer.worksheet_ids` = `visible` IDs (D6). |
| Audit and security events | Administrator only. IDs, times and counts, never content (D5; Decision 1). |

### D3. Leave and return

#### D3.1 What changes sheet state

| Path (`account_operations.py`) | Row it changes | Sheet effect |
| --- | --- | --- |
| `_change_membership_status` to `disabled` (`:204-226`) | `memberships.status` | Open (not present) |
| `_disable_user` (`:311-361`) | `users.status` | Open in every organization of the account |
| `_remove_membership` (`:229-249`) | `memberships.is_deleted` | Open |
| `delete_user` (`:364-428`) | `users.is_deleted` | Open in every organization |
| `_change_membership_status` to `active`, `_activate_user` (`:252-308`) | status back to `active` | Private again, with the earlier shares (L4) |
| `restore_user` (`:431-500`) | `is_deleted` back to false | Private again, with the earlier shares (Decision 6a) |
| Invitation after removal (`users/service.py:237-243`) | membership row reused; new `worksheets_released_at` | Sheets created before the cutoff stay open (Decision 6b) |

No function in `account_operations.py` writes a sheet row. Each of the four leave paths gets two additions:

1. Right after `lock_user` and **before** it changes the user or membership row, it counts the sheets that will open: sheets of the person in the bound organization that are not deleted, on a record that is not deleted, and that are private now (owner present, no release cutoff). The count must run first: after the change, autoflush makes every one of these sheets read as open, so a later count would always be 0.
2. After the commit, when the count is above 0, it writes the security event `worksheets.opened_on_leave` (D5.4). The existing `_record_outcome` and `_record_security_event` (`:57-102`) take no metadata, so they get one new optional `metadata` argument. `SecurityEventIngestRequest` already carries metadata (`records/export.py:325-345`).

The invitation path in `users/service.py` sets `worksheets_released_at` only when it reuses a removed membership.

#### D3.2 Confirmation count (L5)

`GET /api/users/{user_id}/worksheet-impact` returns `{"opening_count": n}`. It is administrator-only (`require_admin`) and uses the same count as D3.1. It shows no titles and no records. The admin interface hides the line when the count is 0 (SH-15).

#### D3.3 The write that races a leave

**Proposed.** Each sheet write first locks the owner's `users` row `FOR SHARE`. It then reads `present` again, and only then locks the sheet or the row. All four leave paths and both return paths start with `lock_user`, `FOR UPDATE` on that row (`access/users/coordination.py:215-221`; called at `account_operations.py:118`, `:372` and `:439`). A write and a leave are therefore serialized: a write either commits before the leave or sees the open state and is refused. This holds SH-13 with no window.

Lock order for a write:

1. the owner's user row, `FOR SHARE`;
2. all record rows that the write touches, `FOR SHARE`, in ID order: the anchor record, the targets of the row's current links, and the targets of its new links (the current links are read first without a lock, then read again after step 4; a change in between answers 409 `row_changed`);
3. the actor's live share rows on the sheet, `FOR SHARE`;
4. the sheet row, `FOR UPDATE` (structure changes, row create and delete, counters);
5. the row, `FOR UPDATE`;
6. the link rows.

All waits use `wait_briefly_for_locks` (2 s, then 503; `sandbox/relationships/locking.py:21-40`). Records come before sheets in both the write and the purge (a purge locks its scope records, then deletes the sheets), and the leave paths take no sheet or record lock. So the orders agree. A wait that still passes 2 s answers 503, as relationship writes do. A concurrent change of group membership is not locked. It can only add access or remove it for a moment, which is the race already accepted in `openview/dashboards/visibility.py:23-25`.

#### D3.4 Account-wide paths

The count and the security event cover the bound organization only, because RLS hides the other organizations' sheets. The sheets of the other organizations still open (D0), but without an event in those organizations. Only the installation owner can disable or delete a shared account (`coordination.py:176-195`). This is a recorded residual risk (D11).

### D4. Lifecycle

| Event | Proposed behavior | Source pattern |
| --- | --- | --- |
| Record delete or restore | No sheet write. `base` reads `records.is_deleted`, so the sheets hide and come back with their shares (F1). | `records/router.py:349-391` writes only the record |
| Module or department close or reopen | Close soft-deletes the records with `lifecycle_close_operation_id`. Sheets hide, and come back on reopen. | `lifecycle/execution.py:385-397`; `records/models.py:24-27` |
| Record purge (and module or department purge) | The planner adds the sheets of the purged records, with their rows, shares, row links and revisions, to `scope_ids`. It adds their states to the private digest (`internal_state`), never to `rows`, which the impact response shows with entity IDs. The response gets one additive field, `worksheet_count` (F2). Execution deletes them one by one through the ORM, children first. | `lifecycle/planning.py:348-356`, `:391-404`; `lifecycle/execution.py:264-340` |
| Links into a purged record | Live links in other sheets that target a purged record get `target_record_id = NULL` and `target_removed = true` before the record is deleted. Their IDs go into the digest. The row stays (N6). | `key_strips` (`lifecycle/execution.py:296-302`) |
| Sheet created after the purge preview | The digest changes, so the purge is refused with "Lifecycle impact changed after planning". | `lifecycle/execution.py:368-371` |
| Linked record deleted or restored | The cell shows "Deleted record" while the target record has `is_deleted` and no `lifecycle_close_operation_id`. A restore shows the link again. | N6 |
| Linked record closed by a lifecycle close | The cell shows "Unavailable" while `lifecycle_close_operation_id` is set, or while the link column's target module is deleted. Reopen shows the link again. | N8 |
| Lookup field removed | `structure` keeps the field ID with no foreign key. When the field is missing or `is_deleted`, the column shows "Field removed" until someone removes the column (N7). A field purge does not need the sheet tables. | |
| Owner deletes a sheet (F3) | Soft delete. Its rows leave Appears in through `base`. The owner restores it from My sheets (`deleted=only`) while its record is live. Open sheets cannot be deleted (L7; Decision 9). | records soft delete and restore |
| Retention of deleted sheets | **Proposed:** a deleted sheet is kept until its record or module is purged, as a deleted record is kept until a purge. There is no new sweep job. The other option is a 30-day sweep in the scheduling worker. See Decisions, item 12. | `records/router.py:349-366` |

### D5. Audit, history and security events

#### D5.1 Redaction

| Table | Redacted | The admin audit log still shows |
| --- | --- | --- |
| `worksheets` | `title`, `structure`, `record_id`, `module_id` | entity ID, owner ID, revision, counters, actor, time |
| `worksheet_rows` | `data` | row ID, sheet ID, position, revision, actor, time |
| `worksheet_shares` | `user_id`, `group_id` | share ID, sheet ID, level, actor, time |
| `worksheet_row_links` | `target_record_id`, `column_key` | link ID, row ID, sheet ID |
| `worksheet_row_revisions` | `data`, `changed_keys` | row ID, revision, action |

The model-level redaction applies to create, update and delete snapshots (`manage/audit/snapshots.py:66-93`, `listeners.py:266-288`). Audit has no exception (spec Preserved behavior).

#### D5.2 No department on sheet audit rows

The sheet models are not added to `DepartmentAncestry.for_instance` (`manage/audit/department_ancestry.py:409-440`). Their audit rows therefore have a NULL `department_id`. Department managers list audit entries only for a department they choose (10-audit-and-history.md, paragraph 2), so only administrators see sheet audit rows (Decision 1a).

#### D5.3 Sheet history

`GET /api/worksheets/{id}/history` reads `worksheet_row_revisions`. Anyone who can see the sheet can read it (H3). A hidden sheet answers 404 (SH-46). Link values in history follow N4: a target that the reader cannot read shows "No access", with no ID and no name.

#### D5.4 Security events

All of them use `append_security_event` or `append_committed_security_event` (`manage/audit/security_events.py:87-140`). No event carries a title, a value or a column name.

| Event | When | `subject_id` | Metadata |
| --- | --- | --- | --- |
| `worksheets.export.authorized` | each data or template export (X3) | sheet ID | `format` (`csv`, `xlsx`, `template`), `row_count`, `column_count`. Pattern: `records.export.authorized` (`records/export.py:325-354`). |
| `worksheets.import.file_parsed` | each Excel parse, success or failure | none | `outcome`, `reason` (`too_large`, `archive_bounds`, `macro`, `unreadable`, `limit`), `bytes`, `row_count` |
| `worksheets.opened_on_leave` | each leave that opens at least one sheet (H5) | the person who left | `opened_count`, `path` (`membership_disabled`, `account_disabled`, `membership_removed`, `account_deleted`) |

A CSV import is parsed in the browser (D9.3), so the server receives no file and writes no file event.

### D6. Live refresh (SSE)

**Current.** An audited change publishes an invalidation for its table (`manage/audit/listeners.py:299-309`). A table in no list sends its row ID to administrators (`platform/events/models.py:210-219`, `hub.py:225-226`). An unclassified sheet table would therefore show admins the sheet IDs and the activity of private sheets.

**Proposed.** This follows the Board pattern (`BOARD_SCOPED_ENTITIES`, `board_ids` in `EventViewer`, `readable_board_ids`):

1. Add `WORKSHEET_SCOPED_ENTITIES = {"worksheets"}` in `events/models.py`. Map the five sheet tables to the entity `worksheets`, with `entity_id` set to the sheet ID, in `listeners._event_entity` and the ID resolver. The payload is `{"entity": "worksheets", "entity_id": "<sheet id>"}`. This adds no new payload key.
2. Add `worksheet_ids: frozenset[UUID] = frozenset()` to `EventViewer` (`hub.py:56-68`), filled at reauthorization (`events/router.py:236-300`) from `visible_worksheet_clause`. It is never `None`: an administrator has no wildcard.
3. `_can_receive` delivers a `worksheets` event only when `entity_id` is in `viewer.worksheet_ids`, with no administrator pass. `_access_signature` adds the sheet IDs. `_can_receive` is a protected control ("SSE delivery filter", `SECURITY.md`). This change adds one entity class and only narrows delivery for it. It does not change the delivery of any existing entity (SEC-R6 statement). The Security Engineer reviews it.
4. Lookup values change with their records. The sheet page also refetches on `records` events for the modules of its link columns, which it already receives under module access.

Behavior and cost:

- A revoked viewer gets no event. The hub filters at enqueue with the stored snapshot (`hub.py:177-181`). The stream then reauthorizes before each delivery and sends a resync instead of the event when the access set changed (`events/router.py:220-226`).
- A newly allowed viewer (a new share, or a sheet that opened at a leave) receives nothing until their snapshot refreshes. This happens at their next event or heartbeat (15 s, `events/router.py:41`), followed by a resync. A leave publishes no sheet event, because no sheet row changes.
- Each reauthorization runs one more query for the sheet IDs, for each subscriber and each event. This is the same cost as `board_ids`. The set includes the open sheets on every readable record, so it grows with the number of departed owners.

### D7. Computed columns

#### D7.1 Grammar (K3)

```text
expr     := term (("+" | "-") term)*
term     := unary (("*" | "/") unary)*
unary    := "-" unary | primary
primary  := NUMBER | colref | call | "(" expr ")"
call     := FUNC "(" expr ("," expr)* ")"        FUNC := SUM | AVERAGE | MIN | MAX | ROUND
colref   := "{" key "}"                          stored form; the editor shows "{Quiz 1}"
NUMBER   := digit+ ("." digit+)?
```

- `ROUND(x, n)` takes an integer literal `n` from 0 to 10. The other functions take 1 to 50 arguments.
- The stored form uses column keys and the canonical separators `.` and `,`. The editor accepts names and the separators of the organization's locale, and converts them on save. In a comma-decimal locale, `;` separates arguments.
- Refused on save, with 422 `expression_invalid` and the reason (SH-21): a bare identifier such as `B2` ("cell references are not supported"), an unknown name, a non-numeric column, another function, a reference loop, more than 1,000 characters, more than 100 nodes, a nesting depth above 20, or a chain of computed columns deeper than 10. The parser enforces the depth limit while it parses, so deep brackets give 422, never a recursion error. At save, the server also computes the expanded node count across the column graph, including "From another sheet" steps, and refuses more than 2,000 expanded nodes (422 `expression_invalid`), so one save cannot make every read build a huge expression.
- Numeric inputs: `number`, `decimal`, `int`, a lookup of a numeric field, and other computed columns (K4).

#### D7.2 Safe evaluation (K5, K6)

There is no `eval`. A hand-written recursive-descent parser builds an allowlisted AST. The server compiles the AST to one SQLAlchemy `numeric` expression over the row's JSONB, with every literal bound. Pattern: the Record query compiler with bound JSONB filters and database sorting (`sandbox/records/query.py`; 06, "JSONB" paragraphs).

- A blank operand in arithmetic gives blank, because SQL `NULL` propagates.
- `SUM` and `AVERAGE` skip blanks. `MIN` and `MAX` use `LEAST` and `GREATEST`, which skip `NULL`. All arguments blank gives blank.
- Division by zero gives `NULL`, with an error flag that is compiled next to the value. Only that cell shows the error mark, and every computed column that reads it shows the mark too.
- `ROUND` uses PostgreSQL `round(numeric, n)`, which rounds half away from zero.

The grid, the sort, the totals and the export call the same compiled expression, so they show the same value (K6, SH-23).

#### D7.3 Values that the viewer cannot read

A lookup value is projected per viewer: `CASE WHEN <target module readable> AND <target live> THEN value END`, plus a `no_access` flag. The value never leaves the database for a viewer who cannot read the target. So:

- a computed column that reads a hidden lookup shows "No access", never a value computed from the hidden one;
- the sort uses the masked value, so blank and "No access" sort last, and the order reveals nothing;
- search matches only masked text;
- totals skip hidden cells and return `hidden_count`;
- the export writes "No access" (X4).

Because of this, computed values are **never stored**. They are computed for each request.

#### D7.3a From another sheet (K9)

The column stores `{"type": "sheet_lookup", "sheet_lookup": {"sourceWorksheetId", "sourceColumnKey", "linkKey", "sourceLinkKey"}}`. For each row, the server finds the source rows whose `sourceLinkKey` link targets the same record as this row's `linkKey` link (`worksheet_row_links`, D1.4). It projects the value per viewer as D7.3 does:
- the source sheet is not `visible` (D2) for the viewer: `no_access`;
- the source column key is gone from the source structure: `column_removed`;
- more than one live source row matches: `multiple_matches`;
- otherwise the source cell, computed the same way as in the source sheet.

The value is never stored. The sheet page also listens for `worksheets` events of the source sheets that the viewer can see (D6), so the column refreshes when the source changes. A loop through From another sheet columns is refused on save (D7.4).

#### D7.4 Loops and renames (K4, SH-22)

On each structure save, a depth-first search over the column-key graph refuses a loop and reports the column names in it. Expressions store keys, and names are shown at render time, so a rename changes no expression.

### D8. Limits and retention

| Limit | Value | Reason |
| --- | --- | --- |
| Columns per sheet | 100 | Four grading periods of about 15 columns each fit with room to spare. It bounds the compiled SQL per row and the grid width. |
| Live rows per sheet | 10,000 (CHECK on `live_row_count`) | It equals the record export cap `MAX_ROWS` (`records/export.py:52`), so a full sheet always exports as one file (SH-31). Per-viewer sorting over all rows stays bounded. |
| Text cell | 4,000 characters | It is well under the Excel cell limit of 32,767, and a full row of text stays inside the row cap. |
| Row data | 32 KiB serialized (CHECK on `data_bytes`) | One row stays one small statement. A JSON batch of 100 rows can still exceed 1 MiB, so batches are also capped by bytes (below). |
| Sheet data | 8 MiB (CHECK on `worksheets.data_bytes`) | It equals the export byte cap `MAX_BYTES` (`records/export.py:53`). Stored JSON is larger than the CSV it produces, so a full export fits in practice. The export keeps its own check (`limit_exceeded`, 422). With short keys this is about 400,000 numeric cells. |
| Excel file | 10 MiB, and each part at most 10 MiB uncompressed | It equals the file upload cap (`platform/files/validation.py:18`, D18). `_office` refuses any part over 10 MiB uncompressed (`validation.py:104`), so the sheet XML of one tab is the real limit. Estimate (not measured): about 150,000 to 250,000 cells. A sheet near the 8 MiB cap can therefore export to Excel and not import again. **CSV is the import path for large sheets**: the browser parses it and sends JSON batches, so only the sheet limits apply. |
| Zip expansion | Existing OOXML bounds: at most 2,048 entries, at most 100 times compression per entry, at most 10 MiB per entry, at most 100 MiB in total, no nested archives, no `vba`, embeddings or external links | `_office` in `platform/files/validation.py` (from line 68), reused unchanged |
| Parser process | CPU 30 s, address space 512 MiB (Linux), wall clock 60 s | It equals `validation_child.py:11-13` and `validation_worker.py:22-36` |
| JSON request body | `REQUEST_BODY_MAX_BYTES` (1 MiB in `.env.example:120`). A row batch holds at most 100 rows and must fit in it. A match request holds at most 2,000 keys of at most 200 characters (about 420 KB). | The existing JSON limit; the Excel upload is the only binary route |
| Expression | D7.1 | |
| Deleted sheets | Kept until the record is purged (D4) | No new job (Decisions, item 12) |

A change past a limit answers 422 `{"detail": {"code": "worksheet_limit", "message": "<names the limit>", "limit": "rows" | "columns" | "cell" | "row_size" | "sheet_size", "maximum": <n>}}` (F6, SH-44). Pattern: `export_limit_exceeded` (`records/export.py:67-74`).

### D9. Import and export

#### D9.1 Data export (X2, X3, X4)

`POST /api/worksheets/{id}/export` follows the record export route (`records/query_router.py:195-245`):

1. It builds the file in an independent snapshot transaction, using the compiled projection of D7. The CSV and Excel writers are reused (`safe_text`, `records/export.py:77-80`; `encode_xlsx` with `strings_to_formulas: False`, `records/export_xlsx.py:104-112`).
2. It rechecks access after the build: `require_fresh_module_access` on the record's module (`access/policy/checks.py:196-236`), then `visible` again with the actor's share rows locked `FOR SHARE`.
3. It commits `worksheets.export.authorized`.
4. It answers with an attachment, `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.

Computed and lookup columns export as values, a hidden link as "No access", and formula-like text is neutralized (SH-37).

Code note: `export_xlsx.py:16` imports `xlsxwriter.worksheet.Worksheet`. The sheet model must be imported under another name in any module that uses both.

#### D9.2 Template JSON (X5, X6)

```json
{
  "kind": "slateops-worksheet-template",
  "schemaVersion": 1,
  "title": "Class sheet",
  "columns": [
    {"key": "c1", "name": "Student", "type": "link", "link": {"moduleName": "Student List", "departmentName": "Registrar"}},
    {"key": "c2", "name": "Student no.", "type": "lookup", "lookup": {"linkKey": "c1", "fieldName": "Student number"}},
    {"key": "c3", "name": "Quiz 1", "type": "decimal", "decimal": {"places": 2, "currency": false}},
    {"key": "c5", "name": "Total", "type": "computed", "computed": {"expression": "{c3} + {c4}", "places": 2}}
  ],
  "groups": [{"name": "Period 1", "keys": ["c3", "c4", "c5"]}],
  "totals": {"c5": "average"}
}
```

- The template holds no organization, module, record, field or person IDs, no rows and no shares. Column keys and option IDs are sheet-local.
- Import validates the file with a Pydantic model: `kind` is a `Literal`, `schemaVersion: Literal[1]`, and a before-validator answers 422 `template_unsupported_version` for any other version. Nothing is created. Pattern: `SandboxDocument` (`sandbox/designs/schemas.py:283-298`).
- The create request carries `module_mapping: {"c1": "<module id>" | null}`. The client suggests a module by name from the modules that the person can read. The server checks that each mapped module is readable (404 otherwise). An unmapped link column becomes `text`. A lookup whose field name is not found in the mapped module becomes `text`.

#### D9.3 Data import (X8 to X11)

There is no staging store. The import is stateless and has three steps, after the record import (`records/import_router.py`: preview and import modes, at most 100 rows, a digest, explicitly not idempotent):

1. **Read the file.**
   - CSV is parsed in the browser, as record import does.
   - Excel goes to `POST /api/worksheet-import-files?tab=<n>` as a binary body. This route is added to `file_transfer_policy` (`core/middleware/file_transfers.py:37-60`) with 10 MiB and a 120 s deadline. It shares `FILE_PROCESSING_SLOTS` and `FILE_MEMORY_BUDGET_MIB` (503 `files_busy` when full).
   - A new child process, `openview/worksheets/import_child.py`, runs it with the same limits as `validation_child.py`. That file is a protected control (SEC-R6), so it is not edited. The child:
     1. calls `inspect_content(".xlsx")` first (archive bounds; `.xlsm` and macro parts refused);
     2. counts, with `defusedxml`, the cells of the chosen sheet part that have `<f>` and no `<v>` (a formula with no saved result);
     3. reads the values with python-calamine (D9.4).
   - The answer is `{"tabs": [{"index", "name"}], "tab_index", "rows": [[cell]], "formula_without_value_count", "row_count", "column_count"}`. Only visible tabs are listed. Cells are JSON strings, numbers, booleans or `null`, and dates are ISO strings. More than 10,001 rows or 100 columns answers 422 `worksheet_limit`. The person then chooses the header row in the browser (X10).
2. **Preview the matching.** `POST /api/worksheet-import-matches` takes `{"module_id", "field_id", "keys": [≤ 2,000 strings]}`. It needs `read` on the module (404 otherwise) and a live scalar field of that module. It returns, for each key, `matched` (with the record ID and label), `unmatched` or `ambiguous`, plus the three counts. Only live records of the readable module match (X8). The browser sends the keys in chunks and adds up the counts. A key matched more than once is decided per key, so the chunking does not change the counts.
3. **Write.** `POST /api/worksheets/{id}/rows/batch` takes at most 100 rows, with `structure_revision`. A changed structure answers 409 `structure_changed`, as record import does with `schema_digest` (`import_router.py:144-150`). Each batch is one transaction, all or nothing. The batch is not idempotent, as record import is not. The server checks each link target again (readable, in the target module, live). Rows that the person keeps unmatched store `{"unlinked": "<key text>"}`.

Text that starts with `=`, `+`, `-` or `@` is stored as text and never evaluated (X11). Only computed columns evaluate anything, and their expressions come from the structure, never from cells.

#### D9.4 Excel reader choice

**Proposed: python-calamine 0.9.1** (MIT; Rust `calamine` 0.37.0), pinned `>=0.9.1,<0.10`.

| Check | python-calamine | openpyxl |
| --- | --- | --- |
| Latest release | 0.9.1, 2026-11-03. Five releases from 2026-07 to 2026-11. | 3.1.5, 2024-06-28. No release since. |
| License | MIT | MIT |
| Python 3.12 to 3.14 | Wheels for manylinux x86_64 and aarch64 (cp312, cp313, cp314; the server image is `python:3.14-slim`, `infra/docker/backend.Dockerfile:31`) and macOS arm64 (development) | Pure Python. Classifiers stop at 3.11. |
| Types for strict mypy | Ships `_python_calamine.pyi` | Needs `types-openpyxl` |
| Speed in the 30 s CPU limit | Native | Pure Python. Formula detection needs two passes (`data_only` false and true). |
| Formula detection (X10) | No formula API. Covered by our own `defusedxml` count. | Yes, with two loads |

Sources: PyPI JSON API (`https://pypi.org/pypi/python-calamine/json`, `https://pypi.org/pypi/openpyxl/json`), read on 2026-11-24. The python-calamine 0.9.1 sdist (`_python_calamine.pyi`, `Cargo.toml`, `LICENSE`) was read, not run.

Costs:

- It is a 0.x Beta release, so its API can change. The pin and a parser test with hostile files (spec S2 proof) guard that.
- It is native code that reads untrusted bytes. It runs only after `_office` has passed, in a process with CPU and memory limits and no provider access (`validation_worker.py:22-36`, a minimal `env`).
- calamine also reads `.xls`, `.xlsb` and `.ods`. The route allows only `.xlsx` (`MIME` allowlist).
- `supply-chain` review: it adds one new runtime dependency (`backend/pyproject.toml`).

#### D9.5 New sheet from this structure, and Make a copy

Both use `POST /api/worksheets` with a `source`:

- **`structure`** (X7) copies the source `structure` with new keys. It copies no rows and no shares. It needs `visible` on the source and the create right on the target record.
- **`copy`** (L6) copies the structure, the rows, the links and the unlinked text. It copies no shares and no history. It writes one `create` revision per row. It is allowed to the owner, and to any non-guest who can see an open sheet (Decision 3a). The target is the same record.

### D10. API contract

Conventions for every route (`backend/AGENTS.md`, "API conventions"; `fastapi-api-design`):

- Prefix `/api`, kebab-case nouns. Record-scoped lists use a router with `prefix="/records"`, as `query_router.py:49` and `batch_router.py:45` already do.
- Cookie changes need CSRF and an exact `Origin`.
- Errors are route-local `{"detail": {"code", "message"}}`. Schema validation stays 422.
- Responses use `Cache-Control: no-store`.
- `ETag` is `"<id>:<revision>"` for a sheet and for a row. `If-Match` is required on sheet changes (row saves use the per-cell `expected` check of route 12 instead): 428 when it is missing, 412 when it is stale (`group_etag` and `require_match`, `access/policy/service.py:65-79`).
- Lists use `StandardListRequest` and `StandardListResponse`. Row and Appears in lists keep `exact_total`, as Records lists do (`common/listing/query.py:37`). Other lists use the capped total.
- No route accepts `Idempotency-Key`. Creates and imports are not idempotent, as record import is not (D11 risk).

| # | Method and path | Who | Request | Success | Errors | Pattern |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `GET /worksheets` (My sheets) | signed-in | list params; `sort_by`: `title`, `updated_at`, `created_at`; `search` on title; `deleted`: `exclude` or `only` (own) | 200 list of `WorksheetSummary` | 422 | `GET /records` list (`records/router.py:235`); saved view list spec (`openview/views/router.py:64-73`) |
| 2 | `GET /records/{record_id}/worksheets` (Sheets tab) | record reader | list params | 200 list of `WorksheetSummary`, exact total | 404 | record-prefixed routers (`query_router.py:49`); `record_access` (`records/access.py:13-23`) |
| 2a | `GET /modules/{module_id}/worksheets` (module page) | module reader | list params | 200 list of `WorksheetSummary` for the module sheets that are `visible` (owned, shared, or open), exact total | 404 | as route 2, with `module_filter` on the module |
| 3 | `POST /worksheets` | non-guest record or module reader | `{record_id \| module_id (exactly one), title, source: {kind: "blank"} \| {kind: "structure", worksheet_id} \| {kind: "copy", worksheet_id} \| {kind: "template", template, module_mapping}}` | 201, `Location`, `ETag`, `WorksheetDetail` | 403 guest, 404, 409 `record_not_active`, 422 | `POST /records` 201 (`records/router.py:272`); discriminated `source` is new |
| 4 | `GET /worksheets/{id}` | `visible` | | 200 `WorksheetDetail`, `ETag` | 404 | `GET /records/{id}` (`records/router.py:260`); `group_etag` (`policy/service.py:65-66`) |
| 5 | `PATCH /worksheets/{id}` | owner, not open | `{title}` + `If-Match` | 200 | 403, 404, 412, 428 | `PATCH /access/groups/{id}` with `If-Match` (`configuration_router.py:299-313`) |
| 6 | `PUT /worksheets/{id}/structure` | owner or Edit | `{columns, groups, totals}` + `If-Match` | 200 `WorksheetDetail` | 403, 404, 409 `column_has_values` (type change on a column with values), 412, 422 `expression_invalid` or `worksheet_limit`, 428 | `PUT /access/groups/{id}/access` with `If-Match` (`configuration_router.py:408-429`) |
| 7 | `DELETE /worksheets/{id}` | owner, not open | `If-Match` | 204 | 403, 404, 409 `worksheet_open`, 412, 428 | `DELETE /records/{id}` (`records/router.py:348-365`); `delete_group` `If-Match` (`policy/service.py:309-313`) |
| 8 | `POST /worksheets/{id}/restore` | owner, record live | | 200 | 404, 409 | `POST /records/{id}/restore` (`records/router.py:368-391`) |
| 9 | `POST /worksheets/{id}/rows/query` | `visible` | `{sort: {key, order}?, search?, limit, offset}` | 200 `{items: [Row], pagination, totals: {key: {fn, value, hidden_count}}}`, exact total | 404, 422 | `POST /records/query` (`query_router.py:56`) |
| 10 | `POST /worksheets/{id}/rows` | owner or Edit | `{cells, after_row_id?}` | 201, `Location`, `ETag`, `Row` | 403, 404, 422 | `POST /records` (`records/router.py:272`) |
| 11 | `GET /worksheets/{id}/rows/{row_id}` | `visible` | | 200 `Row`, `ETag` | 404 | `GET /records/{id}` (`records/router.py:260`) |
| 12 | `PATCH /worksheets/{id}/rows/{row_id}` | owner or Edit | `{cells: {key: {value, expected}}, after_row_id?}` (changed keys only; `expected` is the value the person saw) | 200 `Row` | 403, 404, 412 `{"detail": {"code": "cell_changed", "message", "keys", "current": Row}}` when a stored value differs from `expected` (F4), 422 | `PATCH /records/{id}` with required `If-Match`, 412 and 428 (`records/router.py:154-173`, `:304-329`); the `current` row in the 412 body is new |
| 13 | `DELETE /worksheets/{id}/rows/{row_id}` | owner or Edit | `If-Match` | 204 | 403, 404, 412, 428 | `DELETE /records/{id}` (`records/router.py:348`) |
| 14 | `POST /worksheets/{id}/rows/batch` (paste, import) | owner or Edit | `{structure_revision, creates: [≤ 100], updates: [{row_id, cells: {key: {value, expected}}}]}` | 200 `{rows: [Row]}` | 403, 404, 409 `structure_changed` or `row_changed`, 422 | `POST /records/batch-update` (`batch_router.py:121`); record import digest (`import_router.py:144-150`) |
| 15 | `GET /worksheets/{id}/history` | `visible` | list params; `row_id?` | 200 list of `RowRevision` | 404 | record history list (`manage/audit/router.py:165`); history rows from `worksheet_row_revisions` are new |
| 16 | `GET /worksheets/{id}/shares` | owner | list params | 200 list of `Share` | 403, 404 | `comms_channel_access` grants (`comms/conversations/models.py`); routes are new |
| 17 | `POST /worksheets/{id}/shares` | owner, not open | `{subject, user_id \| group_id, level}` | 201 `Share` | 403, 404, 409 duplicate, 422 (Edit to a guest) | new; uniqueness from the partial index, as `uq_comms_channel_access_active` |
| 18 | `PATCH /worksheets/{id}/shares/{share_id}` | owner, not open | `{level}` | 200 | 403, 404, 422 | new |
| 19 | `DELETE /worksheets/{id}/shares/{share_id}` | owner, not open | | 204 | 403, 404 | new; soft delete as `RelationshipEdge` |
| 20 | `POST /worksheets/{id}/export` | `visible` | `{format: "csv" \| "xlsx" \| "template"}` | 200 attachment | 404, 422 `export_limit_exceeded`, 503 | `POST /records/export` (`query_router.py:195-245`) |
| 21 | `POST /worksheet-import-files?tab=<n>` | non-guest | `.xlsx` bytes, ≤ 10 MiB | 200 parse result (D9.3) | 413, 422 `import_file_invalid` or `worksheet_limit`, 503 `files_busy` | file upload routes in `file_transfer_policy` (`file_transfers.py:37-60`); `validate_bounded` (`validation_worker.py:17-43`) |
| 22 | `POST /worksheet-import-matches` | module reader | `{module_id, field_id, keys}` | 200 matches and counts | 404, 422 | record import preview mode (`import_router.py:119-150`); the key match is new |
| 23 | `GET /records/{record_id}/worksheet-rows` (Appears in) | record reader | list params | 200 list of `{worksheet_id, worksheet_title, row_id, column_key, column_name, cells}`, exact total | 404 | `require_readable_link` both-ends rule (`relationships/access.py:24-41`); route is new |
| 25 | `GET /worksheets/{id}/share-candidates?q=` | owner | `q` (search text) | 200 people the owner can see (`visible_person_ids`, active members of the bound organization) and the groups the owner belongs to | 403, 404 | `visible_person_ids` (`access/users/person_visibility.py`); route is new |
| 24 | `GET /users/{user_id}/worksheet-impact` | admin | | 200 `{opening_count}` | 403, 404 | `require_admin` routes in `account_operations.py` (`:53-54`); route is new |
| 25 | Lifecycle impact (existing) | admin | | adds `worksheet_count: int` | | `LifecycleImpactResponse` (`lifecycle/planning_scope.py:70-83`); additive field |

Shapes:

- `WorksheetSummary`: `id`, `record_id` (null for a module sheet), `module_id` (null for a record sheet), `title`, `owner {id, display_name}`, `state` (`private` or `open`), `my_level` (`owner`, `edit` or `view`), `live_row_count`, `revision`, `updated_at`, `is_deleted`.
- `WorksheetDetail`: the summary, plus `structure` (with names), `etag` and `created_at`.
- `Row`: `id`, `revision`, `etag`, `position`, `cells: {key: Cell}`.
- `Cell` is one of:
  - `{"value": ...}`;
  - `{"link": {"record_id", "label"}}`;
  - `{"unlinked": "<text>"}`;
  - `{"state": "no_access" | "deleted" | "removed" | "unavailable" | "field_removed" | "column_removed" | "multiple_matches"}` (the last two for `sheet_lookup` columns, D7.3a);
  - `{"value": null, "error": "division_by_zero"}`.

  A `no_access` cell carries no ID and no label (N4).
- `Share`: `id`, `subject`, `user {id, display_name}` or `group {id, name}`, `level`, `created_at`.

### D11. New versus reused, costs and risks

| Item | New or reused | Cost |
| --- | --- | --- |
| Five tables in `openview/worksheets/` | New | One migration with five RLS policies. The new tables add no column to an existing table; the next row is the one exception. The hand-kept table lists of the guarded reset must name them (`operations/reset/models.py:11`, `:162`, `:286`). Organization removal finds the `users` foreign keys from the catalog (`operations/reset/organization.py:163-166`), so it needs no list change. |
| `memberships.worksheets_released_at` | New column on an existing table | A change to an access table, listed as go-ahead item 2 (Decisions, item 7). It is needed only for Decision 6b. |
| Access module on `effective_levels` | New module, reused function | One more object rule beside Boards and Comms. `scope.py` is unchanged. |
| Derived open state | New | It joins `users` and `memberships` on each sheet read. There is no audit row for "opened". |
| Leave hooks | Count and event in four paths, release in the invitation | Small. No sheet writes in admin paths. |
| Lock of the owner's user row | Reused order (`lock_user`) | Every sheet write waits behind an admin change to its owner, for at most 2 s, then 503. |
| Expression parser and SQL compiler | New | The largest new code. It needs PostgreSQL integration tests, because SQLite is not allowed. |
| Per-viewer masked projection | New, on the Record query pattern | Every grid page computes the lookups and the computed columns for the viewer. Nothing is cached. |
| SSE `worksheet_ids` | Board pattern reused | One query for each reauthorization. The set grows with the open sheets. Newly allowed viewers refresh after up to 15 s. |
| Purge scope and digest | Reused planner and executor | A record with a full sheet adds up to about 30,000 audited deletes to its purge. |
| Excel parse | New dependency (python-calamine), new child process; validator, limits and slots reused | The supply-chain and parser risk of a 0.x native library |
| CSV and Excel writers, `safe_text`, field validators, import converter | Reused | None |
| History table | New, on the Comms revision pattern | Each row write adds two audit rows (the row and the revision). |

Risks:

1. **Account-wide leave in other organizations** (D3.4). Sheets open without a security event there. The installation owner is the only actor. Owner: Security Engineer to accept or ask for a per-organization event job.
2. **Copy and import volume.** A copy of a full sheet writes up to 10,000 rows, links and revisions, all audited, in one request. Measure in S2. If it is too slow, cap copy at the batch size and copy in chunks, as import does.
3. **No idempotency.** A retried batch after a lost response can duplicate rows, as record import can. The preview step limits the effect.
4. **Lazy cleanup of removed columns.** Orphan keys count toward `data_bytes` until the row is saved again.
5. **Admin traces.** IDs, counts and times reach admins (Decision 1). Redaction (D5.1) keeps titles, values, columns, link targets, share recipients and the anchor record out.

### D12. Where the design changes for the other option of each open decision

| Decision | Designed for | If the owner picks the other option |
| --- | --- | --- |
| 1 Admin traces | a) traces without content | b) mark the sheet models `__audit_enabled__ = False`. This is an exception to the `AuditSession` control, so SEC-R6 applies and the owner must state the reason. It drops `subject_id` and the counts from the security events, and drops `worksheet_count` and the leave count route. History (D1.5) stays as the only record of changes. |
| 6 Return after restore or invitation | a) restore returns; b) a new invitation does not | All of a): drop `worksheets_released_at` and its write. All of b): `restore_user` must also release the sheets. An account restore reaches every organization, so the cutoff moves to a new `users.worksheets_released_at`, because `users` has no RLS. |
| 3 Guests | a) View only, no copy | b) drop the guest cap in `level` and allow `copy` for guests. A copy makes the guest an owner. A guest membership expires by time (`ck_memberships_guest`, `access/users/models.py:135-138`), so a guest's sheets then open with no admin action and no security event. c) refuse a share to a guest (422) and drop the guest branch from `shared`. Open sheets stay readable to guests through `base`. |
| 9 Delete an open sheet | a) keep L7 (409 `worksheet_open`) | b) let an admin `DELETE` an open sheet. This needs a new admin check in route 7, and the sheet becomes visible to the admin, who is then a reader of an open sheet only when they read the record. |
| 18 Default share in templates | a) no shares | b) add `copy_group_shares: bool` to `source.structure`. It copies only group shares, as a choice the person can change. Templates stay share-free. |
| 2 Personal data | not blocking | Erasure would need an admin purge route for one person's sheets, which conflicts with V3. It needs its own decision. |

### D13. Presence

**Proposed.** Presence uses Supabase Realtime Presence on a private topic per sheet, `org:<org>:worksheet:<id>`. Cursor moves travel over the websocket and never touch PostgreSQL. The database is checked only when a person gets a token and joins. This is faster than the HTTP heartbeat design, which needed a database write and a read for every viewer on each cursor move.

- **Join.** The browser asks FastAPI for a presence token for the sheet: `POST /api/worksheets/{id}/presence-token` returns `{token, topic, expires_at, viewers}` (60 s). The token carries `purpose = 'realtime_presence'` and `topic = 'org:<org>:worksheet:<id>'`. FastAPI checks `visible` (D2) with fresh reads and upserts a per-sheet join grant in `worksheet_realtime_grants` (audit off, organization RLS, unique per organization, user and sheet, grant expiry equal to token expiry, own advisory lock key, expired rows swept). The join function checks the purpose per branch: a `worksheet:` topic accepts only a `realtime_presence` token whose `topic` claim equals the topic exactly, with a matching live grant for the same organization and user on a sheet that is not deleted; the existing branches keep requiring `realtime`. The write rule allows `extension = 'presence'` only on `worksheet:` topics; conversation, user and organization-presence topics stay read-only. The client always joins with `private: true`, on a connection that carries no OpenComms channels. Token issuance has its own per-person rate budget, separate from the OpenComms token limit.
- **Revocation.** Realtime checks access once at join and caches it for the connection (Supabase Realtime Authorization docs). The token therefore lasts 60 seconds. The client refreshes it every 45 seconds; a refused refresh makes the client leave. A person who lost access stops within 60 seconds (PR5).
- **Payload.** The presence state is `{row_id, column_key}` only. Names and avatars come from the people list the viewer already has. No value, title or column name is sent (PR2). The receiving client accepts an entry only when its key is in the token response's `viewers` list (or is the viewer), `row_id` is a loaded row and `column_key` matches `^c[0-9a-z]{1,8}$`; it never renders payload text. A current viewer could still move another current viewer's outline; this Low residual is accepted (DEC-0047).
- **Storage.** None. Presence lives in the Realtime channel only (PR6). The grant rows follow the Comms grant cleanup (`revoke_stale`).
- **Security change.** Today browsers publish nothing on Realtime; OpenComms presence goes through HTTP. Here browsers publish their own presence state. The Security Engineer reviews this before build, including whether a client can claim another person's presence key.
- **Cost.** One token request per viewer every 45 seconds, and one join query per join. Cursor moves cost no database work.

### D14. Security constraints (Security Engineer design review, 2026-11-24)

Each constraint is part of the unit that builds it; a missing one is a BLOCKING review finding for that unit.

- **Structure masking (S1).** One per-viewer structure serializer serves route 4, the route 3 and 6 responses, the 412 body and template export. A "From another sheet" column whose source the viewer cannot see carries no source sheet ID or column key (state `no_access`). Template export writes module, department and field names only for modules the exporter can read; otherwise the column exports as `text`. A "From another sheet" column never goes into a template: it exports as `text`, and template import refuses `sheet_lookup` with 422. Saving a "From another sheet" column needs the source sheet to be visible to the person saving; a hidden source and a missing source give identical 422 bodies.
- **Share targets (R1).** Routes 17 and 18 accept a person only with an active membership in the bound organization whom `visible_person_ids` returns for the actor, and a group only when it is live and in the bound organization. Anyone else gets the same 404 as a random UUID, and no response carries their name.
- **Per-cell saves (R2).** `expected` is compared with the actor's masked value. A change to a cell the actor sees as `no_access` is refused (403). The 412 `current` row and Appears in `cells` use the actor's masking.
- **Recheck after locks (R4).** After the authority locks (D3.3), `worksheet_level` is computed again with fresh reads.
- **Error order (R5).** The 404 loader runs before every 403, 428, 412, 409 and semantic 422 check.
- **My sheets deleted list (R6).** `deleted=only` keeps every `base` condition except the sheet's own deleted flag.
- **SSE (C1–C5).** The `worksheets` branch in `hub._can_receive` sits after the organization checks and before `all_authenticated` and the admin pass, and tests only `entity_id in viewer.worksheet_ids`. `EventViewer.worksheet_ids` is a `frozenset[UUID]`, never optional, filled from `visible_worksheet_clause` with an explicit organization filter. `_access_signature` adds `worksheet:<id>` entries before the admin early return. All five sheet tables map to `worksheets` with the sheet ID; any other `worksheet*` table publishes nothing. A `worksheets` payload must carry a UUID `entity_id` and no other key. No existing entity's delivery changes (a captured before/after table proves it).
- **Excel child (E1–E7).** The child reads the exact checked bytes from memory; a streaming defusedxml pre-scan refuses more than 10,001 rows, more than 100 columns or any cell outside the used range, and archives that contain `xl/workbook.bin`, `content.xml` or `mimetype`; output and each cell (4,000 characters) are capped while writing, the parent reads through a bounded read and kills the child on overflow; limits as `validation_child.py` plus core size 0, a minimal environment, stderr to `DEVNULL`, 60 s timeout; the route has CSRF, exact Origin, a `file_transfer_policy` entry, the shared file slots, 413 before buffering past 10 MiB, `tab` bounds; python-calamine is locked with hashes and installed from wheels only.
- **Documentation (P6, SEC-R6).** The same PR updates the `SECURITY.md` control rows for SSE and Realtime, the Comms boundary text, and the "browsers do not publish … presence" lines in architecture 04 and 14, with the reason.

## Slices

Each slice ends with tests that fail first, one code review, a `webapp-security-review`, targeted screenshots, and a hands-on pass as each account level.

| Slice | Content | Criteria | Proof |
| --- | --- | --- | --- |
| S1 Record sheets | Sheets tab, module sheets, per-cell saves, full-page grid, phone layout, column types, link and lookup columns, totals, sort and search, View and Edit sharing, My sheets, CSV and Excel data export, the leave event (open read-only, Edit to View, re-enable, confirmation count, share-dialog sentence), audit redaction, sheet history, lifecycle with the record | SH-1 to SH-16, SH-18 to SH-20, SH-24, SH-26, SH-27, SH-29 to SH-31, SH-38, SH-40 to SH-57, SH-60 to SH-62, SH-67, SH-68 | PostgreSQL integration tests for the access rule (every surface in V7, for each account level); leave-path tests for the four code paths; isolated Playwright for the tab, page and phone; a hands-on pass with two accounts for sharing and live refresh |
| S2 Structure and data reuse | Appears in, computed columns, column groups, templates (JSON export and import, New sheet from this structure), CSV and Excel import with the matching preview, Make a copy, sample packs, presence, From another sheet column | SH-17, SH-21 to SH-23, SH-25, SH-28, SH-32 to SH-37, SH-39, SH-58, SH-59, SH-63 to SH-66, SH-69 to SH-72; re-run SH-5, SH-6, SH-7, SH-38 and SH-43 for the actions and surfaces that S2 adds | Parser tests with hostile files (size, zip expansion, macros, formula text); import preview tests on a real database; sample runs for School and Manufacturer |

**Why the leave event is in S1.** If S1 reaches users without it, a creator who leaves before S3 ships leaves sheets that stay closed to everyone. That is option 2b, which DEC-0044 rejected. Otherwise the sheets would open later, on terms the creator never saw. The leave transition, its confirmation count and the share-dialog sentence therefore ship with sharing. Make a copy moves to S2, because it uses the same copy work as New sheet from this structure.

**Why Appears in is in S2.** S1 already proves the both-ends rule on link cells (SH-27). Appears in is a read across all sheets, and it needs its own query and its own access tests (SH-28).

## Backend changes: separate go-ahead list

None of these is approved. Each needs the owner's go-ahead. The detail is in Data and API.

1. **Schema: five new tables** in `openview/worksheets/models.py` (D1), each with `org_id`, composite restricting foreign keys and an RLS policy:
   - `worksheets`: anchor record or module, owner, title, `structure` (JSONB), revision, row and byte counters with CHECK limits, soft delete;
   - `worksheet_rows`: `data` (JSONB keyed by sheet-local column keys), position, revision, byte size;
   - `worksheet_shares`: person or group, View or Edit;
   - `worksheet_row_links`: one link per cell, `target_removed` for purged targets;
   - `worksheet_row_revisions`: insert-only sheet history.

   There is **no stored private or open state** and **no stored level from before the leave**. The open state is derived from the owner's presence (D0; Decisions, item 8). The guarded reset's table lists must name the five tables (D11).
2. **Schema: one column on an existing access table**, `memberships.worksheets_released_at` (D1.6). It is needed only if a new invitation keeps the sheets open (Decisions, items 6 and 7).
3. **Access rule.** A new module, `openview/worksheets/access.py`, built on `effective_levels` and `module_filter` from `access/policy/scope.py`. `scope.py` does not change. One SQL clause feeds every list, count and SSE set, and every route gets the same 404 for a missing or hidden sheet (D2; Decisions, item 5).
4. **API: 24 new routes** (D10), under `/api/worksheets`, `/api/records/{record_id}/worksheets`, `/api/records/{record_id}/worksheet-rows` (Appears in), `/api/worksheet-import-files` and `/api/worksheet-import-matches`. This includes the admin-only `GET /api/users/{user_id}/worksheet-impact` for the confirmation count (D3.2).
5. **API: one additive field on an existing response.** The lifecycle impact response gets `worksheet_count` (D4; Decisions, item 11).
6. **Leave paths.** The four leave paths in `account_operations.py` count the sheets that will open before they change the user or membership row. After the commit they write `worksheets.opened_on_leave`. `_record_outcome` and `_record_security_event` get an optional `metadata` argument. The invitation path sets `worksheets_released_at` when it reuses a removed membership (D3.1). No admin path writes a sheet row.
7. **Write locking.** Each sheet write locks the owner's user row `FOR SHARE` before the sheet and row locks, so that writes and leaves are serialized (D3.3).
8. **Lifecycle.** The purge planner adds the sheets of purged records to its scope and digest. Links into purged records are marked removed. A sheet created after the preview makes the purge refuse (D4).
9. **Audit and security events.** `__audit_redacted_fields__` on the five models. No department on sheet audit rows (D5.2). New security events: `worksheets.export.authorized`, `worksheets.import.file_parsed` and `worksheets.opened_on_leave` (D5.4).
10. **Live refresh: a change to a protected control.** `WORKSHEET_SCOPED_ENTITIES`, `EventViewer.worksheet_ids`, and a `worksheets` branch in `_can_receive` with no administrator pass (D6). `_can_receive` is the "SSE delivery filter" control in `SECURITY.md`. The change only narrows delivery for the new entity (SEC-R6 statement). **A Security Engineer review is required before build.**
11. **Excel import: one new runtime dependency**, python-calamine (`>=0.9.1,<0.10`, MIT, 0.x Beta) (D9.4). It runs in a new child process with the existing file limits, after the existing OOXML checks (D9.3). `validation_child.py` is a protected control and is not edited. A supply-chain review is part of the go-ahead.
12. **Computed columns.** A hand-written expression parser and a compiler to one SQL expression with bound values. There is no `eval` and no general formula engine (D7).
13. **Sample packs.** Sheets in the School and Manufacturer catalogs, written through the real APIs (O5).
14. **Presence.** A private Supabase Realtime topic per sheet, a 60-second presence token and a join grant (D13). Browsers publish their own presence state, which changes the current rule that browsers publish nothing on Realtime: Security Engineer review before build.

## Assumptions

1. Guests cannot create sheets (DEC-0043 1).
2. Edit changes rows and columns. Only the creator shares, changes visibility, deletes or renames (DEC-0044 3; rename is added by the PM).
3. A re-enabled creator gets the sheets back, private, with their earlier shares (DEC-0044 2). Under L0 this is automatic.
4. The disable and remove confirmations show the count of sheets that will open (DEC-0044 2).
5. A reader of an open sheet can make a copy that they own (DEC-0044 2). Guests cannot copy (Decisions, item 3).
6. The share dialog tells the creator that the sheet opens when they leave (DEC-0044 2).
7. L9 (PM): when the creator loses read on the module, the recipients who still read the record keep their shares. The parent's text ("unreadable until access returns") is read here as unreadable to the creator. D2 implements this reading.
8. A person's own regional format choices keep applying to sheets as they do to records (O3). This is current behavior, not a change to DEC-0043 3.
9. Screens and Data and API are built for the recommended option of every item below. D12 lists what changes in the design for each other option.

## Decisions

Settled on 2026-11-24 with the recommended option for each (DEC-0045).

1. Admins see audit traces of private sheets (who, when, IDs, counts), never their content.
2. Data in private sheets cannot be found for removal requests in version 1. This is a known limit.
3. Guests get View-only shares and cannot copy.
4. "No access" applies to a whole link column. The Share dialog shows no warning.
5. The access rule lives in `openview/worksheets/access.py`, built on `scope.py`.
6. A restore gives the sheets back, private. A new invitation does not: the sheets stay open.
7. `memberships.worksheets_released_at` is added for item 6.
8. The open state is calculated from the owner's membership, not stored.
9. Nobody can delete an open sheet.
10. The open-sheet line reads "… no longer has access", with no date.
11. The lifecycle impact response gets `worksheet_count`.
12. A deleted sheet is kept until its record or module is purged.
13. Import rows that match more than one record get the same keep-or-skip choice as unmatched rows.
14. A sheet made from a data file suggests a type for each column, and the person can change it.
15. Import into an existing sheet adds rows only. The preview shows how many rows already exist.
16. Type names follow the Sandbox: Number stores `decimal` (with the currency option), Whole number stores `int`, and `number` is not offered.
17. The lookup cell next to "Deleted record" or "Removed record" is blank.
18. Templates carry no sharing in version 1.

## Glossary rows to add

For `docs/architecture/21-glossary.md`, when the spec is approved.

OpenView intro: change "Its content belongs to departments and modules, not to people" to "Its content belongs to departments and modules, except sheets, which belong to the person who created them".

OpenView table (columns: Term, Also appears as, Meaning, Copy):

| Term | Also appears as | Meaning | Copy |
| --- | --- | --- | --- |
| Sheet | `Worksheet`, "Sheets" tab | A table of rows and columns that a person creates on a record or a module for their own working data. It never changes its record, and it is private to its owner until the owner shares it. Unlike other OpenView content, it belongs to a person. | Customer |
| Sheet owner | `Worksheet.owner` | The person who created the sheet. Only the owner renames, shares or deletes it. | Customer |
| Sheet share | `WorksheetShare`, "View", "Edit" | A person's or group's access to a sheet: View reads and exports; Edit also changes rows and columns. It never gives access to the record. | Customer |
| Open sheet | `state: "open"` in `WorksheetSummary` (derived, not stored) | A sheet whose owner left the organization or was disabled. Everyone who can read its record or module can read it; nobody can edit it. | Customer |
| My sheets | — | The list of sheets that a person owns or that are shared with them. | Customer |
| Link column | — | A sheet column whose cells each link to one record of a chosen module. It is not a Sandbox relationship field. | Customer |
| Lookup column | — | A read-only sheet column that shows a field of the linked record, as its current value. | Customer |
| Computed column | — | A sheet column that calculates a value from other columns of the same row. | Customer |
| Appears in | — | The read-only list, on a record, of sheet rows that link to it, limited to sheets the viewer can see. | Customer |
| Sheet template | template JSON, `schemaVersion` | A sheet's structure without data, shares or IDs, as a versioned JSON file. | Customer |

One word, several meanings (columns: Word, Meanings, Write):

| Word | Change |
| --- | --- |
| sheet | New row. (1) a side panel, such as the record sheet; (2) a Sheet on a record. Write **record panel** or **side panel** for 1, **sheet** for 2. |
| template | Add meaning (4), sheet template. Write **sheet template**. |
| export | Add meaning (7), sheet export. Write **sheet export**. |
| history | Add meaning (5), sheet history (row changes with values, for people who can see the sheet). Write **sheet history**. |
| group | Add meaning (5), a column group in a sheet. Write **column group**. |
| event | Add meaning (5), the leave event that opens a person's sheets. Write **leave event**. |

## Traceability

| Source | Rules | Criteria |
| --- | --- | --- |
| REQ-0025 item 1 (the line) | P8 | SH-5, SH-51 |
| REQ-0025 item 2, DEC-0043 1 (create) | C1–C4 | SH-1–SH-5 |
| REQ-0025 item 3, DEC-0043 2, DEC-0044 1 (visibility) | V1, V3, V4, V7 | SH-6, SH-7, SH-11, SH-14 |
| DEC-0044 2 (leave) | L0–L10, V8 | SH-12–SH-19, SH-55, SH-57, SH-60, SH-61 |
| DEC-0044 3 (sharing) | V2, V5, V6 | SH-8–SH-10 |
| REQ-0025 item 4 (links) | N1–N8 | SH-26–SH-30 |
| REQ-0025 item 5 (entry point) | P4 | SH-1, SH-8, SH-62 |
| REQ-0025 item 6 (storage) | P1, D1, Backend list 1 | SH-5 |
| REQ-0025 item 7 (formulas) | K3–K8, D7 | SH-21–SH-25, SH-58 |
| REQ-0025 item 8 (name) | P7 | SH-52, glossary rows |
| REQ-0025 item 9, DEC-0043 3 (organization-agnostic) | O1–O5, K1, K2 | SH-20, SH-33, SH-38, SH-39 |
| REQ-0025 item 10, DEC-0044 4 (import and export) | X1–X11, D9 | SH-31–SH-37, SH-59 |
| Parent: placement and phone | P2, P3, P5, P9, F7 | SH-48–SH-50, SH-53, SH-54 |
| Parent: history and audit | H1–H6, D5 | SH-45–SH-47, SH-59 |
| Parent: undefined states | L9, F1, F2, N6, D4 | SH-19, SH-29, SH-40, SH-56 |
| Parent: exclusions | Out of scope | SH-51 |
| TASK-0099 Screens | P2, P4, P5, K1, N4, L10 | SH-48–SH-50, SH-62 |
| TASK-0100 Data and API | L0, L3, L5, K6, F5, F6, H5, H6 | SH-13, SH-43, SH-44, SH-55–SH-61 |
