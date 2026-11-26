# Sheets

> **Status: done (2026-11-24), PR #117.** Built under APR-0016 from REQ-0025 and owner decisions DEC-0043 to DEC-0047. Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/sheets.md`.

## Outcome

A member keeps working data in rows and columns on a record or a module, with no new module. A sheet is private to its owner until shared and never changes its record. Code: `backend/app/systems/openview/worksheets/`, `frontend/src/components/systems/openview/components/sheet-*.tsx`.

## Decisions

Settled 2026-11-24 (DEC-0045); module sheets, From another sheet and per-cell saves by DEC-0046; security choices by DEC-0047.

ID | Decision
--- | ---
Decision 1 | Admins see audit traces of private sheets (IDs, times, counts), never content.
Decision 2 | Private sheet data cannot be found for removal requests in version 1.
Decision 3 | Guests get View-only shares and cannot copy (3a).
Decision 4 | "No access" applies to a whole link column; no Share warning.
Decision 5 | The access rule lives in `openview/worksheets/access.py`, built on `scope.py`.
Decision 6 | A restore returns the sheets, private (6a). A new invitation does not; they stay open (6b).
Decision 7 | `memberships.worksheets_released_at` supports Decision 6.
Decision 8 | The open state is derived from the owner's membership, not stored.
Decision 9 | Nobody can delete an open sheet.
Decision 10 | The open-sheet line reads "… no longer has access", with no date.
Decision 11 | The lifecycle impact response gets `worksheet_count`.
Decision 12 | A deleted sheet is kept until its record or module is purged.
Decision 13 | Import rows that match several records get the keep-or-skip choice.
Decision 14 | A sheet from a data file suggests column types; the person can change them.
Decision 15 | Import into an existing sheet adds rows only.
Decision 16 | Number stores `decimal` (currency option), Whole number stores `int`; `number` is not offered.
Decision 17 | A lookup beside "Deleted record" or "Removed record" is blank.
Decision 18 | Templates carry no shares in version 1.

## Rules

**Placement.** **P1** Sheets are OpenView JSONB rows on a record or a module. **P2** The module page lists its visible module sheets with New sheet; the record panel's last tab is Sheets (after History, or Files). **P3** A sheet is a full-width page; only the grid pane scrolls. **P4** My sheets, in the sidebar foot for every account, lists owned and shared sheets, not open sheets never shared with the person. **P5** At 390px the grid scrolls sideways with the first column pinned; a tapped row opens a form in a bottom panel; the page never scrolls. **P6** Each sheet has a link; a hidden sheet gets the same "not found". **P7** Users read "Sheets"; code says `Worksheet`. **P8** Nothing reads sheet data except its screens, Appears in and exports. **P9** The grid is accessible: grid roles, keys, focus, reduced motion.

**Create.** **C1** A member with read, write or manage on a module creates a sheet on a readable record or the module. **C2** A sheet never changes its record. **C3** Guests cannot create sheets. **C4** No create on a deleted record, a closed module, or an unreadable record (404). **C5** The creator is the owner; only the owner renames.

**Visibility and sharing.** **V1** A new sheet is visible only to its creator. **V2** The creator gives View or Edit to a person or group. **V3** Nobody else, admins included, learns of a private sheet. **V4** A person who cannot read the record (or module) never sees the sheet; the share works again when read returns. **V5** Edit changes rows and columns; only the creator shares, changes visibility or deletes. **V6** A group share follows membership; with two shares the higher level applies. **V7** A hidden sheet is absent from every surface and gets 404. **V8** The share dialog says the sheet opens read-only to record readers when the creator leaves. **V9** Guests receive View only (Decision 3).

**The leave event.** **L0** A sheet is open when its owner is not present or a release cutoff is later than its creation; nothing is stored. **L1** Leave paths: membership disabled, account disabled, membership removed, account deleted. **L2** An open sheet is readable by every record (or module) reader, editable by nobody. **L3** The change is the leave transaction's own write; a racing sheet write locks the owner row first (D3.3). **L4** Re-enable returns the sheets, private, with their shares. **L5** Disable and remove confirmations show a count from `worksheet-impact` (D3.2). **L6** A reader of an open sheet can Make a copy: a private copy on the same record, no shares. **L7** An open sheet cannot be deleted, renamed or shared (409 `worksheet_open`). **L8** Restore and a new invitation follow Decisions 6 and 7. **L9** An owner who loses module read but stays active keeps the sheets private; recipients keep their shares. **L10** The open-sheet line names the owner, says "no longer has access", and shows no date.

