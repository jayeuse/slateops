# CI stability plan

> **Status: done (2026-10-30), PR #72.** Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/plans/ci-stability.md`.

## Outcome

A CI run must fail only for a real defect, not for a random browser-test flake. The fixes are in `frontend/playwright.config.ts` (CI-only retry), `scripts/playwright_flaky.py` and `frontend/tests/flaky.json` (flaky ledger), `scripts/measure_summary.py` (report-only measurement), `.github/workflows/stress.yml` and `scripts/stress_selection.py` (nightly stress job), and `scripts/assertion_guard.py` (retry form guard).

## Decisions

| ID | Decision |
|---|---|
| D1 | One retry in CI only: `retries: isCI ? 1 : 0`; local runs keep zero, and the guard accepts only that exact form. A test that passes only on its retry fails `frontend-verify` unless `frontend/tests/flaky.json` has a current entry with an owner and an expiry at most 14 days after it was added. The `measure` project keeps `retries: 0`. |
| D2 | The Comms timeline measurement (300 ms) reports in the CI job summary, with the trend of the last 10 `main` runs, and does not block. A shared runner cannot hold the limit. |
| D3 | `comms-js-budget` stays blocking because it is deterministic. It warns within 2,000 bytes of the target. A pull request that adds approved shell code records the new target in the same commit, with a test-ledger row that names the feature and the bytes. The CI number is the reference; a Homebrew Node build reads about 1,000 bytes lower (system zlib). |
| S7 | Nightly stress job: recently changed HTTP specs, 20 repeats, 4 workers, zero retries, not required. A race shows here before it reaches a pull request. [ci-speed.md](ci-speed.md) F5 and R4 later set its limits and selection budget. |

## 5. Risks

| Risk | Rule |
|---|---|
| The retry hides a new race | S7 and the `flaky.json` expiry. |
| The HTTP shard weights go stale | When the medians of each HTTP shard's test step time over 3 full runs spread more than 20%, refresh each file's weight with its median over those runs. |
| The backend durations go stale | When the medians of each coverage shard's and unit part's test step time over 3 full runs spread more than 20%, commit each test's median time over those runs from the `backend-coverage` artifact: `test-durations.json` into `backend/tests/.test_durations`, `unit-durations.json` into `backend/tests/.test_durations_unit`. |

## Open items

- D2 also kept the 300 ms limit blocking in `prepush.py`, which `e683f8d0` removed. No local gate now blocks on it.
- The "done when" targets (20 green `main` Frontend runs in a row, 95% first-try green over two weeks) have no recorded result here.
- Not built: an app ready marker and fonts helper (S5), and local Linux parity. Build them when a failure needs them.
