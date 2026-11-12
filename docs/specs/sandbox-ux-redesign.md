# Sandbox UX redesign: find, build fast, write triggers, see what happens

> **Status: approved (2026-11-10, APR-0001).** The owner approved the spec with the recommended answers (OQ-1 to OQ-3 option (a)) and UXD-2 as the EXIT-3 exception. Revision notes: proposed 2026-11-10. Requirements half by the Product Manager (TASK-0046). The Product Designer writes the design half under the headings marked "Product Designer". No product code has changed. The spec has no backend go-ahead item; the build follows APR-0001. This spec must agree with `docs/specs/sandbox-department-setup.md` (approved, APR-0001), which it does not change. Requirement half revised 2026-11-10 after the Software Architect review (UXD-11, TEST-9, FAST-5, FIT-4, UX-C33, UX-C34). N1 rules 1 and 5 amended 2026-11-11 with two decisions taken while building PR2, within APR-0001 and reviewed by the Software Architect (TASK-0048): an edit holds the page during its own save, and browser Back and Forward do not wait for the queue. E4 text aligned 2026-11-11 with PR3 as built (TASK-0049): Test names the field once, under its input in "Change values", and the fix is in Build. N2 and the item menu amended 2026-11-11 after the PR3 hands-on pass (APR-0001, TASK-0049): the entry refuses a duplicate name, and a closed module has no "Connect…". Amended 2026-11-11 after the PR3 screen review: the UXD-2 baselines are the relayout counts, and a choice reason shows under Choices.

## Outcome

An administrator who is not technical can shape the organization in the Sandbox without hunting for controls, without repeating the same pointer trip for each element, and without leaving Triggers to remember the structure. Before publishing, Test answers in plain words what happens to a record in the design, with no typing needed to start.

The owner's four concerns (hands-on use, 2026-11-10) set the scope:

| # | Concern | Requirement group |
| --- | --- | --- |
| 1 | The controls that create departments, modules, fields, and relationships are hard to find. They are all in the right panel, small, and their labels are not enough. | FIND |
| 2 | Creating a structure is tedious: go to the right panel, create one element, set its name and settings, repeat. | FAST |
| 3 | Writing triggers is confusing. The owner forgets the structure, goes to Build and back, and enters wrong values. | TRIG |
| 4 | Test gives no useful information, and "simulating" by typing data does not make sense. | TEST |
| — | The Sandbox becomes the heart of setup (department setup spec). | FIT |

**The job (all four concerns).** When I set up my organization in the Sandbox, I want to lay out its parts and rules quickly and check what they will do, so I can publish with confidence and not break what my people use. Emotional side: feel in control, not lost. Social side: the administrator does not want to publish something that colleagues then report as wrong.

**Who.** Only administrators of the bound organization use the Sandbox (S4 in `sandbox-relayout.md`). Every requirement below is for the administrator role. Other roles must still see no Sandbox navigation and the "not available" notice (preserved).

## Current state (observed at `3149165c`, 2026-11-10)

Paths are under `frontend/src/components/systems/sandbox/` unless the row says otherwise. Each line was opened and checked for this spec.

### Page

| Fact | Source |
| --- | --- |
| One route with four sections, `?section=build\|triggers\|test\|history`, and legacy aliases (`designer`, `trigger`, `simulation`, `preview`, `versions`). | `page.tsx:124-153` |
| The sections are sidebar items, shown to administrators only. | `frontend/src/components/workspace-navigation.ts:33-47`, `:220` |
| The header menu holds Save checkpoint, Start from a template, Import or export, and Discard draft changes. | `components/sandbox-header-actions.tsx:300-337` |

### Build: finding the create controls (concern 1)

| Fact | Source |
| --- | --- |
| The right workbench is 320 to 400 px wide, 360 px by default. | `helpers/view-preferences.ts:13-15` |
| The canvas toolbar holds only Zoom out, Zoom in, Fit, Auto-arrange, and View. Nothing on the canvas creates an element. | `components/designer.tsx:306`, `:325`, `:2555-2600` |
| "Add department" is a small ghost button in the Properties summary (nothing selected). | `components/designer-summary.tsx:90-100` |
| "Add module" is a small ghost button in the Properties of a selected department. | `components/designer.tsx:2416-2426` |
| "Add field" is a small ghost button in the Properties of a selected module. | `components/designer.tsx:2138-2146` |
| "Connect modules" is a small ghost button in the Properties of a selected module, disabled with fewer than two modules. | `components/designer.tsx:2358-2380` |
| The Structure tree has muted `text-xs` "Add …" rows that can be dragged onto the canvas. A dragged field is always Text. | `frontend/src/components/sandbox/sandbox-inspector-outline.tsx:597-668`, `:622-624`, `:649-650` |
| Only an empty design shows a prominent "Add your first department". | `components/empty-canvas-panel.tsx:53` |

### Build: the create loop (concern 2)

| Fact | Source |
| --- | --- |
| Each create opens an inline form. The form clears the name and resets the field type to Text and Required to off every time it opens. | `components/designer.tsx:1282-1295` (type at `:1290`) |
| The form is a real form, so Enter submits it. | `components/designer.tsx:1571` |
| A new department and a new module become the selection. A new field leaves the module selected. So the second module needs the department selected again. | `components/designer.tsx:1315`, `:1344`, `:1389-1456` |
| A field has 11 types, chosen in a native select. | `domain/model.ts:4-16` |
| A relationship opens with the selected module as source and the first other module as target; the name starts empty. | `components/designer.tsx:2368-2375`, `:1286-1288` |
| Field settings in Properties save with a separate "Save field changes" per row. | `components/designer-field-settings.tsx:574` |
| Duplicate exists only in the Structure tree item menu. | `frontend/src/components/sandbox/sandbox-inspector-outline.tsx:476-480` |
| Six organization templates exist. Applying one imports a whole bundle, which replaces the draft. | `domain/template-definitions.ts:56`, `:225`, `:401`, `:567` (six top-level `name:` entries); `page.tsx:1149-1172` |
| A type change on a published field fails only at publish (`field_type_change_blocked`); the client gives no warning while editing. | `backend/app/systems/sandbox/publications/planner.py:410-423`; no client match for the code |
| The client can already read a saved version, including the latest published one. | `state/api.ts:154`, `:630` |

**Click count for the reference structure** (1 department, 2 modules × 3 fields, 1 relationship, all Text). Counted by the Product Manager from the code paths above; it is an estimate from code, not a timed run. Rule: a click is one pointer press on a control; typing and Enter are keystrokes.

| Path | Clicks | Names typed |
| --- | --- | --- |
| Enter submits each form | 12 | 10 |
| The Create button submits each form | 22 | 10 |
| Six of the fields are not Text (Enter path) | 24 (+2 for each: open the type select, choose) | 10 |

The explore inventory of 2026-11-10 gave 21 and 11; the difference is one click for reselecting the department. The target below is a ceiling, so the difference does not change it.

### Triggers (concern 3)

| Fact | Source |
| --- | --- |
| Layout: list, then a When / If / Then rail; explicit Save triggers (D1). | `components/trigger-studio.tsx:584`; `docs/specs/sandbox-ui-ux-pass.md` D1 |
| Each step shows its own summary line; there is no one sentence for the whole trigger. | `components/trigger-rail.tsx:472-496` |
| A new trigger takes the first open module and its first field without asking. | `domain/trigger-rules.ts:435-456` |
| A new condition takes the first field and "is". | `domain/trigger-rules.ts:458-480` |
| Changing the event resets the module to the **first module of the design**, not the current one. | `components/trigger-rail.tsx:532-557` |
| Changing the module resets the event field without notice. | `components/trigger-rail.tsx:559-580` |
| A condition or action that no longer matches the module silently shows the first field of the module. | `components/trigger-rail.tsx:846-851`, `:1003-1008` |
| The module picker is a flat list of names, with no department. Build's relationship dialog groups modules by department. | `components/trigger-rail.tsx:317-329`; `components/designer.tsx:188-200` |
| Field pickers show the name only, with no type. | `components/trigger-rail.tsx:331-341` |
| All six operators are offered for every field type. | `components/trigger-flow.tsx:33-39`; `components/trigger-rail.tsx:895-900` |
| The evaluator compares text with `>`/`<` alphabetically and returns false for `>`/`<` on Checkbox or an empty value. The publish rules do not check operators. | `backend/app/systems/sandbox/test_runs/trigger_values.py:38-63`; `backend/app/systems/sandbox/publications/rules.py` |
| Only `set-field` on the trigger's own module publishes. | `backend/app/systems/sandbox/publications/rules.py:43-67`; `docs/architecture/21-glossary.md:49` |

### Test (concern 4)

| Fact | Source |
| --- | --- |
| The user picks one module and one event, then types values. Start values are only the field defaults; a Person field starts empty. | `components/test-workspace.tsx:125-153`; `domain/test-setup.ts:27-37` |
| A required field with no value stops the run with "Enter a value for this required field." | `backend/app/systems/sandbox/test_runs/evaluator.py:154-187` (`:184`) |
| `POST /api/sandbox/tests` runs the pure `evaluate_test` on the saved draft and stores the evidence. | `backend/app/systems/sandbox/test_runs/evaluator.py:33-97`; `service.py:39-88` |
| The store refuses a new run at 50 runs (`run_history_full`, 409) until the user clears results. | `backend/app/systems/sandbox/test_runs/service.py:28`, `:46-49` |
| Linked records: only relationships that start at the chosen module, one hop. | `backend/app/systems/sandbox/test_runs/relationships.py:39` |
| Conditions on another module are refused. | `backend/app/systems/sandbox/test_runs/evaluator.py:417` |
| The result shows a headline, Steps, Field comparison, a closed "Values used" and "Linked records used", "Test only · live data unchanged", and "Show test on canvas". | `components/test-run-result.tsx:204`, `:259`, `:342`, `:417`, `:432`, `:498-500` |
| The product promise: a simulation shows how data moves through the structure; Test inputs never create records. | `PRODUCT.md:36-43`, `:81-91` |

**Gap.** Test asks the administrator to invent data before it says anything. It answers "what did my typed values do", not "what happens when people use this module". It shows movement only one hop out, behind a closed disclosure.

## Requirements

Each requirement is for the administrator. Priority: P0 = the concern is not answered without it; P1 = a strong improvement that can follow. Requirements state outcomes; the Product Designer decides layout, controls, and words.

### FIND: the create controls (concern 1)

