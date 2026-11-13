# UX friction pass: fewer steps and fewer system words in daily work

> **Status: Proposed 2026-11-12; build approved by APR-0003.** Requirements half by the Product Manager (TASK-0054). The Product Designer writes the design half under the headings marked "Product Designer". No product code has changed.

## Outcome

Staff who are not technical reach each daily objective with fewer steps, fewer dead ends, and fewer system words. Administrators give access and publish without a detour through concepts they do not need.

**The job.** When I do my daily work in the organization (find records, change a value, post, message, search), I want each action to do what it says at once, so I can finish and move on. Emotional side: no false alarms ("Unsaved changes" when nothing can be saved) and no fear of a red error before I type. Social side: an administrator who gives access must not give more than intended by mistake.

**Who.** The account levels are these, as in the hands-on accounts of `CLAUDE.md`:

| Level | Account used in the criteria |
| --- | --- |
| Administrator | `admin@harbor.test` |
| Department manager (manage on Sales) | `sales.manager@harbor.test` |
| Writer | `sales.writer@harbor.test` |
| Reader | `sales.reader@harbor.test` |
| Guest | `sales.guest@harbor.test` |

A **view manager** is a person who has Manage access to the open module, through a department or a module grant (`canManageOpenView`, `frontend/src/components/systems/openview/domain/manage-access.ts:36-44`). Examples: an administrator; the Sales manager in a Sales module. The Sales manager in a module where the grant is Read or Write is not a view manager there.

Item numbers 1–14 are the numbers of the run record's Scope (the audit report). The designer's IDs (F1–F14) are in brackets.

## Current state (observed 2026-11-12 at `f81185d1`)

Sources: the hands-on audit traces and the designer's code references in the run folder. Code paths are under `frontend/src/` unless the row says otherwise.

| Item | Now | Source |
| --- | --- | --- |
| 1 [F1] | One quick-chip click by a writer shows "Unsaved changes". The next sidebar click asks "Discard unsaved view changes?". A writer cannot save a view, so the mark is a dead end. | Trace S5; `components/systems/openview/components/server-backed-views-workspace.tsx` (badge, guard, dialog) |
| 2 [F3] | One value change takes 4 actions: row, Edit, change, Save changes. Edit pressed on Files, Linked records, or History changes nothing visible. | Trace S3; DA19 |
| 3 [F2] | "Add filter" shows a red error before input. While a condition is incomplete, the list blanks, the quick chips go, Export is disabled, and a chip reads "Status: is Unavailable option". | Trace S5; `incompleteRequestFilter` in the same file |
| 4 [F6] | Header Search is a link to the Platform Search page. It leaves the current page and does not search messages or files. | Trace S11; PD21 |
| 5 [F5] | A direct message takes 5 clicks and a scroll before the first word ("+", open Person, pick, Start conversation). | Trace S6; `components/systems/comms/components/direct-dialog.tsx` |
| 6 [F4] | After create, a "Record created." banner stays and moves the toolbar. The default order is oldest first, so the new record is on the last page. | Trace S5; `backend/app/systems/sandbox/records/query.py:283-284` |
| 7 [F7] | A writer's Tools are Boards, Manage (2 read-only pages), and Platform (4 pages; Import & export refuses with a red error). | Trace "Writer sees pages they cannot use" |
| 8 [F8] | A post with a file needs Save draft first ("Save draft to attach"). The order is hidden. | Trace S9; `components/systems/boards/components/server-backed-board-post-editor.tsx` |
| 9 [F13] | Triggers say "item"; Layout settings say "query", "source order", "server", "paged"; conditions offer "is empty" and "is blank" pairs; widget titles read "Sum of Credit limit"; Help shows Sandbox shortcuts to everyone. | Traces S5, S7, A2, Guest |
| 10 [F9] | Invite lists group names only. To give "Finance, Read" when no group fits takes about 10 steps on 3 tabs. The person's Access tab is read-only. | Traces A3, A4 |
| 11 [F10] | Publish ends in a toast with no next step. The counts line lists 9 kinds, 7 of which the owner did not draw. | Trace A2; `components/systems/sandbox/page.tsx` |
| 12 [F14] | At 390 px the record sheet squeezes the title into a 60 px column (7 lines) beside the actions. | Trace "Mobile 390x844" |
| 13 [F12, F11] | A multi-organization account sees the chooser at each sign-in, though the browser stores the last organization. The landing page tells staff "Create the first administrator outside the browser." and shows "First deployment?" in the hero. Both installer links open the `/setup` guide; the sign-in footer has one too. | Traces Sign in, Landing; `lib/organization-context.ts`; `app/page.tsx:19,67`; `app/login/page.tsx:182-187` |
| 14 | Observed by automation, 4 times: after Escape closes a panel or dialog, the first sidebar click only highlights the item. Not checked with real pointer input. | Trace A4 |

## Requirements

Priority: P0 = the item is not solved without it. Requirements state outcomes; the Product Designer decides layout, controls, and exact words unless a requirement quotes them.

| ID | Item | Pri | Required |
| --- | --- | --- | --- |
| UF-1.1 | 1 | P0 | For a person who is not a view manager (writer, reader, guest, and a department manager outside the department), a filter, quick filter, sort, or layout change marks nothing as unsaved and adds no leave question. |
| UF-1.2 | 1 | P0 | The changed view state stays in the page address, as now: browser Back restores it, Copy link copies it, and Reset changes stays in the view menu. |
| UF-1.3 | 1 | P0 | For a view manager nothing changes: "Unsaved changes", Save view as the primary (DA12), and the leave question stay. |
| UF-1.4 | 1 | P0 | The record edit and record create leave guards stay for every level. |
| UF-2.1 | 2 | P0 | Edit always shows the edit form. Edit pressed on any tab opens the Details tab with the form (DA19). |
| UF-2.2 | 2 | P0 | For a person with write access to the record, Choice list, Checkbox, Date, and Date and time values on Details change in place. The value saves when it is picked, with no Edit and no Save. |
| UF-2.3 | 2 | P0 | After an in-place save, the record header status names the change and offers Undo. Undo writes the previous value back. |
| UF-2.4 | 2 | P0 | All other field types (text, long text, numbers, email, web link, user, relationship) keep Edit and Save. User fields keep Edit because a change notifies the person. |
| UF-2.5 | 2 | P0 | Readers, guests, deleted records, and read-only records show plain values with no in-place control. |
| UF-2.6 | 2 | P0 | When the record changed after it loaded, the in-place save is refused, the field shows the stored value, and a reason shows under the field. Nothing is overwritten. |
| UF-3.1 | 3 | P0 | The record read uses only complete filter conditions. An incomplete condition is not sent; the list, the count, the quick filter, and Export keep the last complete result. |
| UF-3.2 | 3 | P0 | An incomplete condition shows no error and no chip. It shows that it is not applied yet. |
| UF-3.3 | 3 | P0 | When a view manager presses Save view with an incomplete condition, an error shows under that condition and nothing is saved. |
| UF-3.4 | 3 | P0 | A value that is not valid (for example a number out of range) keeps its error under its field, and the list keeps the last good result. |
| UF-4.1 | 4 | P0 | Header Search opens a search panel over the current page, with focus in the search box. The page and its address do not change. |
| UF-4.2 | 4 | P0 | Outside OpenComms, Ctrl K (⌘K on a Mac) opens the same panel. Inside OpenComms, ⌘K stays "Switch conversation". |
| UF-4.3 | 4 | P0 | Results show in groups by kind: records, people, posts, events, messages, files. Each group shows only what the person can read. A result that has no page for this person shows as plain text, as on the Search page now (DR-4.5). |
| UF-4.4 | 4 | P0 | Files: library documents found by file name, only from departments that the person can read. This needs the file kind on `/api/search` (APR-0003); the contract is in the design half. |
| UF-4.5 | 4 | P0 | Messages come only from conversations that the person can read. An administrator gets no messages from other people's direct messages or private channels (D43). |
| UF-4.6 | 4 | P0 | A picked result opens its page. Escape closes the panel and keeps the current page with its state. |
| UF-4.7 | 4 | P0 | An action in the panel opens all results on the existing Search page. Its address keeps working. |
| UF-5.1 | 5 | P0 | "Find a conversation…" and ⌘K "Switch conversation" also list matching people, under the matching conversations. |
| UF-5.2 | 5 | P0 | A picked person opens the existing direct message with that person, or starts one, with focus in the composer. |
| UF-5.3 | 5 | P0 | A person who already has a direct message with the user shows once, as that conversation. |
| UF-5.4 | 5 | P0 | Guests get no people list. People are offered only when the current direct-message rule allows it. The "+" dialog stays for group messages. |
| UF-6.1 | 6 | P0 | After create, "Record created" shows as a status in the header meta line, not as a banner. The toolbar does not move. The status clears at the next action. |
| UF-6.2 | 6 | P0 | When the record sheet closes, the new record is the first row with a "New" tag, if it matches the active filters. The tag stays until the person changes the filters, the sort, or the page, or leaves the page. |
| UF-6.3 | 6 | P0 | When the new record does not match the active filters, it is not added to the list, and the status says that the filters hide it. |
| UF-6.4 | 6 | P0 | The record count stays correct: it does not count the new row twice and does not hide it. |
| UF-7.1 | 7 | P0 | The sidebar has no "Platform" group. Search is in the header (item 4), the notifications page opens from the bell's "See all", and Files is its own sidebar item. |
| UF-7.2 | 7 | P0 | Import & export shows only to administrators, under Files. |
| UF-7.3 | 7 | P0 | Writer, reader, and guest Tools: Boards, Files, Organization, System health. Organization and System health show without a group header. |
| UF-7.4 | 7 | P0 | Department manager Tools: Boards, Access (Groups), Files, Manage (Organization, System health, Audit). |
| UF-7.5 | 7 | P0 | Administrator Tools: Sandbox, Boards, Access, Manage (unchanged), Files (Files, Import & export). |
| UF-7.6 | 7 | P0 | Each existing `/platform?section=…` address opens its page with the current access checks. A stored Start page "Platform" still opens a page at sign-in and is not reset or changed in silence (PD62). Its label in Account settings follows D-4. |
| UF-8.1 | 8 | P0 | In the post editor, Choose file works before the first save once Title and Message have text. Picking a file saves the post as a draft with no separate action, then attaches the file. |
| UF-8.2 | 8 | P0 | While Title or Message is empty, Choose file is disabled and shows the reason. |
| UF-8.3 | 8 | P0 | The automatic save makes a draft only. It never publishes or schedules the post. |
| UF-8.4 | 8 | P0 | The editor shows that the draft is saved. A closed editor leaves the draft in Drafts. |
| UF-8.5 | 8 | P0 | When the save or the upload fails, Title and Message stay, the error shows, and no file is left without a post. |
| UF-9.1 | 9 | P0 | Triggers and the Test reading say "record", not "item" ("When a record is added", event "Record added"), as TRIG-6 requires. Stored event values do not change. |
| UF-9.2 | 9 | P0 | Layout settings use no implementation words ("query", "source order", "server", "paged"). Where they name the default order, they state it: oldest records first. |
| UF-9.3 | 9 | P0 | The condition list offers one pair for "no value" ("is empty", "is not empty"), and a value of only spaces counts as empty. Saved views that use the other pair keep their result and show a distinct label. Stored operators do not change. |
| UF-9.4 | 9 | P0 | Widget titles read as plain names ("Total credit limit", "Customers"), and an empty value says that there is no value yet, not "—". The title still comes from the query (BD16); saved chart names do not change. |
| UF-9.5 | 9 | P0 | Help shows the Sandbox shortcuts only to accounts that can open the Sandbox. |
| UF-10.1 | 10 | P0 | In Invite, each group shows what it gives: department and level, and the module count where modules differ ("Sales · Write"). |
| UF-10.2 | 10 | P0 | The person sheet's Access tab gives administrators "Add access": choose a department, then a level. |
| UF-10.3 | 10 | P0 | When a group gives exactly that access and nothing more, the person joins that group. No group is made. |
| UF-10.4 | 10 | P0 | When no group fits, one action that names the new group makes it with exactly that access and adds the person. Its name never matches a Sandbox derived group name ("<Department> managers", "members", "viewers"; SD-C6, SD-C7). |
| UF-10.5 | 10 | P0 | For a guest, the level list offers Read only. The server cap stays. |
| UF-10.6 | 10 | P0 | Department managers, writers, readers, and guests get no "Add access". The server still refuses group and access changes from them. |
| UF-10.7 | 10 | P0 | After a partial failure, the made group stays visible in Groups, and a retry uses it. No second group is made. |
| UF-11.1 | 11 | P0 | After a publish, the dialog shows a "Published" state with one link per newly published module to its records, and a way back to Build. |
| UF-11.2 | 11 | P0 | The review counts line lists only what the owner drew: departments, modules, fields, and links between modules (the word follows D-2), and triggers when the publish has any. |
| UF-11.3 | 11 | P0 | Under each new department, one line names what comes with it. The full list of setup items stays before the password (SD6). |
| UF-11.4 | 11 | P0 | The password stays required at each publish. "Save triggers" and the Review & Publish disabled reason stay (D1). |
| UF-12.1 | 12 | P0 | On a phone (390 px), the record sheet header shows the actions (Previous, Next, Edit, More record actions, Close) on their own row, and the title below them at the full sheet width, then the meta line. |
| UF-12.2 | 12 | P0 | Every DA18 header element and its accessible name stays. Wider screens do not change. |
| UF-13.1 | 13 | P0 | After sign-in, an account with several organizations opens the organization that this browser opened last, with no chooser, when the account is still a member of it. |
| UF-13.2 | 13 | P0 | The chooser shows when nothing is stored, when the stored organization is not a membership of the account, or when the server refuses the open. After a refusal, it shows the reason. |
| UF-13.3 | 13 | P0 | The automatic open uses the same server check as a pick in the chooser. The server never chooses an organization. |
| UF-13.4 | 13 | P0 | The landing page gives staff no installer instructions. Its setup step says that staff get in through an invitation from their administrator. "First deployment?" leaves the landing hero and stays in the sign-in page footer, which keeps opening the `/setup` guide. The `/setup` guide does not change. |
| UF-14.1 | 14 | P0, conditional | Reproduce first with real pointer input (not a scripted DOM click) and by hand: close a panel or dialog with Escape, then click a sidebar item once. If it navigates, change nothing and close the item. If it does not navigate, fix it so the first click navigates, in its own commit with a failing-first test. The result goes in the run record, not in this spec. |

