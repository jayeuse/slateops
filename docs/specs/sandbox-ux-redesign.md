# Sandbox UX redesign: find, build fast, write triggers, see what happens

> **Status: done (2026-11-11), PR #100, #101, #102, #103.** Approved by the owner on 2026-11-10 (APR-0001), with OQ-1 to OQ-3 option (a) and UXD-2 as the EXIT-3 exception. Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/sandbox-ux-redesign.md`.

## Outcome

An administrator finds create controls at the element, adds elements one after another, writes triggers with the structure in view, and sees in plain words what happens to a record before publishing. PR #100 built Triggers and Test, PR #101 the save queue, PR #102 the create surface, PR #103 setup choices, the type warning and the template department. Code: `frontend/src/components/systems/sandbox/` (`components/`, `domain/`). No backend change.

Groups: FIND, FAST, TRIG, TEST (the owner's four concerns) and FIT (`docs/specs/sandbox-department-setup.md`).

## Preserved behavior

- S4: the Sandbox is hidden from non-administrators; a direct link shows "Sandbox is not available to your account."
- The `sandbox-relayout.md` grammar; R1 to R3, D1 and D3 of `sandbox-ui-ux-pass.md`; autosave, Undo/Redo, the publish contract and section URLs.
- Test never creates records; "Module" stays the in-product word.

## Requirements

| ID | Requirement |
| --- | --- |
| FIND-1 | Each create action (department, module, field, relationship) is one pointer move from the element it adds to, on the canvas and in the Structure tree. |
| FIND-2 | The create action of the selected element is visible without opening a panel; others show on hover or focus. |
| FIND-3 | Names say result and parent ("Add field to Orders"). |
| FIND-4 | Every create action is reachable by keyboard from the Structure tree or the selected element. |
| FIND-5 | At 390px each create action is reachable from the pane that shows the parent, with 44px targets. |
| FIND-6 | Duplicate is reachable from the element on the canvas. |
| FAST-1 | After a create, the next sibling can be added at once without reselecting the parent; Escape or an empty name ends the flow and creates nothing. |
| FAST-2 | Type and Required are set while naming a field; a non-Text type costs at most one more action. |
| FAST-3 | Reference structure (1 department, 2 modules × 3 fields, 1 relationship): 6 pointer clicks or fewer all Text, 12 with six non-Text fields, and a keyboard-only path. |
| FAST-4 | The relationship name is prefilled from its two modules. |
| FAST-5 | Changing the type of a field that the latest published version has (matched on module id and field id) warns at once, with the choice to keep the old type. |
| FAST-6 | Each create is one Undo step, with inline feedback. |
| FAST-7 | Add one department from the six organization templates, with its modules, fields and internal relationships, without triggers and without replacing anything. |
| TRIG-1 | While editing a trigger, the module's department, typed fields and links show beside the editor (one action away at 390px). |
| TRIG-2 | Module pickers group modules by department; field pickers show each field's type. |
| TRIG-3 | Number, Whole number, Date, Date and time get six operators; other types get "is" and "is not". |
| TRIG-4 | A saved operator that no longer fits stays, is flagged, and changes only when the administrator acts. |
| TRIG-5 | No silent choice or reset: a new trigger starts with the chosen module; an invalid step shows empty with a reason. |
| TRIG-6 | The whole trigger reads as one plain sentence that updates on each edit; missing parts read as missing. |
| TRIG-7 | The Then step offers only actions that publish (set a field on the trigger's module). |
| TRIG-8 | A new trigger can start from a module in Build, with that module chosen. |
| TEST-1 | For a chosen module, Test reads the saved draft with no typing and no run: each event, its triggers, conditions in words, and fields set. |
| TEST-2 | The reading shows relationships in both directions with the other module, its department, and carried values. |
| TEST-3 | "Try it" runs the existing evaluator on example values built from field settings, shaped only by the event, not by trigger conditions (UXD-11). A User field defaults to the signed-in administrator. |
| TEST-4 | Any example value can be changed and the run repeated; typing is never the start. |
| TEST-5 | The result says which triggers ran or not and why, field changes from → to, and linked modules. "Show test on canvas" becomes "Show on canvas". |
| TEST-6 | Test does not list what a publish creates; for a new department it points to Review and Publish. |
| TEST-7 | Runs need an explicit action; at 50 runs Test offers "Clear results". |
| TEST-8 | "Try every event" runs each event of the module in sequence and states the run count first. |
| TEST-9 | "Try this trigger" runs one trigger alone and fills only its literal same-module conditions; the result says others did not run. |
| FIT-1 | A department with no live binding has its setup choices on itself in Build; the closed control shows how many items are cleared. |
| FIT-2 | The review dialog stays the only list of what a publish creates. |
| FIT-3 | Build and the review edit the same draft `setup` value. |
| FIT-4 | A department created by the entry, a template merge or Duplicate starts from the default setup, never from the source's value. |

## Decisions

| ID | Decision |
| --- | --- |
| UXD-1 | Test is a reading plus an explicit "Try it" on editable example values; the evaluator, the 50-run store and Clear results stay. |
| UXD-2 | Bounded EXIT-3 exception (owner-approved): one canvas "Add department" plus at most two create controls for the selected element; all default-visible controls within baseline +1 (nothing selected) and +2 (element selected). |
| UXD-3 | Create controls may sit on or beside canvas frames and cards. |
| UXD-4 | The speed target is FAST-3. |
| UXD-5 | Department starting points that add (FAST-7) are in scope; module templates and new template content are out. |
| UXD-6 | Operators per type are a client rule; explicit Save triggers stays (D1). |
| UXD-7 | No silent defaults in triggers. |
| UXD-8 | Type, Required and choices set at create are saved by the create; later edits keep the per-row "Save field changes". |
| UXD-9 | FAST-5 is a browser check against `GET /sandbox/versions/{id}` (A3). |
| UXD-10 | Setup choices sit on the department in Build; the review stays the one list. |
| UXD-11 | Example values never try to meet trigger conditions (that would copy the evaluator's priority and chaining); TEST-9 shows each trigger firing. |
| OQ-1 | Owner chose (a): Test runs only on an explicit action. |
| OQ-2 | Owner chose (a): a misfit operator is a client flag, not a publish blocker. |
| OQ-3 | Owner chose (a): a run follows links one hop out; the reading shows both directions. |
| A1 | Frontend-only save queue for the entry (N1). |
| A2 | Frontend-only template department merge from `SANDBOX_ORGANIZATION_TEMPLATES`: new ids, internal relationships only, no trigger, name and limit checks, one change and one Undo step. |
| A3 | FAST-5 is frontend-only; no published version, or a missing field, gives no warning. |

## Build rules

**Element bar.** A screen-scale bar on the canvas: a department shows `+ Module` (and `Setup` when new); a module or field shows `+ Field` and `Connect`. It is visible for the selected element and on pointer rest or row focus for others. At 390px the selected element's bar is pinned to the canvas bottom with 44px controls. The canvas item menu (right-click, long press) matches the tree menu and adds "New trigger" and "Connect…" for an open module.

**The entry.** One popover for departments, modules and fields. Enter adds and keeps the parent and focus; an empty name, Escape or Done ends it. Field types are 11 one-click choices with the screen words of `fieldTypeLabel` (C8).

- **N1, save queue.** Adds queue; one `PUT /api/sandbox/document` at a time; a 409 keeps queued adds in the conflict draft. An edit waits for an empty queue and holds the page during its save. Other draft actions wait with "Saving…".
- **N2, checks before the add.** The entry refuses an invalid add in place: `buildField` rules, names of 80 characters or fewer, document limits, and a name already in use (trimmed, case-insensitive, in publish scopes). A choice reason shows under Choices.
- **N3, one change per add.** An add writes the element and its layout box in one change and one Undo step.
- **N6, relationship name.** `Connect` prefills "Orders to Customers", checked case-insensitively against the source module's field names and outgoing relationship names; a clash adds " 2", then " 3". A typed clash is refused in place.

**Setup choices.** On a new department, `Setup` opens four checkboxes (Groups, Dashboard, Category, Channel) and "Board · always created"; closed, it reads "Setup · 1 cleared". N13: new departments start from the default (FIT-4).

## Triggers rules

Three panes from 1280px: list, editor, structure region; below, an "Orders fields" button. The sentence replaces per-step summaries. Triggers and Test say "record", not "item" (`docs/specs/ux-friction-pass.md` item 9).

**B1, incomplete triggers.** (a) Changed triggers are browser-only drafts that may have empty parts. (b) Kept edits use format 2 (`{version: 2, base, triggers}`) and keep incomplete drafts. (c) Save triggers checks in the browser first: an incomplete trigger sends nothing and is marked "Incomplete".

## Test rules

Two panes from 1280px: the Modules list (footer "Results N of 50 · Clear results") and the reading of the chosen module.

- **N7, example values.** Valid for each field: the default, else a generated value inside its limits (the signed-in administrator for User). The event shapes previous values. Linked values also fit the target field.
- **N9, Try it.** Each event block with a trigger has "Try it", which sends `triggerIds: null` so every enabled trigger runs.
- **N10, run requests and stops.** Every run sends `expectedRevision`. `409 run_history_full` gives E5; `409 stale_revision` uses the reload handling. "Try every event" is disabled when it needs more runs than remain.

## States

| ID | State |
| --- | --- |
| B1 | Build, nothing selected: toolbar "Add department", tree add items. |
| B2 | Element pointed or focused: its element bar. |
| B3 | Department selected: `+ Module` (and `Setup` when new). |
| B4 | Module or field selected: `+ Field`, `Connect`; Properties without create buttons. |
| B5 | Entry open; B5c save refused; B5d add refused, reason under the name or Choices. |
| B6 | Connect open: grouped targets, prefilled name, dashed target card. |
| B7 | Type change warning with "Keep Number". |
| B8 | Add from a template dialog. |
| B9 | Setup open: four checkboxes, Board as text, SD14 line when Category is cleared. |
| B10 | Build at 390: pinned bar; entry and popovers as bottom sheets. |
| B11 | Canvas item menu. |
| B12 | Empty design (unchanged). |
| T1 | Editing a trigger: three panes, sentence, structure region. |
| T2 | New trigger: module empty and focused. |
| T3 | Field picker with types. |
| T4 | Two or six operators by type. |
| T5 | Operator does not fit: warn edge, "· saved" option. |
| T6 | Step emptied, with its reason. |
| T7 | Triggers at 390 with the fields sheet. |
| T8 | Save refused for an incomplete trigger. |
| T9 | Kept edits restored with empty parts. |
| E1 | Reading: event blocks, listening triggers, links; no run. |
| E2 | Result inline under its event: values used, what happened. |
| E3 | Change values: editable values, Edited marks, Triggers row, Run again. |
| E4 | No possible value: no request; Change values names the field once under its input ("Its settings allow no value. Enter one to run."); the fix is in Build. |
| E5 | Store full: "Results 50 of 50" with "Clear results"; Try it disabled. |
| E6 | New department module: "Review & Publish lists what publishing creates." with "Open review". |
| E7 | Empty: "Nothing to test yet" with "Open Build"; no triggers: "No trigger listens.", no Try it. |
| E8 | Try every event running ("Running 2 of 3"). |
| E9 | Test at 390: list, then the reading with Back. |
| E10 | Try this trigger result: "Set for this trigger" marks and "Other triggers on <module> did not run in this test." |
| E11 | Try every event refused: "Needs N runs; M left. Clear results first." |

## Acceptance criteria

PR #103 records a QA pass of every PR4 criterion and a smoke pass across PR1 to PR4; earlier criteria have no per-criterion result.

| ID | Criterion | Result |
| --- | --- | --- |
| UX-C1 | Pointing at a department shows its add-module control one pointer move away. | not recorded |
| UX-C2 | A selected module shows "Add field" and "Connect", named for it. | not recorded |
| UX-C3 | A field can be added from the Structure tree by keyboard only. | not recorded |
| UX-C4 | At 390 a module is added from the pane that shows the department, 44px targets. | not recorded |
| UX-C5 | Default-visible controls stay within baseline +1 / +2; helper words not above baseline. | not recorded |
| UX-C6 | Two modules are added in a row without reselecting the department; Escape on empty creates nothing. | not recorded |
| UX-C7 | Reference structure all Text: 6 clicks or fewer, 10 names or fewer. | not recorded |
| UX-C8 | With six non-Text fields: 12 clicks or fewer, types set at create. | not recorded |
| UX-C9 | Keyboard only: 0 clicks after focus enters Build. | not recorded |
| UX-C10 | Connect prefills the name from both modules; the source is the starting module. | not recorded |
| UX-C11 | Changing a published Number field to Text warns at once with "Keep Number". | met (PR #103) |
| UX-C12 | Create, Undo, Redo work with no page alert. | not recorded |
| UX-C13 | A template department keeps existing elements, takes a free name, adds no trigger. | met (PR #103) |
| UX-C14 | Trigger editing shows the module's fields, types and links without opening Build; unsaved edits stay. | not recorded |
| UX-C15 | Module pickers group by department; field pickers show types. | not recorded |
| UX-C16 | Checkbox gets two operators; Number gets six. | not recorded |
| UX-C17 | An imported misfit operator stays and is flagged. | not recorded |
| UX-C18 | Changing the event keeps the module; the field step empties with a reason. | not recorded |
| UX-C19 | Changing the module empties affected steps with reasons. | not recorded |
| UX-C20 | The sentence follows each edit; a removed action reads as missing. | not recorded |
| UX-C21 | Then offers only actions that publish. | not recorded |
| UX-C22 | The reading lists events, triggers and set fields with no `POST /api/sandbox/tests`. | not recorded |
| UX-C23 | The reading shows links in both directions. | not recorded |
| UX-C24 | Try it completes with valid values on required fields with no defaults. | not recorded |
| UX-C25 | A required User field uses the signed-in administrator. | not recorded |
| UX-C26 | Run again after a change shows ran or not, reasons, and from → to. | not recorded |
| UX-C27 | Reading adds no run; after run 50 Test shows the limit with "Clear results". | not recorded |
| UX-C28 | Test for a new department lists no derived items and points to Review and Publish. | not recorded |
| UX-C29 | Setup is on a new department, absent on a published one, and shows "1" cleared. | met (PR #103) |
| UX-C30 | Build and the review edit the same setup value. | met (PR #103) |
| UX-C31 | Non-administrators see no Sandbox (S4). | not recorded |
| UX-C32 | No page scroll from 1280px or sideways at 390. | not recorded |
| UX-C33 | "Try this trigger" on A sends `triggerIds` = [A] and says B did not run. | not recorded |
| UX-C34 | Duplicate, template merge and the entry each start from the default setup. | met (PR #103) |

## Where each capability goes

Build: the Properties create buttons and the inline create form moved to the toolbar, the element bar, the entry and Connect; the default value and cardinality stay in Properties. Triggers: step summaries became the sentence. Test: the Module select, event rows and values form became the Modules list, reading blocks and Change values; "Run test" became "Try it"; "Test this instead" became "Try this trigger"; Steps and Field comparison merged into "What happened".

## Open items

- Browser Back and Forward do not wait for the save queue (N1).
- FAST-5 gives no warning for a field missing from the latest published version; the publish blocker decides.
- A run follows links one hop out only (OQ-3).