| ID | Pri | Current | Required |
| --- | --- | --- | --- |
| FIND-1 | P0 | Create controls exist only in the right workbench, as small ghost buttons or muted rows. | Each create action (department, module, field, relationship) is reachable **within one pointer move of the element it adds to**: at the parent element on the canvas, and at the parent row in the Structure tree. "Add department" is reachable at the canvas level with nothing selected. |
| FIND-2 | P0 | "Add field" and "Add module" appear only after the parent is selected in Properties. | The create action of an element is visible without opening a panel or a menu when that element is selected, and discoverable (visible on hover or focus) when it is not. Exact rule: Product Designer. |
| FIND-3 | P0 | The Properties buttons name the kind only ("Add field"). The Structure tree rows already name the parent in their accessible name (`frontend/src/components/sandbox/sandbox-inspector-outline.tsx:614`, `:645`). | Each create control names its result and its parent in its accessible name ("Add field to Orders"). Visible labels keep R3 (3 words or fewer). |
| FIND-4 | P0 | The canvas has no keyboard route; the Structure tree is the keyboard route (EXIT-9). | Every create action is reachable by keyboard from the Structure tree or the selected element, with a visible focus. |
| FIND-5 | P0 | At 390 px Build is three pane tabs. | At 390 px each create action is reachable from the pane that shows the parent, with 44 px targets. |
| FIND-6 | P1 | Duplicate exists only in the Structure item menu. | Duplicate is reachable from the element on the canvas too (same one-pointer-move rule). |

### FAST: building a structure (concern 2)

| ID | Pri | Current | Required |
| --- | --- | --- | --- |
| FAST-1 | P0 | After a create, the form closes; the next sibling needs a new trip, and the second module needs the department reselected. | After a create, the administrator can add the next sibling (module after module, field after field) at once, without a pointer trip and without reselecting the parent. The flow ends on Escape or an empty name, with nothing created by the empty entry. |
| FAST-2 | P0 | The field type is a native select in the form and resets to Text on every open. | The type (and Required) can be set while naming the field, in the same flow, by pointer or keyboard. A non-Text type costs at most one more action than a Text field. |
| FAST-3 | P0 | 12 clicks with Enter (22 with Create) for the reference structure. | Reference structure, all Text: **6 pointer clicks or fewer**, 10 names or fewer. Six fields of other types: **12 pointer clicks or fewer** in total. A keyboard-only path exists: 0 pointer clicks after focus enters Build. |
| FAST-4 | P0 | The relationship name starts empty. | The relationship name is prefilled from its two modules and can be changed. Source and target default from the context the administrator started in. |
| FAST-5 | P0 | A field type change on a published field fails only at publish. | When the administrator changes the type of a field that the latest published version has with another type, a warning shows at that moment, before the change is kept, with the reason in one line and the choice to keep the old type (R2 "before"). A warning, not a refusal: the draft may still be changed, and the publish blocker stays the final check. A field matches on the pair (module id, field id), the published identity of a field (`backend/app/systems/sandbox/publications/rules.py:147-151`, `_field_key`), not on the field id alone. Source of truth: the latest published version, read with the existing `GET /sandbox/versions/{id}` (`state/api.ts:154`, `:630`), one read per published version. No warning when no version is published, and none for a field that an earlier version published but the latest published version does not have (known gap; the publish blocker still decides). |
| FAST-6 | P0 | Each element is created one by one; no undo cue for a batch. | Each create is one undoable step in the existing Undo/Redo, and feedback stays inline (R2 ladder step 1): the new element appears where it was added, named. |
| FAST-7 | P1 | Templates exist only for a whole organization and replace the draft. | The administrator can **add** one department from the departments in the six existing organization templates, with its modules, fields, and the relationships between its own modules. The add never replaces or changes existing elements. The name of the added department never equals an existing department name; the administrator sees and can change it before it is added. Triggers are not added. |

### TRIG: writing triggers (concern 3)

| ID | Pri | Current | Required |
| --- | --- | --- | --- |
| TRIG-1 | P0 | The structure is not visible in Triggers; the owner goes to Build and back. | While editing a trigger, the administrator sees, in Triggers and without losing unsaved trigger edits: the trigger module's department, its fields with their types, and the modules it links to. From 1280 px this is visible beside the editor; at 390 px it is one action away and returns to the same place. |
| TRIG-2 | P0 | The module picker is a flat list; field pickers show names only. | Every module picker groups modules by department (as Build's relationship dialog does). Every field picker shows each field's type. |
| TRIG-3 | P0 | All six operators for every type. | Only operators that make sense for the field type are offered: Number, Integer, Date, Date/Time get all six; Text, Long text, Select, Email, URL, Person (User), and Checkbox get "is" and "is not". |
| TRIG-4 | P0 | A saved trigger may already hold an operator that TRIG-3 no longer offers. | Such a trigger keeps its operator. The step shows that the operator does not fit the field type and offers the valid ones. Nothing changes until the administrator changes it. |
| TRIG-5 | P0 | A new trigger silently takes the first module and first field; changing the event resets to the first module of the design; changing the module silently resets fields, conditions, and actions. | No silent choice and no silent reset. A new trigger starts with the module chosen by the administrator (or from the context the administrator came from, for example a selected module in Build). Changing the event keeps the module when the module fits the event. When a change makes a chosen field invalid (a threshold needs a number field; a module change), the step shows it as empty with a reason, and the administrator chooses. |
| TRIG-6 | P0 | Each step has its own summary; no whole reading. | The whole trigger reads as one plain-language sentence, updated as the administrator edits ("When a record is added to Orders, if Amount is at least 100, set Status to Review"). Empty parts read as missing, not as a default. The sentence composes or replaces the per-step summaries, so the same fact does not show twice (R3.4); the Product Designer decides which stays. The sentence is trigger content, not helper text, so it does not count against the Triggers helper-word baseline. |
| TRIG-7 | P0 | Only same-module set-field publishes (glossary: partially implemented). | The Then step offers only actions that publish. The trigger capability does not widen. |
| TRIG-8 | P1 | Triggers start only from the Triggers list. | The administrator can start a new trigger from a module in Build, with that module chosen (TRIG-5). |

### TEST: what happens before publish (concern 4)

The questions an administrator needs answered before publishing, in plain words:

1. When someone adds a record to this module, what happens on its own?
2. When someone changes this field, what happens?
3. Which other modules is this record linked to, and which values go there?
4. Does any rule never run, run on the wrong field, or stop with a problem?
5. What will the publish create and change, and who will see it? (Answered by Review and Publish; see TEST-6.)

| ID | Pri | Current | Required |
| --- | --- | --- | --- |
| TEST-1 | P0 | Test starts with a blank module, event, and value form. | For a chosen department or module, Test shows a **reading of the design** with no typing and no run: for each event of each module (record added, each watched field changed, threshold crossed, schedule), the triggers that listen to it with their conditions in words, and the fields they set. Modules and triggers come from the saved draft. |
| TEST-2 | P0 | Linked records show one hop out, inside a closed disclosure. | The reading shows the module's relationships in both directions (links out and links in), with the related module and its department, and the values a link carries where the design defines them. |
| TEST-3 | P0 | Running needs typed values; a required field with no default stops the run. | "Try it" runs the existing evaluator on example values that Test builds from field types, defaults, choices, and limits. The values are valid for each field and shaped only by the event (a previous value for Field changed; a previous and a new value for Threshold crossed). They do **not** try to meet any trigger's conditions (UXD-11); the administrator meets a condition through "Change values" (TEST-4) or "Try this trigger" (TEST-9). The run raises no `value_required` or `value_invalid` for a field that can have an example. A Person field with no default takes the signed-in administrator as its example (the evaluator accepts any well-formed UUID, `backend/app/systems/sandbox/test_runs/evaluator.py:236-242`; the page already reads the administrator's `id` from `GET /auth/me`, `frontend/src/lib/auth-api.ts:63-64`, `page.tsx:672`), editable in "Change values". Only a required field whose settings allow no valid value is named and asked for. |
| TEST-4 | P0 | Typed values are the only input. | The administrator can change any example value and run again. Typing is optional, never the start. |
| TEST-5 | P0 | The result headline and steps exist; the field comparison is below. | The run result answers questions 1 to 4 for that record: which triggers ran, which did not and why (not triggered, conditions not met, needs attention), which fields changed from what to what, and the linked modules. "Show test on canvas" stays, renamed "Show on canvas" (R3, 3 words or fewer), with the same behavior. |
| TEST-6 | P0 | Not in Test. | Test does not repeat the list of items a publish creates (department setup spec SD6, R11). For a new, unpublished department, Test points to Review and Publish for that list. |
| TEST-7 | P0 | A run stores evidence; at 50 runs the store refuses. | A run happens only on an explicit action (no run on selection or on page load), so reading the design never fills the store. At the limit, Test says so and offers "Clear results" (existing route). |
| TEST-8 | P1 | Each run tests one event. | One action runs every event of the chosen module in sequence. Each event is one run; the action states how many runs it uses before it starts. |
| TEST-9 | P0 | No way to see one trigger fire without inventing the values that meet its conditions. | Each listening trigger that is on has "Try this trigger". It runs that trigger alone: the request sends `triggerIds` with that one trigger (the evaluator then runs only it at every depth, `evaluator.py:269`, `:276-333`), the trigger's own event, and the TEST-3 example values. Before the run, Test changes only the values that this trigger's conditions need: each condition whose field is on the trigger's module and whose value is a literal gets a value that meets it. For Field changed, a condition on the watched field sets the new value, and the previous value stays different from it. A condition that compares with another field, a condition on the field that a Threshold crossed event fixes, and two conditions on one field that cannot both hold keep the TEST-3 value. So does a condition whose value would be invalid for the field or for a linked target field; in an "any" group only the first fillable condition is filled. When a kept value does not meet a condition, the result says "conditions not met" with the reason. The result states that the other listening triggers did not run in this test. No order, priority, or chain of other triggers is copied into the browser. One action is one run (TEST-7). |

### FIT: the department setup spec

| ID | Pri | Current | Required |
| --- | --- | --- | --- |
| FIT-1 | P0 (with setup slice 4) | Not built. Setup spec R14, SD13, BE-SD5: the draft `setup` object per department. | For a department that has no live binding, its setup choices (groups, dashboard, category, channel; the Board cannot be cleared) are reachable from the department itself in Build, under the same one-pointer-move rule as FIND-1. When closed, the control shows how many items are cleared (R1.4). For a published department the choice does not appear. |
| FIT-2 | P0 (with setup slice 1) | Setup spec SD6: the review lists derived items under each new department. | The review dialog stays the only list of what a publish creates. Build and Test do not copy it (R3.4). |
| FIT-3 | P0 (with setup slice 4) | Setup spec SD13: the review clears an item by editing the draft and reviewing again. | Build and the review edit the same draft `setup` value. A change in one shows in the other after the next review. |
| FIT-4 | P0 | — | A department created by FAST-1, by FAST-7 (template merge), or by Duplicate starts from the same default as any new department: all on until setup slice 5, the Manage default (setup spec SD2, BE-SD6) after it. No path copies or invents its own setup value. |

## Decisions