**Columns, computed columns and totals.** **K1** Sandbox type names plus Link, Lookup, From another sheet and Computed; `relationship` gets 422. **K2** Currency is a display option of `decimal`; exports write plain numbers. **K3** Computed columns use same-row arithmetic with `{Name}` and `ROUND`, `MIN`, `MAX`, `AVERAGE`, `SUM`; no cell references. **K4** They read numeric columns; loops are refused; expressions store keys, so renames keep working. **K5** Functions skip blanks; blank arithmetic is blank; division by zero marks the cell and its readers. **K6** Values are computed per request and never stored; hidden lookups show "No access", and totals report hidden cells. **K7** A totals row: sum, average, min, max (numeric) or count (any). **K8** Column groups are named bands over adjacent columns. **K9** From another sheet shows a source sheet's column for the same linked record, read-only, or "No access", "Column removed", "2 matches".

**Links and Appears in.** **N1** A link column targets one readable module; each cell links one record. **N2** A lookup shows the linked record's current field value, read-only. **N3** A person links only records they can read. **N4** An unreadable linked record shows "No access", per column. **N5** Appears in on a record lists linking rows of sheets the viewer can see; read-only, not stored. **N6** A deleted target shows "Deleted record" (restore returns it); a purged one shows "Removed record". **N7** A lookup whose field is removed shows "Field removed". **N8** A closed target module or lifecycle-closed record shows "Unavailable" until reopen.

**Import and export.** **X1** Data is CSV or Excel; a template is versioned JSON. **X2** Anyone who can see a sheet can export it. **X3** Each export writes `worksheets.export.authorized`. **X4** Export is formula-safe, with values and "No access"; CSV uses the locale decimal mark (O4). **X5** A template has `schemaVersion` and no data, shares or IDs. **X6** Template import maps link columns to modules by name; no match gives a text column; an unknown version is refused. **X7** New sheet from this structure copies the template to a chosen record. **X8** Data import matches rows by a key column over readable records, with a preview; nothing is written before confirm. **X9** Import adds rows to an editable sheet or makes a new sheet. **X10** Excel import: `.xlsx` only, at most 10 MiB, 10,000 rows and 100 columns, values only, no macros, one tab, chosen header row. **X11** Text that starts like a formula is stored as text. **X12** Export adds one leading apostrophe to formula-like text and import removes one; person columns cannot be filled from a file (B13).

**Lifecycle.** **F1** Record delete hides its sheets, restore returns them, purge removes them; module sheets follow their module. **F2** The purge preview shows a sheet count. **F3** A deleted sheet disappears for everyone; the owner restores it from My sheets. **F4** Saves are checked per cell (412 `cell_changed`); other people's changes appear without reload. **F5** Live-refresh events reach only people who can see the sheet. **F6** Limits (D8) answer 422 `worksheet_limit`. **F7** Sort by one column and search; neither is saved.

**Presence.** **PR1** The header shows avatars of others with the sheet open ("+N" over four). **PR2** Each person's cell is outlined; presence carries the cell position only. **PR3** Only people who can see the sheet get a presence token (D13). **PR4** Presence shows no one outside the people directory. **PR5** Lost access stops presence within 60 seconds. **PR6** Presence keeps no history and writes nothing to the database.

**History and audit.** **H1** Changes go through `AuditSession`. **H2** Admin audit rows redact content and carry no department (D5). **H3** A sheet has its own row history for people who can see it. **H4** The record's History tab shows no sheet events. **H5** `worksheets.opened_on_leave` per leave that opens sheets. **H6** Each Excel parse writes `worksheets.import.file_parsed`.

**Organization-agnostic.** **O1** No industry words, columns or templates. **O2** Templates belong to each organization. **O3** Formats follow the organization, with the person's own overrides. **O4** Pasted and imported numbers use the locale decimal separator. **O5** School and Manufacturer sample packs show sheets (deferred, see Open items).

## Acceptance criteria

"Met" means: in the stated scope of PR #117.