## Changed decisions

Each change below is approved by APR-0003: Human Owner, 2026-11-12, "alright, I want you to do all of them". No other decision changes.

| Decision | Source | Old rule | New rule | Approval |
| --- | --- | --- | --- | --- |
| OD5 | `openview-relayout.md:159`, umbrella line `:109`; restated in `openview-department-pages.md:71` | An "Unsaved changes" chip joins the meta line when the view changed, for everyone. | The chip shows only to view managers (UF-1.1, UF-1.3). Save view and DA12 stay for them. | APR-0003, 2026-11-12 |
| Guard line | `openview-relayout.md:56`; `openview-department-pages.md:27` | "The unsaved-changes guards … behave as they do now." | The view leave guard shows only to view managers. The record edit and create guards stay as they are (UF-1.4). | APR-0003, 2026-11-12 |
| PD21 | `profile-sidebar-relayout.md:202` (header text `:135`) | Search stays a link that opens Platform search. | Search opens a panel over the page; the Search page stays for "all results" (UF-4.1, UF-4.7). | APR-0003, 2026-11-12 |
| BD16 | `openview-dashboard.md:88` | A widget title comes from its query in the query's words ("Equipment by Category", "Number of Quotes"). | Titles still come from the query but read as plain names ("Quotes", "Total credit limit") (UF-9.4). Saved chart names and the rule stay. | APR-0003, 2026-11-12 |

Not changed: DA19 (UF-2.1 makes the build match it) and TRIG-6 (its requirement already says "record"; only the design text of `sandbox-ux-redesign.md:391,411` says "item" and follows UF-9.1).

## Preserved behavior

- Access: access stays group-based; only administrators make groups and set their access; a guest is capped at Read; a module the person cannot read stays hidden; a server refusal stays the source of truth.
- D43: an administrator cannot read other people's direct messages or private channels, in Search too.
- Saved views stay shared, and only view managers save them (DA12, DA13).
- The publish password, the administrator-only Sandbox, D1 "Save triggers", and SD6.
- Owner decisions: "module"; "Announcements"; "Gantt"; Profile is view-only; "Make a copy now"; one dashboard per department.
- Addresses: `?section=`, `?module=`, `?view=`, `?record=`, `/platform?section=…`, and the view state in the address.
- Stored values: Start page values, filter operators, trigger event values, and widget queries.

## Not in scope

- Moving the phone quick-filter chips into the Filters sheet, and the other phone toolbar rows of F14 (rules 1–4).
- A new endpoint that creates organizations (F11 rule 2). Changes to the `/setup` installer guide.
- The import flow.
- The three Sandbox save states (D1 keeps "Save triggers").
- The manager half of item 1: DA12 keeps Save view as the primary after a change.
- Any backend or API change other than file search on `/api/search`.
- Any reversed decision other than OD5 with the guard line, PD21, and BD16.
- Any access change other than "Add access" for administrators.
- Proposals in `solutions.md` that the run record's Scope does not name: the F13 rows "No module overrides", the Choices placeholder, "Create Contacts record", and the Start page labels; F9 rule 3 (guest words in the Groups table); "Add linked record" in the post editor (item 8 covers files). The parent adds them only if the audit report named them under APR-0003.

## Decisions needed

| ID | Question | Why it is not a requirement here | Options |
| --- | --- | --- | --- |
| D-1 | Change the DA21 empty-organization words ("Nothing published yet" → "No departments yet" with "Set up your first department")? | It reverses DA21, which APR-0003 excludes. | (a) Keep DA21 (default; nothing removed). (b) Change the words; removes "Open Sandbox" as the label. |
| D-2 | Use "link" or "relationship" for a connection between modules in Build, Review, and Test? | `docs/architecture/21-glossary.md:261` prefers "relationship"; Test already says "links". A change touches the glossary and the area of G10 and G2, which APR-0003 excludes. UF-11.2 uses the chosen word. | (a) Keep each screen's current word (default; the drift stays). (b) "link" everywhere and update the glossary; removes "relationship" from screens. |
| D-3 | Conditional: if `GET /sandbox/bindings` does not give the new module IDs right after publish, UF-11.1 needs a backend change. | Backend changes other than file search are excluded. | Resolved 2026-11-12 (Software Architect): the publish writes the module bindings in its own transaction (`publications/executor.py:240,305-306`), so the read gives the new module IDs right after a successful publish. No backend change. |
| D-4 | Label of a stored Start page "Platform" after item 7 removes the Platform group. | Under PD62 a section that the sidebar no longer shows reads "<Section> (not available)" for everyone. A new label changes PD62, and the Start page labels are not in the run record's Scope. | (a) Keep PD62: "Platform (not available)" shows; the stored value still opens Search at sign-in (default; the label reads as broken). (b) Show it as "Search" and let people choose it; changes PD62. |

## Acceptance criteria

Check each criterion on the live development stack with the Harbor testing accounts at 1440×900, unless the row says otherwise. Item 11 uses a fresh organization.

| ID | Req | Account | Given | When | Then | Must not break |
| --- | --- | --- | --- | --- | --- | --- |
| UF-C1.1 | UF-1.1 | Writer, reader, guest | Sales › Contacts, default view | Click the quick chip "Former", then Sales › Customers in the sidebar | The list shows Former records with no "Unsaved changes" mark; Customers opens with no question. | No view write request is sent. |
| UF-C1.2 | UF-1.2 | Writer | UF-C1.1 done | Press browser Back | Contacts opens with "Former" applied. | Copy link and Reset changes stay in the view menu. |
| UF-C1.3 | UF-1.3 | Department manager in Sales; administrator | Sales › Contacts | Click "Former", then a sidebar item | "Unsaved changes" and Save view (primary) show; the leave question shows. | DA12. |
| UF-C1.4 | UF-1.1 | Department manager | Setup: the account gets Read or Write on one module outside Sales (or a Sales module with a module grant below Manage); that module open | Change a filter, then click a sidebar item | No mark and no question, as for a writer. | — |
| UF-C1.5 | UF-1.4 | Writer | A record in Edit with a changed value | Click a sidebar item | The open Edit form is modal: the click does not reach the sidebar, the address does not change, the typed value stays, and no question shows (behavior as before this pass). | Record create dialog the same. |
| UF-C2.1 | UF-2.1 | Writer | A record open on the Files tab | Click Edit | The Details tab opens with the form, Save, and Cancel. | Same from Linked records and History. |
| UF-C2.2 | UF-2.2, UF-2.3 | Writer | A Contacts record, Status "Active", on Details | Pick "Former" in Status | One update request is sent; the header status names the change with Undo; after reload Status is "Former". | Edit was not pressed. |
| UF-C2.3 | UF-2.3 | Writer | UF-C2.2 done | Press Undo | After reload Status is "Active". | — |
| UF-C2.4 | UF-2.4 | Writer | Same record | Click a text field and a user field | No in-place control; Edit is needed. | — |
| UF-C2.5 | UF-2.5 | Reader, guest | Same record | Click the Status value | Plain value; no control; no update request. | No Edit for them, as now. |
| UF-C2.6 | UF-2.6 | Two writers | Both open the record | A changes Status; then B picks a value in place | B's save is refused; B sees A's value and a reason under the field. | A's value stays. |
| UF-C3.1 | UF-3.1, UF-3.2 | Writer | Contacts, all records listed | Filters › Add filter; choose nothing | The rows, the count, the quick chips, and Export stay; no red error, no banner, no chip; the row reads as not applied. | No record read contains the incomplete condition. |
| UF-C3.2 | UF-3.1 | Writer | UF-C3.1 | Complete "Status is Former" | The list shows the Former records; the chip reads "Status: is Former". | Chip words (DA16). |
| UF-C3.3 | UF-3.3 | Department manager | Contacts with one incomplete condition | Press Save view | An error shows under that condition; no view write request is sent. | — |
| UF-C3.4 | UF-3.4 | Writer | A number condition | Type a number out of the safe range | The error shows under that field; the list keeps the last result. | — |
| UF-C4.1 | UF-4.1, UF-4.3, UF-4.6 | Writer | Contacts with "Former" applied | Click Search, type "Harbor", press Escape | The panel opens with focus in the box; the address does not change; results show in groups; after Escape, Contacts shows with "Former". | — |
| UF-C4.2 | UF-4.4 | Writer, guest | A Sales library document and a document in a department the account cannot read | Search for both file names | Only the readable document is listed under Files. | Files access checks. |
| UF-C4.3 | UF-4.5 | Administrator | A word that is only in a direct message between two other people | Search for it | Messages does not list it. | D43. |
| UF-C4.4 | UF-4.2 | Writer | OpenComms, then Contacts | Press ⌘K in each | OpenComms: "Switch conversation". Contacts: the search panel. | — |
| UF-C4.5 | UF-4.6, UF-4.7 | Writer | Panel with results | Pick a record result; then open all results | The record opens; all results open on the Search page with the query. | Old Search addresses work. |
| UF-C5.1 | UF-5.1, UF-5.2 | Writer | OpenComms; no direct message with a colleague | In "Find a conversation…" type the colleague's name and pick them | The person row is inside the viewport at 1440x900 and at 390x844 without a scroll (DR-5.7); the direct message opens with focus in the composer; 3 actions from OpenComms. | One conversation is made. |
| UF-C5.2 | UF-5.3 | Writer | A direct message with that colleague exists | Type the name | The colleague shows once; picking opens that conversation. | No new conversation. |
| UF-C5.3 | UF-5.4 | Guest | OpenComms | Type a colleague's name | No people list. | Guests cannot start a conversation. |
| UF-C5.4 | UF-5.4 | Writer | OpenComms | "+" › Group message | A group message starts as now. | — |
| UF-C6.1 | UF-6.1, UF-6.2 | Writer | Contacts, default view (oldest first) | Create a record; close the sheet | The record is the first row with "New"; "Record created" is in the meta line; no banner; the toolbar did not move. | Server order unchanged. |
| UF-C6.2 | UF-6.3 | Writer | Filter "Status is Former" | Create a record with Status "Active" | The record is not in the list; the status says the filters hide it. | — |
| UF-C6.3 | UF-6.2, UF-6.4 | Writer | UF-C6.1 | Change the sort | "New" goes; the record shows in its sorted place; the count shows each record once. | — |
| UF-C7.1 | UF-7.1, UF-7.3 | Writer, reader, guest | Signed in | Read the sidebar Tools | Boards, Files, Organization, System health; no Platform, no Import & export. | Departments and OpenComms unchanged. |
| UF-C7.2 | UF-7.4 | Department manager | Signed in | Read the sidebar Tools | Boards, Access (Groups), Files, Manage (Organization, System health, Audit). | — |
| UF-C7.3 | UF-7.2, UF-7.5 | Administrator | Signed in | Read the sidebar Tools | Sandbox, Boards, Access, Manage as now, Files (Files, Import & export). | — |
| UF-C7.4 | UF-7.6 | Writer | Signed in | Open `/platform?section=import-export` and the notifications page from the bell's "See all" | Import shows the current administrator refusal; notifications open. | Server refusal. |
| UF-C7.5 | UF-7.6 | Writer | Start page "Platform" stored | Sign in; open Account settings › Appearance | A page opens at sign-in; the Start page still shows the stored choice. | The stored value is unchanged. |
| UF-C8.1 | UF-8.1, UF-8.4 | Writer | New post with Title and Message | Choose file; pick a PDF; Publish | "Draft saved" shows; the file is listed; the post publishes with the file. | No "Save draft to attach". |
| UF-C8.2 | UF-8.2 | Writer | New post, Title empty | Look at Choose file | Disabled, with the reason. | — |
| UF-C8.3 | UF-8.3, UF-8.4 | Writer, reader | Writer picked a file, then closed the editor | Reader opens Sales › Announcements | The post is in the writer's Drafts and not visible to the reader. | Readers cannot post. |
| UF-C8.4 | UF-8.5 | Writer | New post with text | Pick a file over the size limit | The error shows; Title and Message stay; no file is attached. | — |
| UF-C9.1 | UF-9.1 | Administrator | Sandbox › Triggers and Test | Add a trigger; open the Test reading | "When a record is added", "Record added"; no "item" on either tab. | Saved triggers keep their events. |
| UF-C9.2 | UF-9.2 | Writer | Contacts | Open Layout settings | None of "query", "source order", "server", "paged". | Sort and group still work. |
| UF-C9.3 | UF-9.3 | Writer; view manager | A text condition; a saved view that uses the other "no value" pair | Open the condition list; open the saved view | One "no value" pair is offered; the saved view lists the same records as before, with a distinct label. | Stored operator unchanged. |
| UF-C9.4 | UF-9.4 | Writer | Sales dashboard | Read the widgets | No "Sum of" or "Number of" titles; an empty value says there is no value yet. | Values and saved chart names unchanged. |
| UF-C9.5 | UF-9.5 | Writer, guest; administrator | Signed in | Open Help › Keyboard shortcuts | No Sandbox shortcuts for writer and guest; present for the administrator. | — |
| UF-C10.1 | UF-10.1 | Administrator | Access › People | Open Invite | Each group shows department and level. | Invitation still sends group IDs only. |
| UF-C10.2 | UF-10.2, UF-10.3 | Administrator | A group gives exactly Finance Read; the person has no Finance access | Access tab › Add access › Finance › Read | The person joins that group; no group is made; the tab lists Finance Read from that group. | — |
| UF-C10.3 | UF-10.4 | Administrator | No group gives exactly Finance Read | Same steps, then the action that names the new group | A group with exactly Finance Read exists with the person in it; its name is not "Finance managers", "members", or "viewers". | A later Sandbox setup publish for Finance is not refused by the group name. |
| UF-C10.4 | UF-10.5 | Administrator | A guest's Access tab | Add access › a department | Only Read is offered. | Guest cap on the server. |
| UF-C10.5 | UF-10.6 | Department manager | Access | Open Access › People (or `/access?view=people`) | Access opens on Groups with "People is not available to your account."; no person sheet and no "Add access" are reachable. | Server refuses group changes. |
| UF-C10.6 | UF-10.7 | Administrator | The add step fails after the group is made | Retry | The person joins the made group; Groups shows one such group. | — |
| UF-C11.1 | UF-11.2, UF-11.3 | Administrator (fresh organization) | A draft with 1 department, 1 module, 2 fields | Open Review & Publish | The counts line lists only departments, modules, fields (and links, if any); a "Comes with" line under the department; the full setup list before the password. | SD6. |
| UF-C11.2 | UF-11.1 | Administrator (fresh organization) | UF-C11.1 | Enter the password; publish; click the module link | "Published" shows a link for the module; the module's records open in one action. | — |
| UF-C11.3 | UF-11.4 | Administrator | Review & Publish | Publish with a wrong password | Refused; nothing is published. | Password at every publish. |
| UF-C11.4 | UF-11.1 | Administrator | A draft with only field changes | Publish | "Published" shows with no module link and a way back to Build. | — |
| UF-C12.1 | UF-12.1, UF-12.2 | Administrator, 390×844 | Contacts | Open the record "UX audit test contact" | The actions are on one row above the title; the title uses the full width (at most 2 lines); each target is at least 44 px; no sideways scroll. | Every DA18 element. |
| UF-C12.2 | UF-12.2 | Administrator, 1440×900 | Same | Open the same record | The header is as now. | — |
| UF-C13.1 | UF-13.1 | Writer (several organizations) | Harbor opened last in this browser | Sign out; sign in | Harbor opens with no chooser. | — |
| UF-C13.2 | UF-13.2 | A second account in the same browser, not a Harbor member | Harbor stored by the first account | Sign in | The chooser shows. | No open of another account's organization. |
| UF-C13.3 | UF-13.2, UF-13.3 | Account without two-step | The stored organization requires two-step | Sign in | The chooser shows with the reason. | Two-step and address checks. |
| UF-C13.4 | UF-13.4 | Signed out | — | Open `/`, then `/login` | `/` has no installer instruction and no "First deployment?" in the hero; the `/login` footer keeps "First deployment?", and it opens `/setup`. | The `/setup` guide is unchanged. |
| UF-C14.1 | UF-14.1 | Administrator | The defect reproduced with real pointer input | Close the person panel with Escape; click Dashboard once | The page navigates on the first click. | Focus returns to the opener after Escape. |
| UF-C14.2 | UF-14.1 | — | The defect did not reproduce | — | No code change is made for item 14. | — |