| ID | Decision | Removes or excludes |
| --- | --- | --- |
| UXD-1 | **Test job (concern 4): option (b), with the editable values of (a); not (c); not (d).** Test becomes a reading of the design (TEST-1, TEST-2) plus an explicit "Try it" run on generated example values (TEST-3 to TEST-5). It keeps the backend `evaluate_test`, `POST /api/sandbox/tests`, stored evidence, the 50-run limit, Clear results, Show test on canvas (renamed "Show on canvas", TEST-5), and the URL `?section=test` with its aliases. The reading is computed in the browser from the saved draft; the reading sends no `POST /sandbox/tests`, so it needs no backend change. The results count ("Results N of 50") reads the `total` of the existing `GET /sandbox/tests` (`backend/app/systems/sandbox/test_runs/schemas.py:115`; the list adapter `listSandboxTests` returns only `{ items }`, `state/api.ts:538-550`, so it adds `total`, browser-only). `total` and the refusal count both count runs that are not cleared (`test_runs/service.py:92-95`, `:164-173`), so "Results N of 50" is exact.. The run stays the only place that says what *did* fire. | The blank form as the start of Test; typing as a condition for the first answer; "Values used" as the primary input. Option (c) in Test: a second list of derived items would break R3.4 and duplicate SD6. Option (d): it would remove the product's stated differentiator (`PRODUCT.md:36-43`). |
| UXD-2 | **Bounded EXIT-3 exception (concern 1).** The owner's concern 1 (2026-11-10) is the owner-approved addition that EXIT-3 requires. Bound: in each measured Build state, the default-visible create controls are at most **one canvas-level "Add department"** plus the create controls of the **selected element** (department: add module; module: add field, connect; at most 2 in any state). Create controls of other elements show only on hover or focus. No new permanent helper text. The Product Designer may remove the duplicate create buttons from Properties; each removal gets a destination in "Where each capability goes". Two counts apply and stay separate: (1) **create controls** shown by default, bound as above; (2) **all default-visible controls** against the relayout baseline (UX-C5): at most +1 with nothing selected and +2 with a department or module selected. The Structure tree "Add …" items were in the baseline; they stay always visible and count in neither addition. The hover-only rule covers the new canvas controls only. FIT-1 `Setup` on a new department is not a create control, but it is a default-visible control: with `+ Module` it reaches the +2 ceiling of count (2). This holds only because Duplicate and New trigger sit in the canvas item menu, not in the element bar; any further default-visible control on a department needs a removal. | The EXIT-3 baseline ceiling for these create controls only. It does not lift the ceiling for any other control or for helper words. Headroom: none left for a selected new department after setup slice 4. |
| UXD-3 | **Create controls on the canvas.** Create controls may sit on or beside canvas frames and cards. The DESIGN.md "Sandbox canvas (signature)" section is updated by `impeccable` in the design half. | The relayout exclusion "the canvas itself stays as it is" (`sandbox-relayout.md`, Outcome) for create controls only. Frames, cards, lines, labels, Key, and minimap stay. |
| UXD-4 | **Speed target (concern 2):** FAST-3 ceilings (6 clicks all Text; 12 with six non-Text fields; a keyboard-only path). Counted by the rule in Current state. | The one-element-per-trip loop. |
| UXD-5 | **Starting points.** Department-level starting points that **add** (FAST-7) are in scope as P1, built only from the departments already in the six organization templates; no new template content. Module-level starting points are out. | Module templates (fields vary too much by organization; Duplicate covers copying a module). New template authoring. Adding triggers with a template department (they need Save triggers and their own review). |
| UXD-6 | **Trigger clarity (concern 3):** TRIG-1 to TRIG-6. Operators per type are a client rule (TRIG-3); no backend change. Explicit Save triggers stays (D1): a trigger is valid only when complete. | Operators "is greater than" etc. on Text, Long text, Select, Email, URL, Person, and Checkbox for new choices. Today they compare alphabetically or always fail (`trigger_values.py:53-63`), so no working rule is lost; existing ones stay (TRIG-4). |
| UXD-7 | **No silent defaults in triggers.** A new or changed step never takes "the first" module or field on its own (TRIG-5). | The quick start where a new trigger is already "complete" with the first module and field. One more choice for a new trigger. |
| UXD-8 | **Field settings at create.** Type, Required, and Select choices set during creation are saved by the create itself (FAST-2). Later edits of an existing field keep the per-row "Save field changes" (classification in `sandbox-ui-ux-pass.md`, field row). | The Properties round trip after creation as the only way to set type, Required, and Select choices. |
| UXD-9 | **Published field type (FAST-5)** is checked in the browser against the latest published version, matched on (module id, field id), read with the existing `GET /sandbox/versions/{id}`. The Software Architect confirmed no backend change (A3). | A publish-time-only discovery. It does not cover a field missing from the latest published version (FAST-5 gap). |
| UXD-10 | **Fit (concern "heart of setup"):** setup choices on the department in Build (FIT-1); the review stays the one list (FIT-2). This spec does not change the department setup spec. | Setup choices in Test, or a second derived-items list. |
| UXD-11 | **Example values (TEST-3, TEST-9): option (b).** Example values are valid for each field and shaped only by the event. They never try to meet the conditions of the listening triggers as a set: the evaluator runs triggers by priority, each action changes values before the next trigger's conditions are checked, and changes chain up to 10 levels (`evaluator.py:276-333`), so a browser generator would have to copy the evaluator. Instead "Try this trigger" (TEST-9) runs one trigger alone and fills only its literal same-module conditions, so each trigger can be shown firing (concern 4: typing data to simulate "does not make sense"). Option (a), without TEST-9, was not chosen: a typical "Try it" would end "conditions not met" and leave the administrator to type values again. | The design rule that example values aim to meet the listening triggers' conditions in list order (Product Designer, Test "Try it"; the Designer removes it). A guarantee that the event-level "Try it" shows a trigger firing. Any browser copy of trigger priority or chaining. |

## Exclusions

- New trigger capabilities: actions on other modules, messages, or cross-module conditions (glossary: partially implemented). TRIG-7 keeps the current set.
- Changes to the evaluator, the test-run API, or the store limit, unless the owner chooses otherwise in OQ-1 or OQ-3.
- Autosave for triggers (D1 stays).
- The per-row "Save field changes" for edits of an existing field.
- Module-level templates; new template content; organization templates that replace the draft stay as they are.
- History, the header menu, Review and Publish layout (except FIT-2 and FIT-3), and the canvas parts named in UXD-3.
- Renaming "module" (owner decision 2026-10-18, `docs/specs/sandbox-followup-pass.md:122`).
- Anything in the department setup spec; conflicts go to open questions.
- Final layout, controls, and words (Product Designer).

## Preserved behavior

- S4: the Sandbox is hidden from non-administrators; a direct link shows "Sandbox is not available to your account."
- The Access grammar of `sandbox-relayout.md`: slim 40 px rows from 1280 px, label-left rows, one main action per section, Advanced last.
- No page scroll at 1280×720, 1440×900, 1920×1080; no sideways scroll at 390; targets of 44 px or more at 390 (EXIT-8, EXIT-9).
- R1 (essentials first; lifecycle actions in Advanced), R2 (feedback ladder), R3 (labels of 3 words or fewer; helper line of 12 words or fewer; a fact in one place), D3 (dialog buttons) from `sandbox-ui-ux-pass.md`.
- Explicit Save triggers, the unsaved count in the header chip, and Save · Discard · Stay on leave (D1).
- Draft autosave, conflict handling, Undo/Redo, the publish contract, and section URLs with their aliases.
- Test inputs never create operational records; "Test only · live data unchanged" stays true.
- "Show test on canvas" keeps its behavior; only its label changes to "Show on canvas" (TEST-5).
- The canvas signature parts listed in UXD-3; the Structure tree as the keyboard route.
- "Module" as the in-product word.

## Acceptance criteria

Each criterion is checked on the live development stack as `admin@harbor.test` (existing data) and on a fresh organization, at 1440×900 and 390×844, unless the row says otherwise.

| ID | Req | Start state | Action | Expected result |
| --- | --- | --- | --- | --- |
| UX-C1 | FIND-1 | Build with one department "Sales" and one module "Orders"; nothing selected | Point at "Sales" on the canvas | An add-module control for Sales is reachable with one pointer move from the Sales frame; no panel or menu was opened. |
| UX-C2 | FIND-1, FIND-2 | Same; "Orders" selected | Look at the screen without moving the pointer | "Add field" and "Connect" for Orders are visible on or next to Orders and named for it ("Add field to Orders" as accessible name). |
| UX-C3 | FIND-4 | Same; focus in the Structure tree on "Orders" | Use only the keyboard to add a field | A field is created under Orders with no pointer use; focus is visible at every step. |
| UX-C4 | FIND-5 | 390×844, same design | Add a module to Sales, from the Structure pane item or from the pinned bar after Sales is selected | The action is in the pane that shows Sales; every target on the path is at least 44 px. A tap on the scaled canvas drawing itself is not measured (canvas cards scale with zoom). |
| UX-C5 | UXD-2 | 1440×900; each Build state of the relayout baseline (nothing selected, department, module, field expanded) | Count default-visible controls and helper words | Controls are at most baseline + 1 (nothing selected) and baseline + 2 (department or module selected); helper words are not above the baseline. |
| UX-C6 | FAST-1 | A department "Sales" with no modules | Add module "Orders", then type "Invoices" without any pointer action | Both modules exist under Sales; Sales was never reselected. Escape on an empty entry creates nothing. |
| UX-C7 | FAST-3 | Empty design (fresh organization) | Build 1 department, 2 modules × 3 Text fields, 1 relationship by pointer and typing; count clicks by the rule in Current state | 6 pointer clicks or fewer; 10 names typed or fewer; the design matches the reference structure. |
| UX-C8 | FAST-2, FAST-3 | Same | Build it with six fields of six different non-Text types | 12 pointer clicks or fewer; each field has the chosen type after creation with no Properties edit. |
| UX-C9 | FAST-3 | Same | Build it with the keyboard only | 0 pointer clicks after focus enters Build; same result. |
| UX-C10 | FAST-4 | Modules "Orders" and "Customers" | Start a relationship from Orders | The name is prefilled from both modules; the source is Orders. |
| UX-C11 | FAST-5 | A published field "Amount" of type Number | Change its type to Text in Build | A one-line warning shows at once with the choice to keep Number; no publish attempt is needed to see it. |
| UX-C12 | FAST-6 | Any design | Create a field, then Undo | The field is gone; Redo brings it back. No page alert appears. |
| UX-C13 | FAST-7 | A design with "Sales" | Add the "Sales" department from an organization template | The draft keeps every existing element unchanged; a new department with a name other than "Sales" appears with its modules, fields, and internal relationships; no trigger was added; a fresh review lists it as new with the default setup. |
| UX-C14 | TRIG-1 | Triggers, editing a trigger on Orders with an unsaved change | Look for Orders' fields and types and its linked modules | They are visible beside the editor at 1440, one action away at 390; the unsaved change and the header count stay. Build was not opened. |
| UX-C15 | TRIG-2 | Two departments with modules | Open the module picker and a field picker | Modules are grouped under their department; each field shows its type. |
| UX-C16 | TRIG-3 | A condition on a Checkbox field, then on a Number field | Open the operator choice | Checkbox: "is" and "is not" only. Number: all six. |
| UX-C17 | TRIG-4 | A saved trigger with "is greater than" on a Text field (set through import) | Open it | The operator stays as saved; the step shows it does not fit the type; nothing is changed until the administrator acts. |
| UX-C18 | TRIG-5 | A trigger on "Invoices" (not the first module), event "Record added" | Change the event to "Field changed" | The module stays "Invoices"; the field step is empty with a reason until chosen. |
| UX-C19 | TRIG-5 | A trigger on Orders with one condition and one action | Change the module to Customers | No field is replaced by "the first field" without notice; each affected step shows empty with a reason. |
| UX-C20 | TRIG-6 | A complete trigger | Edit its condition value | The one-sentence reading changes in step with the edit; a removed action reads as missing. |
| UX-C21 | TRIG-7 | Any trigger | Open the Then choices | Only actions that publish are offered. |
| UX-C22 | TEST-1 | Harbor; Test opened for a module with two triggers | Open Test and choose the module; type nothing | The reading lists each event with the triggers that listen and the fields they set. No request to `POST /api/sandbox/tests` was sent (network). |
| UX-C23 | TEST-2 | A module that is the target of one relationship and the source of another | Open its reading | Both relationships show, with the other module and its department. |
| UX-C24 | TEST-3 | A module with required Number, Date, Select, and Checkbox fields and no defaults | "Try it" | The run completes with no `value_required` or `value_invalid` issue; the values used are visible and valid for their fields. |
| UX-C25 | TEST-3 | A module with a required Person field with no default | "Try it" | The run completes with no `value_required` issue; the Person value used is the signed-in administrator, and "Change values" can change it. Nothing is asked for before the run. |
| UX-C26 | TEST-4, TEST-5 | A completed run | Change one example value and run again | The new result shows which triggers ran or did not and why, and each changed field from its old to its new value. |
| UX-C27 | TEST-7 | 49 stored runs | Open Test, choose modules, read; then "Try it" twice | Reading adds no run. The first "Try it" stores run 50; the second shows the limit with "Clear results", and no error page. |
| UX-C28 | TEST-6, FIT-2 (with setup slice 1) | A new, unpublished department (after setup slice 1, which builds the review list) | Open Test for it | Test does not list groups, dashboard, Board, category, or channel; it points to Review and Publish. |
| UX-C29 | FIT-1 | A new department and a published department (after setup slice 4) | Select each in Build | The setup choice is reachable from the new department (one pointer move) and absent for the published one; with one item cleared, the closed control shows "1" cleared. |
| UX-C30 | FIT-3 | A new department with "channel" cleared in Build | Open Review and Publish | The review lists no channel for it (setup spec SD-C18 holds). Re-enabling it in the review and reviewing again shows it in Build. |
| UX-C31 | Preserved | `general.noaccess@harbor.test` and a department manager account | Open `/sandbox` | No Sandbox navigation; the "not available" notice; no refused request. |
| UX-C32 | Preserved | Every new state | 1280×720, 1440×900, 1920×1080, 390×844 | No page scroll from 1280 px; no sideways scroll at 390. |
| UX-C33 | TEST-9 | Orders with trigger A (priority 1, "if Amount is at least 100, set Status to Review") and trigger B (priority 2, "if Status is Open, set Owner"); example Amount is 1 and example Status is Open | "Try this trigger" on A | One `POST /sandbox/tests` with `triggerIds` = [A]; Amount used is at least 100; A ran and Status changed from its example value to Review; the result states that B did not run in this test. "Try this trigger" on a trigger whose condition compares two fields runs with the example values and reads "conditions not met" with the reason. |
| UX-C34 | FIT-4 | After setup slice 4: a new department with "channel" cleared | Duplicate it; add a department from a template; add one by the entry | Each new department starts with the default setup (all on before slice 5; the Manage default after it), not with the cleared channel of the source. |

