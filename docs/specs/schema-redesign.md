# Schema Redesign

> **Status: done (2026-09-28), PR #24.** Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/schema-redesign.md`. Delivery record: [schema-redesign-plan.md](../plans/schema-redesign-plan.md). Current behavior: [architecture](../architecture/README.md).

## Outcome

The 64-table baseline became 49 application tables that model the product: administrators design departments, modules, fields, relationships and record triggers in the Sandbox and publish them; each department has an OpenView home (dashboards, views, reports); Boards are for communication (one company board, one per department, project boards); groups decide read, write or manage per department and module. Everything users create belongs to a department, a board or the company; there is no personal content. A module is rows in `modules`, `fields` and `records` (values in `records.data`); no publish creates a database table.

Main changes: `users.role` (`admin`, `member`, `guest`), `groups`, `group_members` and the new `group_access` (`department_id`, optional `module_id`, `level`); `published_automation_*` renamed to `record_trigger_*`, running as the workspace; dashboards, saved views and reports owned by the department (no `owner_id`); `boards.scope` (`company`, `department`, `project`) with `board_groups` for project boards, posts with revisions and archive instead of delete; `audit_logs.department_id`. 17 tables were removed, among them `roles`, `user_departments`, `service_identities`, `access_rules`, `board_grants` and the personal-content tables.

## Access behavior

1. An `admin` may do everything; only administrators change the schema through the Sandbox.
2. A disabled, pending or expired user is denied.
3. For each group, take the most specific `group_access` row (module, else department).
4. Take the highest level across groups. There is no deny.
5. A `guest` is capped at `read`.
6. `read` reads records; `write` also creates, changes and deletes them; `manage` also changes the department's dashboards, board, shared views and reports, and members of groups whose access lies entirely in departments the user manages.
7. No matching row means no access.

Links into unreadable departments or modules are hidden. One function, `allowed_module_ids(user, level)`, filters every read path. Record triggers act only on their own record ("set field"), run as the workspace, and audit as `actor_label = "Trigger: <name>"`.

## Decisions

| # | Decision |
|---|---|
| 1 | Field-level access: later. |
| 2 | Select options with IDs: yes, slice 7. |
| 3 | A record title field (`modules.title_field_id`): yes, slice 7. |
| 4 | A `user` field type: yes, slice 7. |
| 5 | A `file` field type: deferred with the file changes. |
| 6 | Library documents: open (remove, or make a department library). |
| 7 | Rename `access_groups`, `access_group_members`, `board_announcements` and related tables: yes. |
| 8 | No installation with real data: a new fresh-install root, no data conversion. |
| 9 | `is_deleted` generated from `deleted_at`: open (recommended yes). |
| 10 | Soft delete only on restorable tables: open (recommended, per area). |
| 11 | One shared rate-limit table: open (optional). |
| 12 | Pinned records on boards: removed; posts link to records. |
| 13 | `audit_logs.department_id`: added. |
| 14 | Fill `audit_logs.actor_label` for users: open (declined for now). |

Delivery: slices 1 to 8, each with its own Alembic revision, then slice 8 replaced them with a new fresh-install root (since replaced by the rebrand root, see the plan).

## Acceptance criteria

| ID | Criterion | Result |
| --- | --- | --- |
| 1 | `alembic upgrade head` and `alembic check` per slice. | not recorded here (see the plan) |
| 2 | A user without a group for a department cannot read its records through any read path; guests cannot write; the highest level wins; a manager cannot change a group that reaches outside their departments. | not recorded here (see the plan) |
| 3 | An existing trigger still runs after its publisher loses access. | not recorded here (see the plan) |

## Open items

- Decisions 6, 9, 10, 11 and 14 stay open.
- Deferred by this spec (some may have shipped since; check the code): automations, the organization theme, the Manage Backup, Licensing and Updates panels, user-owned API keys, board templates, post read tracking, file changes (`file_scans`, the `file` field type, library documents), generalized notifications, record import, workspace search, user settings, presence, an Activity screen for audit and security events, record discussions.