## Design rules and states (Product Designer)

`ui-ux-pro-max` decided the structure, flow, and states below. `impeccable` decides only the visual treatment inside them, and records the new patterns in `DESIGN.md` in a later request (see "Design-system items"). Code paths are under `frontend/src/` unless the row says otherwise; line numbers are at `f81185d1`. Comps of the three new structures are in `.impeccable/mocks/friction/` (`search.html` with `?state=empty|none|fail`; `add-access.html` with `?state=fits|have|guest|partial`; `published.html` with `?state=nolinks|review`). Each is laid out for 1440 and for 390 (not rendered in this task), and `?theme=light` shows Slate light. They reuse the Access comp shell (`.impeccable/mocks/access/access.css`) and take tokens from the app build.

**Rules for every item (DS-6).**

- G1 Motion belongs only to the element the person acted on. A value saved in place, a pinned "New" row, a status in the meta line, a People group, and the Published state appear at once, with no slide or fade of their own. Shared dialogs and sheets keep their current open and close behavior. Page navigation is never animated. Reduced motion stays honored.
- G2 No cover, curtain, or "checking" screen. A wait shows the current frame and keeps the last good content; a layout-matched skeleton shows only after a 300 ms delay, as `components/ui/loading-region.tsx` does.
- G3 An explanation sits directly under the headline or control it explains. No help paragraphs, tours, or tooltips that explain.
- G4 From 1280 px, still pages keep filling the window, with panes that scroll alone (DA4, PD66). No item here adds a page-level scroll.
- G5 Targets are 32 px from 1280 px and at least 44 px below it (EXIT-A5). Every new control has a visible label or an accessible name, a visible focus ring, and keyboard access.
- G6 The server stays the source of truth for access. The client hides a control only where the server refuses it, and it shows the server's refusal when one comes.

### Item 1 [F1]: no "Unsaved changes" for people who cannot save a view

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-1.1 | One test decides the mark and the questions: `canManageViews` (`components/systems/openview/components/server-backed-views-workspace.tsx:592`, from `canManageOpenView`). While the identity loads, the value is false; no draft exists before the page loads. | UF-1.1, UF-1.3 | `domain/manage-access.ts:36-44` |
| DR-1.2 | The "Unsaved changes" badge shows only when the view changed and the person is a view manager (`dirty && canManageViews`, badge at `:2756`). | UF-1.1, UF-1.3; UF-C1.1, UF-C1.3, UF-C1.4 | `components/ui/badge.tsx` |
| DR-1.3 | For a person who is not a view manager, the three places that ask "Discard unsaved view changes?" continue at once and drop the page draft: the sidebar and link guard (`navigationGuard`, `:1591-1605`), a pick in the view picker (`selectSavedView`, `:1481`), and `confirmDraftDiscard` (`:1606-1616`). No view write request is sent. | UF-1.1; UF-C1.1, UF-C1.4 | the same functions |
| DR-1.4 | The view state stays in the address exactly as now (`&changes=…`, `temporaryChanges` at `:699`). Browser Back restores it. Copy link, Reset changes, and Archived views stay in the view menu (DA13). | UF-1.2; UF-C1.2 | `domain/temporary-view.ts` |
| DR-1.5 | The header of a person who is not a view manager does not change after a filter: a writer keeps New record as the primary; a reader and a guest keep no primary. | UF-1.1 | `PageHeader` at `:2750` |
| DR-1.6 | A view manager sees no change: the badge, Save view as the primary with "Save as new view" (DA12), and the leave question stay. | UF-1.3; UF-C1.3 | DA12, DA13 |
| DR-1.7 | The record edit guard and the record create guard do not change for any level. The guard is the modal form itself: while Edit or New record is open, a click outside does not reach the page, so nothing is lost and no separate question shows (screen review 2026-11-12). | UF-1.4; UF-C1.5 | `record-details-controls.tsx`, `record-create-dialog.tsx` |

| State | Not a view manager (writer, reader, guest, manager outside the module) | View manager |
| --- | --- | --- |
| Rest | Meta line "Sales · 601 records". | Same. |
| After a filter, quick chip, sort, or layout change | Meta line "Sales · 83 records", no badge; the address holds the change. | Meta line with the "Unsaved changes" badge; Save view is the primary. |
| In progress (records reading) | "Refreshing records…" in the meta line (DA14). | Same. |
| Leave (sidebar, link, view picker) | Goes at once; Back restores the filter. | "Discard unsaved view changes?" as now. |
| Failure (records read) | The current read error, as now. | Same. |
| Empty (no records match) | The table's current empty state, as now. | Same. |
| No permission (no readable module) | DA21 no-access state, as now. | — |
| Phone (390) | Same rules; the DA22 header row is unchanged and has no badge. | Badge and Save view as now. |

