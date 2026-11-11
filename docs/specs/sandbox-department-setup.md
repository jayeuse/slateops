# Sandbox department setup: a published department comes alive

> **Status: approved (2026-11-10, APR-0001); built in PR1 (setup slices 1 and 2), 2026-11-11.** The text was amended on 2026-11-11 to match the build (TASK-0047: R3, R10, SD8, SD10, BE-SD7, SD-C22, SD-C25). Owner's answers (2026-11-10): BE-SD1 to BE-SD8 approved; OQ1 option (b); OQ2 option (a); SD9 approved. Review history: proposed (2026-11-02), revised after the Software Architect and Security Engineer reviews, and revised after the R5 adjudication (2026-11-02); observed 2026-11-02 at `d3efacd1`, rechecked 2026-11-10 at `3149165c`. Part 2 of the completion work ("Sandbox as the heart of setup"). Direction agreed with the owner on 2026-10-30: four rules, three kinds of objects, and six open questions with defaults (recorded below as SD1 to SD6). The Software Architect decided SD8 (the link) and SD19 (the lock order). Slices 3 to 5 are not built yet. The owner approved every item under "Backend changes needing your go-ahead" on 2026-11-10 (APR-0001). The two owner questions are resolved (see "Owner decisions").

## Outcome

When an administrator publishes a new department in the Sandbox, the department gets its working parts in the same publish:

- three Access groups: "<Department> managers" (`manage`), "<Department> members" (`write`), and "<Department> viewers" (`read`);
- one OpenView dashboard, the department's home, empty;
- its Board (automatic today);
- one OpenComms category and one department channel in it.

Before anything changes, the publish review lists each of these items. After the publish, each item is an ordinary object of its own system: people edit it, fill it, or remove it with that system's own tools. The Sandbox keeps a link to each item it created, and the link follows only two things: the department's name and its open or closed state.

**In scope.**

- Creation of the derived items at publish, through each system's own code, in the publish transaction.
- The publish review: the derived items as new kinds of change.
- Name and state follow-up on both close and reopen paths (publish and the live lifecycle actions), with the lifecycle close preview showing the derived changes and the lifecycle reopen reporting them in its result.
- The Access state "this department has no manager".
- Clear-before-publish per item, and organization-wide defaults in Manage (later slices).
- The sample-pack population change that the derived dashboard makes necessary.

**Out of scope.**

- Modules. A module creates nothing (SD1).
- Sub-departments. The code has none (SD4).
- Departments that exist before this change. Nothing is created for them; a backfill is a separate, opt-in action, not specified here (SD5).
- Members. Nobody is added to a derived group (SD3).
- Final words, layout, and visuals. The Product Designer decides them; this spec gives interface rules only.
- A change to the sidebar rule DA2 (SD15).

**Preserved behavior.**