ID | Criterion | Result
--- | --- | ---
SH-1 | A read-only member creates a sheet; it shows in Sheets and My sheets. | met
SH-2 | The same for write and manage. | met
SH-3 | A guest cannot create. | met
SH-4 | Create on a deleted, closed or unreadable record is refused. | met
SH-5 | The record stays unchanged. | met
SH-6 | A peer sees nothing of a private sheet. | met
SH-7 | The same for a module manager and an admin. | met
SH-8 | View: read and export, no writes. | met
SH-9 | Edit: rows and columns, not rename, share or delete. | met
SH-10 | Group shares follow membership; the higher level wins. | met
SH-11 | Lost record read hides the sheet; it returns with read. | met
SH-12 | The share dialog shows the leave sentence. | met
SH-13 | A leave opens the owner's sheets read-only at commit. | met
SH-14 | Non-readers still get "not found". | met
SH-15 | The confirmation shows the opening count. | met
SH-16 | Re-enable restores privacy and shares. | met
SH-17 | Make a copy of an open sheet. | met
SH-18 | An open sheet cannot be deleted, renamed or shared. | met
SH-19 | An owner without module read cannot open; recipients keep access. | met
SH-20 | Every K1 type works; `relationship` is refused; currency shows. | met
SH-21 | Computed columns and functions work; bad expressions are refused. | met
SH-22 | A rename keeps expressions working. | met
SH-23 | Blanks, division by zero, and one value everywhere. | met
SH-24 | Totals per column. | met
SH-25 | Column groups. | met
SH-26 | Link and lookup columns. | met
SH-27 | "No access" link cells, also in export. | met
SH-28 | Appears in per viewer. | met
SH-29 | "Deleted record" and "Removed record". | met
SH-30 | "Field removed" and closed-module cells. | met
SH-31 | CSV and Excel export with a security event. | met
SH-32 | Template export has no data or IDs. | met
SH-33 | Template import maps modules; unknown versions are refused. | met
SH-34 | New sheet from this structure. | met
SH-35 | Import preview counts; Cancel writes nothing. | met
SH-36 | Excel import limits and formula cells. | met
SH-37 | Formula-like text stays text and exports safe. | met
SH-38 | Locale decimal separator and formats. | met
SH-39 | No industry words; School and Manufacturer packs create sheets. | partly: packs deferred (REQ-0027)
SH-40 | Record delete, restore and purge; purge count. | met
SH-41 | Owner delete and restore. | met
SH-42 | Per-cell saves and conflicts; live changes. | met
SH-43 | Live events reach only viewers. | met
SH-44 | Each limit gives 422 `worksheet_limit`. | met
SH-45 | Redacted audit rows. | met
SH-46 | Sheet history for viewers only. | met
SH-47 | Leave security event with the count. | met
SH-48 | The Sheets tab position; other tabs unchanged. | met
SH-49 | Full-width page; only the grid scrolls. | met
SH-50 | Phone grid and row form. | met
SH-51 | Views, exports and reports unchanged by sheets. | met
SH-52 | No visible "Worksheet". | met
SH-53 | Sort and search are not saved. | met
SH-54 | Keyboard, screen reader and reduced motion. | met
SH-55 | `worksheet-impact` gives `{"opening_count": n}` to admins only. | met
SH-56 | A sheet made after the purge preview refuses the purge. | met
SH-57 | A save racing a leave commits first or is refused. | met
SH-58 | Hidden lookups mask computed cells, sort, search and totals. | met
SH-59 | Excel parse events; none for CSV. | met
SH-60 | An account-wide disable opens sheets in both organizations; one event. | met
SH-61 | Restore and new invitation follow Decisions 6 and 7. | met
SH-62 | My sheets for every account; never-shared open sheets excluded. | met
SH-63 | Avatars and cell outlines. | met
SH-64 | No presence token for people who cannot see the sheet. | met
SH-65 | Lost access stops presence within 60 seconds. | met
SH-66 | Presence carries IDs and positions only; nothing stored. | met
SH-67 | Module sheets on the module page. | met
SH-68 | Module sheets on leave, close, reopen and purge. | met
SH-69 | From another sheet values and states. | met
SH-70 | Hidden sources leak no IDs or names (D14). | met
SH-71 | Presence token scope on Realtime topics (D13). | met
SH-72 | Oversized computed chains are refused fast (D7.1). | met

## Screens

### Screens 1. Record panel, Sheets tab

"On this record" lists visible sheets; no New sheet for guests; the panel stays 540px.

### Screens 2. New sheet and columns

New sheet: blank, template file or data file. Add column popover: name, type, group, total.

### Screens 3. Sheet page

Breadcrumb department › module › record › sheet; header actions Import, Export, Share, More; fixed headers, first column and totals.

### Screens 4. Share

View or Edit per person or group, with the leave line.

### Screens 5. Open sheet after the owner left

Read-only chip, the owner line, Export and Make a copy.

### Screens 6. Appears in

Linking rows of visible sheets, read-only.

### Screens 7. My sheets

A still page with filters All, Owned by me, Shared with me, Deleted.

### Screens 8. Import preview

File, columns, match counts, then confirm.

### Screens 9. Phone, 390×844