### Item 2 [F3]: change a value in place; Edit always opens Details

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-2.1 | Edit, pressed on any tab, first selects the Details tab, then opens the form with Save and Cancel pinned at the bottom (DA19). Focus moves to the first field of the form. | UF-2.1; UF-C2.1 | `components/systems/shared/components/record-sheet.tsx` tabs; `startEditing` in `components/systems/openview/components/record-details-controls.tsx` |
| DR-2.2 | Exactly four field types change in place on Details: Choice list (`select`), Checkbox (`boolean`), Date (`date`), and Date and time (`datetime`). The control sits where the value sits, in the label-left row. It is the same control the form uses (`FieldControl`, `record-form-fields.tsx:96-181`): the native select, the checkbox, and the date and date-time inputs. | UF-2.2; UF-C2.2 | `components/systems/openview/components/record-form-fields.tsx` |
| DR-2.3 | When the value commits: a Choice list on pick; a Checkbox on toggle; a Date or Date and time when the input loses focus or on Enter, only when the value is complete and different. Escape puts back the stored value and sends nothing; a second Escape closes the sheet. A date that is not complete, or a cleared required value, goes back to the stored value when the control loses focus and sends nothing. A required Choice list has no "None" option in place; an optional one keeps "None". A stored option that no longer exists shows "Unavailable option" (`domain/record-display.ts`). | UF-2.2 | native `change` and `blur` of the `FieldControl` controls |
| DR-2.4 | (B-1) A commit sends one `PATCH /api/records/{id}` whose `data` holds every active value of the complete stored record, as the Edit save does, with only that field changed. A PATCH replaces every active value (`backend/app/systems/sandbox/records/router.py:155-158`, `mutation_validation.py:191-204`); its meaning does not change. `If-Match` is the record's current `updated_at` (DR-2.13). While it saves, that control is disabled with `aria-busy`, and the meta line reads "Saving…". | UF-2.2, UF-2.6 | the Edit save's value set and record PATCH adapter in `record-details-controls.tsx` |
| DR-2.5 | Success: the meta line of the record header (DA18) gets a status, `role="status"`: "Status changed to Former." ("Status cleared." for None; "Paid turned on." or "Paid turned off." for a Checkbox) with an Undo button: a ghost button in the action text color, inline after the words, 32 px from 1280 px and 44 px below. The status sits on its own line under the meta line. The "Updated" date in the same line refreshes. The list row behind the sheet shows the new value. | UF-2.3; UF-C2.2 | meta line at `server-backed-views-workspace.tsx:3430-3448` |
| DR-2.6 | Undo stays offered until the next in-place change (also one that fails), Edit, a tab change, Previous or Next, or closing the sheet. (Screen review) The status words go with the Undo: when Undo ends for any of these reasons, the status line clears, so no "<Field> changed to …" stays beside a later state. A failure message stays until the next action. It has no timer, so nobody must act within a set time (WCAG 2.2.1). Undo sends one PATCH built as in DR-2.4, with the previous value of that field and the `updated_at` of the last response (DR-2.13). Success: "Status changed back to Active.", with no Undo. The undo is a second change: it shows in History and runs triggers as any change does. | UF-2.3; UF-C2.3 | meta-line status of DR-2.5; record PATCH adapter |
| DR-2.7 | Write conflict (412): nothing is overwritten. The sheet reads the record again; the control shows the stored value; under the field, `aria-describedby`, in the destructive text style: "Someone changed this record. It shows their value now." The meta line "Updated" date refreshes. An Undo that meets a 412 shows "Not undone. Someone changed this record after you." in the meta line, and the field shows the stored value. | UF-2.6; UF-C2.6 | field error pattern of `record-form-fields.tsx`; `components/ui/error-reference.tsx` |
| DR-2.8 | Any other failure (network, 5xx, refused): the control shows the stored value; under the field: "Not saved. Try again." with the error reference. A 422 for this field shows the server's field message under it. (B-1) A 422 that names another field shows the server's message in the meta line, because that field has no control on screen. Nothing else changes. | UF-2.6 | `components/ui/error-reference.tsx` |
| DR-2.9 | Text, long text, numbers, email, web link, user, and relationship values stay plain on Details and change only through Edit and Save changes. User fields keep Edit because a change notifies the person. | UF-2.4; UF-C2.4 | `RecordFormFields` Edit form (`record-form-fields.tsx:183`) |
| DR-2.10 | No in-place control and no hover change for readers, guests, a deleted record, or a record marked Read-only: the value is plain text (the current Details read view). | UF-2.5; UF-C2.5 | Details read view in `record-details-controls.tsx` |
| DR-2.11 | While the Edit form is open, in-place controls do not show; the form owns every field. | UF-2.2 | `editing` state of `record-details-controls.tsx:130-157` |
| DR-2.12 | Items 2 and 12 apply to the OpenView record sheet only. The Boards card sheet (`components/systems/boards/components/board-record-card-sheet.tsx`) keeps its own header and form. | UF-2.2, UF-12.1 | `board-record-card-sheet.tsx` unchanged |
| DR-2.13 | (B-1) In-place controls are disabled while the record's fields are incomplete, with the same guard as Edit: the alert "Load all fields before editing so existing values are kept." and its "Load more fields for editing" button (`record-details-controls.tsx:380-398`; Edit's `fieldsHasMore` check at `:411`). Commits on one record run one at a time: while one saves, the other in-place controls and Edit wait. (Screen review) They wait with `aria-disabled`, so focus stays where it is; only the saving control shows the busy look at once, and the others take the disabled look only when the save runs longer than 300 ms (G2), so a normal save does not flash the whole sheet. Each next PATCH, the Undo, and the Edit form use the `updated_at` of the last response, so a second commit is not refused with a false conflict. | UF-2.2, UF-2.6; UF-C2.2, UF-C2.6 | `fieldsHasMore` and "Load more fields for editing" in `record-details-controls.tsx` |

| State | Writer | Reader, guest |
| --- | --- | --- |
| Rest | Four field types show their control, label-left; others plain. | Plain values. |
| Fields incomplete | (B-1) In-place controls and Edit disabled; "Load all fields before editing so existing values are kept." with "Load more fields for editing". | Plain values. |
| In progress | That control `aria-busy`; the other in-place controls and Edit disabled until the response; meta line "Saving…". | — |
| Success | Meta line "Status changed to Former." + Undo. | — |
| Failure | Stored value back; "Not saved. Try again." under the field; a 422 on another field: the server message in the meta line. | — |
| Conflict | Stored value back; "Someone changed this record. It shows their value now." under the field. | — |
| Deleted or Read-only record | Plain values; the Deleted or Read-only badge, as now. | Same. |
| Phone (390) | Controls 44 px; the native select and date pickers; the status wraps under the meta line. | Plain values. |

### Item 3 [F2]: the list reads only complete conditions

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-3.1 | The record read, the count, the quick-filter counts, and Export use only applied conditions: a condition is applied when `isFilterReady` is true and it has no unsafe integer. Incomplete conditions stay in the draft and in the address, but they are not sent (`incompleteRequestFilter`, `server-backed-views-workspace.tsx:820-835`, `:869-873`). | UF-3.1; UF-C3.1, UF-C3.2 | `domain/server-view-draft.ts` |
| DR-3.2 | The list-level warning "Complete the condition in Filters before loading matching records." (`:3184-3189`) is removed. The table or cards, the quick filter, and Export stay; Export is no longer disabled by an incomplete condition (`:2605`). | UF-3.1; UF-C3.1 | `ExportDialog` (`export-dialog.tsx`) |
| DR-3.3 | Add filter adds a row and moves focus to its Field select. The new row starts with the module's first field chosen and "is" as the condition (as before this pass), so its line reads "Not applied yet: choose a value."; "choose a field" shows only when the field is cleared. No error text shows before input. | UF-3.2; UF-C3.1 | `components/systems/openview/components/saved-view-filter-controls.tsx` |
| DR-3.4 | An incomplete row shows one muted line under it, `col-span-full`: "Not applied yet: choose a field." or "Not applied yet: choose a value." It gets no chip; the chip row shows only applied conditions, so "Status: is Unavailable option" never shows for an empty value. A condition on the quick-filter field shows as the selected quick chip, not as a condition chip (DA17). The line "Complete this condition or remove it before saving." (`:460-464`) is removed. | UF-3.2; UF-C3.1 | chip row of DA16 |
| DR-3.5 | A view manager who presses Save view or Save as new view with an incomplete row: no request is sent; the Filters popover opens (the bottom sheet below 768 px); under that row, in the destructive style: "Choose a value or remove this condition."; focus moves to the missing control. | UF-3.3; UF-C3.3 | DA16 popover |
| DR-3.6 | A number that is not safe keeps its current error under its field (`UNSAFE_INTEGER_FILTER_ERROR`, `:47`, `:437-443`). That condition is not applied, so the list keeps the last good result. | UF-3.4; UF-C3.4 | the same constant |
| DR-3.7 | "This saved filter refers to an unavailable field. Remove it before saving." stays as now. | — | `saved-view-filter-controls.tsx:465-470` |

| State | All levels |
| --- | --- |
| Rest | Popover with Match filters, the conditions, Add filter, Deleted (DA16). |
| Incomplete row | "Not applied yet: …" under it; list, count, chips, and Export unchanged. |
| In progress | "Refreshing records…" in the meta line (DA14). |
| Success | Chip "Status: is Former"; the list shows the matches. |
| Failure | Unsafe number: the error under the field; manager Save with an incomplete row: the error under the row. |
| Empty | No match: the table's current empty state. |
| No permission | Not a view manager: Save view does not show (DA12), so DR-3.5 never applies. |
| Phone (390) | The same rows in the Filters bottom sheet; the "Not applied yet" line wraps under the row. |

### Item 4 [F6]: a search panel over the page (new structure; comp `search.html`)

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-4.1 | Header Search (`components/app-shell.tsx:952`) becomes a button that opens the search panel. It keeps the visible word "Search" and the accessible name "Search workspace", with `aria-haspopup="dialog"`. It no longer links to `/platform`. Outside `/comms`, Ctrl K (⌘K on a Mac) opens the same panel when "Use shortcuts" is on (the preference check of `quick-switcher.tsx:35-67`). Inside `/comms`, ⌘K stays "Switch conversation" (`components/systems/comms/components/quick-switcher.tsx`). | UF-4.1, UF-4.2; UF-C4.1, UF-C4.4 | `components/ui/dialog.tsx` |
| DR-4.2 | The panel is a dialog with the accessible name "Search workspace". From 768 px it is 640 px wide and anchored 96 px below the top of the window; its result area scrolls alone and the whole panel is at most the window height minus 160 px. Below 768 px it fills the screen. The page and its address do not change while it is open. The panel code loads on first open, so no page's cold load grows. (PR3 screen review) The field row shows its focus as a 2 px line in the focus colour along the bottom of the row, drawn inside the panel, so it is never cut by the panel edge; the field itself has no outline. The header Search button shows no "⌘K" hint: Help lists the shortcut. | UF-4.1 | `quick-switcher.tsx` dialog pattern; `components/ui/search-field.tsx` |
| DR-4.3 | Layout, in reading order: the search field ("Search workspace", focus on open) with Close at its right; under the field, one muted line that names the scope, "Records · People · Posts · Events · Messages · Files"; then the result groups; then the footer link "Show all results for "harbor"". (PR3 screen review) The quotes around the typed text are typographic: “harbor”. | UF-4.3, UF-4.7 | new structure (comp `search.html`); `components/ui/search-field.tsx` |
| DR-4.4 | Groups in this fixed order: Records, People, Posts, Events, Messages, Files. Each group has a heading with its total ("Records · 12", "1,000+" when the total is capped) and at most 5 rows. A group with no match is hidden. Row: the title on line 1, with the matched words marked only in message excerpts (the only kind whose response gives match positions); the context on line 2 (records: module · department; people: job title; posts and events: board; messages: conversation · author · date with the match excerpt; files: department). | UF-4.3; UF-C4.1 | row text of `components/systems/platform/components/search.tsx` |
| DR-4.5 | Reads: the query settles 250 ms after the last key (as `search.tsx:44-46`). Six reads run at once, each with `limit=5`: `GET /api/search` with `kind=record`, `person`, `post`, `event`, `file`, and `GET /api/comms/search?q=`. Each group shows exactly what its endpoint returns. A row with `can_open: false` shows as plain text, as on the Search page. (N-4) A group lists what the person can read; a result with no page for this person (`can_open: false`, such as person rows for non-administrators, `backend/app/systems/platform/search/query.py:254`) is plain text, as on the Search page now. (Rate note) A query sends its six reads only after the 250 ms debounce settles, and a new query cancels the previous query's reads (`AbortSignal`), so typing does not multiply reads against the proposed search limit of 60 requests a minute (`docs/plans/api-rate-limits.md`). | UF-4.3, UF-4.4, UF-4.5; UF-C4.2, UF-C4.3 | `platformSearchOptions` in `components/systems/platform/adapters/platform-search-api.ts` (its fixed `limit: 10` becomes a parameter); `search()` in `components/systems/comms/adapters/search-api.ts`, called with a Comms context of the verified account and organization; it does not need the live Comms runtime, which mounts only under `/comms` |
| DR-4.6 | Keyboard: focus stays in the field. Arrow Down and Arrow Up move the active row across groups (combobox with `aria-activedescendant`); Enter opens it; Tab reaches "Show all results" and Close; Escape closes the panel and focus returns to the Search button. (PR3 screen review) A row that cannot open is not an option, so the arrows skip it. Pointer hover moves the active row, so only one row is ever highlighted. Ctrl K (⌘K) also opens the panel on the Search page. | UF-4.6; UF-C4.1 | `finalFocus` pattern of `quick-switcher.tsx:102` |
| DR-4.7 | A picked row closes the panel, then navigates through the workspace navigation guard, so an open record edit still asks first. Destinations: records, people, posts, and events use the typed destinations of `search.tsx`; a message opens `/comms?conversation=<id>&message=<id>`; a file opens `/platform?section=files&department=<department_id>&search=<file name>`. (N-3) The Files page reads `search` from the address once and fills its search box with it, as it reads `department` now (`components/systems/platform/components/files.tsx:135`, search state at `:320-322`), so the picked file is in view. | UF-4.6; UF-C4.5 | `GuardedWorkspaceLink`; link format of `components/systems/platform/helpers/notification-kind.ts:26` |
| DR-4.8 | "Show all results for "harbor"" opens `/platform?section=search&q=harbor`. The Search page seeds its field from `q` once, and it gains Messages and Files cards in the same card grid and card pattern as its four cards. Old Search addresses without `q` open as now. (PR3 screen review) The page cards use the panel's words: "<Kind> could not be searched." with "Try again" (and the reference when there is one). The Messages card holds its place from the first frame, with its loading state, so the grid never shifts. The field writes `q` back to the address with replace, after the 250 ms settle, so a reload shows the words the person sees; the Files library does the same for `search`. A card count reads "1 result" in the singular. | UF-4.7; UF-C4.5 | `components/systems/platform/components/search.tsx` |
| DR-4.9 | Each group fails alone: under its heading, "Messages could not be searched." with a Try again button and the error reference. A refused admission rechecks the session as the Search page does (`requestSessionRecheck`). | UF-4.3 | `search.tsx:56-62` |

| State | All levels |
| --- | --- |
| Rest (empty field) | The field and the scope line; no groups. |
| In progress | The previous results stay; skeleton rows show in a group only after 300 ms. |
| Success | Groups with rows, as DR-4.4. |
| Nothing matches | Under the scope line: "Nothing matches "xyz"." and, under it, "Check the spelling, or try fewer words." |
| Failure | Per group, DR-4.9. |
| No permission | No new rule: each endpoint returns only what the person can open. A guest sees fewer groups. An administrator gets no messages from other people's direct messages or private channels (D43). |
| Phone (390) | Full screen; the field and Close at the top; groups scroll; rows 44 px. |

