# Sandbox department setup: a published department comes alive

> **Status: done (2026-11-11), PR #100, #103.** Approved by the owner on 2026-11-10 (APR-0001). Slices 1 and 2 shipped in PR #100; slices 3, 4 and 5 shipped in PR #103. Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/sandbox-department-setup.md`.

## Outcome

A department that is new and open in a Sandbox publish gets its working parts in the same publish: three empty Access groups ("<Department> managers" `manage`, "<Department> members" `write`, "<Department> viewers" `read`), one empty home dashboard, its Board, and one OpenComms category with one department channel. The review lists each item before the publish. After the publish, each item is an ordinary object of its own system. The Sandbox keeps a link row per item (`sandbox_derived_objects`) and follows only the department's name and its open or closed state. Code: `backend/app/systems/sandbox/derived/` (`planning.py`, `sync.py`), `sandbox/publications/`, `sandbox/lifecycle/derived_changes.py`; frontend `frontend/src/components/systems/sandbox/domain/department-setup.ts` and `components/setup-popover.tsx`; the Access Overview "Add a manager" row; Manage › Organization "New departments".

Three kinds of objects: **Derived** (created from the structure; the Sandbox owns name and state only), **Attached** (made by people; the Sandbox owns nothing), **Organization-wide** (no department).

## Rules

| ID | Rule |
| --- | --- |
| R1 | A department derives its items once, in the publish that creates it open. Modules, existing departments and reopened departments derive nothing. |
| R2 | The derived set: three groups (no members), the home dashboard "<Department> dashboard", the Board, the category and the channel (`created_by` = the publishing administrator, no member row). Close archives only the Board and the channel. A department rename renames all of them. |
| R3 | Creation goes through each system's own no-commit helper. Rename and archive writes are individual audited ORM changes in `sandbox/derived/sync.py`. |
| R4 | No helper commits. A failed derived step rolls back the whole publish. |
| R5 | Each derived item except the Board has one link row. The sync finds items only through the link, never by name. A link outlives its target (target column NULL). |
| R6 | The sync changes only the name and the state of a linked item. |
| R7 | Removal wins: an item that a person removes is never created again. A restored item is followed again. |
| R8 | Close archives the channel and deletes nothing. Every link row records `closed_at`; only the channel row can record `archived_by_close` with the exact `archived_at`. |
| R9 | Reopen clears `closed_at` and unarchives the channel only when `archived_by_close` is set and `archived_at` is unchanged. |
| R10 | The publish path and the lifecycle path run the same sync. Only the publish creates (`create_derived_items`). |
| R11 | Every derived step is in its preview and impact digest. The lifecycle reopen reports its steps in `impact.derived_changes`. |
| R12 | A derived group name that collides case-insensitively with an active group or another derived name blocks the publish. Renamed names are staged first, so a name swap publishes. |
| R13 | Administrators see on Access Overview each open department with no non-guest, non-administrator manager, with an action to add one. |
| R14 | An administrator can clear any derived item of a new department before publish. A cleared item is never created later. |
| R15 | One pure function computes the derived actions for the planner and the executor. The executor refuses a publish whose applied rows differ from the plan. |
| R16 | The sync skips a linked category or channel that a person moved to another department. |
| R17 | Creating Comms items sends the `structure` and `grants` events. A close, reopen, archive or unarchive calls `revoke_stale(db)` before the commit. |

## Decisions

