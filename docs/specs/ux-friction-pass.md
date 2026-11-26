# UX friction pass: fewer steps and fewer system words in daily work

> **Status: done (2026-11-13), PR #107, #108, #109.** Build approved by APR-0003. Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/ux-friction-pass.md`. PR #110 (pass 4) is `subtle-interactions.md`.

## Outcome

Staff reach daily objectives with fewer steps, dead ends and system words. Administrators give access and publish with no detour. PR #107 built items 1, 2, 3, 6 and 12 (OpenView record list and record panel). PR #108 built items 5, 7, 8, 9, 11 and 13. PR #109 built items 4 and 10, with the two backend changes: file search (BE-UF1) and `has_other_grants` on every access group response (DR-10.10). Main code: `frontend/src/components/systems/openview/` (list, record sheet, `domain/record-inplace-change.ts`), `systems/platform/components/search-panel.tsx`, `workspace-navigation.ts`, `systems/access/helpers/add-access.ts`, `lib/last-organization.ts`, `backend/app/systems/platform/search/files.py`.

**Who.** Account levels: administrator (`admin@harbor.test`), department manager on Sales (`sales.manager@harbor.test`), writer (`sales.writer@harbor.test`), reader (`sales.reader@harbor.test`), guest (`sales.guest@harbor.test`). A **view manager** has Manage on the open module, through a department or module grant (`canManageOpenView`). Item numbers 1–14 come from the audit; the designer IDs F1–F14 are in brackets.

## Decisions

ID | Decision
--- | ---
OD5 | Changed (APR-0003): the "Unsaved changes" chip shows only to view managers. `openview-relayout.md` points here.
Guard line | Changed (APR-0003): the view leave guard shows only to view managers. Record edit and create guards stay.
PD21 | Changed (APR-0003): header Search opens a panel over the page; the Search page stays for all results.
BD16 | Changed (APR-0003): widget titles still come from the query, as plain names ("Total credit limit").
DA19, TRIG-6 | Not changed. Item 2 makes the build match DA19. Item 9 makes Triggers and Test say "record", as TRIG-6 requires.
D-1 | DA21 empty-organization words: option (a), keep DA21 ("Nothing published yet" stays in the code).
D-2 | "link" or "relationship": Review keeps "relationship" (DR-11.1).
D-3 | Resolved: the bindings read gives new module IDs right after publish. No backend change.
D-4 | Stored Start page "Platform": option (a), keep PD62, label "Platform (not available)" (DR-7.8).
DR-10.10 | Security, Human Owner choice 1a (2026-11-13): Add access reuses a group only when it fits by access and `has_other_grants` is false.

## Preserved behavior

- Access stays group-based. Only administrators make groups. A guest is capped at Read. The server refusal is the source of truth.
- D43: an administrator cannot read other people's direct messages or private channels, in Search too.
- Saved views stay shared; only view managers save them (DA12, DA13).
- The publish password, the administrator-only Sandbox, D1 "Save triggers", and SD6.
- Owner decisions: "module", "Announcements", "Gantt", view-only Profile, "Make a copy now", one dashboard per department.
- Addresses (`?section=`, `?module=`, `?view=`, `?record=`, `/platform?section=…`) and the view state in the address.
- Stored values: Start page, filter operators, trigger events, widget queries.

## Acceptance criteria

"Met" means: in the stated scope of the merged PR for that item. Accounts are the Harbor testing accounts at 1440×900 unless stated.