### Item 5 [F5]: people in "Find a conversation…"

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-5.1 | With text in "Find a conversation…" (`components/systems/comms/components/conversation-list.tsx:182-187`), a "People" section shows after the matching conversation sections: at most 5 people from `listDirectCandidates({ q, limit: 5 })`, read 250 ms after the last key. (PR2 screen review) While the candidate read runs with no earlier result, one skeleton row shows after 300 ms; screen readers hear "Loading people…" (visually hidden). | UF-5.1; UF-C5.1 | `direct-dialog.tsx:29-41` candidate read |
| DR-5.2 | The same People group shows in the ⌘K "Switch conversation" dialog, under the conversation matches (`quick-switcher.tsx:115-133`). | UF-5.1 | `quick-switcher.tsx` dialog |
| DR-5.3 | A person whose one-to-one direct message with the user is among the visible conversation matches is left out of People, so the person shows once. Otherwise the person shows under People, and the pick opens that existing conversation. | UF-5.3; UF-C5.2 | Direct messages section of `conversation-list.tsx` |
| DR-5.4 | A picked person calls `POST /api/comms/directs`, which opens the existing conversation or starts one, then opens it with focus in the composer. While it runs, the row reads "Starting…" and is disabled. On failure, under the People heading: "The conversation did not start. Try again." with the error reference; the typed name stays. | UF-5.2; UF-C5.1 | the start call of `direct-dialog.tsx` |
| DR-5.5 | A guest gets no People section. A refused candidate read hides the section with no message. The "+" dialog stays for group messages. | UF-5.4; UF-C5.3, UF-C5.4 | `actor.data?.membership_role` check of `direct-dialog.tsx` |
| DR-5.6 | No conversation and no person matches: "No conversations or people match." for a member; a guest keeps "No conversations match." | UF-5.1 | `quick-switcher.tsx:131`; `conversation-list.tsx:238-242` |
| DR-5.7 | (QA-P2-D1) While "Find a conversation…" has text, the list shows only what matches, in the current order: Starred rows that match; each category that has a matching channel, with only those channels and its header and "…" menu; "Records you follow" rows whose record title matches the same text; Direct messages rows that match; then People (DR-5.1). Sections and categories with no match, and every hint ("Star conversations to find them here.", "No channels here.", "Start a direct or group conversation."), do not show. A collapsed category that has a match shows its matches while the text is there and is collapsed again when the text is cleared; its saved open or closed state does not change. When the text is cleared, the list is exactly as before (every section, hint, category, and menu). (PR2 re-check) "Create category" is hidden while the text is there, because it is not a match; it returns with the full list. A category header shows no open or close chevron while the text is there, because its matches always show then (later fix; it does not block pull request 2). | UF-5.1; UF-C5.1 | `visible` filter and the section blocks of `conversation-list.tsx` (`:72-76`, `:239-249`, `:392-404`, `:426-440`, `:486-506`); no new module |

| State | Member | Guest |
| --- | --- | --- |
| Rest | Conversation list as now. | Same. |
| Typing | Only the matching rows, in their sections, then People (DR-5.7); empty sections and hints hidden. | Only the matching rows; empty sections and hints hidden; no People. |
| In progress | People rows keep the last result; a skeleton row only after 300 ms. | — |
| Success | Conversation opens, composer focused. | — |
| Failure | DR-5.4 message. | — |
| Empty | DR-5.6: no section shows; only "No conversations or people match.". | Only "No conversations match.". |
| No permission | A refused candidate read hides People; the server still refuses a start it does not allow. | No People section; "Guests cannot start conversations." stays in the "+" dialog. |
| Phone (390) | The list is the screen; DR-5.7 applies, so a matching person shows in the first screen under the filter; rows 44 px; picking opens the conversation screen. | Same, no People. |

### Item 6 [F4]: the new record shows first, tagged "New"

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-6.1 | After create, no banner: `setNotice("Record created.")` (`server-backed-views-workspace.tsx:3572`) is removed. The status "Record created." shows in the meta-line status span (`role="status"`, `:2758`). It clears at the next action on the page (a filter, sort, search, page, or view change, opening a record from the list, including the pinned one, or New record). The toolbar does not move: the status and its "Open record" button stay on the meta line's one line. The button's visible box is sized to the text line; its tap target is 32 px from 1280 px and 44 px below (an enlarged hit area). (CI re-check) At every width, while an item 6 status shows ("Record created.", with or without "Open record"), it takes the place of the meta text ("Sales · 83 records"): no breakpoint, and the fit never depends on the department name, the count, or the system's fonts. The meta text returns when the status clears at the next action. Meanwhile the count stays in the Records tab ("Records 83") and the department in the breadcrumb. Screen readers hear the status sentence only; the hidden meta text leaves the accessibility tree while the status shows. (Build, confirmed 2026-11-12) The meta text keeps its place, invisible, and the status draws over it, so the line keeps its height even when a long department name wraps; a view manager's "Unsaved changes" badge yields with it and returns at the next action, while "Save view" stays the primary; "Refreshing records…" (DA14) shows in the status's place, never in two places. | UF-6.1; UF-C6.1 | meta-line status of DA14 |
| DR-6.2 | When the sheet of the new record closes, the page asks the server if the record matches the applied conditions: one `POST /records/query` with the applied definition (its filters kept), the record id as `search`, and no search fields. The server applies the search and the filters together (`compile_query`, `backend/app/systems/sandbox/records/query.py:186-206` and the filter loop after it), so one item back means it matches. No backend change. (N-5) The person's own search text counts as an applied condition, and the id search replaces it in this read. So when search text is applied, the check cannot prove a match: the page skips the read, adds no row, and (N-10) shows "Record created." with "Open record", with no claim about the filters, because the record may still show in the list. | UF-6.2, UF-6.3 | the id lookup at `server-backed-views-workspace.tsx:802-810`, with its filters kept |
| DR-6.3 | It matches: the record is the first row of the table, grid, gallery, or phone cards, with a "New" tag directly after its title (on a phone card, on the title line, not after the second line). If the server rows of the current page also hold it, it shows once, in the first place. | UF-6.2, UF-6.4; UF-C6.1 | `components/ui/badge.tsx` (outline) |
| DR-6.4 | The count and the pager keep the server total ("Showing 1–50 of 602"). The pinned row is not added to the count; the record is counted once, at its sorted place. | UF-6.4; UF-C6.3 | `components/ui/table-pagination.tsx` |
| DR-6.5 | The match read ran and returned nothing: no row is added. The status reads "Created, hidden by filters." with an "Open record" button that opens its sheet, at every width. It takes the place of the meta text at every width (DR-6.1), so the words fit for any department name and record count (screen and CI re-check 2026-11-12). Screen readers hear the one status sentence. (N-10) When search text is applied and the read is skipped (DR-6.2), the status reads "Record created." with "Open record". | UF-6.3; UF-C6.2 | meta-line status of DR-6.1 |
| DR-6.6 | The "New" tag and the pinned place go when the person changes a filter, the sort, the search, the page, or the view, or leaves the page. Then the record shows only at its sorted place. | UF-6.2; UF-C6.3 | `draftKey` reset effect (`server-backed-views-workspace.tsx:853-856`) |

| State | Writer |
| --- | --- |
| Rest | List as now. |
| In progress | The create dialog shows "Creating…" as now; the match read keeps the list and shows nothing extra. |
| Success, matches | First row with "New"; "Record created." in the place of the meta text until the next action. |
| Success, hidden | "Created, hidden by filters." + Open record, in the place of the meta text until the next action, at every width. |
| View manager with unsaved changes | The "Unsaved changes" badge yields with the meta text while the status shows; "Save view" stays the primary; the badge returns at the next action. |
| Success, search text applied (N-10) | No row added; "Record created." + Open record. |
| Failure | The create dialog's current errors. The match read fails: no row is added; "Record created." with "Open record" (screen review: the person can still reach the record). |
| Grouped view (Layout settings › Group records by) | No match read and no pinned row; "Record created." with "Open record". |
| Empty list before create | The new record becomes the only row, with "New". |
| No permission | Reader and guest have no New record (as now). |
| Phone (390) | The first card carries "New". |

### Item 7 [F7]: the sidebar shows what each person can use

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-7.1 | The "Platform" group leaves the sidebar. Search is the header button (item 4). Notifications open from the bell's "View all" link (`components/systems/platform/components/notification-bell.tsx:242-248`). Files becomes its own tool with the description "Department documents". | UF-7.1; UF-C7.1 | `components/workspace-navigation.ts` definitions |
| DR-7.2 | Files is one row for everyone except administrators. An administrator gets a Files group with Files and Import & export. The administrator's Files group has the description "Department documents, and import and export" and the icon `FileText`. | UF-7.2; UF-C7.3 | `visibleItems` in `workspace-navigation.ts` |
| DR-7.3 | Writer, reader, guest Tools, in order: Boards, Files, Organization, System health. Organization and System health are top-level rows, with no Manage header, because these two are all that person sees of Manage. (Build, decided 2026-11-12) Every tool row keeps a one-line description, as the drawer rule says ("the phone drawer has 44px rows with visible descriptions"; desktop hover): Files "Department documents"; Organization "Name, region, and look"; System health "Whether everything is working". Icons, from the sidebar's icon library (lucide, same stroke and size): Files `FileText`, Organization `Building2`, System health `Activity`. `Settings` stays the Manage group's icon only, so one icon never names two places. | UF-7.3; UF-C7.1 | `visibleManageItem` in `workspace-navigation.ts` |
| DR-7.4 | Department manager Tools: Boards, Access (Groups), Files, Manage (Organization, System health, Audit). | UF-7.4; UF-C7.2 | `accessNavigationFor`, `auditDepartmentsFor` |
| DR-7.5 | Administrator Tools: Sandbox, Boards, Access, Manage (as now), Files (Files, Import & export). | UF-7.5; UF-C7.3 | `workspace-navigation.ts` |
| DR-7.6 | Each `/platform?section=…` address opens its page with its current checks. The current row: Files for `section=files`; Files › Import & export for `section=import-export`; no sidebar row for `section=search` and `section=notifications` (the header Search and the bell own them). A non-administrator who opens `/platform?section=import-export` sees the current refusal, as now (`platform-section.ts:1-7`; an unknown section such as `import` opens Search). | UF-7.6; UF-C7.4 | `sectionFor` in `workspace-navigation.ts` |
| DR-7.7 | The breadcrumb of these pages drops "Platform": "Files", "Files › Import & export", "Search", "Notifications". | UF-7.1 | `components/ui/breadcrumb.tsx` |
| DR-7.8 | Start page: a stored "Platform" still opens Search at sign-in. In Account settings it reads "Platform (not available)" under PD62 (D-4 default). The stored value never changes in silence. | UF-7.6; UF-C7.5 | `components/settings/domain/start-page.ts` |

| State | Levels as DR-7.3 to DR-7.5 |
| --- | --- |
| Rest | The lists above. |
| Success (a row picked) | The page opens; its row is current (DR-7.6). |
| Empty | Not possible: everyone has at least Boards, Files, Organization, and System health. |
| In progress (identity loading) | The current rule: rows that need a level stay hidden until the identity loads (`accessNavigationFor` returns "none"). |
| Failure | As now. |
| No permission | An address the person cannot use shows the current refusal or notice (MD3). |
| Phone (390) | The drawer shows the same rows, each with its one-line description, as now. |

### Item 8 [F8]: Choose file saves the draft first

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-8.1 | Before the post has a draft, the Files row of the post editor shows a "Choose file" button in place of "Save draft to attach" (`components/systems/boards/components/server-backed-board-post-editor.tsx:291-302`). | UF-8.1; UF-C8.1 | `components/ui/file-picker-button.tsx` |
| DR-8.2 | While Title or Message is empty after trimming spaces (N-7; the server strips both, `backend/app/systems/boards/post_schemas.py:15-18`), Choose file is disabled with the reason "Add a title and a message first." | UF-8.2; UF-C8.2 | `components/ui/disabled-reason.tsx` |
| DR-8.3 | A picked file is checked first, with the checks of `server-backed-board-attachments.tsx:258-270` (`MAX_FILE_BYTES`, the file-name length). If it fails, the error shows under Files, no draft is saved, and Title and Message stay. | UF-8.5; UF-C8.4 | the same checks; `components/systems/shared/adapters/files-api.ts:10` |
| DR-8.4 | A valid file: the editor saves the post as a draft through its existing Save draft call, never Publish or Schedule; then the attachments control (`HydratedBoardAttachments`) takes over and uploads that file. The status line reads "Draft saved" (`:208-216`). (PR2 screen review) The editor title stays "New post" after the automatic save, because it names the task the person started; the "Draft saved" status beside the audience line says the draft exists. | UF-8.1, UF-8.3, UF-8.4; UF-C8.1, UF-C8.3 | `onSave`, `HydratedBoardAttachments` |
| DR-8.5 | If the draft save fails: the save error shows as it does now, no upload starts, and Title and Message stay. If the upload or the link fails after the draft exists: the draft stays with Title and Message, and the attachments control handles it as now (an upload error, or the pending file with its retry, `server-backed-board-attachments.tsx:217-254`). The new step adds no file without a post: no upload starts before the draft exists. | UF-8.5 | current error texts of `server-backed-board-attachments.tsx` |
| DR-8.6 | Closing the editor after an automatic save leaves the post in Drafts, as after a Save draft. Only its author and the board's managers see it, as now. | UF-8.4; UF-C8.3 | Drafts list of `board-post-list.tsx` |
| DR-8.7 | "Save draft to link" for linked records stays as it is (not in scope). | — | `server-backed-board-post-editor.tsx:414-426` |

