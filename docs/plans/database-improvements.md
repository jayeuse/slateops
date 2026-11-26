# Database improvements

> **Status: done (2026-11-10), PR #81, #91, #94, #95, #96, #97, #98, #99.** Pull request 2d (steps 2.6, 2.7 and the 1.5 schedule, DBI-11) is not built; it moved to the [cloud pilot plan](cloud-pilot.md) as C13 (D25), and its steps are kept below unchanged. Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/plans/database-improvements.md`.

## Outcome

The plan made the database hold its speed and size as data grows, for one 8-core, 16 GB server with about 300 active people and the seven Large packs. It capped list totals and added keyset paging to the growth lists, removed queue state from audit, added a retention sweep, partitioned and sealed the audit log, replaced worker polling with wake-ups, and closed integrity gaps (soft-delete pair checks, orphan notifications, idle-transaction limit). Main code: `app/common/listing/query.py` (capped count), `app/systems/platform/scheduling/` (retention sweep, work hints), `app/systems/access/policy/scope.py` (access once per transaction), `backend/operations/verify_audit_seals.py` and `check_file_storage.py`, and the migrations named in each step.

## Rules for every item

These rules still govern database work:

1. Change the schema only through a model and an Alembic migration.
2. Create an index on a table that can be large with `postgresql_concurrently=True` inside `op.get_context().autocommit_block()`.
3. Add a constraint to an existing table in two steps: `NOT VALID`, then `VALIDATE CONSTRAINT`.
4. Use real PostgreSQL for constraints, locks, plans and catalog facts; use the statement-budget tests for read counts.
5. Keep `AuditSession` and individual ORM mutations; the only exceptions are the models that D2 and D9 remove from audit and the partitions that step 2.6 drops after a verified archive.
6. Read every query plan as `slateops_runtime`. `postgres` and the owner skip row-level security, so their plans do not show production (F29).
7. A CI test asserts statement counts, pages read, plan shape or row counts, never wall-clock time.

## Decisions

| ID | Decision |
|---|---|
| D1 | Cap totals at 10,000 for every list on the shared helper; keyset paging on the growth lists only. Records lists keep their exact count. |
| D2 | `RecordTriggerEvent` is out of audit (SEC-R6 narrowing for one queue model). |
| D3 | Retention: trigger events and runs 30 days if succeeded, 90 if failed; read notifications 30 days, unread 90; report runs the latest 30 per report plus every run younger than 30 days; Sandbox test runs the latest 20 per document. |
| D4 | `audit_logs` partitioned by month; 13 months online; older months archived, then dropped only after a verified archive (2.6, not built). |
| D5 | Point-in-time recovery closed for this plan; decide again before the first client installation. |
| D6 | Orphan notifications are deleted with their subject. |
| D7 | Nine pull requests, each from its own branch. |
| D8 | Hourly per-organization audit hash chains in `audit_seals`, the chain head in every backup manifest, and a verify command. |
| D9 | A report run is audited as one row with its row count and `csv_sha256`; output rows are not audited (SEC-R6). |
| D10 | Security events archived after 13 months with the audit archive command (2.7, not built). |
| D11 | Comms realtime writes: measure first, then drop the expiry and last-seen indexes and lower the fillfactor. |
| D12 | Auth audit log retention 90 days; replaced by D26. |
| D13 | The 28 partial indexes use `is_deleted IS FALSE` (and `IS TRUE` for `is_home`, `is_default`); the migration lock polls. A catalog test keeps the form. |
| D14 | The member audit page fix (3.7) moved into the follow-up PR #91. |
| D15 | Comms search under row-level security added as step 3.8. |
| D16 | The retention sweep runs on development data too, with no setting to turn it off. |
| D17 | All seven packs populated at Large; later Large runs go one at a time. |
| D18 | Defer pull request 2d; replaced by D25. |
| D19 | The parent runs each pull request to green CI without a stop for approval; Jay merges. |
| D20 | `public.ensure_audit_partitions()` creates months; the audit index set adds `(org_id, created_at, id)` and keeps `ix_audit_logs_action` (SEC-R6: one owner-run routine with no input). |
| D21 | Drop `fk_audit_logs_performed_by_users` so audit rows never change after they are written. |
| D22 | `SECURITY DEFINER` function `public.comms_search_message_ids(text, uuid[])` applies the organization condition itself and returns message ids only (SEC-R6). |
| D23 | Notifications keep offset paging with the capped count; `GET /api/notifications` has no cursor. |
| D24 | Keep 3b as built; the action-filtered audit pages at 25 or 50 rows stay a named gap. |
| D25 | Pull request 2d and DBI-11 move to the cloud pilot plan as C13. |
| D26 | `GOTRUE_AUDIT_LOG_DISABLE_POSTGRES=true`: Auth writes no audit copy to the database. Slate Operations security events are the audit record. |
| D27 | The partial audit index `(department_id, action, created_at, id)` is not built; the production planner settings of 4.1 remove the sort. |

