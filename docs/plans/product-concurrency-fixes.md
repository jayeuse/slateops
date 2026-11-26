# Product concurrency fixes

> **Status: done (2026-10-30), PR #71, with the one-pack removal in PR #73; Phase 5 step 3 (the hands-on pass) has no recorded result.** Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/plans/product-concurrency-fixes.md`.

## Outcome

Seven sample packs that populated one installation at the same time showed product defects. This plan fixed their causes in the product, not by tuning the product or tests to pass a sample run. Each item has a real-world trigger, a failing-first test, and a record in `docs/specs/sample-pack-realism.md`. Target for every capacity default and load test: one server with 8 cores and 16 GB, up to about 300 people active at the same time across all organizations.

## Decisions

| ID | Defect and decision |
|---|---|
| C1 | Purge or close confirmation deadlock: a per-administrator transaction advisory lock serializes the attempt counter; the user row is never upgraded to `FOR UPDATE`. |
| C2 | A short Auth outage no longer signs users out. On Auth unavailable, or a fresh token that fails local checks, the session stays and the API answers 503 with `Retry-After`. Only a definite refusal revokes. The browser is quiet for 5 s, then shows "Reconnecting…". |
| C3 | File transfers: see step 3.1. |
| C4 | Automations run within 2 s at the target: 4 trigger threads (`TRIGGER_WORKERS`) claim with `FOR UPDATE SKIP LOCKED`; one record's events never run in parallel or out of order. |
| C5 | Withdrawn: the existing Jobs retry flow is the design. |
| C6 | Comms exports failed on a refused transfer slot; fixed by C3. |
| C7 | One publisher thread per API process with a bounded queue (1,024 events) and one long-lived connection; a failed or overflowing publish sends one `resync`, so browsers refetch instead of losing the update. |
| C8 | Production runs the measured best number of API workers (Phase 4). |
| C9 | The operator acts like an organization administrator: "end all sessions" skips accounts of other organizations. |
| C10 | Expired rate-limit bucket cleanup skips buckets another transaction holds (`SKIP LOCKED`), so it no longer deadlocks with sign-ins. |
| C11 | The installation security save takes session locks with a normal wait, before the organization row, and logs the cause of every 503. The runtime role has no role-wide `lock_timeout` because of this. |
| C12 | Caddy's FastAPI upstreams use `keepalive 3s`, below the API's 5 s idle close; the sample client expires idle connections after 2 s. |
| C13 | `relationship_edges` has plain `(org_id, source_record_id)` and `(org_id, target_record_id)` indexes (migration `48e05d7138d7`). |

Sample tooling defects T1 and T3 to T9 were fixed in the sample runners, not in the product.

### Step 3.1: file transfer capacity (C3)

Two limits replace the old two transfer slots. A memory budget per API process (`FILE_MEMORY_BUDGET_MIB`, default 256) is reserved from `Content-Length` or the file size before the body is read; a chunked body reserves the route maximum, and a body past its declared size gets 413. Processing slots (`FILE_PROCESSING_SLOTS`, default 4) cover only validation and Storage I/O, and are released before a slow client receives the response. A full budget answers 503 `files_busy` with `Retry-After: 1`. The upload and download UI retries it and shows "Waiting for the server…", then an error after about 30 s. Logo and avatar saves use the same budget and slots.

### Phase 4: throughput

`API_WORKERS` (default 1, range 1 to 8) sets the Uvicorn worker processes. Every background claim is safe with several processes. Each worker costs about 250 to 300 MB and up to `DATABASE_POOL_SIZE` + `DATABASE_MAX_OVERFLOW` + 3 database connections. On the development machine, 2 and 3 workers were slower than 1, so production keeps `API_WORKERS=1` in `compose.production.yaml`. Measure again with a load that saturates one process before raising it. Record create and edit now read the module's readers and fields once per request.

## Open items

- Phase 5 step 3: the hands-on pass for purge confirmation, session refresh, and file upload and download has no recorded result.
- Not changed: the audit listener's redacted-field and link-module reads, the reader query's separate department lookup, and the batch-update route reading readers once per item.
- Rate-limit numbers belong to `docs/plans/api-rate-limits.md`.