| State | Writer |
| --- | --- |
| Rest, no text | Choose file disabled, reason "Add a title and a message first.". |
| Rest, text | Choose file enabled. |
| In progress | "Saving…" on the editor status, then the attachments control's upload progress. |
| Success | "Draft saved"; the file is listed. |
| Failure | DR-8.3 or DR-8.5. |
| No permission | Readers and guests have no New post (as now). |
| Phone (390) | Same; the button is 44 px. |

### Item 9 [F13]: plain words

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-9.1 | Triggers and the Test reading say "record": the trigger sentence, the event label, the Test head and rows, and "Example record" (see Words). Stored event values do not change. The design text of `sandbox-ux-redesign.md:391,411` follows. | UF-9.1; UF-C9.1 | `components/trigger-sentence.tsx`, `components/trigger-flow.tsx`, `components/trigger-rail.tsx`, `domain/test-reading.ts`, `domain/test-run-summary.ts` in `components/systems/sandbox/` |
| DR-9.2 | Layout settings use the Words rows for `saved-view-advanced-controls.tsx`. The default order is named: oldest records first (`backend/app/systems/sandbox/records/query.py:283-284`). (PR2 screen review) The "Sort and group" heading has no line under it; the one hint sits under "Sort order": "Use up to three rules. The first one counts most." The grouped list page uses the same plain words: its line "Counts include all matching records. Only the selected group's page of records is loaded." is removed (the counts beside each group say it), and "Select a group to load its records." reads "Choose a group to see its records." (QA-P2-D3). | UF-9.2; UF-C9.2 | `components/systems/openview/components/saved-view-advanced-controls.tsx` |
| DR-9.3 | The condition menu offers one "no value" pair: "is empty" (stored `blank`) and "is not empty" (stored `not_blank`). A value of only spaces counts as empty. The stored operators `empty` and `not_empty` leave the menu. A saved condition that still uses them shows "is empty (exact)" or "is not empty (exact)" on text fields, where the result differs, and "is empty" or "is not empty" on other fields, where it is the same (`query.py:213-227`). The same labels apply in Views, Reports, and Charts. | UF-9.3; UF-C9.3 | `OPERATOR_LABELS` in `domain/server-view-draft.ts:20-35`; `report-recipe-editor.tsx`; `chart-query.ts` |
| DR-9.4 | Widget titles follow the query, in plain words. A count reads as the module name ("Customers"); a sum reads as "Total credit limit"; an average reads as "Average credit limit"; smallest, largest, and distinct read as "Smallest …", "Largest …", and "Different … values". "by <field>" and "per week" stay. The field name keeps its letters, except that a leading capital is lowered when the first word is not all capitals ("VAT amount" stays). A saved chart keeps its name. | UF-9.4; UF-C9.4 | `widgetTitle` in `domain/dashboard-widget-text.ts` |
| DR-9.5 | A Number widget with no value shows "No values yet" in the muted text style in place of the large "—" (`dashboard-widget-card.tsx:438`). Empty cells in table and records widgets keep "—". | UF-9.4; UF-C9.4 | `components/systems/openview/components/dashboard-widget-card.tsx` |
| DR-9.6 | Help › Keyboard shortcuts lists "Search workspace" (Ctrl K, ⌘K on a Mac) for everyone and "Switch conversation" (⌘K in OpenComms, `COMMS_SHORTCUTS`). The Sandbox shortcuts and their scope line show only to accounts that can open the Sandbox (`accessNavigationFor` = "all"). The "Shortcuts are off" line stays. | UF-9.5; UF-C9.5 | `components/help/help-panel.tsx:216-235` |

| State | All levels |
| --- | --- |
| Rest | The new words in their current places. |
| In progress, success, failure | Each screen keeps its current states; only the words change. |
| Empty | Number widget with no value: "No values yet" (DR-9.5). |
| No permission | Help without the Sandbox: no Sandbox shortcuts (DR-9.6). |
| Phone (390) | The same words; nothing moves. |

### Item 10 [F9]: Invite says what each group gives; "Add access" (new structure; comp `add-access.html`)

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-10.1 | In Invite (`components/systems/access/components/invite-person-dialog.tsx:426-450`), each group row gets a second muted line from `GroupResponse.access`: "Sales · Write"; for several departments, "Sales · Write, Finance · Read" and then "+2 more"; when modules differ, "Sales · Write (2 modules differ)"; with no access rows, "Gives no access yet". When the role is Guest, a level above Read reads "Sales · Read (guest limit)". The invitation still sends group IDs only. (PR3 screen review) Words: "Sales · Read (guest limit)"; "Gives no access yet"; "Sales · Write (1 module differs)" or "(2 modules differ)"; a group that reaches one module only reads "Sales · Invoices · Read", several modules "Sales · 2 modules"; more than two departments add "+2 more". (Security S3-5) When `has_other_grants` is true, the line shows it, because the read gives no names or counts for those grants: a group with no access rows reads "Boards or OpenComms access only" (not "Gives no access yet"); a group with access rows adds " · also Boards or OpenComms" to its line, for example "Sales · Read · also Boards or OpenComms". | UF-10.1; UF-C10.1 | `AccessLevelBadge` words in `access-level-badge.tsx`; "Departments reached" of `groups-view.tsx:339-344` |
| DR-10.2 | The person sheet's Access tab (`person-access.tsx`) shows "Add access" (outline button) under the access list, only when the viewer is an administrator and the person is not an administrator. It opens an inline form in the tab, not a dialog over the sheet (as DA19). | UF-10.2, UF-10.6; UF-C10.2, UF-C10.5 | `components/systems/access/components/person-access.tsx` |
| DR-10.3 | The form, in reading order: (1) Department, a search select of the departments (`useAccessCatalog` kind `departments`); (2) Level, a radio group: "Read", "Write", "Manage", each with one short line under its label (see Words); for a guest only "Read"; (3) one result line; (4) the action and Cancel. | UF-10.2, UF-10.5; UF-C10.4 | `components/ui/search-select.tsx`, `components/ui/radio-group.tsx` |
| DR-10.4 | The result line names what will happen before the action: "Sales Desk gives exactly this." with the action "Add to Sales Desk". A group gives exactly this when its access is one row: that department, no module, that level. If several do, the one with the earliest name in alphabetical order. (PR3 screen review) When several groups fit exactly, the department's own group made by the Sandbox ("<Department> managers", "members", or "viewers" for Manage, Write, Read) is taken first; otherwise the earliest name. Before a department is chosen, the action reads "Add" and is disabled with the reason "Choose a department first.". A guest's form shows the guest note once, at the top of the tab. | UF-10.3; UF-C10.2 | `listAccessGroups` (`use-access-catalog.ts:72`), every page |
| DR-10.5 | No group fits: "No group gives exactly this." with the action "Make group "Finance read access" and add". The name is "<Department> read access", "write access", or "manage access"; it never equals a Sandbox derived name ("<Department> managers", "members", "viewers"). (N-9) Derived names always end in managers, members, or viewers (`backend/app/systems/sandbox/derived/actions.py:94-97`), so "<Department> <level> access" cannot collide; the owner test of UF-C10.3 is a name rule at the isolated layer, not a publish. If an active group already has that name and other access, the name ends with " 2", then " 3". | UF-10.4; UF-C10.3 | new structure (comp `add-access.html`); `POST /api/access/groups` (`configuration_router.py:269`) |
| DR-10.6 | The person already has that level or more in that department: "Already has Write in Finance, from Sales Desk." and the action is disabled with that reason. | UF-10.3 | `components/ui/disabled-reason.tsx` |
| DR-10.7 | The make action runs, in order: create the group with no members (`POST /api/access/groups`), set its access (`PUT /api/access/groups/{id}/access`), add the person (`changeGroupMembership`, `adapters/group-membership.ts`). The button reads "Adding…" until all three end. Success: the form closes, the list shows the new row ("Finance · All modules · From Finance read access (Read)"), and the tab's status line reads "Added Finance · Read, from Finance read access." (PR3 screen review) While the groups are read, the result line shows nothing for 300 ms, then a skeleton line; screen readers hear "Reading the groups…" (visually hidden). A failed read: "The groups could not be read." with "Try again" and the reference. When the groups change between the line and the action, nothing is written and the form reads "The groups changed. Check the new line, then add." After a success, focus returns to "Add access". | UF-10.4, UF-10.7; UF-C10.3 | existing Create group and access adapters |
| DR-10.8 | Partial failure: the form stays, with "Finance read access was made, but this person was not added. Try again." and Try again. A retry first looks for a group that gives exactly this (DR-10.4), then for the made name with no access rows and no members; it uses that group and makes no second one. A same-name group with members is never reused: the name takes " 2" (the S9 rule of `access-ui-ux-pass.md`). Any refusal shows the server's reason. (PR3 screen review) A refused create (403) reads "Only an administrator can make groups." with the reference, not the Groups-page wording. (PR3 re-check, 2026-11-13) On the join path, no group is made; a member write with no answer reads "The change got no answer, so it may have completed. Try again to finish it." with "Try again". | UF-10.7; UF-C10.6 | S9 rule of `access-ui-ux-pass.md`; `changeGroupMembership` |
| DR-10.9 | Department managers, writers, readers, and guests get no Add access; the Access tab reads as now. | UF-10.6; UF-C10.5 | `accessNavigationFor` (`workspace-navigation.ts`) |
| DR-10.10 | (Security, Human Owner choice 1a, 2026-11-13) Each group in the group read has `has_other_grants`: true when the group has a project Board link, an OpenComms channel grant, or a capability grant. The form reuses only a group that fits by access and has no other grants. There are three results. No group fits by access: "No group gives exactly this." and the make action (DR-10.5). One or more groups fit by access, but each has other grants: "No group gives only this." and the make action makes a new group, as DR-10.5 (the name takes " 2" when the name is taken). A group fits by access and has no other grants: "<Group> gives exactly this." and "Add to <Group>". | UF-10.3, UF-10.4 | `has_other_grants` on the group read; `helpers/add-access.ts`; `add-access-form.tsx` |

| State | Administrator viewing a member | Administrator viewing a guest | Others |
| --- | --- | --- | --- |
| Rest | The access list + "Add access". | Same + the guest note. | The access list only. |
| Form open | Department, Level (3), result line, action. | Level shows "Read" only. | — |
| In progress | "Adding…"; the form disabled. | Same. | — |
| Success | Form closes; new row; status line. | Same, level Read. | — |
| Failure | DR-10.8. | Same. | — |
| Empty (no access yet) | "No access yet." over "Add access" (replaces "No access yet. Add them to a group in Details."). | Same. | "No access yet." |
| Administrator person | "Full access" as now; no Add access. | — | — |
| Phone (390) | The sheet is full screen; the form stacks; radios and buttons 44 px. | Same. | — |