ID | Req | Criterion | Result
--- | --- | --- | ---
UF-C1.1 | UF-1.1 | Writer, reader, guest: a quick chip shows no "Unsaved changes"; the sidebar leaves with no question; no view write. | met
UF-C1.2 | UF-1.2 | Browser Back restores the filter; Copy link and Reset changes stay. | met
UF-C1.3 | UF-1.3 | Manager and administrator keep the mark, Save view as primary, and the question (DA12). | met
UF-C1.4 | UF-1.1 | A manager outside the module behaves as a writer. | met
UF-C1.5 | UF-1.4 | An open Edit form is modal; the typed value stays. | met
UF-C2.1 | UF-2.1 | Edit from Files, Linked records or History opens Details with the form. | met
UF-C2.2 | UF-2.2, UF-2.3 | A Status pick saves in place with one request; the header names it with Undo. | met
UF-C2.3 | UF-2.3 | Undo writes the old value back. | met
UF-C2.4 | UF-2.4 | Text and user fields need Edit. | met
UF-C2.5 | UF-2.5 | Reader and guest see plain values. | met
UF-C2.6 | UF-2.6 | A stale in-place save is refused; the reason shows; nothing is overwritten. | met
UF-C3.1 | UF-3.1, UF-3.2 | An empty new filter keeps rows, count, chips and Export; no error; "not applied". | met
UF-C3.2 | UF-3.1 | A completed condition filters; chip "Status: is Former". | met
UF-C3.3 | UF-3.3 | Save view with an incomplete condition shows the error and sends nothing. | met
UF-C3.4 | UF-3.4 | An unsafe number keeps its error; the list keeps the last result. | met
UF-C4.1 | UF-4.1, UF-4.3, UF-4.6 | Search opens a panel with focus; the address stays; Escape keeps the page state. | met
UF-C4.2 | UF-4.4 | File results list only readable departments. | met
UF-C4.3 | UF-4.5 | An administrator gets no messages from others' direct messages (D43). | met
UF-C4.4 | UF-4.2 | ⌘K: "Switch conversation" in OpenComms, the panel elsewhere. | met
UF-C4.5 | UF-4.6, UF-4.7 | A result opens its page; "all results" opens the Search page. | met
UF-C5.1 | UF-5.1, UF-5.2 | A typed name lists the person in view (DR-5.7); a pick opens a direct message with composer focus. | met
UF-C5.2 | UF-5.3 | A person with an existing direct message shows once. | met
UF-C5.3 | UF-5.4 | A guest gets no people list. | met
UF-C5.4 | UF-5.4 | "+" › Group message works as before. | met
UF-C6.1 | UF-6.1, UF-6.2 | A new record is the first row with "New"; status in the meta line; no banner. | met
UF-C6.2 | UF-6.3 | A record hidden by filters is not added; the status says so. | met
UF-C6.3 | UF-6.2, UF-6.4 | A sort change removes "New"; the count shows each record once. | met
UF-C7.1 | UF-7.1, UF-7.3 | Writer, reader, guest Tools: Boards, Files, Organization, System health. | met
UF-C7.2 | UF-7.4 | Manager Tools: Boards, Access (Groups), Files, Manage. | met
UF-C7.3 | UF-7.2, UF-7.5 | Administrator Tools add Files › Import & export. | met
UF-C7.4 | UF-7.6 | Old `/platform` addresses keep their checks; "See all" opens notifications. | met
UF-C7.5 | UF-7.6 | A stored Start page "Platform" still opens a page and is unchanged. | met
UF-C8.1 | UF-8.1, UF-8.4 | Choose file saves a draft, then attaches; the post publishes with the file. | met
UF-C8.2 | UF-8.2 | Empty Title disables Choose file with the reason. | met
UF-C8.3 | UF-8.3, UF-8.4 | The automatic draft is not visible to readers. | met
UF-C8.4 | UF-8.5 | An oversized file shows the error; text stays. | met
UF-C9.1 | UF-9.1 | Triggers and Test say "record". | met
UF-C9.2 | UF-9.2 | Layout settings have no implementation words. | met
UF-C9.3 | UF-9.3 | One "no value" pair; old saved views keep results with a distinct label. | met
UF-C9.4 | UF-9.4 | No "Sum of" titles; an empty Number widget says "No values yet". | met
UF-C9.5 | UF-9.5 | Sandbox shortcuts show only to Sandbox users. | met
UF-C10.1 | UF-10.1 | Invite shows what each group gives. | met
UF-C10.2 | UF-10.2, UF-10.3 | Add access joins an exact-fit group. | met
UF-C10.3 | UF-10.4 | With no fit, it makes a group with a non-Sandbox name and adds the person. | met
UF-C10.4 | UF-10.5 | A guest gets Read only. | met
UF-C10.5 | UF-10.6 | A manager gets no People page and no Add access. | met
UF-C10.6 | UF-10.7 | A retry after partial failure uses the made group. | met
UF-C11.1 | UF-11.2, UF-11.3 | The counts line lists only what the owner drew; "Comes with" under each department. | met
UF-C11.2 | UF-11.1 | "Published" links to the new module's records. | met
UF-C11.3 | UF-11.4 | A wrong password publishes nothing. | met
UF-C11.4 | UF-11.1 | A field-only publish shows "Published" with no link. | met
UF-C12.1 | UF-12.1, UF-12.2 | At 390×844 the actions sit in one row above a full-width title. | met
UF-C12.2 | UF-12.2 | At 1440×900 the header is unchanged. | met
UF-C13.1 | UF-13.1 | The last organization opens with no chooser. | met
UF-C13.2 | UF-13.2 | Another account in the same browser gets the chooser. | met
UF-C13.3 | UF-13.2, UF-13.3 | A refused open shows the chooser with the reason. | met
UF-C13.4 | UF-13.4 | `/` has no installer text; `/login` keeps "First deployment?". | met
UF-C14.1 | UF-14.1 | If the first-click defect reproduces with real input, the first click navigates. | not recorded
UF-C14.2 | UF-14.1 | If it does not reproduce, no code change. | not recorded

