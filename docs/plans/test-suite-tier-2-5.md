# Tier 2.5: test suite refactor plan

> **Status: mostly done, PR #35 (2026-10-15) and later commits.** Item 13 covers F1 to F8 and B2 to B13 (B1 removed no test); items 12, 16, 21, 24, 25 and 26 are implemented. Item 27 is implemented within a lean scope; its open parts are kept in full below. Items without a recorded result are listed in Open items. Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/plans/test-suite-tier-2-5.md`.

## Outcome

This plan refactored every test suite and the CI that runs them, for less bloat, less duplicated setup and shorter run times, with the same or better protection. The final shape is in `docs/architecture/16-testing-architecture.md`. Item numbers are stable identifiers that skills and configuration files cite; do not renumber them. The test parts of later plans, for example the [OpenComms plan](opencomms.md), supersede F9 and I4.

## 1. Non-negotiable rules

These rules apply to every test change. A change that breaks one does not merge.

1. Do not weaken an assertion. Do not replace an exact matcher with a loose one (`toBeTruthy`, `toBeDefined`, `in`, a wider regex). Do not remove an expected value, a status check, or a negative check.
2. Do not make a test pass with a proxy solution: no raised timeout, retry, sleep, `test.skip`, `test.fixme`, `xfail`, `noqa` or `eslint-disable`, and no snapshot update with `-u` without reading the diff.
3. Do not bypass an error. Find whether it is a product bug, a test bug, or an environment difference, and fix that cause.
4. Remove a test only with the evidence that the consolidation rules D1 to D6 of the `tdd-workflow` skill require. Keep each removal in its own commit, apart from any fix.
5. Report test lines and test counts, but never treat them as a target.
6. Obey root rule zero: one heavy test lane at a time on the development machine.

Item 14 makes rules 1, 2 and 4 a machine check (`scripts/assertion_guard.py`).

## 4. Items

| Item | Result |
|---|---|
| 1 | HTTP browser tests run on the static export through a test-only ASGI entry over production `StaticSite`. `PLAYWRIGHT_HTTP_SERVER=dev` is an opt-in for local debugging only. An unmocked `/api` request fails the test. |
| 2 | Worker and shard counts chosen from measurements. |
| 3 | A stack-free backend lane with `pytest-xdist`; stack shards run only `integration` tests. |
| 4 | Per-test coverage contexts for unique-coverage reports; no overall result recorded. |
| 5 | Mutation baseline with `mutmut`; `backend/tests/app_mutation.py` and `backend/tests/sample_mutation.py` run one module in its own root. |
| 6 | Deferred: cheaper fault matrices; item 3 moved these tests off the stack shards instead. |
| 7 | Closed without a change: the stacks keep `JWT_EXPIRY=45` on purpose. |
| 8 | Shared browser mocks in `frontend/tests/http/helpers/`; no overall result recorded. |
| 9 | Remove scaffolding: slice-ID titles, capture calls, the duplicate Access contract spec; no overall result recorded. |
| 10 | Deferred guards on: Ruff `PT011` and `PT012` (give `pytest.raises` a specific exception or `match=`, and keep only the raising statement in its block), and the ESLint Playwright rules. `pytest-randomly` is installed but opt-in (`-p randomly`). |
| 11 | Closed without a change: the file-validation child runs with a scrubbed environment, so coverage cannot reach it. |
| 12 | HTTP shards balanced by duration: a planner assigns whole files longest-first. |
| 13 | Consolidation by work package (section 6), with rules D1 to D6. |
| 14 | Assertion ledger and forbidden-pattern check: each removed assertion needs a row in `docs/plans/test-ledger.md` that names the new owner test. |
| 15 | Clean baseline measured on 2026-10-11. |
| 16 | Sandbox and Access full-stack acceptance split into named journeys; the Harbor Small smoke seed is kept whole. |
| 17 | Open suspects fixed at the cause or removed under D1. |
| 18 | Behavior maps: one checked-in file per `http` family in `frontend/tests/behavior-maps/<family>.md`, each behavior with one owner test. The frontend has no mutation runner, so the map is its proof. |
| 19 | Evaluation of per-test browser coverage; no result recorded. |
| 20 | Shared backend builders and a per-process sample dataset cache that returns copies. |
| 21 | Local and CI parity proved at one exact commit (`ab5bad22006786a7222b559779e94eb6110093cd`) only. |
| 22 | Closed: disposable stacks already run with PostgreSQL durability off; services cannot be trimmed. |
| 23 | Documents updated to the final shape. |
| 24 | Survivor triage: every module with a mutation score triaged. A survivor in behavior that a user, an API client or the data depends on is killed with a test written from the rule, not from the code. Every other survivor is recorded with its class and reason in [mutation-survivors.md](mutation-survivors.md). Do not add `pragma: no mutate`. A module's score must not drop. |
| 25 | Approved product changes that let a lower-layer test own a rule, or remove dead code (backend and frontend parts done). |
| 26 | Compaction pass: row builders and shared fixtures, with no row, input or assertion removed. |

### Item 27 (kept in full)