## What was found

F1 count and `OFFSET` paging; F2 Comms member counts C × N; F3 repeated access reads; F4 trigger events in audit; F5 untrimmed trigger events, runs and notifications; F6 `audit_logs` growth; F7 soft-delete pair not enforced; F8 orphan notifications; F9 no idle-transaction limit; F10 duplicate `users` indexes; F11 one-second worker poll; F12 default PostgreSQL settings; F13 no point-in-time recovery; F14 audit indexes store unused rows; F15 no audit tamper evidence; F16 report runs stored three times; F17 trigger event updates not HOT; F18 `records` fillfactor 100; F19 security events never archived; F20 Sandbox test runs never deleted; F21 redundant relationship-edge index; F22 Comms realtime row churn; F23 no file and Storage check; F24 Auth audit log growth; F25 no Auth session limit; F26 partial indexes unusable with `IS false`; F27 slow member audit page; F28 worker polling; F29 Comms search reads every message under row-level security.

## Acceptance criteria

| ID | Criterion |
|---|---|
| DBI-1 | Every list page runs its SQL under 100 ms at p95 on Harbor Large, with the same response shape and authorization. |
| DBI-2 | Comms member counts for the largest Harbor department under 50 ms, same counts. |
| DBI-3 | A record save writes one `records` audit row and no trigger event rows; runs, notifications and automation changes stay audited. |
| DBI-4 | One sweep removes rows older than the D3 periods; newer, pending or referenced rows stay. |
| DBI-5 | Every table with `is_deleted` and `deleted_at` rejects a mismatched pair. |
| DBI-6 | After a record purge, no notification points to that record. |
| DBI-7 | An idle transaction past the limit ends and releases its locks. |
| DBI-8 | The statement budgets do not increase. |
| DBI-9 | An index migration on `audit_logs` or `relationship_edges` does not block record writes. |
| DBI-10 | The seal verify command reports nothing on an unchanged installation, and names the organization, hour and kind of change otherwise. |
| DBI-11 | An audit month is dropped only after its archive passes the checksum check, and a loaded archive verifies against its seals. Not built (D25). |
| DBI-12 | Every audit query returns the same rows after partitioning. |
| DBI-13 | A report keeps its latest 30 runs and every run younger than 30 days; the audit keeps the run and its `csv_sha256`. |
| DBI-14 | A succeeded trigger event holds no value copies; a failed event keeps them for its retry. |
| DBI-15 | The file check command reports removed objects, extra objects and size differences, and changes nothing. |
| DBI-16 | A revoked or expired session ends the provider session no later than the Auth limit. |

## Phases

Steps and their pull requests (all built unless marked):