## Rules for every item (DS-6)

- G1 Motion only on the element acted on. Page navigation is never animated.
- G2 No cover or "checking" screen. A skeleton shows only after 300 ms.
- G3 An explanation sits directly under what it explains.
- G4 From 1280 px, still pages fill the window; panes scroll alone.
- G5 Targets are 32 px from 1280 px and 44 px below; every control has a name, focus ring and keyboard path.
- G6 The server is the source of truth for access.

### Item 1 [F1]: no "Unsaved changes" for people who cannot save a view

UF-1.1 to UF-1.4. DR-1.1 `canManageViews` decides the mark and the questions. DR-1.2 The badge needs a change and a view manager. DR-1.3 For others, the three discard questions continue at once. DR-1.4 The view state stays in the address. DR-1.5 A non-manager's header does not change. DR-1.6 View managers see no change. DR-1.7 The record edit and create guards stay (the modal form is the guard).

### Item 2 [F3]: change a value in place; Edit always opens Details

UF-2.1 to UF-2.6. DR-2.1 Edit on any tab selects Details and opens the form. DR-2.2 Exactly four types change in place: Choice list, Checkbox, Date, Date and time. DR-2.3 Commit on pick, toggle, or blur/Enter for a complete date; Escape restores. DR-2.4 One `PATCH /api/records/{id}` with every active value and `If-Match`. DR-2.5 The header meta line names the change with Undo. DR-2.6 Undo lasts until the next change, Edit, tab change, Previous/Next or close; no timer. DR-2.7 A 412 overwrites nothing and shows "Someone changed this record." DR-2.8 Other failures show "Not saved. Try again." DR-2.9 Other types keep Edit and Save. DR-2.10 No control for readers, guests, deleted or read-only records. DR-2.11 No in-place control while Edit is open. DR-2.12 Items 2 and 12 apply to the OpenView sheet only; the Boards card sheet is unchanged. DR-2.13 In-place controls wait for all fields to load, and commits run one at a time.

### Item 3 [F2]: the list reads only complete conditions

UF-3.1 to UF-3.4. DR-3.1 Reads, counts and Export use only applied conditions. DR-3.2 The list-level warning is removed. DR-3.3 Add filter focuses the Field select. DR-3.4 An incomplete row reads "Not applied yet" and has no chip. DR-3.5 Save view with an incomplete row sends nothing and shows the error. DR-3.6 An unsafe number keeps its error and is not applied. DR-3.7 The unavailable-field message stays.

### Item 4 [F6]: a search panel over the page (new structure; comp `search.html`)

UF-4.1 to UF-4.7. DR-4.1 Header Search is a button that opens the panel; Ctrl K / ⌘K outside OpenComms. DR-4.2 A dialog "Search workspace", 640 px wide from 768 px, full screen below; the page and address stay. DR-4.3 Order: field, scope line, groups, "Show all results for “…”". DR-4.4 Fixed group order Records, People, Posts, Events, Messages, Files; at most 5 rows each. DR-4.5 Six reads 250 ms after the last key; `can_open: false` rows are plain text. DR-4.6 Arrow keys move across groups; Escape returns focus to Search. DR-4.7 A pick closes, then navigates through the guard; a file opens the Files page with `search` (N-3). DR-4.8 "Show all results" opens `/platform?section=search&q=…`, which adds Messages and Files (PR3 screen review). DR-4.9 Each group fails alone with Try again.

**BE-UF1: file kind on `GET /api/search`.** `kind=file` finds ready, not-deleted library documents by name, only in departments the actor can read. `SearchItem` gains `department_id` (set for `file`, null for other kinds). No migration.

### Item 5 [F5]: people in "Find a conversation…"