### Item 11 [F10]: Published state; counts of what the owner drew (new structure; comp `published.html`)

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-11.1 | The counts line (`publicationChangeSummary`, `components/systems/sandbox/components/publish-change-groups.tsx:137-150`) counts departments, modules, fields, and relationships (D-2: Review keeps "relationship"), and triggers when the publish has any (a trigger-only publish would otherwise show an empty line). Groups, dashboards, Boards, categories, and channels leave the line. | UF-11.2; UF-C11.1 | the same function |
| DR-11.2 | Under each new department row, one line directly under its name: "Comes with: 3 access groups · home dashboard · Announcements board · chat category and channel". It lists only the setup kinds that the publish creates for that department. The full setup list (`Setup for <Department>`, `:497-524`) stays under it, before the password row (SD6). | UF-11.3; UF-C11.1 | `SETUP_KIND_WORDS` |
| DR-11.3 | The password, "Your team sees these changes as soon as you publish.", and "Publish changes" stay. A wrong password is refused as now. "Save triggers" and the disabled reason stay (D1). | UF-11.4; UF-C11.3 | `review-publish-dialog.tsx:470-540` |
| DR-11.4 | After a publish, the dialog stays open (no `onOpenChange(false)` at `review-publish-dialog.tsx:243-246`). Its title becomes "Published", with no motion of its own; the look's title signature keeps playing once on the Sandbox page title, as now (`sandbox-page-header.tsx:142`). The body: "Your team sees these changes now." directly under the title; then, under the heading "Open records", one link per newly published module ("Orders", with its department mark and "Sales" as context) to `/openview?section=views&module=<live id>`. The footer has one button: "Back to Build", which closes the dialog. | UF-11.1; UF-C11.2 | `DialogFrame` (`components/ui/dialog-frame.tsx`); `DepartmentMark` |
| DR-11.5 | The live module IDs come from the bindings read (`GET /api/sandbox/bindings`, `state/lifecycle-api.ts:47`), read again after the publish (`page.tsx:421-538`), matched by the `sandboxId` of each created module. (D-3 resolved) The publish writes the module bindings in its own transaction (`backend/app/systems/sandbox/publications/executor.py:240,305-306`), so the read gives the new module IDs right after a successful publish. While it reads, the "Open records" area shows a skeleton row after 300 ms. (PR2 screen review) While the read runs, nothing shows for 300 ms, then a skeleton heading and one skeleton link row; screen readers hear "Finding the new records…" (visually hidden). | UF-11.1 | `bindingsQuery` |
| DR-11.6 | No module link: when the publish creates no module, or (D-3 resolved) when the bindings read fails, the Published state shows only the title, "Your team sees these changes now.", and "Back to Build". A module published closed gets no link, because it has no records page. "Back to Build" only closes the dialog: Build is already behind it. | UF-11.1; UF-C11.4 | new structure (comp `published.html`, `?state=nolinks`) |

| State | Administrator |
| --- | --- |
| Rest (review) | Counts line of DR-11.1; department rows with "Comes with"; full setup list; password. |
| In progress | "Publishing…" as now. |
| Success | Published state with links, or DR-11.6. |
| Failure | The current refusal texts (password, conflict, blockers). |
| Empty (nothing to publish) | As now. |
| No permission | The Sandbox is for administrators only (as now). |
| Phone (390) | The dialog as now on a phone; links are 44 px rows; "Back to Build" full width. |

### Item 12 [F14, part]: phone record header

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-12.1 | Below 640 px, the record header (`server-backed-views-workspace.tsx:3416-3500`) stacks: the actions row first, full width, aligned to the end (Previous, Next, Edit, More record actions, Close); then the title at the full sheet width, at most 2 lines with an ellipsis; then the meta line. The DOM order does not change (title first, then actions), so a screen reader reads the title first; the stack is visual only (`max-sm:flex-col-reverse`). | UF-12.1; UF-C12.1 | record header in `server-backed-views-workspace.tsx` |
| DR-12.2 | Every DA18 element and accessible name stays ("Record details", "Previous record", "Next record", "Edit record", "More record actions", "Close"). Targets stay 44 px (`size-11`). Nothing scrolls sideways. From 640 px the header does not change. | UF-12.2; UF-C12.1, UF-C12.2 | `components/ui/button.tsx` `size="icon"` |

| State | All levels |
| --- | --- |
| Rest, phone (390) | Actions row, then the title (2 lines at most), then the meta line. |
| Rest, from 640 px | As now (DA18). |
| In progress (record loading) | "Loading record…" as the title, as now, in the same stacked order. |
| Failure | "Record unavailable" as the title, as now. |
| Editing | Previous, Next, and Close step aside or are disabled, as now. |
| No permission | Reader and guest: no Edit; the actions row holds Previous, Next, More record actions, Close. |

### Item 13 [F12, F11 part]: open the last organization; landing words