## Owner decisions (resolved 2026-11-10, APR-0001)

The owner also approved UXD-2 as the owner-approved EXIT-3 exception.

| ID | Question | Options and what each removes | Decision |
| --- | --- | --- | --- |
| OQ-1 | **Should Test run on its own each time a module or event is chosen?** Today every run is stored, and the store refuses at 50 (`service.py:28`, `:46-49`). | (a) Explicit "Try it" (default in this spec): no backend change; removes automatic answers, one action per run. (b) A new evaluate-only route that stores nothing, used on every choice: removes the extra action and the risk of a full store; adds a public API route (backend go-ahead) and a second path that must stay equal to the stored one. | **(a), owner, 2026-11-10 (APR-0001).** The reading (TEST-1, TEST-2) already answers without a run; a run is only for "what fires with these values". Revisit after hands-on use. |
| OQ-2 | **Should publish also block an operator that does not fit its field type?** | (a) Client rule only (default): no backend change; removes nothing; an imported trigger with such an operator can still publish and behaves as today. (b) A new publish blocker: removes that case; adds a blocker code (wire format change) and can block publishes of existing drafts. | **(a), owner, 2026-11-10 (APR-0001).** No working rule depends on these operators, and TRIG-4 shows the problem in the editor. |
| OQ-3 | **Should a run follow links in both directions and beyond one hop?** Today the evaluator follows one hop out (`relationships.py:39`). | (a) No (default): the reading shows both directions without values; the run keeps one hop out. Removes nothing. (b) Extend the evaluator: removes the gap between reading and run; changes the evaluator and the stored result shape (backend go-ahead). | **(a), owner, 2026-11-10 (APR-0001).** Published triggers act only on their own module, so movement beyond one hop has no rule to show yet. |

**Not owner questions, for the record.**

- Glossary rows are needed in `docs/architecture/21-glossary.md` for any new term the design half introduces (for example the name of the Test reading). This spec creates one file only, so the row is added with the build.
- FAST-5 assumption, resolved in the Software Architect review: the published identity of a field is the pair (module id, field id), not the field id alone (`rules.py:147-151`). FAST-5 matches on that pair against the latest published version from the existing `GET /sandbox/versions/{id}`, so it needs no backend change (A3). Known gap: a field that an earlier version published but the latest published version does not have gets no warning; the publish blocker stays the final check.
- Software Architect review, 2026-11-10: no public API, schema, storage, or wire-format change. A1 (save queue) and A2 (template department merge) are frontend-only.

## Design rules and states (Product Designer)

Base revision `3149165c`. Skills: `ui-ux-pro-max` set the structure, flows, and interaction below; `impeccable` set the visual treatment inside it (`DESIGN-RULES.md`). The comps use Slate dark, the theme of the hands-on references in `.playwright-mcp/sandbox-relayout/final/`. Every rule below keeps the Access grammar: slim 32 px controls and 40 px rows from 1280 px, label-left rows, one main action per section, Advanced last, 44 px targets below 1280 px.

### Structure choices

| Choice | Options considered (what each removes) | Chosen |
| --- | --- | --- |
| Where a create starts | (a) Buttons inside the scaled canvas drawing: unreadable at 50 % zoom, and below 44 px at 390. (b) Properties only: keeps the trip to the right panel that concern 1 names. (c) A small bar at the element, drawn at screen scale over the canvas, plus the existing Structure rows. | (c), the **element bar**. |
| Where the add-next entry lives | (a) An input inside the canvas card: unreadable at low zoom, and it fights canvas pan keys. (b) A form in Properties: the result appears far from the entry. (c) A popover anchored to the control that opened it, beside the element that grows. | (c), the **entry**. One component, anchored to the element bar or to the Structure row. |
| Where the Test result appears | (a) Its own pane: at 1280 px a third pane leaves the reading too narrow. (b) A dialog: hides the reading it explains. (c) Inline, under the event block that ran. | (c). The result sits in reading order, under the question it answers. |
| Where Triggers shows the structure | (a) A tab inside the list pane: hides the list while editing. (b) A dialog: hides the editor. (c) A third pane beside the editor. | (c), the **structure region**. |

### Build: find and create (FIND, FAST, FIT)

**Canvas level.** "Add department" is the first control of the canvas toolbar, always visible. It opens the entry for departments.

**Element bar.** A small raised bar on the canvas, drawn at screen scale (not canvas scale), so it reads the same at every zoom.

| Element | Bar holds | Anchor |
| --- | --- | --- |
| Department | `+ Module`; for a department with no live binding (after setup slice 4), `Setup` | In the head band, after the name. It never covers the name or the module count. |
| Module | `+ Field`, `Connect` | Under the card, aligned left, where the next field appears. It flips above the header when the card bottom is out of view. |
| Field (selected in Properties or the tree) | The bar of its module | As for the module |

- Visible without any pointer action for the selected element only. For any other element it shows on pointer rest (120 ms) or on focus of its Structure row, and it stays 300 ms after the pointer leaves, so the pointer can reach it. It hides while the canvas pans, zooms, or drags.
- Touch: a tap selects the element, and its bar shows. At 390 px the bar of the selected element is pinned to the bottom of the canvas pane: the element name, then the controls, all 44 px.
- Accessible names name the result and the parent: "Add module to Sales", "Add field to Orders", "Connect Orders to another module", "Setup for Field service: 1 item cleared" (FIND-3). Visible labels are one word.
- `Connect` with fewer than two modules is disabled and keeps the reason "Add a second module first." (`DisabledReason`, on hover and focus).

**Item menu on the canvas (FIND-6, TRIG-8).** Right-click or long-press on a department, module, or field opens the same item menu as the Structure tree (Rename, Duplicate, Close or Reopen, Delete). A module's menu adds "New trigger" (TRIG-8) and "Connect…". A closed module's menu holds neither of them. The bar holds no "More" button, so the UXD-2 bound holds (see the count table).

**The entry (FAST-1, FAST-2, FAST-6).** One popover for departments, modules, and fields, anchored to the control that opened it.

| Part | Department | Module | Field |
| --- | --- | --- | --- |
| Title | "Add department" | "Add module to Sales" (with the department mark) | "Add field to Orders" (with the department mark) |
| Name | Focused at open | Focused at open | Focused at open |
| Type | — | — | 11 one-click choices in a radio group, in model order, with the screen words (Text, Long text, Number, Whole number, Date, Date and time, Checkbox, Choice list, User, Email, Web link). Text is chosen at open. |
| More | "From a template" link (FAST-7) | — | Required checkbox. Choice list shows a "Choices" input (comma-separated) and moves focus to it. |
| Footer | Done · Add department | Done · Add module | Done · Add field |

**Type words (C8).** One screen word per type wherever a type shows: the entry, the pickers, the structure region, the FAST-5 notice, and the Properties Type select. Default: the entry uses `FIELD_TYPES.name`; if the new words stay, the Properties select labels change in the same slice (a label map; the per-row save is untouched), and the glossary row maps each screen word to its model name. **Chosen: the new words stay** (Text, Long text, Number, Whole number, Date, Date and time, Checkbox, Choice list, User, Email, Web link). The label map already exists: `fieldTypeLabel` (`domain/model.ts:19-33`), and the Properties Type select already renders `fieldTypeLabel(entry.name)` (`components/designer-field-settings.tsx:475-477`), as the canvas type labels do. So the select needs no change in this slice; the entry, the pickers, the structure region, and the FAST-5 notice call `fieldTypeLabel` too, and the glossary row maps each screen word to its model name (Whole number = Integer, Date and time = Date/Time, Choice list = Select, Web link = URL).