Pinned 160px column; row form in a bottom panel.

## Data and API

**D0** The open state is derived from the owner's presence, never stored (Decision 8).

**D1** Tables in `openview/worksheets/models.py` follow the organization-table rules (`org_id`, composite foreign keys, RLS); column keys are sheet-local (`c1`). **D1.1** `worksheets`: one anchor (record or module), owner, title, `structure`, revision, row and byte counters. **D1.2** `worksheet_rows`: `data` JSONB, position, revision, byte size. **D1.3** `worksheet_shares`: person or group, `view` or `edit`. **D1.4** `worksheet_row_links`: one link per cell, `target_removed`. **D1.5** `worksheet_row_revisions`: insert-only history. **D1.6** `memberships.worksheets_released_at` for Decision 6. **D1.7** `structure` JSON: `structureVersion`, columns (`link`, `lookup`, `computed`, `sheet_lookup`), groups, totals.

**D2** `visible_worksheet_clause` and `worksheet_level` decide every list, count, route and SSE set; no admin override; guests capped at View; hidden sheets answer 404 `worksheet_not_found`.

**D3** Leave and return. **D3.1** The four leave paths count the sheets that will open before the change, then write `worksheets.opened_on_leave`. **D3.2** `GET /api/users/{user_id}/worksheet-impact`. **D3.3** A sheet write locks the owner's user row `FOR SHARE` first. **D3.4** Account-wide paths write the event in the request's organization only.

**D4** Lifecycle: record delete hides sheets; purge removes them and marks links removed; a sheet made after the preview refuses the purge.

**D5** Audit. **D5.1** Redacted fields per table. **D5.2** No department on sheet audit rows. **D5.3** `GET /api/worksheets/{id}/history`. **D5.4** Security events `worksheets.export.authorized`, `worksheets.import.file_parsed`, `worksheets.opened_on_leave`.

**D6** SSE: the `worksheets` entity reaches only `EventViewer.worksheet_ids`, with no admin pass.

**D7** Computed columns. **D7.1** Grammar: `+ - * /`, unary minus, `SUM`, `AVERAGE`, `MIN`, `MAX`, `ROUND`, `{key}`; size and depth limits. **D7.2** No `eval`: a parser compiles to one bound SQL expression. **D7.3** Lookups are masked per viewer. **D7.3a** From another sheet matches source rows through the linked record. **D7.4** Loops are refused; renames change no expression.

**D8** Limits: 100 columns, 10,000 rows, 4,000-character text cells, 32 KiB rows, 8 MiB sheets, 10 MiB Excel files.

**D9** Import and export. **D9.1** Data export rechecks access and writes the event. **D9.2** Template JSON with `schemaVersion: 1`. **D9.3** Import: CSV in the browser, Excel in a child process, a match preview, batches of 100 rows. **D9.4** The Excel reader is python-calamine. **D9.5** `POST /api/worksheets` with `source` `structure` or `copy`.

**D10** API routes, under `/api`: 1 `GET /worksheets`; 2 `GET /records/{record_id}/worksheets`; 2a `GET /modules/{module_id}/worksheets`; 3 `POST /worksheets`; 4 `GET /worksheets/{id}`; 5 `PATCH` rename; 6 `PUT /worksheets/{id}/structure`; 7 `DELETE`; 8 restore; 9 rows query; 10 row create; 11 row read; 12 row `PATCH` (per-cell `expected`); 13 row delete; 14 `rows/batch`; 15 history; 16 to 19 shares; 20 export; 21 `/worksheet-import-files`; 22 `/worksheet-import-matches`; 23 `GET /records/{record_id}/worksheet-rows` (Appears in); 24 `worksheet-impact`; 25 `share-candidates`; 26 `worksheet_count` on lifecycle impact.

**D11** Risks: copy volume, no idempotency.

**D12** The recommended option of each decision was chosen (DEC-0045).

**D13** Presence: a private Realtime topic per sheet, a 60-second presence token from `POST /api/worksheets/{id}/presence-token`, and cell positions only.

**D14** Security constraints (2026-11-24): S1 per-viewer structure masking; R1 share targets; R2 masked per-cell checks; R4 recheck after locks; R5 404 before other errors; R6 deleted-list conditions; C1–C5 SSE branch; E1–E7 Excel child; P6 documentation.

## Slices

S1 and S2 shipped in PR #117, except the sample packs (O5).

## Open items

- O5 and SH-39: sheets in the School and Manufacturer sample packs (REQ-0027).
- Purge as scheduled work (REQ-0026): a purge of a very large sheet can pass the 60 s proxy limit.