UF-5.1 to UF-5.4. DR-5.1 Typed text adds a People section (at most 5) after the conversation matches. DR-5.2 The same in ⌘K "Switch conversation". DR-5.3 A person with a visible direct message shows once. DR-5.4 A pick calls `POST /api/comms/directs` and focuses the composer. DR-5.5 Guests get no People. DR-5.6 No match: "No conversations or people match."; a guest keeps "No conversations match." DR-5.7 (QA-P2-D1) While text is typed, only matches show.

### Item 6 [F4]: the new record shows first, tagged "New"

UF-6.1 to UF-6.4. DR-6.1 No banner; "Record created." is the meta-line status and clears at the next action. DR-6.2 On close, one `POST /records/query` checks if the record matches. DR-6.3 A match is the first row with a "New" tag, shown once. DR-6.4 The count stays the server total. DR-6.5 No match: "Created, hidden by filters." with "Open record". DR-6.6 "New" goes at a filter, sort, search, page or view change.

### Item 7 [F7]: the sidebar shows what each person can use

UF-7.1 to UF-7.6. DR-7.1 No Platform group; Files is its own item. DR-7.2 Administrators get Files with Import & export. DR-7.3 Writer, reader, guest: Boards, Files, Organization, System health. DR-7.4 Manager: Boards, Access (Groups), Files, Manage. DR-7.5 Administrator: Sandbox, Boards, Access, Manage, Files. DR-7.6 Every `/platform?section=…` address keeps its page and checks. DR-7.7 Breadcrumbs drop "Platform". DR-7.8 A stored "Platform" Start page still opens Search and reads "Platform (not available)" (D-4).

### Item 8 [F8]: Choose file saves the draft first

UF-8.1 to UF-8.5. DR-8.1 "Choose file" replaces "Save draft to attach". DR-8.2 Disabled until Title and Message have text. DR-8.3 The file is checked before any save. DR-8.4 A valid file saves a draft (never publish), then uploads. DR-8.5 On failure, text stays and no file is orphaned. DR-8.6 A closed editor leaves the draft in Drafts. DR-8.7 "Save draft to link" stays.

### Item 9 [F13]: plain words

UF-9.1 to UF-9.5. DR-9.1 Triggers and Test say "record". DR-9.2 Layout settings name the default order: oldest records first. DR-9.3 One "no value" pair (stored `blank`, `not_blank`); old `empty` conditions show "(exact)". DR-9.4 Plain widget titles. DR-9.5 An empty Number widget shows "No values yet". DR-9.6 Help lists "Search workspace" for everyone and Sandbox shortcuts only for Sandbox users.

### Item 10 [F9]: Invite says what each group gives; "Add access" (new structure; comp `add-access.html`)

UF-10.1 to UF-10.7. DR-10.1 Invite rows show "Sales · Write". DR-10.2 Administrators get "Add access" in a person's Access tab. DR-10.3 The form: department, then level. DR-10.4 An exact-fit group: "Add to <group>". DR-10.5 No fit: make "<Department> read access" and add; never a Sandbox derived name. DR-10.6 Existing equal or higher access disables the action. DR-10.7 Make runs create, set access, add member, in order. DR-10.8 A partial failure retries with the made group. DR-10.9 No Add access for other levels. DR-10.10 See Decisions.

### Item 11 [F10]: Published state; counts of what the owner drew (new structure; comp `published.html`)

UF-11.1 to UF-11.4. DR-11.1 The counts line lists departments, modules, fields, relationships and triggers. DR-11.2 "Comes with: …" under each new department. DR-11.3 Password and "Save triggers" stay. DR-11.4 The dialog stays open with title "Published". DR-11.5 Module links come from the bindings read after publish. DR-11.6 No module: only the title and "Back to Build".

### Item 12 [F14, part]: phone record header

UF-12.1, UF-12.2. DR-12.1 Below 640 px the actions row comes first, then the full-width title. DR-12.2 Every DA18 element and name stays; 44 px targets.

### Item 13 [F12, F11 part]: open the last organization; landing words

UF-13.1 to UF-13.4. DR-13.1 After sign-in, the browser's last organization opens with the same server call as a pick. DR-13.2 No chooser flash and no cover while it opens. DR-13.3 The chooser shows when nothing is stored, it is not a membership, or the open is refused, with the reason. DR-13.4 Pending invitations stay reachable. DR-13.5 The landing page says "Join"; "First deployment?" stays only in the `/login` footer.

## Open items

- Item 14 (first sidebar click after Escape): the result went to the run record; this spec has none.
- Not in scope and not built: phone quick-filter chips in the Filters sheet, an endpoint that creates organizations, import flow changes, and "Add linked record" in the post editor.