- Enter in any control of the entry adds the element, clears the name, resets the type to Text and Required to off, and keeps focus in the name. The parent stays the parent; nothing is reselected.
- Enter on an empty name, Escape, or Done ends the flow. The empty entry creates nothing. Focus returns to the control that opened the entry; the last created element becomes the selection.
- Keyboard inside the entry: Tab moves name → type group (one Tab stop; arrows and type-ahead choose) → Required → buttons. Clicking a type returns focus to the name, except Choice list, which moves focus to Choices.
- The new element appears at once where it was added (the next row of the card, the next slot of the frame, the next free slot right of the existing frames for a department), named, with a quiet **saving mark**: muted ink and a small ring at the row end, never an error. The mark clears when the save confirms. The newest row keeps the `--flow` tint until the next add (FAST-6, R2 step 1).
- Each element is one Undo step, and the header Undo stays enabled while adds are saving (rule 4 below). No page alert.
- When the canvas pans to show a new element out of view, it moves at once. No animated pan (motion only on the acted element).
- **Checks before the add (N2).** Several adds can join one save, and one bad element would refuse the whole batch with 422. So the entry checks each add in the browser before it changes the draft, and refuses it in place, under the name, with the reason; the name stays for correction. A choice reason ("Add at least one choice." and the other choice reasons) shows under the Choices input instead, with `aria-invalid` and focus on Choices. Checks: the `buildField` rules (`components/designer.tsx:1405-1435`), including "Add at least one choice." for a Choice list (`field_schemas.py:105`); names of 80 characters or fewer; and the document limits: 100 departments, 500 modules, 5,000 fields, 1,000 relationships, 600 layout entries, coordinates within ±100,000 (`domain/validation-types.ts:9-23`). The entry also refuses a name that is already in use. It compares the trimmed name and ignores letter case, as Connect does (`domain/relationship-name.ts:53`); publish compares exact names. The scopes are those of publish. A department name counts among the open departments (`publications/preflight.py:23-38`). A module name counts among the open modules of its department (`preflight.py:39-53`). A field name counts among the open fields of its module and the relationships that start at that module and end at an open module (`preflight.py:145-175`, `fields/validation.py:251-252`). Reason: publish refuses these names later ("Field names must be unique"), so the entry catches them where they are typed. Names that live departments and modules use stay a publish check (`preflight.py:57-130`). At a limit the add control is disabled with the reason ("This design has 500 modules, the limit.").
- **One change per add (N3).** An add writes the element and its layout box in the same change, so it is one Undo step and one entry in the save. The automatic layout fill (`components/designer.tsx:516-540` → `page.tsx:1080-1099`) never makes an Undo step of its own.

**Saves in a fast entry flow (FAST-1, FAST-3, N1).** Today a second change while a save is in flight is refused with "A Sandbox change is already being saved." (`frontend/src/components/systems/sandbox/page.tsx:818-918`). The entry must never show that message.

**The rule: only queued Build adds count as accepted when the browser accepts them. Every other action waits for an empty queue.**