| Rule | Rule text | Serves | Reuses |
| --- | --- | --- | --- |
| DR-13.1 | After sign-in, when the session has no organization and the account has several, the app reads the organization this browser opened last (`lastOrganizationId`, `lib/organization-context.ts:55-58`). If it is one of the account's memberships, the app selects it with the same server call as a pick (`selectOrganization`, which `openOrganization` wraps, `components/app-page.tsx:811-824`). The server checks it as a pick (two-step, address). Accepted: the tab takes the organization and the session check runs again, as after a pick (`:826-829`). | UF-13.1, UF-13.3; UF-C13.1 | `selectOrganization`, `chooseOrganization` |
| DR-13.2 | While it opens, AppPage stays in its current session-check state; no chooser flashes, and nothing new shows (no cover, no "Opening…"). | UF-13.1 | G2 |
| DR-13.3 | The chooser (`components/organization-gate.tsx`) shows when nothing is stored, when the stored organization is not a membership of this account, or when the open is refused (a 403 from `selectOrganization`; unlike a pick, the automatic open does not enter the organization's two-step or network screen). After a refusal, an alert at the top of the chooser names the reason: two-step required (N-6: `mfa_required` covers both an account without two-step and an enrolled account whose session has not passed the second step, `backend/app/common/dependencies/auth.py:272-286`), "Harbor Operations Group asks for two-step verification. Choose it to continue."; a pick then opens the same set-up or verify screen as today; address not allowed, "Harbor Operations Group does not allow sign-in from this network."; other, "Harbor Operations Group could not be opened." with the error reference. (PR2 screen review) The two-step and network reasons use the warning style (a policy the person meets, not a failure); "could not be opened" uses the destructive style with its reference. A 401 from the select is not an organization refusal: it follows the existing session check (refresh, then the sign-in page), not the chooser. | UF-13.2; UF-C13.2, UF-C13.3 | `Alert` of `organization-gate.tsx`; a pick from the chooser then works as now, including the two-step screen (`app-page.tsx:877`) |
| DR-13.4 | Pending invitations stay reachable: the organization menu shows them as now ("1 invitation"), and the chooser lists them as now. | UF-13.1 | organization menu |
| DR-13.5 | Landing page (`app/page.tsx`): step 01 reads "Join" over "Your administrator sends you an invitation by email."; the header link "First deployment?" (`:67`) and the hero button "Read setup guide" (`:99`) are removed. The `/login` footer keeps "First deployment? Read the setup guide" (`app/login/page.tsx:182-187`). `/setup` does not change. | UF-13.4; UF-C13.4 | `app/page.tsx` `workflow` list |

| State | Signed in, several organizations |
| --- | --- |
| Rest | The last organization opens; the chooser does not show. |
| Success | The organization's start page opens, as after a pick. |
| No permission (membership gone) | Chooser as now (DR-13.3). |
| In progress | DR-13.2. |
| Failure | Chooser with the DR-13.3 alert. |
| Empty (nothing stored) | Chooser as now. |
| Phone (390) | The chooser as now; the landing step stacks as now. |

### Words

Every new or changed user-visible string. Old strings that stay are not listed.

| Item | Old | New | Old string's file |
| --- | --- | --- | --- |
| 2 | — | "Saving…" (record meta line) | — |
| 2 | — | "<Field> changed to <value>." + "Undo" | — |
| 2 | — | "<Field> changed back to <value>." | — |
| 2 | — | "<Field> cleared." (optional Choice list set to None, or a date removed) | — |
| 2 | — | "<Field> turned on." / "<Field> turned off." (Checkbox) | — |
| 2 | — | "Someone changed this record. It shows their value now." | — |
| 2 | — | "Not undone. Someone changed this record after you." | — |
| 2 | — | "Not saved. Try again." | — |
| 3 | "Complete this condition or remove it before saving." | "Not applied yet: choose a field." / "Not applied yet: choose a value." | `components/systems/openview/components/saved-view-filter-controls.tsx:462` |
| 3 | "Complete the condition in Filters before loading matching records." | removed | `server-backed-views-workspace.tsx:3188` |
| 3 | — | "Choose a value or remove this condition." (manager Save view) | — |
| 4 | Search link "Search workspace" to `/platform` | Button "Search" (name "Search workspace") that opens the panel | `components/app-shell.tsx:954` |
| 4 | — | Panel field "Search workspace"; scope line "Records · People · Posts · Events · Messages · Files" | — |
| 4 | — | Group headings "Records", "People", "Posts", "Events", "Messages", "Files", each with " · <total>" | — |
| 4 | — | "Show all results for “<text>”" (typographic quotes) | — |
| 4 | — | "Nothing matches “<text>”." + "Check the spelling, or try fewer words." | — |
| 4 | — | "<Group> could not be searched." + "Try again" (panel and Search page cards) | — |
| 4 | "Search could not be completed." + "Retry" (Search page cards) | "<Kind> could not be searched." + "Try again" | `components/systems/platform/components/search.tsx:210-217` |
| 4 | "<n> results · showing <m>" with n = 1 | "1 result · showing 1" | `search.tsx:301` |
| 4 | "Search people, records, posts and events…" | "Search records, people, posts, events, messages, and files…" | `components/systems/platform/components/search.tsx:71` |
| 5 | — | Section "People"; row state "Starting…" | — |
| 5 | — | Screen-reader text while people load: "Loading people…" | — |
| 5 | — | "The conversation did not start. Try again." | — |
| 5 | "No conversations match." | "No conversations or people match." (members; guests keep the old) | `components/systems/comms/components/quick-switcher.tsx:131`, `conversation-list.tsx:240` |
| 6 | Banner "Record created." | Meta-line status "Record created." | `server-backed-views-workspace.tsx:3572` |
| 6 | — | Tag "New" | — |
| 6 | — | "Created, hidden by filters." + "Open record" (match read returned nothing), at every width | — |
| 6 | — | "Record created." + "Open record" (search text applied, match not checked) | — |
| 7 | Sidebar group "Platform" | removed; tool "Files" with the description "Department documents" | `components/workspace-navigation.ts:105-118` |
| 7 | — | Tool descriptions: Organization "Name, region, and look"; System health "Whether everything is working"; administrator Files group "Department documents, and import and export" | — |
| 7 | Breadcrumb "Platform › …" | "Files", "Files › Import & export", "Search", "Notifications" | breadcrumb of `/platform` |
| 8 | "Save draft to attach" | "Choose file" | `components/systems/boards/components/server-backed-board-post-editor.tsx:300` |
| 8 | — | Disabled reason "Add a title and a message first." | — |
| 9 | "When an item is added to " | "When a record is added to " | `components/systems/sandbox/components/trigger-sentence.tsx:131` |
| 9 | "Item added" | "Record added" | `trigger-flow.tsx:38`, `trigger-rail.tsx:911` |
| 9 | "When an item is added" (Test) | "When a record is added" | `components/systems/sandbox/domain/test-reading.ts:222` |
| 9 | "An item is added" (Test event block) | "A record is added" | `components/systems/sandbox/domain/test-run-summary.ts:222` |
| 9 | "Runs when an item is added to <module>." | "Runs when a record is added to <module>." (the "Try it: …" name follows the Test title) | `components/systems/sandbox/domain/test-run-summary.ts:142` |
| 9 | "Example item", "Example item · <trigger> only" | "Example record", "Example record · <trigger> only" | `components/systems/sandbox/components/test-workspace.tsx:754-755` |
| 9 | — | Help: "Search workspace" with Ctrl K / ⌘K; "Switch conversation" with ⌘K | `components/help/help-panel.tsx` |
| 9 | "Advanced query settings" | "Sort and group" | `components/systems/openview/components/saved-view-advanced-controls.tsx:61` |
| 9 | "Control sort priority and grouping." | removed (the "Sort order" hint says it; PR2 screen review) | same file `:64` |
| 9 | "The first rule has the highest priority. Use up to three rules." | "Use up to three rules. The first one counts most." | `saved-view-advanced-controls.tsx:75` |
| 9 | "Counts include all matching records. Only the selected group's page of records is loaded." | removed | `components/systems/openview/components/live-grouped-results.tsx:71` |
| 9 | "Select a group to load its records." | "Choose a group to see its records." | `server-backed-views-workspace.tsx:3331` |
| 9 | "Records keep their source order." | "With no rule, the oldest records come first." | same file `:117` |
| 9 | "Counts come from the server. Select a group to load its paged records." | "Choose a group to see its records." | same file `:253-254` |
| 9 | "is empty" (`empty`), "is blank" (`blank`) | "is empty" (`blank`); a saved `empty` reads "is empty (exact)" on text fields | `components/systems/openview/domain/server-view-draft.ts:31-35`; `report-recipe-editor.tsx`; `chart-query.ts` |
| 9 | "is not empty" (`not_empty`), "is not blank" (`not_blank`) | "is not empty" (`not_blank`); a saved `not_empty` reads "is not empty (exact)" on text fields | same files |
| 9 | "Number of <Module>" | "<Module>" | `components/systems/openview/domain/dashboard-widget-text.ts:24-31,66-70` |
| 9 | "Sum of <Field>" | "Total <field>" | same file |
| 9 | "Distinct <Field>" | "Different <field> values" | same file |
| 9 | "Average <Field>", "Smallest <Field>", "Largest <Field>" | "Average <field>", "Smallest <field>", "Largest <field>" | same file |
| 9 | Number widget "—" | "No values yet" | `components/systems/openview/components/dashboard-widget-card.tsx:438` |
| 10 | — | Group line "Sales · Write", "+2 more", "(2 modules differ)", "Gives no access yet", "(guest limit)" | — |
| 10 | — | Button "Add access"; labels "Department", "Level" | — |
| 10 | — | Level lines: "Read" / "See records."; "Write" / "Add and change records."; "Manage" / "Also manage its views, dashboard, and group members." | — |
| 10 | — | "<Group> gives exactly this." + "Add to <Group>" | — |
| 10 | — | "No group gives exactly this." + "Make group "<Department> <level> access" and add" | — |
| 10 | — | "Already has <Level> in <Department>, from <Group>." | — |
| 10 | — | "Adding…"; "Added <Department> · <Level>, from <Group>." | — |
| 10 | — | "<Group> was made, but this person was not added. Try again." | — |
| 10 | "No access yet. Add them to a group in Details." | "No access yet." (administrator view adds Add access under it) | `components/systems/access/components/person-access.tsx:198` |
| 10 | — | "Add" (disabled, reason "Choose a department first."); "Reading the groups…" (screen readers); "The groups could not be read." + "Try again"; "The groups changed. Check the new line, then add."; "Only an administrator can make groups." | — |
| 10 | — | Invite lines: "Sales · Invoices · Read"; "Sales · 2 modules"; "(1 module differs)" | — |
| 10 | — | DR-10.10: "No group gives only this." | — |
| 10 | — | Join path, no answer: "The change got no answer, so it may have completed. Try again to finish it." | — |
| 10 | — | Invite line with other grants (S3-5): "Boards or OpenComms access only"; "<access line> · also Boards or OpenComms" | — |
| 11 | "2 new departments · 6 new groups · 2 new dashboards · 2 new Boards · 2 new categories · 2 new channels · 3 new modules · 8 new fields · 1 new relationship" | "2 new departments · 3 new modules · 8 new fields · 1 new relationship" | `components/systems/sandbox/components/publish-change-groups.tsx:137-150` |
| 11 | — | "Comes with: 3 access groups · home dashboard · Announcements board · chat category and channel" | — |
| 11 | — | Screen-reader text while the module links load: "Finding the new records…" | — |
| 11 | Toast "Changes published" | Dialog title "Published"; "Your team sees these changes now."; heading "Open records"; button "Back to Build" | `components/systems/sandbox/page.tsx:2177` |
| 13 | "Set up" / "Create the first administrator outside the browser." | "Join" / "Your administrator sends you an invitation by email." | `app/page.tsx:19` |
| 13 | Header "First deployment?"; hero "Read setup guide" | removed from `/` (the `/login` footer keeps "First deployment? Read the setup guide") | `app/page.tsx:67,99` |
| 13 | — | "<Organization> asks for two-step verification. Choose it to continue." | — |
| 13 | — | "<Organization> does not allow sign-in from this network." | — |
| 13 | — | "<Organization> could not be opened." | — |

### Design-system items (for a later `impeccable` request)

1. In-place value control in a label-left Details row: the rest, busy, and error looks, and the meta-line status with Undo.
2. "Not applied yet" line under a filter row (muted, not destructive).
3. The search panel: field row, scope line, group heading with total, two-line result row, active row, footer link (comp `search.html`).
4. The "New" tag on a pinned list row and card.
5. The inline "Add access" form in a sheet tab, with the result line (comp `add-access.html`).
6. The dialog end state "Published" with a link list (comp `published.html`).
7. The "Comes with" line under a department row in Review & Publish.

## Where each capability goes (Product Designer)

| Removed or moved | Item | New place, or why it is removed |
| --- | --- | --- |
| "Unsaved changes" badge, for people who are not view managers | 1 | Removed: they cannot save a view (DA12). The change stays in the address; Back restores it. |
| "Discard unsaved view changes?" for people who are not view managers (sidebar, links, view picker, discard points) | 1 | Removed: nothing is lost that Back cannot restore. View managers keep it. |
| Edit that changed nothing on Files, Linked records, History | 2 | Edit now selects Details and opens the form there. |
| Edit and Save for one Choice list, Checkbox, Date, or Date and time value | 2 | The value changes in place on Details; Edit stays for every field. |
| Warning "Complete the condition in Filters before loading matching records." | 3 | Removed: incomplete conditions are not applied, so the list stays. |
| List-level warning "Correct the number condition in Filters before loading matching records." | 3 | Removed: a number that is not safe keeps its error under its field, and the list keeps the last good result (DR-3.6). |
| Early error "Complete this condition or remove it before saving." | 3 | "Not applied yet" under the row; the error shows at Save view only. |
| Export disabled by an incomplete condition | 3 | Export stays enabled and uses the applied conditions. |
| Header Search as a link to the Platform Search page | 4 | The search panel over the page. "Show all results" opens the Search page. |
| Sidebar row Platform › Search | 4, 7 | The header Search button; the address `/platform?section=search` keeps working. |
| Platform › Search page, four kinds | 4 | Stays; it also shows Messages and Files, and reads `q` from the address. |
| "Start conversation" through "+" for a single person | 5 | Also reachable by typing the name in "Find a conversation…" or ⌘K. "+" stays for group messages. |
| Banner "Record created." | 6 | The meta-line status. |
| Sidebar group "Platform" | 7 | Removed: its four rows moved (see the rows below and above). |
| Sidebar row Platform › Notifications | 7 | The bell's "View all" link; the address `/platform?section=notifications` keeps working. |
| Sidebar row Platform › Files | 7 | The tool "Files". |
| Sidebar row Platform › Import & export, for non-administrators | 7 | Removed: the server refuses it for them. Administrators: Files › Import & export. |
| Group header "Manage", for writers, readers, guests | 7 | Removed: Organization and System health show as their own rows. |
| Breadcrumb word "Platform" | 7 | Removed; the page name stays. |
| "Save draft to attach" | 8 | "Choose file", which saves the draft first. |
| "Save draft to link" | 8 | Stays as it is: "Add linked record" is not in scope. |
| Words in the Words table | 9 | The new words in the same places. |
| Condition choices "is empty" (`empty`) and "is not empty" (`not_empty`) in the menu | 9 | Removed from the menu; saved conditions that use them keep working and show "(exact)" on text fields. |
| Sandbox shortcuts in Help, for accounts without the Sandbox | 9 | Removed for them; administrators keep them. |
| "No access yet. Add them to a group in Details." | 10 | "No access yet." For administrators, "Add access" sits under it; Details › Add to group stays. |
| The detour through Groups › Create group › Access › Members to give one level | 10 | "Add access" in the person's Access tab. The Groups pages keep every action. |
| Six setup kinds in the review counts line | 11 | The "Comes with" line under each department, and the full setup list, which stays before the password. |
| Toast "Changes published" and the dialog closing at publish | 11 | The Published state in the same dialog. |
| Chooser at each sign-in for several organizations | 13 | Shown only when nothing is stored, the stored one is not a membership, or the open is refused. The organization menu switches. |
| Landing header "First deployment?" and hero "Read setup guide" | 13 | The `/login` footer "First deployment? Read the setup guide", to `/setup`. |
| Landing step "Create the first administrator outside the browser." | 13 | Removed from `/`; the installer steps live in `/setup`. |

## Backend changes needing your go-ahead (Product Designer)

**Approved by APR-0003** (Human Owner, 2026-11-12). This is the only backend change. For the Software Architect's review.

### BE-UF1: file kind on `GET /api/search`

**Request.** The existing `SearchRequest` (`backend/app/systems/platform/search/schemas.py:23-26`) with one more value in `SearchKind`: `file = "file"`. The other parameters, their limits, and their 422 rules do not change (`search` up to 100 characters, `limit` 1 to 100, `offset` ≥ 0, `sort_by=relevance`, `deleted=exclude` only).

**Response item.** `SearchItem` gains one field, `department_id: UUID | None`, for every kind:

| Field | `file` | `record` | `person` | `post`, `event` |
| --- | --- | --- | --- | --- |
| `kind` | `"file"` | as now | as now | as now |
| `id` | the file ID | as now | as now | as now |
| `title` | the file name | as now | as now | as now |
| `context_label` | the department name | as now | as now | as now |
| `module_id` | `null` | as now | `null` | `null` |
| `board_id` | `null` | `null` | `null` | as now |
| `department_id` | the library's department | `null` | `null` | `null` |
| `can_open` | `true` | as now | as now | as now |

The frontend schema (`platform-search-api.ts:9-26`, `.strict()`) adds `department_id` and the refine rule `file` ⇒ `department_id` set, `module_id` and `board_id` null; for other kinds, `department_id` null.

**What it finds.** Files with `purpose = "library_document"`, `state = "ready"`, and `is_deleted` false, in the bound organization. An archived library document is `is_deleted` (the library list's deleted field, `files/router.py:82,95`), so it is not found. They are matched by file name with the existing full-text rule (`to_tsvector('simple', …) @@ plainto_tsquery('simple', search)`, `query.py:336-345`). The search text is the file name with `.`, `-`, and `_` read as spaces, then the file name as written, so that "invoice" finds "invoice-2026.pdf". Order and paging: the existing `ts_rank` relevance, the ID tie-breaker, and `capped_pagination`, as for the other kinds.

**Access rule.** A file is listed only when the actor's department level for the file's department includes `read`: the same rule as the library list (`backend/app/systems/platform/files/access.py:80-90`, `level_for`). An administrator reads every department of the bound organization. A guest is capped at `read`, which is enough to read. The candidate subquery must apply the rule in SQL; it must not filter after paging, so `total` counts only readable files. (N-1) The existing `department_filter` (`backend/app/systems/access/policy/checks.py:74-84`) uses `department_ids()`, which also counts departments reached only through a module grant, so it is not the rule here. Add a helper in `checks.py` (every filter goes through `checks.py`, `backend/AGENTS.md`), for example `department_level_filter(db, user, column, AccessLevel.READ)`, built on `effective_levels(db, user).departments` (the direct department levels): `true()` for an administrator, `false()` when empty, else `column.in_(…)` of the departments whose direct level includes read. (N-2) Files of a deleted department are excluded, as records of deleted departments are (`search/query.py:123-134`). Board files, record attachments, OpenComms attachments, logos, and avatars are never listed.

**Code and tests that check the item shape (B-2).** Adding `department_id` to every `SearchItem` breaks each place that checks the exact item keys. Update all of them in the same unit as the schema change:

- Operator code: `backend/operations/sample/controls/platform_verification.py:224-238` (the key set; it raises "Search result shape differs"): add `department_id` to the key set, with its rule (set for `file`, null for the other kinds).
- Backend tests: `backend/tests/search/test_search_routes.py:110` (the `{"kind": "file"}` → 422 row leaves the invalid list; a new case asserts that `kind=file` with no `search` returns an empty page, 200, as the other kinds do) and `:158-166`; `backend/tests/operations/sample/controls/sample_platform_wire.py:311`.
- Frontend `.strict()` fixtures: `frontend/tests/http/auth-session-activity`, `auth-session-reconnecting`, `person-card`, `platform-refactor-journeys`, `frontend/tests/http/helpers/person-card-api.ts`, `frontend/tests/http/helpers/board-kanban-api.ts`, and `frontend/tests/isolated/platform/platform-search-api.spec.ts`.
- Contracts: the `readPlatformSearch` override in `frontend/tests/isolated/contracts/platform-contract.spec.ts:47`, and the `contracts/openapi.json` snapshot that `test_openapi_snapshot.py` checks (refresh it).

Architect's facts: no migration and no new index (the other kinds compute `to_tsvector` at query time, `query.py:336`); `frontend/api-route-manifest.json` does not change (the route is the same); `query.py` is 366 lines and stays under the 500-line limit.

**New tests (for the Engineering Manager's plan).**
1. A Sales library document is found by a word of its file name by a Sales reader, and by a guest of Sales (UF-C4.2).
2. (N-1) A Finance library document is not listed, and not counted in `total`, for an account with no Finance department level, including an account with only a module-level grant in Finance.
3. A file that is not `ready`, a deleted (archived) file, a file of a deleted department, and a board file are not listed.
4. (N-2) An administrator of organization A does not find a library file of organization B (administrator filters are `true()`, so isolation depends on the bound transaction and RLS).
5. The response item shape for each kind, including `department_id`, in the frontend contract test (`frontend/tests/isolated/contracts/platform-contract.spec.ts`).

**Not changed.** `/api/comms/search` (Messages) and the files list routes do not change.