| ID | Decision |
| --- | --- |
| SD1 | The department is the unit. A new module creates nothing. |
| SD2 | Everything is on by default. Organization-wide defaults live in Manage (slice 5); the Sandbox has a per-department override (slice 4). |
| SD3 | Nobody is added to a derived group. Access shows "no manager" to administrators (R13). |
| SD4 | Sub-departments are out of scope. |
| SD5 | No backfill. Existing departments, including the Large sample packs, get nothing. A removed and repopulated pack is a new organization and gets the set. |
| SD6 | The publish review lists, under each new department, the groups with levels, dashboard, Board, category and channel, before the password row. |
| SD7 | Derived items are new `kind` values in `changes[]` (`group`, `dashboard`, `board`, `category`, `channel`), with matching `counts` keys, not warnings. The preview lists every Board change the Board loop makes. |
| SD8 | One Sandbox-owned link table, `sandbox_derived_objects`, with composite `(org_id, <target>_id)` foreign keys and `RESTRICT` (D09; Architect decision). `release_derived_target` sets a target to NULL through the ORM and flushes; the Comms moderation purge calls it after `lock_projection`. |
| SD9 | Creation runs only for departments created and open in this publish. A reopen never creates derived items. |
| SD10 | Both paths call `sync_derived_objects` (no `create` flag); only the publish calls `create_derived_items`. |
| SD11 | No-commit helpers: `stage_group`, `stage_dashboard`, `stage_category`, `stage_department_channel`. A name race is refused with `publication_blocked` / `derived_name_unavailable`. |
| SD12 | Sample population fills the derived home dashboard and keeps its own functional groups. |
| SD13 | The clear-before-publish choice is an optional `setup` object on the draft department, covered by the draft hash and the digest. The Board cannot be cleared. |
| SD14 | A cleared category puts the channel in no category. A cleared channel leaves the category empty. |
| SD15 | Sidebar rule DA2 does not change. |
| SD16 | The channel close uses the existing `archived_at`. The category has no archived state. |
| SD17 | After a close, members lose the derived channel; administrators and D45 grant holders keep it read-only. Other channels of the department stay as they are and the close preview names them. |
| SD18 | The sync writes derived names only in a publish that renames the department. |
| SD19 | Lock order (Architect decision): every publish takes `lock_projection` first; linked groups of renamed or state-changed departments are locked `FOR UPDATE` before `lock_operational_rows`; `sandbox_derived_objects` follows `SandboxBinding`; then dashboards, categories, conversations in ID order. This rules out deadlocks D1 to D3. |
| SD20 | A department purge has a named blocker for any category or channel of the department. |
| SD21 | Only group names can collide (R12). |
| SD22 | A derived channel does not break D9: a publish is an administrator action. |
| SD23 | A derived change's `sandboxId` is `<department sandboxId>#<role>`. |
| SD24 | Dashboard on close: no change here; resolved by OQ1. |
| SD25 | The executor applies exactly the planned derived changes. `live_state_digest` covers the link rows and targets of affected departments. |
| SD26 | A moved item is not followed (R16). |
| SD27 | Every publish takes `lock_projection` and calls `revoke_stale` on a state change (R17). |
| OQ1 | Owner chose (b): dashboard reads and writes need an open department for non-administrators, as a separate fix. |
| OQ2 | Owner chose (a): a department with Comms content cannot be purged until a separate Comms decision. |

## Backend changes (approved, APR-0001)

| ID | Change |
| --- | --- |
| BE-SD1 | Table `sandbox_derived_objects` with RLS, composite keys, `closed_at`, `archived_by_close`, `close_archived_at`; the migration changes no data or `audit_logs` row (K36). |
| BE-SD2 | `PublicationChange.kind` adds five kinds; label maximum 150 → 200; `PublicationCounts` adds five keys. |
| BE-SD3 | Preview blocker `derived_name_unavailable`. |
| BE-SD4 | Lifecycle purge blocker `comms_department_content`. |
| BE-SD5 | Optional draft `setup: {groups, dashboard, category, channel}`, kept through every Build save. |
| BE-SD6 | `WorkspaceProfile.department_setup_defaults` through `GET`/`PATCH /api/workspace` (migration `fcde5c2045b7`). |
| BE-SD7 | `LifecycleImpactResponse.derived_changes` in the close preview and every mutation result. |
| BE-SD8 | `GET /api/users/summary` adds `departments_without_manager`. |

## Slices