**Item 27. Scheduled mutation runs** (implemented in `.github/workflows/mutation.yml` and `scripts/mutation.py`; open parts kept in full). Item 24 cleared a backlog of about 1,400 survivors at once. From now on, new survivors must show up one at a time during normal work. Add a scheduled GitHub Actions workflow that runs mutation testing on the modules that changed since its last successful run.
   - **Scope.** Every `app/` module with stack-free owner tests (`backend/tests/app_mutation.py`) and `operations/sample` (`backend/tests/sample_mutation.py`). Select a module when its source file or one of its owner test files changed since the commit of the last successful scheduled run. Modules without stack-free owners stay out (item 24 records them as stack-owned).
   - **Baseline (partial).** `docs/plans/mutation-baseline.json` declares 301 eligible entries: 13 populated baselines and 288 null baselines. The first-run rescan covers the recorded survivors of those 13 seeded entries only, not all survivors documented under item 24. Each remaining module gets a reviewed, revision-bound baseline when its source or owner tests next change; missing-baseline proposals are never automatically accepted. The stored totals of 3,890 kills and 475 survivor names are historical inventory, not a fresh mutation score or a complete baseline for the declared scope.
   - **Result.** The job fails when a module's killed count drops, or when a survivor appears that the baseline does not name. A failure opens or updates one GitHub issue. Known-baseline regressions have native mutant diffs in the bounded artifact path; unbaselined proposals currently provide JSON counts and survivor names, not native diffs. Capturing native diffs for those proposed survivors remains an OPEN item 27 follow-up. The job never blocks a pull request; the developer who changed the module triages the new survivors under the item 24 rules and updates the baseline in the same change.
   - **Schedule and cost.** Run weekly, and on manual dispatch. Cap one run at 60 minutes; modules that do not fit roll over to the next run in a fixed order. Rerun a `timeout` mutant alone before it counts. Report the runner minutes of each run.
   - **Pain points.** CI minutes: only changed modules run, weekly. Flaky timeouts: the single-mutant rerun. Baseline drift: the baseline changes only in the same commit as the tests or code that change it, and the item 14 guard applies to that commit.
   - **Metric.** The report labels this attempt's modules checked (compared) and newly discovered survivor names separately from cumulative cycle and retained-failure totals. Counters reset for each attempt and update on comparison; they are not counts of fresh native invocations. Wall minutes cover the first lane step through report generation, excluding later upload, issue handling and finalization; they are neither billed minutes nor total job time.
   - **Hidden kills (OPEN follow-up).** A cache in a test helper (`@cache`, `lru_cache`, a module-level memo) that calls into the mutated module hides later tests from mutmut's stats run (found in G8b: 15 existing kills were invisible). General scheduled refusal of owner/helper caches that hide calls into the mutated module remains OPEN. Three known sample-cache bypasses under `MUTANT_UNDER_TEST` protect their owned fixture builders, but are not general enforcement. The first run rescans only the recorded survivors of the 13 seeded entries with `MUTANT_UNDER_TEST`; that rescan is not a substitute for general cache protection.

## 6. Work packages for item 13

A work package applies rules D1 to D6 to one area, with a behavior map (frontend) or a mutation result (backend) and test-ledger rows for every removed assertion. Area results are recorded for F1 to F8 and B2 to B13.

| WP | Scope |
|---|---|
| F1 to F8 | Frontend `http` families: F1 OpenView, F2 Boards, F3 Sandbox, F4 Access, F5 Platform, F6 Manage, F7 Auth, F8 Shell and settings (organization settings, theme and display preferences, profile, Help, person card, aggregate calendar, workspace, motion, dialogs). |
| F9, I4 | Comms `http` and isolated tests. **Superseded** by the [OpenComms plan](opencomms.md); removed assertions have [test ledger](test-ledger.md) rows. |
| I1 to I3 | Frontend `isolated` tests: I1 OpenView, Boards and Sandbox matrices; I2 contracts and API; I3 Access, runtime and security. |
| S1, S2, H1 | Full stack (item 16), smoke (item 16), and shared helpers (item 8). |
| B1 to B13 | Backend areas: B1 sample controls (no test removed; fault matrices), B2 other sample tests, B3 Auth, B4 records and views, B5 Boards, B6 workspace, audit and events, B7 files and jobs, B8 Sandbox, B9 lifecycle, B10 backups, B11 migrations, B12 Access and RBAC, B13 runner, runtime and contracts. |

## 12. Decision record

- **Static export server:** `StaticSite` through a test-only ASGI entry; it applies the production CSP.
- **Behavior maps:** checked in, one file per `http` family.
- **Vitest and Stryker for the frontend: not now.** Playwright is the only frontend runner. A second runner needs a recorded decision here. First try per-test browser coverage (item 19), then Vitest and Stryker for an area that loses a behavior the map did not catch.
- **Playwright test agents (planner, generator, healer): do not use.** They add tests and can mark a test as skipped.
- **Retries:** originally 0 everywhere; [ci-stability.md](ci-stability.md) D1 now allows one retry in CI only.
- **PostgreSQL durability off:** disposable test stacks only, never the development or production stack.
- **A module's access rows follow the module (owner, 2026-10-12).** A publish moves each live module access row to its module's department in the same transaction, audited per row; department rows do not move. Every publish repairs rows an earlier move left behind. Two live rows of one group and module keep the most recently written one.
- **Publish lock order:** groups `FOR SHARE`, then module access rows `FOR UPDATE`, then structure. A publish does not bump the group revision. A group writer must not wait for an administrator's user row while it holds a group `FOR UPDATE`.

## Open items

- Item 27: 288 of 301 baselines are deferred; general cache-hiding protection and native diffs for proposed survivors are OPEN follow-ups; hosted scheduled execution, artifact transport, issue handling and real timeout-retry behavior are unverified.
- Item 21's parity proof applies only to commit `ab5bad22006786a7222b559779e94eb6110093cd`.
- Item 6 (cheaper fault matrices) is deferred. Items 4, 8, 9 and 19 and work packages I1 to I3, S1, S2 and H1 have no recorded area result.
- Item 25: the Platform upload state machine refactor is not done; the Platform account helpers, the remaining Manage extractions and the `rate_limit_fingerprint` separator are optional.
- The exit criteria (section 10 of the full text) have no recorded overall result.