- The systems stay independent. A system works the same when a derived item is removed, renamed by a person, or never created.
- The department Board stays as it is today: one per department, created, archived, restored, and renamed by `sync_department_board`, on every publish and on the lifecycle path. Only its preview is new (SD7).
- The publish contract stays: password check, preview token, `impactDigest` match, `live_state_digest` match, idempotency, one commit.
- Access rules stay: an administrator manages everything and is never a group member; a guest is capped at `read` in any group; closing a department keeps its group access rows.
- OpenComms D44 and D45 stay: department channels follow department roles; grants only add; no invitations. D9 stays: a new organization has no channels until an administrator or a department manager creates one (a publish is an administrator's action).
- OpenView BD3 stays: one home dashboard per department; an empty home shows the set-up state with presets to managers.

## Current state (observed 2026-11-02 at `d3efacd1`, rechecked 2026-11-10 at `3149165c`)

Paths are under `backend/app/systems/` unless they start with `frontend/`, `backend/operations/`, `backend/migrations/`, or `tests/`.

**Publish.**

- `POST /api/sandbox/publication-previews` is admin only and returns `previewToken`, `impactDigest`, `changes[]`, `counts`, `warnings[]`, and `blockers[]` (`sandbox/publications/router.py:53-86`).
- A change has `kind` (`department`, `module`, `field`, `relationship`, `trigger`), `action` (`create`, `update`, `close`, `reopen`), a required `sandboxId`, and `label` (at most 150 characters). `PublicationCounts` has one count per kind. Both models forbid extra keys (`sandbox/publications/schemas.py:12-13,30-48`).
- The planner makes `create` for a department with no live binding, `close`, `reopen`, or `update` when the name differs (`sandbox/publications/planner.py:357-391`).
- `_finish` builds `counts` as `<kind>s` over `_kinds()`, and the impact digest covers only `changes` and `blockers`. `warnings` is always empty (`planner.py:317-346`).
- `POST /api/sandbox/publications` checks the password, calls `reauthorize()` again, then checks the token claims and the digest, then calls `apply_publication` (`router.py:89-174`; the second `reauthorize()` is at 127-128). The publish path does not take `lock_projection`; the lifecycle router does. It takes `lock_projection` before `require_fresh_exact_admin` at `sandbox/lifecycle/router.py:178-179` (close) and `:265-266` (purge). The reopen router function (`router.py:282-304`) takes no lock itself; the reopen takes `lock_projection` in `_execute` (`sandbox/lifecycle/execution.py:347-348`).
- `apply_publication` locks (`lock_operational_rows`), recomputes the plan, stages renamed names (`stage_bound_names_and_positions`), applies departments, modules, fields, and relationships, closes removed structure, calls `sync_department_boards`, checks `_assert_no_record_or_edge_changes`, and commits once (`sandbox/publications/executor.py:112-224`). It calls no OpenComms code, so a publish close does not call `revoke_stale`.
- `lock_operational_rows` first locks every live group `FOR SHARE` and every module access row `FOR UPDATE`, then the structure tables in class order, with `SandboxBinding` second (`sandbox/publications/operational_locks.py:25-45`; `sandbox/publications/structure_mutations.py:42-60`).
- `sync_department_boards` loops over every department on every publish (`sandbox/publications/structure_mutations.py:187-192`).
- `SandboxBinding` links one Sandbox document id to one live row, with one nullable foreign key per kind and an exactly-one check (`sandbox/publications/models.py:24-78`).
- A department in the draft has only `id`, `name`, and `closed` (`sandbox/designs/schemas.py:70-73`).

**The second close and reopen path.**

- `POST /api/sandbox/departments/{id}/close` and `/reopen` act on a live department outside a publish (`sandbox/lifecycle/router.py:307-344`).
- The execution locks its NOWAIT scope (`sandbox/lifecycle/execution.py:62-100`), takes `lock_projection` (`execution.py:347-350`), sets `is_deleted`, calls `sync_department_board(db, instance, create=not instance.is_deleted)`, calls `revoke_stale(db)`, and commits (`execution.py:372-393`).
- Plan rows are Sandbox targets only (`_transition_instances`, `execution.py:142-156`). The client parses the lifecycle preview with strict schemas (`frontend/src/lib/lifecycle.ts:27-44,101-112`).
- A department purge removes the department's boards, dashboards, and group access rows (`execution.py:258-273`). It has no step for OpenComms rows.

**Department.** `department_name` (150 characters), `is_deleted` for closed, `lifecycle_close_operation_id`; active names are unique, case-sensitive. There is no parent column (`sandbox/departments/models.py:13-39`).

**Board precedent.** `sync_department_board` creates the Board, archives it on close, restores it on reopen, and copies the name. It never commits (`boards/department_boards.py:14-56`).

**Access.**

- `Group` has no department column. Active names are unique per organization, case-insensitive (`uq_groups_name_active_ci`, `access/policy/models.py:28-52`).
- `GroupAccess` gives a group `read`, `write`, or `manage` on a whole department (module NULL) or one module (`models.py:75-118`).
- `create_group` commits inside the function (`access/policy/service.py:239-260`, commit at 250). It cannot run inside a publish.
- An administrator cannot be a group member (`_refuse_administrators`, `service.py:184-191`).
- A member's access check takes share locks on that member's groups (`access/policy/checks.py:135-171`; `_lock_authority` is 110-173).
- `department_level_reader_statement(..., MANAGE)` gives the people with department manage authority; it leaves out guests (`access/policy/readers.py:134-155`).
- The guest cap is applied when access is read (`access/policy/scope.py:286,299-301`).
- Closing a department keeps its group access rows, so a reopen restores the same access (`sandbox/lifecycle/access_dependencies.py:20-24`).
- Nothing creates groups automatically.

**OpenView.**

- `POST /api/dashboards` needs `manage` on the department and commits inside the route (`openview/dashboards/router.py:287-326`).
- `claim_home_if_missing` makes a dashboard the home when the department has none, and does not commit (`openview/dashboards/service.py:15-31`).
- `uq_dashboards_department_home` allows one active home per department (`openview/dashboards/models.py:44-48`).
- The sidebar leaves out a department with no readable module (`frontend/src/components/department-navigation-model.ts:29-48`, rule DA2). Each listed department starts with its Dashboard row, then Announcements (`frontend/src/components/app-navigation.tsx:556-570`).

**OpenComms.**

- `CommsCategory.department_id` is nullable. A `department` channel requires `department_id`. Both foreign keys to `departments` are `RESTRICT` (`comms/conversations/models.py:27-125`).
- A channel has `archived_at` (`models.py:114`). An archived channel refuses every post (`comms/messages/admission.py:69`), leaves the default list (`comms/conversations/reads.py:184`), and leaves Realtime grants (`comms/realtime/grants.py:43`).
- The archive route sets `archived_at`, calls `revoke_stale`, and sends `organization_event(db, "structure")` (`comms/conversations/router.py:165-182`). The create routes send `structure` and `grants` events (`router.py:101,133-134`).
- A category has no archived state, and no route deletes a category. A category's department can be changed (`comms/conversations/mutations.py:93-111`).
- `stage_conversation` inserts the conversation, its `CommsConversationCounter`, and one member row per person given (`mutations.py:43-60`). `create_channel` passes the creator, which makes the creator a channel manager (`mutations.py:63-81`; `comms/access.py:117-125`, creator arm; the administrator arm is `:132-145`). `_drop_channel_manager` keeps the creator's row (`mutations.py:182-187`).
- `require_department` refuses a closed department (`comms/conversations/service.py:151-163`).
- A department role counts only while the department is open (`access/policy/readers.py:157-201`, open-department check at `174-180`; open department: `comms/access_inputs.py:63-79`). An administrator's channel level and a D45 grant do not depend on it (`comms/access.py:92-146`).
- The moderation purge hard-deletes a conversation (`comms/moderation/purge.py:377`).
- Nothing renames or archives a category or channel when its department changes.

**Manage.** The organization settings have no "new departments get …" setting (`manage/workspace/models.py:75-128`).

**Sample packs.**

- Population runs through the HTTP API and publishes the Sandbox before it creates people and groups (`backend/operations/sample/population/workflow.py:145-160`).
- It reads the automatic Boards and refuses any count other than one per department plus the Company Board (`population/boards.py:149-178`).
- It creates its own functional groups, named from keys such as `harbor-operations` (`population/people.py:143-198`).
- It posts one dashboard per department (`population/openview.py:374-403`) and counts all dashboards (`openview.py:486-487`). Verification matches dashboards by the pack's `dashboard_name` (`controls/openview_verification.py:52,61`).
- No population step creates department categories or channels.

**Publish dialog.** `review-publish-dialog.tsx` renders `warnings` (272-281) and `changes` through `PublishChangeGroups` (288-291). The zod schemas are strict: `kind` is an enum, `label` has a maximum, and `counts` is a strict object (`frontend/src/components/systems/sandbox/state/api.ts:342-377`; the label maximum is at `:347`).

## Three kinds of objects

| Kind | What it is | Examples | Sandbox owns |
| --- | --- | --- | --- |
| Derived | Created from the Sandbox structure. Follows the department's name and state. | The department's three groups, home dashboard, Board, category, and channel | Name and open or closed state only |
| Attached | Made by people, belongs to a department | Cards, posts, extra channels, widgets, extra dashboards, group members | Nothing |
| Organization-wide | No department | Company Board, direct and group messages, My calendar, Manage | Nothing |

## Rules

1. **R1. Creation unit.** A department derives its items once: in the publish that creates it, when it is open after that publish. Modules, existing departments, and reopened departments derive nothing (SD1, SD5, SD9).
2. **R2. The derived set.**

   | Item | Name (pattern) | Created with | Close | Reopen | Department rename |
   | --- | --- | --- | --- | --- | --- |
   | Group | "<Department> managers" | A department access row at `manage`; no members | No change | No change | Takes the new name |
   | Group | "<Department> members" | A department access row at `write`; no members | No change | No change | Takes the new name |
   | Group | "<Department> viewers" | A department access row at `read`; no members | No change | No change | Takes the new name |
   | Dashboard | "<Department> dashboard" (BD2) | Home (`claim_home_if_missing`), no widgets, refresh `manual`, position 0 | No change (OQ1: a separate fix makes dashboard reads and writes require an open department for non-administrators) | No change | Takes the new name |
   | Board | Department name | Existing behavior | Archived (`action: close`) | Restored (`action: reopen`) | Takes the new name |
   | Category | Department name | `department_id` = the department, last position | No change | No change | Takes the new name |
   | Channel | Department name | Scope `department`, in the derived category, `created_by` = the publishing administrator, no member row | Archived (`action: close`) | Unarchived (`action: reopen`), only under R9 | Takes the new name |

   The name patterns are constants. The Product Designer may change the words before slice 1 starts. A group's change label in the review states its access level (for example "Sales managers · manage").
3. **R3. Through each system's code.** Each system gives one helper that creates or updates its object without a commit, and with the same checks its route uses where they apply. The Sandbox calls the helper; it never writes another system's tables directly. Every write is an individual ORM change through the audited session; no Core statement writes through `db.connection()`; `lock_projection` reads a lock. The sync runs no member access check. The actor's authority is the second `reauthorize()`, whose fresh membership read clears the stored result (`common/dependencies/auth.py:376-405`). `effective_levels` flushes (`scope.py:192`), and a content-row lock does not clear a stored result (`docs/architecture/14-security-architecture.md:15-31`). **Accepted departure (PR1, 2026-11-11):** creation goes through each system's own no-commit helper. The follow-up writes (a rename's `name`, a close's `archived_at`) are individual audited ORM changes that the Sandbox sync makes directly on the linked rows (`sandbox/derived/sync.py:115`, `:120`), not through a system helper.
4. **R4. One transaction.** No helper commits. A failure in any derived step rolls back the whole publish, as a failure in the structure does today.
5. **R5. The link.** Each derived item (not the Board, which is unique by department) has one link row: department, role, and the item. The sync finds items only through the link, never by name (SD8). A link row outlives its target: when the target is gone, its target column is NULL.
6. **R6. People own everything else.** The sync changes only the name and the state of a linked item. It never changes members, access rows after creation, widgets, messages, grants, topics, or settings.
7. **R7. Removal wins.** When a person removes a derived item (group deleted, dashboard archived, channel archived, deleted, or purged), the sync leaves it alone and never creates it again. The link stays as the record. An item that a person restores (a dashboard or channel taken out of the archive) is followed again from the next department rename or state change. A deleted group cannot be restored, so it is never followed again.
8. **R8. Close archives, never deletes.** A close archives the derived channel and keeps everything else. It removes no message, no member, no grant, and no access row. Every link row of the closed department records the close (`closed_at`), so the audit log has an entry for every derived item, archived or not. Only the channel's link row can also record `archived_by_close`, with the exact `archived_at` value that the close set, and only when the close itself archived the channel (SD10).
9. **R9. Reopen undoes only the close.** A reopen clears `closed_at` on every link row of the department. It unarchives the channel only when its link row has `archived_by_close` and the channel's `archived_at` still equals the stored value. A channel that a person archived before the close, or archived again or restored after it, keeps the person's state.
10. **R10. Both paths.** The publish path and the lifecycle path run the same sync for every derived kind, in the same order as the Board sync. The sync only follows names and state; only the publish creates derived items (`create_derived_items`, SD10).
11. **R11. Preview equals the action.** Every derived create, rename, archive (`action: close`), and unarchive (`action: reopen`) in a publish is a `change` in its publish preview, and the impact digest covers it. Every derived archive (`action: close`) in a lifecycle close is in the close preview, and the lifecycle impact digest covers it. The lifecycle reopen has no preview; it does only the derived steps that R9 defines and reports them in the result's `impact.derived_changes` (BE-SD7). Neither path does a derived step that its preview, or R9, did not define.
12. **R12. Names that cannot be used block the publish.** A derived group name is a preview blocker when it equals, case-insensitively, an active group name or another derived group name in the same publish (for example new departments "Sales" and "sales"). The blocker names the group and the department; the administrator renames one of them. Renamed derived group names are staged first, as `stage_bound_names_and_positions` does for departments, so a swap of two department names publishes.
13. **R13. No manager.** For administrators only, the Access Overview shows, from `GET /api/users/summary`, that a department has no manager when no active, non-guest, non-administrator account has department `manage` authority on it (`department_level_reader_statement(..., MANAGE)`, without administrators), and offers to add one (SD3, BE-SD8).
14. **R14. Clear before publish (slice 4).** The administrator can clear any derived item of a new department before publish. A cleared item is not created and has no link. It is not created later by any publish.
15. **R15. One computation of derived actions.** One pure function computes the derived actions from the draft, the bindings, the links, and the live targets. The planner uses it for the preview; the executor applies exactly the derived changes of the recomputed `plan.changes`, and after applying, the sync helpers return the rows they created or changed; the executor refuses the publish when that set differs from the plan's derived changes (SD-C26). The audit pending list is already drained at flush, so it is not the comparison source (SD25).
16. **R16. A moved item is not followed.** The sync skips a linked category or channel whose `department_id` no longer equals the link's department (a person moved or rebound it) (SD26).
17. **R17. Comms side effects.** A publish that creates OpenComms items sends `organization_event("structure")` and `organization_event("grants")`. Every publish that closes or reopens any department, or archives or unarchives a derived channel, calls `revoke_stale(db)` before the commit (SD27).

## Decisions

| ID | Decision | Removes or excludes |
| --- | --- | --- |
| SD1 | **Q1, unit.** The department is the unit. A new module creates nothing. Later, a new module may suggest a dashboard widget in the dashboard's set-up state; it never creates one. | Module-level groups, widgets, and channels. |
| SD2 | **Q2, defaults.** Everything is on by default. Organization-wide defaults ("new departments get a channel: yes") live in Manage, and the Sandbox has a per-department override. Both are later slices (slice 4 the override, slice 5 Manage). Until then every new department gets the full set. | A settings surface in slice 1; per-module defaults. |
| SD3 | **Q3, members.** Nobody is added to a derived group. Administrators already manage everything and cannot be group members (`service.py:184-191`). The Access page shows "no manager" to administrators and offers to add one (R13). | Adding the publishing administrator or anyone else; any automatic membership. |
| SD4 | **Q4, sub-departments.** Out of scope. `Department` has no parent column (`departments/models.py:13-39`). | Nested derivation; inherited groups. |
| SD5 | **Q5, existing organizations.** No backfill in this spec. Existing departments, including every department in the seven permanent Large sample packs, get nothing. A backfill is a separate, opt-in action with its own preview, specified later if the owner wants it. A pack that is removed and populated again (`seed_sample_data.py remove`, then populate) is a new organization and gets the derived set. Its Large-pack controls must accept the derived groups and channels. The slice 1 proof stays a small pack. Trade-off: an existing organization does not get the new setup until an administrator creates it by hand or runs the later backfill; in exchange, no publish can flood an existing organization. | The original default (one backfill pass at rollout); derivation for any department that this publish does not create. |
| SD6 | **Q6, preview.** The publish review lists, under each new department, the groups (with their levels), dashboard, Board, category, and channel that the publish will create, before the password row. | Creation that the owner sees only after it happened. |
| SD7 | **Trap 1, kinds not warnings.** Derived items are new `kind` values in `changes[]`: `group`, `dashboard`, `board`, `category`, `channel`. `counts` gets the matching keys. `warnings` stays unused. The preview lists the Board changes of every department that the Board loop touches (`sandbox/publications/structure_mutations.py:187-192`), not only new departments, because the loop changes them all. | Derived items in `warnings`, which the digest does not cover (`planner.py:329-333`); a publish that does more than its review shows. |
| SD8 | **Trap 2, stable link (Architect decision).** One link table owned by the Sandbox, `sandbox_derived_objects` (BE-SD1). Composite `(org_id, <target>_id)` foreign keys with `RESTRICT` (D09, `backend/migrations/AGENTS.md:20`); `SET NULL` on a composite key would set `org_id` to NULL. "At most one target, and a set target matches the role", so the link outlives a removed target (R7). The Sandbox provides a no-commit helper, `release_derived_target(db, conversation_id=…)`, that sets the target to NULL through the ORM, so the audit log records it. `release_derived_target` flushes before it returns, so the link UPDATE precedes the conversation DELETE at the database. It lives in a Sandbox module that imports only the link model. The Comms moderation purge takes `lock_projection` at the start of its graph delete, before it releases the link with `release_derived_target`, so it follows the SD19 order. It releases the link before `db.delete(current.conversation)` (`comms/moderation/purge.py:379-380`). Any other future hard delete of a linked target fails at the foreign key, which is the safe failure. | Lookup by name (a person's rename would make the next publish create a duplicate); columns in four systems' tables; `SET NULL`; an exactly-one check that would block a removed target. |
| SD9 | **Trap 3, scope of each publish.** The derived sync runs only for departments with a derived link or created in this publish. Creation runs only for departments created and open in this publish. Rename and state follow-up run only for departments with link rows whose name or state changes in this publish. The Board loop stays as it is. This narrows the brief's default ("or reopened, if they have no derived objects yet"): a reopen never creates derived items. | Copying the Board loop for groups, dashboards, and channels (it would create the full set for every existing department on the next publish); derivation for a reopened legacy department (it would be an unasked backfill, and the lifecycle reopen previews no creation). |
| SD10 | **Trap 4, both paths.** `apply_publication` and lifecycle execution call one Sandbox function, `sync_derived_objects(db, department, steps, actor_id)` (`sandbox/derived/sync.py:94`), beside the Board sync. It has no `create` flag. Only the publish creates derived items, with `create_derived_items` (`sandbox/derived/planning.py:228`, called at `publications/executor.py:180`). The sync only follows names and state, on both paths. On the publish path it runs (through `follow_derived_items`) after `close_removed_structure` and before the commit. On the lifecycle path it runs after `is_deleted` changes, so `require_department` sees the right state (`execution.py:406`). | A follow-up that runs on one path only. |
| SD11 | **Trap 5, transactions.** Each system adds a no-commit helper: Access `stage_group` (group plus one department access row, no members), OpenView `stage_dashboard` (with `claim_home_if_missing`), Comms `stage_category` and `stage_department_channel`. The channel helper calls `stage_conversation(people=set())`, so it still inserts `CommsConversationCounter` and adds no member row. The channel creator is the publishing administrator (`created_by`): access follows department roles (D44), and the administrator manages every channel by role. Accepted: `_drop_channel_manager` keeps a `created_by` row if one is ever added (`mutations.py:182-187`), as for any channel an administrator creates. Because every group writer and every publish take `lock_projection` first, a group created between review and publish commits before the publish's locked plan, whose R12 recheck refuses with `publication_blocked` and blocker code `derived_name_unavailable`. The unique index stays as the last guard. | Calling `create_group` or the dashboard route inside the publish (both commit); a creator member row; a 503 for a name race. |
| SD12 | **Trap 6, sample packs.** Included: population reads the derived home dashboard of each department and fills it (name and widgets through `PATCH /api/dashboards/{id}`), as it reads the automatic Boards. Population keeps its functional groups. The derived groups stay empty beside them; the names do not collide. Harbor's groups (for example "Sales Writers", `packs/harbor/people.py:53-54`) never end in managers, members or viewers, so they cannot collide. The derived channel and category stay. | A second, populated dashboard beside an empty home; changing the packs' group design. |
| SD13 | **Trap 7, clear before publish.** Slice 1 always creates the full set and lists it. Slice 4 adds clearing. The selection is stored in the Sandbox draft, as an optional `setup` object on the department (`{"groups": true, "dashboard": true, "category": true, "channel": true}`). The draft hash, the plan, and the digest then cover the selection, and the publish request does not change. The review dialog clears an item by editing the draft and reviewing again. Manage defaults (slice 5) set the starting value of `setup` for a new department. The Board cannot be cleared. | A new field in `PublicationRequest`; a selection outside the token and the digest; clearing the Board, which other systems require (`population/boards.py:170-174`). |
| SD14 | **Clearing the category.** A cleared category puts the derived channel in no category. A cleared channel leaves the category empty. | — |
| SD15 | **Trap 8, sidebar DA2.** No change. A new department with no readable module stays out of the sidebar, with its dashboard and Board. Its dashboard is reachable by address, and it appears when its first module is published. A change to DA2 is a separate proposal to the owner. | A silent change to DA2. |
| SD16 | **Trap 9, channel close.** The channel model already has an archived state (`archived_at`). An archived channel refuses every post and leaves Realtime grants. The derived close uses it, with the archive route's side effects (R17). The category has no archived state and stays as it is. No schema change is needed for Comms. | A new Comms archived column; archiving or deleting the category. |
| SD17 | **Who reads a closed department's channel.** Department roles count only while the department is open (`readers.py:157-201`, open-department check at `174-180`). After a close, members lose the derived channel; administrators and D45 grant holders keep it, read-only because it is archived. A channel manager (an administrator) can restore it while the department is closed; R9 then keeps that state at reopen. "Read-only because archived" is true only for the derived channel. Other channels of a closed department stay as they are today: administrators and grant holders can still post there. The lifecycle close preview lists those channels by name (BE-SD7), so the administrator sees them before the close. | A new rule that keeps department readers on a closed department's channel; archiving channels the Sandbox did not create. |
| SD18 | **Rename.** The sync writes the derived names only in a publish that renames the department. A person's rename of a derived item stays until the next department rename. | Enforcing the derived names on every publish. |
| SD19 | **Lock order (Architect decision).** (1) Every publish takes `lock_projection` first: after the password check and before the second `reauthorize()` (`router.py:127-128`), as the lifecycle router does (`lifecycle/router.py:177-179`). (2) Inside `lock_module_access`, before the `FOR SHARE` pass (`sandbox/publications/structure_mutations.py:50-55`), the publish locks `FOR UPDATE`, in ID order, the live linked groups of every department whose draft name or state differs from the live one. After `locked_publication_plan`, every derived group rename of the plan must be inside that set, or the publish raises `live_state_changed`. The publish never upgrades a `FOR SHARE` lock to `FOR UPDATE` during the transaction. (3) `sandbox_derived_objects` joins `lock_operational_rows` directly after `SandboxBinding` (`sandbox/publications/operational_locks.py:29-41`). (4) The linked dashboards, categories, and conversations that the sync changes are locked `FOR UPDATE` after the structure locks and before the locked plan, in this order: dashboards, categories, conversations, each in ID order. (5) The lifecycle path adds `sandbox_derived_objects` and the channel after `sandbox_bindings` in its NOWAIT scope (`execution.py:62-100,347-350`). The lifecycle planner loads the department's link row IDs and its linked conversation IDs into `plan.scope_ids` under the new keys; `_LOCK_MODELS` gains the two entries after `sandbox_bindings`. This rules out three deadlocks: D1, the publish holds groups `FOR SHARE` while a group writer holds the guard; D2, the publish holds the document while a lifecycle close holds the guard; D3, a member's access check holds share locks on a derived group (`checks.py:135-171`) while the publish upgrades its lock. | Lock upgrades inside the publish; a publish without the projection lock. |
| SD20 | **Purge blocker.** A department purge already fails at the database when the department has any category or channel (`RESTRICT`, no purge step). Slice 1 adds a named purge blocker for the department's categories and channels, derived or not, and the purge removes the department's link rows before its dashboards and the department, as it removes bindings. What happens to the content is OQ2. | A purge that fails with an empty blocker list. |
| SD21 | **Name collisions.** A derived group name that collides (case-insensitive) with an active group or with another derived name of the same publish is a preview blocker (R12), on create and on rename. Renamed names are staged first, so a swap publishes. Dashboards, categories, and channels have no name uniqueness, so they never block. | A suffix that hides the collision; a publish that fails at the unique index; a refused name swap. |
| SD22 | **D9.** A publish is an administrator's action, so a derived channel does not break D9. A new organization with nothing published still has no channels. | — |
| SD23 | **`sandboxId` of a derived change.** A derived change uses `<department sandboxId>#<role>`, for example `dep_7#managers` and `dep_7#channel`. The label is the derived name; a group label adds its level (R2). | A second id field in `PublicationChange`. |
| SD24 | **Dashboard on close.** Resolved by the owner in OQ1 (option (b), 2026-11-10): R2 keeps "no change"; a separate fix covers every dashboard. | — |
| SD25 | **Exactly what was planned.** The planner and the sync share one pure function (R15). The executor applies exactly the derived changes of the recomputed `plan.changes`; the sync helpers return the rows they created or changed; the executor refuses the publish when that set differs from the plan's derived changes (SD-C26). The audit pending list is already drained at flush, so it is not the comparison source. The `live_state_digest` adds only the link rows and targets of departments that this publish creates, renames, closes, or reopens, so a change between preview and publish refuses the publish (`live_state_changed`). | A sync that decides on its own at apply time. |
| SD26 | **Moved items.** The sync skips a linked category or channel whose department changed (R16). The link stays; the item is then Attached in practice. | Moving an item back; renaming an item that now belongs to another department. |
| SD27 | **Projection and revoke.** Every publish takes `lock_projection` (SD19). It calls `revoke_stale(db)` before the commit when it closes or reopens any department or archives or unarchives a derived channel. This also closes the existing gap where a publish close never revokes. Creating Comms items sends the `structure` and `grants` events (R17). | Stale Realtime grants after a publish close. |

## Owner decisions (resolved 2026-11-10, APR-0001)

| ID | Question | Options and what each removes | Decision |
| --- | --- | --- | --- |
| OQ1 | **The dashboard of a closed department.** | (a) Archive the derived dashboard on close: runs the BD25 home hand-over, needs a restore rule, and covers only derived dashboards. (b) A separate small fix: dashboard reads and writes require an open department for everyone except administrators; keeps "no change" here. (c) No dashboard rule for a closed department. | **(b), owner, 2026-11-10 (APR-0001).** R2 stays "no change" on close. The separate fix covers all dashboards, not only derived ones, and keeps this spec small. The Security Engineer recommended the same. |
| OQ2 | **Purge of a department with OpenComms content.** No route deletes a Comms category, so after slice 1 no new department can be purged (SD20). | (a) Accept: the purge stays blocked until a separate OpenComms content decision; removes nothing; departments are closed, not purged. (b) The department purge removes the derived category and channel, with their messages, through Comms helpers, listed in the purge preview: removes the block, and deletes messages permanently. | **(a), owner, 2026-11-10 (APR-0001).** Deleting messages is a data-deletion decision that needs its own Comms-owned design and review. Close stays the normal path and keeps everything; purge is rare and already password-checked. The blocker (SD20) makes the limit visible. |

## Backend changes needing your go-ahead

These change a public API, the schema, or a wire format (`fastapi-api-design`, `postgres-patterns`). BE-SD1 to BE-SD4 land first, in slice 1.

| ID | Change | Contract |
| --- | --- | --- |
| BE-SD1 | **Link table** (SD8) | New table `sandbox_derived_objects`: `org_id`, `department_id`, `role` (CHECK in `managers`, `members`, `viewers`, `dashboard`, `category`, `channel`), `group_id`, `dashboard_id`, `category_id`, `conversation_id`, `closed_at` (timestamp, set on close and cleared on reopen), `archived_by_close` (boolean, default false; CHECK false unless `role = 'channel'`), `close_archived_at` (the exact `archived_at` the close set; NULL unless `archived_by_close`), audit fields. Foreign keys are composite `(org_id, <column>)` with `RESTRICT`, for the department and each target (D09). CHECK: at most one target is set, and a set target matches the role. Unique (`org_id`, `department_id`, `role`) and unique per non-NULL target. RLS policy on `org_id` like every organization table (`backend/tests/migrations/test_organization_row_security.py`). Lock entry after `sandbox_bindings` (SD19). Department purge scope: link rows are deleted before dashboards and the department, as bindings are, with a purge-impact display label (`frontend/.../lifecycle-purge-review.tsx:74-76`). Add the table to `APPLICATION_TABLES`, `DELETE_ORDER` and the lock statement (`backend/operations/reset/models.py:99,180,310`). Both the application reset and per-organization removal read these lists (`operations/reset/organization_execution.py:102`). Removal refuses a table with a user reference that is not listed (`organization.py:166-172`), and `BaseModel.performed_by` refers to `users`. The RLS table set is `ORGANIZATION_TABLES` in `backend/tests/migrations/test_organization_root.py:20`. The model joins the audit department-ancestry map (`manage/audit/department_ancestry.py:408-450`). The no-commit helper `release_derived_target` (SD8); `release_derived_target` flushes before it returns, so the link UPDATE precedes the conversation DELETE at the database. Alembic migration with no data change (SD5). The model inherits `BaseModel`, so it gets `ck_sandbox_derived_objects_deletion_state` automatically (`core/database/base.py:14-47`, DBI-5), and the revision must contain it. Link rows are never soft-deleted, and `closed_at` is a separate column. Any partial-index predicate on `is_deleted` uses `IS FALSE` (guard `test_partial_index_predicates.py:122`). Register the model in `model_registry.py`. The revision changes no `audit_logs` row (K36, `backend/migrations/AGENTS.md:21`). |
| BE-SD2 | **Preview and publish wire format** (SD7, SD23) | `PublicationChange.kind` adds `group`, `dashboard`, `board`, `category`, `channel`. `sandboxId` for these is `<department sandboxId>#<role>` (`#board` for the Board). `PublicationChange.label` maximum rises from 150 to 200 on the server (`sandbox/publications/schemas.py:34`) and in zod (`frontend/.../sandbox/state/api.ts:347`), because "<150-character name> managers" is longer than 150. `PublicationCounts` adds `groups`, `dashboards`, `boards`, `categories`, `channels`. No new `action` value. A derived change uses the existing four: `create`, `update` for a rename, `close` for an archive, `reopen` for an unarchive, on `board` and `channel` kinds as on `department`. The digest covers the new changes. The frontend zod schemas change in the same slice; server and client ship in one image. Implementation note: counts are built as `kind + "s"` in `planner._finish` (lines 324-328), so the implementation maps `category` to `categories` explicitly. |
| BE-SD3 | **New preview blocker** (SD21, SD11) | Blocker code `derived_name_unavailable`, `targetId` = the department's `sandboxId`, for a derived group name that collides with an active group or another derived name of the publish. |
| BE-SD4 | **New lifecycle purge blocker** (SD20) | `LifecycleBlockerCode` adds `comms_department_content`, and the strict client enum adds it in the same slice (`frontend/src/lib/lifecycle.ts:27-44`). The department purge preview returns it when a category or channel references the department. |
| BE-SD5 | **Draft `setup` object** (SD13, slice 4) | `DepartmentDocument` adds optional `setup: {groups, dashboard, category, channel}` (booleans, default true). Old documents stay valid. The draft API, versions, import, and export carry it. Only a department without a live binding uses it. Note (N14): every Build save rebuilds the design from its projection (`frontend/src/components/systems/sandbox/domain/document-bridge.ts:540-554`, `design: documentDesign(nextDesign)`), so the design projection must carry `setup` and keep it through every save, or each save drops it. |
| BE-SD6 | **Manage defaults** (SD2, slice 5) | `WorkspaceProfile` adds `department_setup_defaults` (the same four booleans, default true), read and written by `GET` and `PATCH /api/workspace`. Changing it changes no existing department or draft. |
| BE-SD7 | **Lifecycle derived changes** (R11, SD17, slice 2) | `LifecycleImpactResponse` adds `derived_changes: list[DerivedChange] = []` (role, target id, name, action), present in the close preview (`LifecycleClosePreviewResponse.impact`) and in every mutation result (`LifecycleMutationResponse.impact`), empty for module, field, record, file, board, report, and purge impacts. On a department close preview it lists each derived archive plus the department's other channels by name with the note that they stay postable for administrators and grant holders; on a department reopen result it lists each unarchive R9 performed. The lifecycle impact digest covers it. The client changes `lifecycleImpactSchema` (`frontend/src/lib/lifecycle.ts:101-112`) in the same slice. A channel is not a plan row (`execution.py:142-156`), so this is a separate field. Channel names are read directly from `CommsConversation`, administrator-only and organization-scoped (`sandbox/lifecycle/derived_changes.py:94-103`); no Comms read helper exists. A rename between preview and close gives `impact_changed` (`LifecyclePlanDriftError`), and the administrator reviews again. |
| BE-SD8 | **Departments without a manager in the user summary** (R13, slice 3) | `UserSummaryResponse` (`GET /api/users/summary`, administrator-only, `access/users/router.py:101-111`) adds `departments_without_manager: list[UUID]`: the open departments (`is_deleted` false) for which `department_level_reader_statement(..., MANAGE)` filtered to `Membership.role != admin` returns no account. The strict zod schema `userSummarySchema` (`frontend/.../access/state/api-contracts.ts:63-70`) changes in the same slice. |

No change is needed for the channel archive state (SD16) or the dashboard home (BD3).

## Security note (SEC-R6)

This spec weakens no control in the "Controls that reviews protect" table of `SECURITY.md`:

- **Access.** Derived groups have no members, so creating them changes nobody's access. The guest cap and the administrator rule are unchanged; the group label shows its level before publish (R2).
- **OpenComms.** The derived channel is an ordinary department channel. Access still comes only from department roles and D45 grants (`comms/access.py` is unchanged). No member row is added. Close narrows access (archive) and never widens it; reopen restores only what the close changed (R9).
- **Realtime.** Every publish takes `lock_projection` and calls `revoke_stale` when it changes department state or a derived channel, so no grant outlives a close (SD27). This also closes an existing gap on the publish path.
- **Access resolution.** The control "One access function, resolved once per transaction and again after each authority lock or fresh membership read; hidden module returns 404" (`access/policy/transaction_access.py`) is not weakened. The sync runs no member access check; the actor's authority is the second `reauthorize()` (R3).
- **Audit.** Every derived write is an individual ORM change in the audited session (R3), including `release_derived_target`.
- **Organization isolation.** The new table has composite organization foreign keys and an RLS policy (BE-SD1).
- **Preview integrity.** The derived changes are inside the impact digests on both paths and in `live_state_digest`; the executor asserts that it did exactly what it planned (SD25).

## Slices

Slices 1 and 2 ship together: slice 1 alone leaves derived names and channels behind on a rename or a close. Each slice ends with tests that fail first, one code review, and targeted screenshots; the owner checks the live app.

| Slice | Content | Criteria | Narrowest proof |
| --- | --- | --- | --- |
| 1 | **A department comes alive.** BE-SD1 to BE-SD4. The four no-commit helpers and `release_derived_target` with its Comms purge call. The shared derived-action function and the executor assertion (SD25). `lock_projection` and the link lock entry (SD19 steps 1 and 3). Creation for a department created and open in the publish, with the Comms events (R17). The derived kinds and the Board changes of every touched department in the preview and the review dialog. The purge blocker. The population change (SD12). Implementation note: `sandbox/publications/planner.py` (490 lines) and `sandbox/lifecycle/router.py` (499 lines) are at the 500-line limit (`backend/AGENTS.md:19`), so the derived planning and the lifecycle derived-changes read go in their own modules. | SD-C1 to SD-C8, SD-C15 to SD-C17, SD-C21 to SD-C26 | Publication integration tests on PostgreSQL (create, digest, rollback, blockers, race, no creation for existing departments, assertion); migration and RLS tests; dialog test for the new kinds; a fresh-organization population run on a small pack |
| 2 | **Follow name and state.** Rename, close, and reopen on the publish path and the lifecycle path (R7 to R10, R16, R17, SD16 to SD19, SD26, SD27). Rename locks (SD19 steps 2, 4, 5). BE-SD7 and the lifecycle preview. Implementation note: `sandbox/publications/planner.py` (490 lines) and `sandbox/lifecycle/router.py` (499 lines) are at the 500-line limit (`backend/AGENTS.md:19`), so the derived planning and the lifecycle derived-changes read go in their own modules. | SD-C9 to SD-C13, SD-C27 to SD-C32 | Integration tests per path; a concurrency test for SD19; a two-account Comms check that a close stops posting at once |
| 3 | **No manager.** BE-SD8 and the Access state and its action (R13). | SD-C14, SD-C33 | Access API test and page test for each account level |
| 4 | **Clear before publish.** BE-SD5; the per-department choice in the Sandbox and the review dialog. Add `setup` to the Sandbox design projection and keep it through every Build save (N14, see BE-SD5). | SD-C18, SD-C19 | Planner test (cleared item absent, digest changes); dialog test |
| 5 | **Manage defaults.** BE-SD6; the Manage setting. | SD-C20 | Workspace API test; a new department starts from the defaults |

## Acceptance criteria

| ID | Start state | Action | Expected result |
| --- | --- | --- | --- |
| SD-C1 | A draft with a new open department "Sales" | Review | The review lists, under Sales, three groups with their levels, the dashboard, the Board, the category, and the channel, each as a create with its name. `counts` matches. |
| SD-C2 | Same | Publish | Exactly three groups exist with one department access row each (`manage`, `write`, `read`) and no members; one home dashboard with no widgets; one Board; one category and one department channel in it. Each item except the Board has one link row. |
| SD-C3 | Same | Publish | The channel's `created_by` is the administrator; it has no member row and has its counter row. A Sales writer posts; a Sales reader reads only; a guest in "Sales members" reads only. |
| SD-C4 | An organization with existing departments and no link rows | Publish a change to a module, or add one new department | Nothing is created for the existing departments. Only the new department gets its set. No group, dashboard, category, or channel count changes for the others. |
| SD-C5 | A derived step fails during the publish | Publish | The whole publish rolls back: no department, no derived item, no link row. |
| SD-C6 | An active group "sales MANAGERS" exists | Review a new department "Sales" | The review has a `derived_name_unavailable` blocker naming the group; Publish is disabled. |
| SD-C7 | A preview of a new department "Sales" | Another administrator creates the group "Sales managers", then the first publishes | Refused with `publication_blocked` (409) whose blockers carry `derived_name_unavailable`; nothing changes. |
| SD-C8 | A new department created closed in the draft | Publish | No derived item is created; the Board follows today's behavior. |
| SD-C9 | A derived set; a person renamed the channel to "sales-chat" | Publish a rename of Sales to "Revenue" | The groups, dashboard, category, and channel take the derived names for "Revenue". The review listed each rename. |
| SD-C10 | Same, before the rename | Publish another change that does not rename Sales | The person's channel name "sales-chat" stays. |
| SD-C11 | A derived set with messages, grants, and group members | Close Sales by publish, and separately by the lifecycle action | The derived channel is archived: nobody posts. Messages, members, grants, and access rows are unchanged. Each link row has `closed_at`, with an audit entry; only the channel's row has `archived_by_close` and the stored `archived_at`. Members of Sales lose the channel; an administrator reads it. |
| SD-C12 | A closed Sales whose channel the close archived, `archived_at` unchanged | Reopen by publish, and separately by the lifecycle action | The channel is unarchived and Sales members read and post again. `closed_at` is cleared on every link row. The reopen response's `impact.derived_changes` lists the unarchive. |
| SD-C13 | A person archived the channel, then Sales was closed | Reopen | The channel stays archived. A person deleted "Sales viewers": no reopen or publish recreates it. |
| SD-C14 | A department whose groups have no members | An administrator opens Access | The page shows that the department has no manager and offers to add one. With a non-administrator, non-guest manager, the state does not show. |
| SD-C15 | A Large sample pack in the development database | Publish any change | No derived item is created for its departments. A pack that is removed and populated again (`seed_sample_data.py remove`, then populate) is a new organization and gets the derived set. Its Large-pack controls must accept the derived groups and channels. The slice 1 proof stays a small pack. |
| SD-C16 | A fresh organization | Run a population of a small pack | Each department has one dashboard, the derived home, filled by the pack; verification passes. |
| SD-C17 | A department with a derived channel | Preview a purge | The preview shows `comms_department_content`, and the client parses it; the purge does not run. |
| SD-C18 | A new department with "channel" cleared | Review, then publish | The review lists no channel; no channel and no channel link exist after the publish; the digest differs from the uncleared review. |
| SD-C19 | Same, published | Publish later changes | The channel is never created. |
| SD-C20 | Manage default "channel: no" | Add a new department in the Sandbox | Its `setup.channel` starts as false; the administrator can turn it on before publish. |
| SD-C21 | A draft with new departments "Sales" and "sales" | Review | A `derived_name_unavailable` blocker names the colliding derived groups; Publish is disabled. |
| SD-C22 | A department whose name is 80 characters, the draft maximum (`sandbox/designs/field_schemas.py:16`) | Review | The group change labels ("<name> managers · manage", 98 characters at most) are accepted by the server and the client. The 200 limit also covers Board labels of existing live departments and matches `Group.name` and `Dashboard.name` (`String(200)`). |
| SD-C23 | Existing departments without Boards, or with a Board whose name differs | Review any publish | The review lists the Board change of each department that the Board loop changes, and the publish does exactly those. |
| SD-C24 | A derived channel | An administrator purges it through the Comms moderation purge | The purge succeeds; the link row stays with `conversation_id` NULL and an audit entry; later publishes and reopens do not recreate the channel. |
| SD-C25 | A link row or a linked target changes between preview and publish | Publish | The executor checks live state before the impact digest (`publications/executor.py:159-161`), so the publish is refused with `live_state_changed`; nothing changes. |
| SD-C26 | A test hook makes the sync write one more derived item than planned | Publish | The sync helpers return one more row than the plan's derived changes; the executor refuses the publish and it rolls back. |
| SD-C27 | Two published departments "Sales" and "Support" | Publish a draft that swaps their names | The publish succeeds; each derived group takes its department's new name. |
| SD-C28 | A publish renames Sales while a member's access check and a group edit run | Run them at the same time | No deadlock; each finishes or is refused with a named error. |
| SD-C29 | A derived category moved to another department by a person | Publish a rename of Sales | The category keeps its name and department; the other derived items follow. |
| SD-C30 | A person restored an archived derived dashboard | Publish a rename of the department | The dashboard takes the derived name. |
| SD-C31 | A live Realtime grant on a Sales channel | Close Sales by publish | The grant is revoked before the commit; the client stops receiving events within the token lifetime (D34). |
| SD-C32 | Sales has the derived channel and one channel a person created | Preview a lifecycle close, then close | The preview lists the derived channel's archive and names the other channel as staying postable for administrators and grant holders; the close does exactly what the preview listed. |
| SD-C33 | A non-administrator member | Calls `GET /api/users/summary` | 403; the 'no manager' state never renders for a non-administrator. |

## Exit criteria

| Exit | Criterion |
| --- | --- |
| EXIT-SD1 | A new department published in a fresh organization has its full set, listed in the review before the publish. |
| EXIT-SD2 | No existing department in any organization gets a derived item (SD-C4, SD-C15). |
| EXIT-SD3 | Rename, close, and reopen behave the same on the publish path and the lifecycle path, and each path with a preview previews what it does; the lifecycle reopen reports what it did. |
| EXIT-SD4 | No close removes a message, a member, a grant, or an access row; every derived change has an audit entry. |
| EXIT-SD5 | Each system works when a derived item is renamed, archived, removed, or purged by a person (SD-C13, SD-C24). |
| EXIT-SD6 | A sample-pack population on a fresh organization passes its verification. |
| EXIT-SD7 | Each finding has a test that failed first, or a recorded reason; focused batches pass; CI is green. |
| EXIT-SD8 | The owner reviews the live app and approves the result. |

## Risks

- **A larger publish transaction.** Each new department adds about eight inserts and their audit rows, and every publish now takes the projection lock. Large organizations add departments one at a time, so the cost is small; measure it in slice 1.
- **Lock order.** SD19 removes the known deadlocks D1 to D3. A new writer of groups, dashboards, categories, or channels must follow the same order; SD-C28 is its guard.
- **Comms side effects inside the publish.** A mistake in R17 leaves a stale Realtime grant until the token lifetime ends (D34). SD-C31 guards it.
- **Empty groups.** Three groups without members per department add rows to the Access group list. The "no manager" state (SD3) is the answer; a later filter can hide empty derived groups.
- **A department that does not appear.** Until its first module is published, the department is out of the sidebar (SD15). The review should say so; the Product Designer words it.
- **Sample controls that count conversations or groups.** Derived channels and groups can change counts that sample controls expect. Slice 1 runs a population on a fresh organization and fixes such counts in the controls, not in the product.
- **A Large pack populated again.** A pack that is removed and populated again (`seed_sample_data.py remove`, then populate) is a new organization and gets the derived set. Its Large-pack controls must accept the derived groups and channels. The slice 1 proof stays a small pack.
- **Purge stays blocked.** SD20 makes the existing purge failure visible; it does not make a department with a channel purgeable (OQ2).