| Slice | Content | Criteria | PR |
| --- | --- | --- | --- |
| 1 | A department comes alive (BE-SD1 to BE-SD4) | SD-C1 to SD-C8, SD-C15 to SD-C17, SD-C21 to SD-C26 | #100 |
| 2 | Follow name and state (BE-SD7) | SD-C9 to SD-C13, SD-C27 to SD-C32 | #100 |
| 3 | No manager (BE-SD8) | SD-C14, SD-C33 | #103 |
| 4 | Clear before publish (BE-SD5) | SD-C18, SD-C19 | #103 |
| 5 | Manage defaults (BE-SD6) | SD-C20 | #103 |

## Acceptance criteria

Result key: "met" means the PR #103 QA hands-on pass recorded the criterion as passing. "Not recorded" means the behavior shipped in PR #100 with its tests, but no per-criterion result was recorded.

| ID | Criterion | Result |
| --- | --- | --- |
| SD-C1 | Review of a new open department lists the three groups with levels, dashboard, Board, category and channel; `counts` match. | not recorded |
| SD-C2 | Publish creates exactly that set; each item except the Board has one link row. | not recorded |
| SD-C3 | The channel has the administrator as `created_by`, no member row; writer posts, reader and guest read only. | not recorded |
| SD-C4 | Existing departments get nothing. | not recorded |
| SD-C5 | A failed derived step rolls back the whole publish. | not recorded |
| SD-C6 | A colliding group name gives a `derived_name_unavailable` blocker. | not recorded |
| SD-C7 | A group created between preview and publish refuses the publish (409 `publication_blocked`). | not recorded |
| SD-C8 | A department created closed derives nothing. | not recorded |
| SD-C9 | A department rename renames every derived item. | not recorded |
| SD-C10 | A publish without a rename keeps a person's channel name. | not recorded |
| SD-C11 | Close (both paths) archives the channel and keeps messages, members, grants and access rows. | not recorded |
| SD-C12 | Reopen (both paths) unarchives the channel and reports it in `impact.derived_changes`. | not recorded |
| SD-C13 | A person's archive survives reopen; a deleted group is never recreated. | not recorded |
| SD-C14 | Access shows "no manager" with an action to add one. | met |
| SD-C15 | Large sample packs get nothing on publish. | not recorded |
| SD-C16 | A small pack population fills one derived home per department. | not recorded |
| SD-C17 | A purge preview shows `comms_department_content`. | not recorded |
| SD-C18 | A cleared channel is not created and the digest differs. | met |
| SD-C19 | A cleared item is never created later. | met |
| SD-C20 | Manage default "channel: no" starts a new department's `setup.channel` as false. | met |
| SD-C21 | "Sales" and "sales" in one draft give a blocker. | not recorded |
| SD-C22 | An 80-character department name gives labels within the 200 limit. | not recorded |
| SD-C23 | The review lists every Board change the Board loop makes. | not recorded |
| SD-C24 | A Comms moderation purge of the derived channel succeeds and nulls the link. | not recorded |
| SD-C25 | A live change between preview and publish gives `live_state_changed`. | not recorded |
| SD-C26 | A sync that writes more than planned is refused and rolled back. | not recorded |
| SD-C27 | A swap of two department names publishes. | not recorded |
| SD-C28 | A rename beside an access check and a group edit does not deadlock. | not recorded |
| SD-C29 | A moved category keeps its name and department. | not recorded |
| SD-C30 | A restored dashboard takes the derived name at the next rename. | not recorded |
| SD-C31 | A close revokes live Realtime grants before the commit. | not recorded |
| SD-C32 | The lifecycle close preview lists the derived archive and names the other channels. | not recorded |
| SD-C33 | `GET /api/users/summary` returns 403 to a non-administrator. | met |

Exit criteria EXIT-SD1 to EXIT-SD8 (full set on a fresh organization, no derived item for existing departments, both paths behave the same, close deletes nothing, systems survive removal of a derived item, sample population passes, tests failed first and CI is green, owner review) shipped with PR #103. No exit result was recorded in the spec; EXIT-SD8 (owner review of the live app) is not recorded.

## Open items

- A backfill for existing departments (SD5) is not specified.
- A department with Comms content cannot be purged (OQ2).
- Empty derived groups show in the Access group list; a filter is a later option.
