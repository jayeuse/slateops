# Schema Redesign Implementation Plan

> **Status: done (2026-09-28), PR #24.** The active fresh-install root is now `e46611902f25`, from the rebrand (PR #84). Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/plans/schema-redesign-plan.md`.

## Outcome

The redesign replaced the flat capability model with department and module access through groups, replaced published automations with record triggers, made OpenView content department-owned, scoped Boards, and added audit department ancestry. It ended with a new fresh-install root of 49 application tables. Later work extends the root, and the active chain now creates 55 application tables; count them from `op.create_table` and `op.drop_table` in the active revisions under `backend/migrations/versions/`, not from model `__tablename__` declarations. Main code: `backend/app/systems/access/policy/scope.py` (the access function), `sandbox/record_triggers/`, `openview/`, `boards/`, `manage/audit/listeners.py`. The contract is the [schema redesign spec](../specs/schema-redesign.md); current behavior is in [data architecture](../architecture/06-data-architecture.md) and the other architecture documents.

## Decisions

Decisions of the user (section 1.3): no real data to convert, and a new fresh-install root; select option IDs, a record title field and a `user` field type (slice 7); rename `groups`, `group_members`, the Board post tables and `record_triggers` everywhere, with no conversion of old designs; remove `board_record_placements`; add `audit_logs.department_id`; field-level access later; scheduled reports run as the workspace, module readers open runs, managers set schedules; event reminders are set by the author and notify the Board audience; a never-published post is deleted and a published post is archived; read tracking is not a Boards responsibility.

| ID | Decision |
|---|---|
| D1 | Retire the old seeder during the redesign; the later API-based runner is `backend/operations/seed_sample_data.py` (see the [sample-pack contract](sample-pack-contract.md)). |
| D2 | Slice 3 used an integration branch with sub-pull requests; main received it only when all of it passed. |
| D3 | Each slice added a normal Alembic revision; slice 8 replaced the chain with a new root. |
| D4 | `GET /api/auth/me` returns `role` and an `access` list of `{department_id, module_id, level}`, not `permissions`. |
| D5 | Rebuilt Access screens use TanStack Query, following the `query-cache-patterns` skill. |
| D6 | A Sandbox publish creates one department board for each new department; there is one company board. |
| D7 | Administrators create project boards and assign `board_groups`; `manage` in `board_groups` lets that group manage the board. |
| D8 | Users with `manage` on a department read that department's audit entries. |
| D9 | Only administrators use the Sandbox, publish, and lifecycle close, reopen and purge. Record export follows Tier 2 D12: module readers may export CSV and Excel. |
| D10 | Record and relationship invalidation events carry `module_id`; the SSE hub sends them only to subscribers who can read that module. |
| D11 | The 409 "Use Close" delete routes for departments, modules and fields are removed. |
| D12 | `POST /api/modules/{id}/fields/reorder` is removed; field order comes only from the Sandbox document. |
| D13 | The Access nav item shows for administrators and for users with `manage` on any department. A manager sees only the Groups tab and only the groups they may manage. |
| D14 | Members change through `PUT /api/access/groups/{id}/members` with `If-Match`; `PATCH` (name, description) is administrator-only. A non-guest active user with `manage` on every department that the group's `group_access` rows reach may replace the members; a group with no access rows is administrator-only. `GET /api/access/groups` returns only the groups a manager may change. `GET /api/access/member-candidates` returns the minimal list for a manager. |
| D15 | `GET /api/reports/audience-roles` returns 422 because `/api/reports/{report_id}` matches the path; the route no longer exists. |

Boards continuation decisions (section 1.5, 2026-09-28): authors archive their own posts and events; reminder timings are start, 15 minutes before and 1 day before, delivered up to 15 minutes late, never duplicated; purging a department purges its department board and owned content, and file bytes must already have a confirmed purge before their metadata goes.

## Slices

| Slice | Content | Criteria |
|---|---|---|
| 1 | Close the direct schema routes: the Sandbox publish is the only way to change departments, modules and fields; `modules.is_schema_accepted` dropped | S1-1 to S1-5 |
| 2 | Record triggers: every `published_automation_*` table renamed to `record_trigger*`; Sandbox document version 3; triggers run as the workspace with `actor_label` "Trigger: <name>" | S2-1 to S2-5 |
| 3 | Access, on an integration branch: 3a sample data out of Access, 3b schema and identity, 3c the access function and every read path, 3d manager delegation, 3e Access screens | S3-1 to S3-10 |
| 4 | OpenView belongs to departments | S4-1 to S4-6 |
| 5 | Boards: company, department and project boards; posts with revisions; event reminders | S5-1 to S5-8 |
| 6 | Audit department: `audit_logs.department_id`, derived at write time | S6-1, S6-2 |
| 7 | Field model: select option IDs, record title field, `user` field type | S7-1 to S7-4 |
| 8 | New fresh-install root | Chain and root give identical `pg_dump --schema-only` |

### 3c: The access function and every read path

`scope.py` gives `effective_levels`, `allowed_module_ids` and `level_for`. An administrator has `manage` everywhere; a user in several groups gets the highest level per module; a guest is capped at `read`; no access row means no access. Every read path takes its filter from this function: records (list, get, mutations, query, aggregate, export), relationships (both endpoints readable, else the edge is hidden; `write` on the source, `read` on the target), file access through the record module, report capture, eligibility and run reads, saved views, Sandbox `GET` routes, SSE delivery (D10) and Board record links. Each path has one denial test (`backend/tests/access/test_read_paths_integration.py`).

### 3d: Manager delegation

A user with `manage` on every department that a group's `group_access` rows reference can change that group's members (D14). Other group changes stay administrator-only. A manager of Inventory gets 403 for a group that also reaches Finance.

## Rollback

Use only the downgrade that a revision supports. Slice 7 refuses downgrade, because option IDs cannot be converted back losslessly. Do not stamp an existing database onto a new root.

## Open items

- Spec decision 6 (library documents): deferred with files.
- Spec decisions 9 and 10 (generated `is_deleted`, soft delete only on restorable tables): not in any slice.
- Spec decision 11 (one rate-limit table): deferred.
- Spec decision 14 (`actor_label` for users): declined; only triggers write `actor_label`.