- Phase 0 (PR #81): 0.1 measurement procedure; 0.2 baseline.
- Phase 1 (PR #81): 1.1 `idle_in_transaction_session_timeout = 60s` on `slateops_runtime`, `lock_timeout = 5s` in migrations only; 1.2 soft-delete pair `CHECK` on all 82 tables through `BaseModel`; 1.3 purge deletes notifications about purged records; 1.4 redundant indexes dropped (catalog test); 1.5 `operations/check_file_storage.py` built, its schedule not built (below).
- Phase 2: 2.1 trigger events out of audit, 2.2 retention sweep (bounded batches, at most 50 audited rows per commit), 2.3 per-table autovacuum, 2.8 report run `csv_sha256` and run retention, 2.9 event values cleared on success, 2.10 `records` fillfactor 90 (PR #94); 2.4 monthly audit partitions (PR #95); 2.5 hourly audit seals, sealed 2 hours after the hour ends, verified by `operations/verify_audit_seals.py`, with chain heads in each backup manifest (PR #96). Steps 2.6 and 2.7 are not built (below).
- Phase 3: 3.3 Comms counts C + N, 3.4 access scope once per transaction in `scope.py`, 3.5 worker wake-up through `slateops_invalidation` with a 30 s safety poll, 3.6 Comms realtime indexes and fillfactor 80, 3.8 Comms search function (PR #97); 3.1 capped count with `total_is_capped`, 3.2 keyset paging on the audit log, relationship list and trigger run list (PR #98); 3.7 member audit page (PR #91).
- Phase 4 (PR #99): 4.1 production PostgreSQL settings in `compose.production.yaml`; 4.2 `ix_comms_messages_live_roots` dropped; 4.3 no connection pooler below 3 workers; 4.4 point-in-time recovery out of scope; 4.5 Auth audit copy off (D26); 4.6 Auth sessions end after 9 h idle and provider sign-out runs on every revoke.
- Phase 5 (PR #99): measurements against DBI-1 to DBI-16.

Not built, kept unchanged (cloud pilot C13). The schedule part of step 1.5: run `check_file_storage.py` on a schedule from the backup runner; this needs the command to run in the server image with the application environment, the runner state to record exit codes 1 and 2, and a way to show exit 1 to the operator.

| Step | Item | Design | Test (real trigger) |
|---|---|---|---|
| 2.6 | F6 | Archive and drop old audit months (D4). An operator command, `operations/archive_audit_month.py`, runs from the backup runner, not from the API, because a drop needs the owner role and the runtime role stays INSERT-only. For each month older than the online period, it: (1) exports the partition in the canonical form of step 2.5, compressed, into the backup export directory, with a manifest that holds the row count for each organization, the file's SHA-256, and the first and last chain hashes of the month; (2) reads the file back and checks the checksum and the chain hashes against `audit_seals`; (3) lets the next encrypted Restic backup, which goes off-host, take the file; (4) only after a snapshot that holds the file is verified, detaches and drops the partition. The seals stay in `audit_seals`. A second command, `operations/load_audit_archive.py`, loads an archived month into a scratch database so that `verify_audit_seals.py` can check it there. | PostgreSQL: a month with a changed archive file is not dropped. A month whose snapshot is not verified is not dropped. A dropped month, loaded from its archive, verifies against its seals (DBI-11). |
| 2.7 | F19 | Archive old security events with the command of step 2.6 (D10). It exports the events older than the online period, checks the file, waits for a verified snapshot, and then deletes them with the owner role. The table stays unpartitioned while it is small. | PostgreSQL: events on both sides of the cutoff; only the archived, old events go. |

## Open items

- Pull request 2d and DBI-11: cloud pilot plan C13 (D25). Security events are deleted at 365 days with no archive until then.
- D24: the School administrator's action-filtered audit page and, under development settings only, the manager's 50-row action-filtered page.
- The audit options statements are above 100 ms for three of four accounts.
- The relationship list with no record filter (only the sample tool and API clients read it).
- Auth sessions that end by local expiry, or are revoked after Auth's 9-hour limit, are not deleted by Auth's cleanup.
- A provider sign-out refused with a code other than `session_expired` stops after 5 attempts.
- The Auth container log has no rotation.
- The step 4.1 settings have not run on Large data on a target host.
- D22-1 (search cost across organizations), the pooler review above 3 workers, and D5 (point-in-time recovery).