1. **Accept.** Each add (and each Undo or Redo of an add) changes the local design and the Undo history at once and joins the queue. While the `PUT /api/sandbox/document` in flight saves an add or an Undo or Redo, the queue holds the new add, and the new element shows the saving mark. A Build edit of an existing element (rename, type, settings, delete, move) is not a queued add: it waits for an empty queue (rule 5), then saves as before and holds the page during its own save. While the save of an edit is in flight, the add controls are disabled, so no add control shows "A Sandbox change is already being saved." Reason: the field settings panel resets its draft when the saved field changes, so values typed during an edit save would be lost. The saving mark on the entry rows is drawn in PR3 with the entry; PR2 builds the queue without it.
2. **On success.** The client keeps the local design with the queued adds; it does not replace it with the confirmed one, as the success path does today (`page.tsx:838-845`). It sends the next `PUT` with `mergeProjectedDesign(confirmed.document, confirmed.projected, localPresent)` (`domain/document-bridge.ts:512`) and `expectedRevision = confirmed.revision`. Two or more queued adds join one save. Requests stay one at a time.
3. **On 409 or failure.** The conflict record is built from the local design at that moment, queued adds included, not from the request body (`page.tsx:851`). The entry closes, and today's destructive alert shows ("Reload the shared draft, then reapply your edits."). No add is dropped silently.
4. **Undo and Redo.** They go through the queue, so they stay enabled while adds are saving; today they call `persist` and are refused while busy (`page.tsx:923-936`, `:1329-1330`). An entry with an empty name changes nothing and does not set `designerDraftDirty`.
5. **Everything else waits.** A non-empty queue counts as pending for every action that reads `session.revision` or `session.document`: Save triggers (`page.tsx:882-887`), checkpoint (`:1100-1124`), import, apply template, discard, reload, lifecycle actions, Review & Publish, Test runs, and `syncSandboxDocumentMetadata` (`state/document-session.ts:111-119`). These controls show their pending state with the reason "Saving…" and run once the queue is empty. A section move (Build to Triggers, Test, or History), including "New trigger" from a module menu (TRIG-8), also waits for the queue to empty; it happens at once when the queue is already empty. Known limit: browser Back and Forward do not wait for the queue; this rule covers section moves inside the page only. No data is lost: a trigger save that waited for a queue that ended in a conflict is not sent, and the Test run controls ("Try it", "Try this trigger", "Try every event", "Run again") and Review & Publish stay disabled with "Saving…" while the queue holds saves.
6. While a publish, a lifecycle action, or a conflict holds the draft, the entry controls are disabled with the reason "Wait for the current Sandbox action to finish." (today's words).
7. Leaving the page with queued adds triggers the existing leave guard.

The Software Architect confirmed that this is frontend-only (go-ahead section, A1).

**Relationship (FAST-4).** `Connect` opens a popover "Connect Orders to": a target list grouped by department (as Build's relationship dialog groups it today), with "this module" and "already linked" rows shown dim and not choosable, then Name, prefilled "Orders to Customers" and focused once a target is chosen. Source is the module whose bar opened it. The name follows the target until the administrator types in it. The prefill is checked against the names that publish compares it with exactly (N6, `publications/preflight.py:136-184`, `fields/validation.py:250-252`): the source module's field names and the names of its other outgoing relationships. The browser compares case-insensitively, stricter than publish. On a clash the prefill adds " 2" (then " 3"). A name that the administrator types and that clashes is refused in place with the reason ("Orders already has a field named Customers."). On the canvas the chosen target card takes a dashed edge while the popover is open. Cardinality starts at today's default; cardinality and field mappings stay in the relationship's Properties. When the source has no module left that it can connect to, `Connect` is disabled with the reason "Orders has no module left to connect to."

**Template department (FAST-7).** "From a template" in the department entry opens the dialog "Add from a template": the 23 template departments grouped by their organization template (left, with module counts); the chosen department's modules with their first fields and the internal links (right); a Name row prefilled with the template name, or "Sales 2" when the name is taken (case-insensitive; publish compares department names exactly (`preflight.py:28-32`), and SD-C21 refuses "Sales" with "sales", so the stricter check avoids that blocker), with the limit line "Sales is taken in this design."; the footer line "Adds 4 modules and 3 links, without triggers."; Cancel · Add department. Add department is disabled with a reason while the name equals an existing department name, or while the merge would pass a document limit (N2; "Adds 4 modules; this design has room for 2."). The merge rules are in the go-ahead section (A2). The added department appears at the next free slot, selected, as one Undo step, and starts from the FIT-4 default setup (N13).

**Field type change (FAST-5).** The page reads the latest published version once per published version, with the existing `GET /sandbox/versions/{id}` (`state/api.ts:154`, `:630`), and keeps it until a newer version is published. A field matches on the pair (module id, field id) (`publications/rules.py:147-151`). In a field's Properties, when the Type select differs from the type of the matching published field, a warning notice shows under the select at once: "Published as Number; publish will refuse this change." with one quiet button, "Keep Number", which sets the select back. Nothing is saved until "Save field changes" (UXD-8); the publish blocker stays the final check. No notice when no version is published, or when the latest published version has no field with that pair (the known gap in FAST-5; the publish blocker decides). The read uses `getSandboxVersion`, which also records its outcome in History's access tracker (`state/sandbox-history-access.ts:80-124`), as every version read does; that is intended. A published version is never deleted, so the read fails only when the session is refused. When it fails, Build shows no notice; the publish blocker decides.

**Setup choices (FIT-1, FIT-3, FIT-4; only after setup slice 4, BE-SD5).** On a department with no live binding, the element bar holds `Setup`. Closed, it reads "Setup" when all items are on, and "Setup · 1 cleared" (count in warn ink) otherwise (R1.4). It opens a popover "Created at publish": Groups (managers, members, viewers), Dashboard, Category, Channel as checkboxes, then "Board · always created" as text (SD13). With Category cleared, the line "The channel goes in no category." shows under it (SD14). Each toggle edits the draft `setup` value through the normal save and is one Undo step; the review dialog edits the same value (FIT-3). Keyboard route: "Setup…" in the department's item menu in the Structure tree. A published department shows no Setup. **Default (FIT-4, N13).** A department created by the entry, by a template merge, or by Duplicate starts from the default setup: all on until setup slice 5, the Manage default (BE-SD6) after it. Until setup slice 5 it writes no `setup` (missing means all on, BE-SD5). From slice 5 it writes `setup` = the Manage default (`GET /api/workspace`, BE-SD6) when the department is created, so SD-C20 holds. It never copies the source's value; Duplicate of a department with "channel" cleared gives a copy with the default (UX-C34).

**Structure tree (FIND-4).** The tree keeps its "Add …" items and the Tree Keys Rule: one Tab stop, the add items are tree items. The add items get a plus icon and read in `--action-text` on hover and focus. Enter on an add item opens the entry anchored to that row (like F2 opens rename). The item menu (context-menu key or Shift+F10) of a module adds "Connect…", and of a new department adds "Setup…".

**UXD-2 count at 1440 (default-visible controls, against the relayout baseline).**

| State | Added | Removed | Net | Bound |
| --- | --- | --- | --- | --- |
| Nothing selected (baseline 13) | Toolbar "Add department" | Summary "Add department" | 0 | +1 |
| Department selected (baseline 15) | Toolbar "Add department"; bar `+ Module`; `Setup` for a new department after slice 4 | Properties "Add module" | +1; +2 with Setup | +2 |
| Module selected (baseline 26) | Toolbar "Add department"; bar `+ Field`, `Connect` | Properties "Add field", "Connect modules" | +1 (27) | +2 |
| Field expanded (baseline 32) | As for module | As for module | +1 (33) | +2 |

Default-visible helper words do not change in these states. The new helper lines (FAST-5 notice, SD14 line, template footer) appear only in the state that needs them. The Structure tree "Add …" items are baseline items and stay; UXD-2 applies to the new canvas controls.

**Reference structure, by pointer (FAST-3, UX-C7).** 1 department, 2 modules × 3 Text fields, 1 relationship.

| # | Click | Then typed |
| --- | --- | --- |
| 1 | Toolbar "Add department" | "Sales", Enter, Escape. Sales is selected. |
| 2 | Sales bar `+ Module` | "Orders", Enter, "Customers", Enter, Escape. Customers is selected. |
| 3 | Customers bar `+ Field` | 3 names, each with Enter; Escape. |
| 4 | Point at Orders; its bar shows; `+ Field` | 3 names, each with Enter; Escape. Orders is selected. |
| 5 | Orders bar `Connect` | — |
| 6 | "Customers" in the target list | Enter (name prefilled). |

6 clicks, 9 names typed. With six fields of six non-Text types (UX-C8): one type click per field, so 12 clicks. Keyboard only (UX-C9): in the Structure tree, Enter on "Add department" → names → Escape (focus returns to the tree) → arrow to "Add module" → Enter → names → Escape → arrow to "Add field" under each module → Enter → names, Tab to the type group where needed → Escape → on Orders, context-menu key → "Connect…" → type "Cus", Enter, Enter. 0 clicks.

### Triggers: write with the structure in view (TRIG)

**Layout.** Three panes from 1280 px, each scrolling alone (Still Page Rule).

| Width | Trigger list | Editor | Structure region | Condition and action rows |
| --- | --- | --- | --- | --- |
| 1600 px and up | 280 px; the event column shows its icon only (word in the accessible name and tooltip) | Fills | 256 px | One line each |
| 1440–1599 px | 280 px; event icon only, as above | Fills | 256 px | Two lines: the field, then operator and value |
| 1280–1439 px | 248 px; the event column shows its icon only (word in the accessible name and tooltip) | Fills | 248 px | Two lines |
| 768–1279 px | Page scrolls (as today) | — | Becomes the "Orders fields" button, opening a side sheet | Two lines |
| 390 px | List, then the detail with Back (as today) | — | "Orders fields" button in the detail header (44 px), opening a bottom sheet; Close returns to the same scroll point | Two lines, 44 px |

The open sheet and the region never touch unsaved trigger edits: they belong to the page (Kept Edits Rule).

**Structure region (TRIG-1).** Head: the department mark, the module name, the department name. Then "Fields 6": each field with its required dot and its type in the code face. Then "Links 2": "→ Customers · Sales" for links out, "← Invoices · Finance" for links in. Fields used by the focused step take the selection tint. Read-only. With no module chosen, the region lists every department and its modules.

**Whole-trigger sentence (TRIG-6).** Directly under the trigger name in the editor head, one sentence that changes with each edit: "When an item is added to **Orders**, if **Amount** is at least **100**, set **Status** to **Review**." The sentence replaces the per-step summaries (`trigger-rail.tsx:472-496`); step heads keep only When, If, Then. Grammar: event phrase ("an item is added to Orders", "Status changes in Orders", "Amount reaches at least 1,000 in Orders", "every day at 09:00 in Stock counts"); no conditions gives no if-clause (the If step still shows "Always"); conditions join with "and" or "or" from the group; actions join with "and". A missing part reads as its kind ("an event", "a module", "a field", "a value", "no action yet") in warn ink with a dashed underline, never as a default. The sentence is the editor's description (`aria-describedby`), not a live region.

Changed by `docs/specs/ux-friction-pass.md` item 9 (APR-0003): the built Triggers and Test screens say "record", not "item", as TRIG-6 requires ("When a record is added to **Orders**", "Record added", "When a record is added" in the reading, "Example record"). Stored event values do not change.

**Pickers (TRIG-2).** Every module picker groups modules under their department (mark and name), with a search and each module's field count. Every field picker shows each field's type on the right in the code face, and the closed select shows it too.

**Operators (TRIG-3, TRIG-4).** Number, Whole number, Date, Date and time: is, is not, is more than, is at least, is less than, is at most. Text, Long text, Choice list, Email, Web link, User, Checkbox: is, is not. A saved operator that does not fit stays selected; the select takes the warn edge; its list shows it last, dim, with the option text "<operator> · saved"; the line under the row reads "Does not fit Text; choose is or is not." Nothing changes until the administrator picks. Save triggers does not refuse it (OQ-2 default).

**No silent choice (TRIG-5).** "New trigger" opens with Module empty and focused (module first, then event). From Build ("New trigger" in a module's item menu, TRIG-8) the module is preset. A change of event keeps the module. A step that a change makes invalid shows empty with its reason in warn ink (the trigger draft of B1 holds it), and Save triggers refuses it in the browser (B1 rule c): "Choose the field to watch." (Field changed), "Choose a number or date field." (Threshold crossed, when the field does not fit), "Not in Customers; choose a field." (module change). A new condition row and a new action row start with the field empty ("Choose a field.") and no value; today's first-field defaults (`domain/trigger-rules.ts:458-480`, `addTriggerAction`) are not used (UXD-7).

**Then (TRIG-7).** The Then step offers only "Set a field" on the trigger's module: "Set [field] to [value]", and "Add action" adds another.

**Incomplete triggers (B1).** TRIG-5 and UXD-7 make a trigger with an empty module, an empty field, an empty value, or no action a normal editing state. Today two checks refuse it: the kept edits in session storage are parsed with `parseSandboxDocumentValue` (`components/use-trigger-draft.ts:143-171`), which refuses an empty `moduleId` (`domain/document-parser.ts:72-81`) and zero actions (`:1116-1123`), so they drop silently on reload (against D1); and a save sends them to the server, which refuses with 422 (`backend/app/systems/sandbox/designs/schemas.py:15`, `:231`), which `persist` turns into a whole-draft save failure (`page.tsx:856-862`) that Reapply repeats. Three rules:

- **(a) A browser-only draft shape.** The trigger editor holds each changed trigger as a trigger draft: the `SandboxTrigger` shape in which the event module, the watched field, each condition field and value, and each action target and value may be empty, and the action list may be empty. Saved triggers load as complete drafts. A trigger draft never enters `session.document`, the document parser, or a request; it becomes a `SandboxTrigger` only in rule (c), after the check passes. A complete trigger draft serializes exactly as its `SandboxTrigger`; an empty part is the only difference, and the reason shown for an empty part is derived when rendered, not stored. The equality checks against the saved triggers (`use-trigger-draft.ts:235`, `:249`, `:276-287`, `:330`) therefore keep their meaning.
- **(b) Kept edits, format 2.** Kept edits are written as `{ "version": 2, "base": <base>, "triggers": [<trigger draft>] }`, under the same key and the same size limit. A draft parser reads them: it checks the shape and the ids, accepts empty parts, and turns a part that points at a module or field that is no longer in the current draft into an empty part with the reason "No longer in the design." It never drops a record because a trigger is incomplete. It drops only a damaged record (unreadable, a wrong shape, or over the size limit) or one whose triggers equal the saved triggers, as today (`use-trigger-draft.ts:151-162`, `:235`). A record whose base changed is kept and offered with its warning, as today (`:428-431`). `base` stays the saved triggers' JSON at the first edit (`:334`) and is used only for that warning; format 2 adds no other check: `version` is `2`, `base` is a string, `triggers` is an array. A version 1 record still reads through today's path. The Restore prompt of the Kept Edits Rule is unchanged.
- **(c) Save triggers checks first, in the browser.** Before any request, Save triggers checks every changed trigger. If one is incomplete, it sends nothing: the save bar reads "1 trigger is incomplete; choose a module." (it names the first missing part, with the count when there are more), the list row of each incomplete trigger carries an "Incomplete" warn badge beside "Unsaved", and the first incomplete step opens with focus on its empty control. Each empty part already shows its reason in warn ink ("Choose a module.", "Choose the field to watch.", "Choose a number or date field.", "Add an action."). When all are complete, the drafts become `SandboxTrigger` values and save through the normal path. An incomplete trigger therefore never reaches `persist`, and never causes a 422 or a whole-draft save failure. Review & Publish keeps its reason "Save trigger changes first." while incomplete drafts exist. The check runs on every save path: the Save triggers button, Ctrl+S (`trigger-studio.tsx:223`), and Save in the leave dialog (`trigger-leave-dialog.tsx:103-110`), which then stays open with the same message.

### Test: a reading first, a run on request (TEST)

**Layout.** Two panes from 1280 px. Left: "Modules", grouped by department (a new department carries the New chip), 40 px rows with each module's trigger count, a search, and a footer "Results 12 of 50 · Clear results". Right: the **reading** of the chosen module. At 390 px: the list, then the reading with "← Modules".

**Reading (TEST-1, TEST-2).** Built in the browser from the saved draft, with no request. Head: the module name, then the facts line under it ("Sales · 6 fields · 4 triggers · 2 links"; zero counts are left out). Then one block per event in reading order: "When an item is added", one "When <field> changes" per watched field, one "When <field> reaches <limit>" per threshold, one per schedule. Each block lists the triggers that listen, with their conditions in words and "sets <field>"; an Off trigger shows "Off" in muted ink; a trigger that needs attention shows the existing attention reason. A block with no trigger reads "No trigger listens." Last, "Links": each relationship out (→) and in (←) with the other module, its department mark, and "carries <field>" from its field mappings, or "no values".

**Try it (TEST-3, TEST-4, TEST-7, N9).** Each event block with at least one trigger has a quiet "Try it". It sends today's `POST /api/sandbox/tests` with `moduleId`, `values`, the block's `event`, `expectedRevision`, and `triggerIds: null`, so every enabled trigger runs, including triggers that a first trigger sets off (`backend/app/systems/sandbox/test_runs/evaluator.py:269`). The values are the example values below, shaped only by the event (UXD-11): they never try to meet any trigger's conditions. The reading above the button still shows which triggers listen. The head has "Try every event · N runs" (TEST-8), where N is the number of blocks with a trigger. A run happens only on these buttons and on "Try this trigger".

**Example values (TEST-3, N7).** Built in the browser from each field's settings. Every value is valid for its field; the evaluator raises no `value_required` or `value_invalid` for a field that can have one.

| Field type | Example value |
| --- | --- |
| Text, Long text | The default when it is not empty, else "Example <field name>", cut to the length limit. A default of "" counts as no default. |
| Email | The default, else `a@example.com`; with a length limit under 13, the shortest address the evaluator accepts, `a@b.c` |
| Web link | The default, else `https://example.com`; with a length limit under 19, `http://a.io`, and under 11, `http://a` |
| Number | The default, else the first value on the step that starts at the minimum (else at 0) and is inside the limits, checked in exact decimals (0, or the minimum, is that value) |
| Whole number | As Number, sent as a JSON integer |
| Date, Date and time | The default, else today (now, to the hour), moved inside the earliest and latest limits |
| Checkbox | The default |
| Choice list | The default, else the first choice's id (the evaluator matches the option id, `evaluator.py:222-228`), shown by its label |
| User | The default, else the signed-in administrator, from the `id` that the page already reads from `GET /auth/me` (`frontend/src/lib/auth-api.ts:63-64`, `page.tsx:672`); editable in "Change values". Nothing is asked for. |

- **The event shapes the values.** Field changed: the previous value of the watched field differs from the new value (the next choice, the next step, the next day, or "Example <field name> (before)"). Threshold crossed: the previous value does not meet the limit, and the new value does. The limit is the trigger's threshold value; when it is "Another field" (`trigger-rail.tsx:154`, `:740`), the limit is that field's example value. The new value is the smallest valid value that meets the limit; when no valid value meets it (the limit is above the field's maximum), the block keeps the example values and its result reads "Not triggered" with the reason. Schedule: no previous value.
- **Linked values.** When a relationship's field mappings carry a field to another module, its example must also be valid for the target field there (inside both limits, or a choice label that the target list also has), or the run stops with `relationship_invalid` (`test_runs/relationships.py:94-136`). The browser picks a value that fits both.
- **No possible value (E4).** When a field's settings allow no valid value (for example a minimum above the maximum, a Choice list with no choices, a length limit under 5 for Email or under 8 for Web link, or a linked field with no value that fits both modules), Test names that field under its input in "Change values" ("Its settings allow no value. Enter one to run."), and the run waits for a value there. No other value is asked for. Try it on such a module opens the result card in "Change values" (E3) with no request, names the field, and "Run again" sends the run once the value is valid. The administrator changes the field's settings in Build; the result card has no link to Build.

**Try this trigger (TEST-9, UXD-11).** Each listening trigger row that is on carries a quiet "Try this trigger" at its end, always visible (at 390 px it sits under the row, 44 px). An Off trigger has none. One action is one run (TEST-7). The request sends `triggerIds` with that one trigger, the trigger's own event, `expectedRevision`, and the example values, after one change: each condition of this trigger whose field is on the trigger's module and whose value is a literal gets a value that meets it (for example "Amount is at least 100" sets Amount to 100). For Field changed, a condition on the watched field sets the new value, and the previous value stays different from it. These conditions keep the example value instead:

- a condition that compares with another field;
- a condition on the field that a Threshold crossed event fixes;
- two conditions on one field that cannot both hold.

A fill is used only when the value is valid for its field and for every linked target field that a field mapping carries it to; an invalid value stops the run before any trigger runs (`evaluator.py:56-66`, `:154-187`; `relationships.py:120-129`). Otherwise the condition keeps the example value, and the result reads "Conditions not met" with the reason ("100 is outside Amount's limits; value kept."). In an "any" group, only the first condition that can be filled is filled; the others keep their example value.

The browser copies no order, priority, or chain of other triggers.

**Result (TEST-5).** Under the event block that ran: head "Example item", the chip "Test only · live data unchanged", and "Show on canvas". Left, "Values used" with "Change values"; right, "What happened": each trigger that ran, with each field change "Status Open → Review"; each that did not run, with the reason in words when there is a specific one ("Paid is Unchecked; it needs Checked."); "Off" and "Not triggered" show as the status only; each that needs attention; each linked module and the value it carries. Footer: "Run 13 of 50 kept" and "Run again".

**Result of Try this trigger.** It appears under the trigger's own event block, in the same card, with three differences: the head reads "Example item · Flag large orders only"; each value that the trigger's conditions set carries a "Set for this trigger" mark ("Amount 100"); and "What happened" ends with one line, "Other triggers on Orders did not run in this test." A condition that kept its example value reads under the trigger as "Conditions not met" with the reason ("Amount is compared with Total; values kept."). "Run again" repeats the same single-trigger run.

**Change values (TEST-4).** The value rows become slim inputs; a changed row carries an "Edited" mark; a "Triggers" row (all listening, checked) replaces the old "Triggers to run"; "Run again" becomes the primary action of the result. When the "Triggers" row is unchanged or every trigger is checked, "Run again" sends `triggerIds: null`; otherwise it sends the checked ids (today's rule, `test-workspace.tsx:249`), and the result says that the unchecked triggers did not run in this test.

**Run requests and stops (N10).** Every run sends `expectedRevision` from the saved draft. A `409 run_history_full` gives E5. A `409 stale_revision` uses today's reload handling ("Sandbox draft changed; reload before testing."). Either one stops "Try every event" after the runs that already finished; their results stay. Before it starts, "Try every event" compares N with 50 minus the `total` of the existing `GET /sandbox/tests`; when N is larger, it is disabled with the reason "Needs 3 runs; 2 left. Clear results first." A run uses the saved draft, so every Try button is disabled with "Saving…" while the Build queue is not empty or a save is in flight (N1 rule 5), and with "Save trigger changes first." while trigger edits are unsaved.

### States

| ID | State | Shows |
| --- | --- | --- |
| B1 | Build, nothing selected | Toolbar "Add department"; Summary without its add button; tree with add items |
| B2 | Element pointed or focused | Its element bar, not selected |
| B3 | Department selected | Bar `+ Module` (and `Setup` when new, after slice 4) |
| B4 | Module or field selected | Bar `+ Field`, `Connect`; Properties without create buttons |
| B5 | Entry open | Name, type choices (fields), Required, Choices (Choice list); new rows with the saving mark |
| B5c | Save refused during entry | Entry closed; today's conflict or failure alert; proposed document kept |
| B6 | Connect open | Grouped target list, prefilled name, dashed target card |
| B7 | Type change warning | Warn notice under Type with "Keep Number" |
| B8 | Add from a template | Dialog with grouped departments, preview, unique name |
| B9 | Setup open | Four checkboxes, Board as text, SD14 line when needed |
| B10 | Build at 390 | Pinned bar on the canvas pane; entry and popovers as bottom sheets with 44 px controls; Structure add items 44 px |
| B11 | Item menu on the canvas | Same items as the tree menu, plus "New trigger" and "Connect…" for modules |
| B12 | Empty design | Today's "Add your first department" and "Start from a template" (unchanged) |
| T1 | Editing a trigger | Three panes, sentence, region with the module's fields and links |
| T2 | New trigger | Module empty and focused, grouped module list, region lists the whole structure, sentence with missing parts |
| T3 | Field picker open | Fields with types |
| T4 | Operator by type | Two or six operators |
| T5 | Operator does not fit | Warn edge, "· saved" option text, with the does-not-fit line under the row, one-line reason |
| T6 | Step emptied | Empty step with its reason in warn ink |
| T7 | Triggers at 390 | Detail with "Orders fields" button and bottom sheet |
| E1 | Reading | Event blocks, listening triggers, links; no run |
| E2 | Result | Inline under its event: values used, what happened |
| E3 | Change values | Editable values, Edited marks, Triggers row, Run again |
| E4 | No possible value | Try it sends no request: the result card opens in "Change values" (E3) and names the field whose settings allow no valid value once, under its input ("Its settings allow no value. Enter one to run."); "What happened" lists nothing before a run; "Run again" sends the run once the value is valid; nothing else is asked for. The administrator changes the field's settings in Build (no link from the card) |
| E5 | Store full | Footer "Results 50 of 50" in warn ink with "Clear results"; Try it disabled with "Clear results first." |
| E6 | New department module (after setup slice 1, N12) | New chip; "Review & Publish lists what publishing creates." with "Open review"; no list of derived items. Before slice 1 the line is not shown. |
| E7 | Empty and first run | No modules: "Nothing to test yet" with "Open Build". Module with no triggers: blocks read "No trigger listens.", no Try it |
| E8 | Try every event running | The head button shows "Running 2 of 3"; each result appears under its block |
| E9 | Test at 390 | List, then the reading with Back; Try it and Try this trigger 44 px |
| E10 | Try this trigger result | Under the trigger's event block: "Example item · <trigger> only", "Set for this trigger" marks, the trigger's outcome, "Other triggers on <module> did not run in this test." |
| E11 | Try every event refused | Disabled with "Needs N runs; M left. Clear results first." |
| T8 | Save refused, incomplete trigger | No request; save bar names the first missing part; "Incomplete" badge on each such row; first empty step focused |
| T9 | Kept edits restored with empty parts | Restore prompt (unchanged); the restored drafts keep their empty parts and reasons |
| B5d | Add refused in the entry | Reason under the name (name too long, name in use, document limit); a choice reason under Choices, with `aria-invalid` and focus on Choices; the name stays |

### Criteria to states

| Criterion | State or rule |
| --- | --- |
| UX-C1 | B2: pointing at Sales shows `+ Module` in its head band |
| UX-C2 | B4: `+ Field` and `Connect` under Orders, named "Add field to Orders" |
| UX-C3 | Tree route: Enter on "Add field" under Orders → B5 → Enter; focus ring at every step |
| UX-C4 | B10: tap Sales → pinned bar `+ Module` (44 px) → entry sheet; or the Structure pane add item |
| UX-C5 | UXD-2 count table (B1, B3, B4, field expanded) |
| UX-C6 | B5 for modules: Enter keeps the entry on Sales; Escape on an empty name creates nothing |
| UX-C7 | Reference walkthrough: 6 clicks, 9 names |
| UX-C8 | B5 type choices: one click per non-Text field, 12 clicks |
| UX-C9 | Keyboard walkthrough, 0 clicks |
| UX-C10 | B6: "Orders to Customers", source Orders |
| UX-C11 | B7 |
| UX-C12 | B5 + Undo: one step per element, no page alert |
| UX-C13 | B8 and the merge rules in A2; a fresh review lists the department with the FIT-4 default setup |
| UX-C14 | T1 at 1440, T7 at 390 |
| UX-C15 | T2 (grouped modules), T3 (field types) |
| UX-C16 | T4 |
| UX-C17 | T5 |
| UX-C18 | T6 (held by the trigger draft, B1): module kept, field empty with "Choose the field to watch."; T8 if saved before a field is chosen |
| UX-C19 | T6: each affected step empty with "Not in Customers; choose a field." |
| UX-C20 | T1 sentence; a removed action reads "no action yet" |
| UX-C21 | T1 Then step: "Set a field" only |
| UX-C22 | E1: no request on open or on module choice |
| UX-C23 | E1 Links block, both directions |
| UX-C24 | E2 with the example value table |
| UX-C25 | E2: the User field holds the signed-in administrator, editable in "Change values" (E3); nothing asked before the run |
| UX-C26 | E3 → E2 |
| UX-C27 | E1 adds no run; E5 after run 50 |
| UX-C28 | E6, after setup slice 1 |
| UX-C29 | B3 and B9; absent for a published department |
| UX-C30 | B9 and the review dialog, same draft value |
| UX-C31 | No new state: S4 unchanged, the Sandbox stays hidden and shows "Sandbox is not available to your account." |
| UX-C32 | Layout tables above; 1280×720 comp of T1 shows no page scroll |
| UX-C33 | E10: one request with `triggerIds` = [A]; Amount set to 100 for A's condition; A ran, Status Open → Review; "Other triggers on Orders did not run in this test."; a two-field condition reads "Conditions not met" with the reason |
| UX-C34 | FIT-4 default rule in "Setup choices": the entry (B5), the template merge (B8, A2), and Duplicate (B11) each start from the default, never from the source's cleared channel |

### Design-system items for impeccable (recorded at build time, `DESIGN.md` not edited now)

1. **Layout, "The Sandbox" paragraph (about line 546).** Replace "creation actions live in the workbench, not on the canvas" with: creation actions sit in the canvas toolbar (Add department), in the element bar of the selected or pointed element, and in the Structure tree; Properties holds no create buttons.
2. **Sandbox canvas (signature) (about line 992).** Add: the element bar (screen scale; `--surface-raised` with a `--rule` edge and `--lift-raised`; 28 px buttons from 1280 px; pinned 44 px bar at 390 px; shown for the selected element, and on pointer rest or row focus for others); the saving mark (muted ink and a ring at the row end); the newest-row `--flow` tint; the New chip on an unpublished department; the dashed edge on a Connect target. Restate that the bar is not canvas content: it carries the slim sizes and the 44 px floor.
3. **Sandbox sections (relayout).** Triggers: three panes with the structure region, the whole-trigger sentence in place of step summaries, two-line rows below 1600 px. Test: the module list and the reading, the result inline under its event; replaces "Setup and Result".
4. **No new tokens.** The comps use existing tokens only (`--surface-raised`, `--lift-raised`, the 6 % and 14 % ink tints, `--action-tint`, `--warn-*`, `--flow`, canvas and department tokens).

**Glossary rows for the build (`docs/architecture/21-glossary.md`):** element bar, entry (add-next), structure region, reading (Test).

## Comps (Product Designer)

Location: `.impeccable/mocks/sandbox/` (ignored by Git). New files: `build.html`, `triggers-structure.html`, `test-reading.html`, and `redesign.css`; 17 icon symbols were appended to `icons.svg`. `sandbox.css`, `tokens.js`, `triggers.html`, and `history.html` are unchanged. Theme: Slate dark. The comps load the app's built stylesheet through `tokens.js`, so they render only over HTTP: serve the folder (`python3 -m http.server` in `.impeccable/mocks/sandbox/`) and open `http://127.0.0.1:<port>/<file>?state=<state>`. Under `file://` they render without tokens.

Renders: `.playwright-mcp/sandbox-ux-redesign/comp/`.

| # | Structure | Comp | Renders |
| --- | --- | --- | --- |
| 1 | Create controls: canvas level, pointed department, selected module, Structure rows | `build.html?state=hover`, `?state=adddept`, `?state=module` | `build-hover-1440.png`, `build-adddept-1440.png`, `build-module-1440.png`, `build-module-390.png` |
| 2 | Add-next entry with type choices and Required | `build.html?state=addfield` | `build-addfield-1440.png`, `build-addfield-390.png` |
| 3 | Relationship with prefilled name | `build.html?state=connect` | `build-connect-1440.png` |
| 4 | Field type change warning | `build.html?state=typewarn` | `build-typewarn-1440.png` |
| 5 | Department from a template | `build.html?state=template` | `build-template-1440.png` |
| 6 | Setup choices | `build.html?state=setup` | `build-setup-1440.png` |
| 7 | Triggers: region, sentence, grouped pickers with types, fitting operators, flag | `triggers-structure.html?state=edit`, `?state=picker`, `?state=flag`, `?state=new`, `?state=sheet` | `triggers-edit-1440.png`, `triggers-edit-1280x720.png`, `triggers-picker-1440.png`, `triggers-flag-1440.png`, `triggers-new-1440.png`, `triggers-edit-390.png`, `triggers-sheet-390.png` |
| 8 | Test: reading, Try it result, empty, full store, new department | `test-reading.html?state=reading`, `?state=result`, `?state=empty`, `?state=full`, `?state=newdept` | `test-reading-1440.png`, `test-result-1440.png`, `test-empty-1440.png`, `test-full-1440.png`, `test-newdept-1440.png`, `test-reading-390.png`, `test-result-390.png` |
| 9 | Test: Try this trigger and its result (TEST-9) | `test-reading.html?state=trythis` | `test-trythis-1440.png` |

At 390 px, comps 3, 4, and 6 use the same bottom sheet with 44 px controls as comp 2, so they have no separate 390 render. The template dialog (comp 5) follows the existing Sandbox dialog rule on phones (pinned header and footer, the dialog is the only scroller) with the department list above the preview; it is not comped at 390. Revised 2026-11-10 after the review: the reading, result, full, and new-department comps predate TEST-9 and show no "Try this trigger" on the trigger rows; comp 9 shows it, and the rules above win. The comps draw a short sample structure (Sales, Finance, Field service), not Harbor data. They do not show states B5c, B5d, B11, E3, E4, E8, E11, T6, T8, or T9, the template dialog at 390, or the open operator list of T5 (the saved operator listed last, dim, as "<operator> · saved"); the rules above define them.

## Where each capability goes (Product Designer)

Paths are under `frontend/src/components/systems/sandbox/` unless the row says otherwise.

| Current control (source) | Change | Destination |
| --- | --- | --- |
| Summary "Add department" ghost button (`components/designer-summary.tsx:90-100`) | Removed | Canvas toolbar "Add department"; Structure "Add department" item |
| Summary "Start from a template" on an empty design | Kept | Same place; it still replaces the whole draft |
| Department Properties "Add module" ghost button (`components/designer.tsx:2416-2426`) | Removed | Department element bar `+ Module`; Structure "Add module" item |
| Module Properties "Add field" ghost button (`components/designer.tsx:2138-2146`) | Removed | Module element bar `+ Field`; Structure "Add field" item |
| Module Properties "Connect modules" ghost button and its disabled reason (`components/designer.tsx:2358-2380`) | Removed | Module element bar `Connect` (same disabled reason); "Connect…" in the item menu |
| Inline create form in Properties: name, native type select, default value, Required, Select options (`components/designer.tsx:1282-1456`) | Replaced | The entry: name, one-click type choices, Required, Choices. The default value moves out of create: set it in the field's Properties after creation (existing per-row edit). |
| Relationship create form: source, target, name, cardinality, field mappings (`components/designer.tsx:1459-1530`) | Replaced for create | Connect popover: target and name; source from the module. Cardinality and field mappings: the relationship's Properties edit (existing `editRelationship`). |
| Structure "Add …" rows (`frontend/src/components/sandbox/sandbox-inspector-outline.tsx:597-668`) | Kept, restyled | Same tree items; Enter or click opens the entry at the row instead of the Properties form |
| Drag of a Structure "Add …" row onto the canvas (`sandbox-inspector-outline.tsx:585-595`, `frontend/src/components/sandbox/sandbox-canvas.tsx:1170-1196`) | Removed | Create with the bar or the tree item, then drag the new card on the canvas (existing node drag). A field type is chosen in the entry instead of always Text. Moving a module to another department stays "Move module to department" in Advanced (`components/designer.tsx:2449`). |
| Duplicate, only in the Structure item menu (`sandbox-inspector-outline.tsx:476-480`) | Kept | Same menu; also the canvas item menu (right-click, long-press) |
| Trigger step summaries (`components/trigger-rail.tsx:472-496`) | Removed | The whole-trigger sentence under the trigger name |
| Trigger list event word | Shortened | Event icon at every list width, with the word as accessible name and tooltip and in the sentence; one row badge (Incomplete, else Unsaved) on a second line under the name (gate R5 adjudication, 2026-11-11: a 280 px list cannot hold the word beside an 8rem name) |
| Test "Module" select (`components/test-workspace.tsx:525-544`) | Removed | The Modules list pane |
| Test "When", "Changed field", "Previous value", "Frequency", "Time", "Day" (`components/test-event-rows.tsx:51-165`) | Removed | One reading block per event with its own Try it; the event values are generated and editable through "Change values" |
| Test values form with Relevant, All, Edited tabs | Replaced | "Values used" in the result, editable through "Change values", with an Edited mark per row |
| Advanced "Triggers to run" (`components/test-setup-advanced.tsx`) | Moved | "Triggers" row in "Change values" |
| Advanced "Recent results" and "Clear results" (`components/test-setup-advanced.tsx`) | Moved | Modules pane footer: "Results N of 50" opens the recent results; "Clear results" beside it; opening one shows it under its event |
| "Run test" primary button | Replaced | "Try it" per event; "Try this trigger" per trigger; "Try every event · N runs" |
| "Test this instead" per trigger (`components/test-run-result.tsx:81-84`) | Replaced | "Try this trigger" on the trigger's row in its module's reading (TEST-9); the module is one row in the Modules list |
| Setup and Result toggle at 390 px (`components/test-workspace.tsx:475-485`) | Removed | List, then the reading with Back |
| Result "Steps", "Field comparison", "Values used", "Linked records used" (`components/test-run-result.tsx:342`, `:417`, `:432`, `:498`) | Merged | Result card: "Values used" and "What happened" (ran, did not run with reason, needs attention, field changes from → to, linked modules) |
| "Show test on canvas" (`components/test-run-result.tsx`) | Renamed | "Show on canvas" in the result head (R3: 3 words); same behavior |
| "Test only · live data unchanged" | Kept | Result head chip |

## Backend changes needing your go-ahead (Product Designer)

**None.** The Software Architect review (2026-11-10) found no API, schema, storage, or wire-format change. Every rule above runs on today's API: `PUT /api/sandbox/document` for every Build change, `POST /api/sandbox/tests` with its current request (`moduleId`, `values`, `event`, `triggerIds`, `expectedRevision`) for Try it and Try this trigger, the `total` of `GET /sandbox/tests` for the results count, the existing clear route, `GET /sandbox/versions/{id}` for FAST-5, and `GET /auth/me` for the User example. The Test reading sends no request. Kept edits format 2 (B1) lives in browser session storage only. The setup choices (FIT-1) depend on BE-SD5, which the department setup spec owns; this spec adds nothing to it.

**Confirmed frontend-only by the Software Architect.**

| ID | Question | Confirmed contract |
| --- | --- | --- |
| A1 | Save queue for the entry | Frontend-only (N1 rules 1 to 7 above). One `PUT /api/sandbox/document` at a time; the next one carries `mergeProjectedDesign(confirmed.document, confirmed.projected, localPresent)` with `expectedRevision = confirmed.revision`. Request and response shapes do not change. The conflict record is built from the local design. Undo history stays client-side, one step per element. Every other action waits for an empty queue. |
| A2 | Add one template department | Frontend-only. The client copies the chosen department from `SANDBOX_ORGANIZATION_TEMPLATES` (`domain/templates.ts`) into the draft as one change and saves it with the normal `PUT` (N4). New `uid()` ids for the department, its modules, and its internal relationships (required). New field ids are optional (template field ids are `<moduleId>-<key>`, `domain/templates.ts:33`, and the new module id already makes the pair unique). Choice option ids need no change. Remapped: each module's `departmentId` and `titleFieldId`, each relationship's `sourceModuleId`, `targetModuleId`, and `fieldMappings`, and the layout keys. Only relationships with both ends in the department come along. The template trigger is not copied (UXD-5). Until setup slice 5 no `setup` is written (missing means all on); from slice 5 the merge writes `setup` = the Manage default (BE-SD6), so the department starts from the FIT-4 default (N13). The layout places the frame in the next free slot right of the existing frames. The name is checked case-insensitively against existing departments, and the merge is checked against the document limits before the change (N2). One Undo step. |
| A3 | FAST-5 published type | Resolved. Frontend-only: match on (module id, field id) against the latest published version, read with the existing `GET /sandbox/versions/{id}`, once per published version. No published version, or a field missing from it, gives no warning. |
