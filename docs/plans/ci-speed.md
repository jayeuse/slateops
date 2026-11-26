# CI speed plan

> **Status: done (2026-11-06), PR #92 (steps 1 to 3) and PR #93 (section 8, root-cause work).** Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/plans/ci-speed.md`.

## Outcome

Backend and Frontend CI each finish in about 8 minutes on a pull request. The unit lane runs as 3 jobs, the coverage shards went from 5 to 10, and the HTTP shards from 6 to 8 (`.github/workflows/backend.yml`, `.github/workflows/frontend.yml`). PR #93 replaced the PR #92 workarounds with root-cause fixes. All rules of [ci-stability.md](ci-stability.md) stay.

### 1.1 Runners have two speeds

The same unit tests took 1.36× longer on the slow GitHub runner (EPYC 7763) than on the fast one; integration tests took 1.09× longer. Every job is sized for the slow runner.

## Decisions

| ID | Decision |
|---|---|
| F3 | CI uploads the trace folder when a test passes only on its retry, not only on failure. |
| F4 | No `--with-deps` on any Chromium install, so CI never uses `apt-get`. |
| F5 | The stress job's step limit is 110 minutes and its job limit 120 minutes, so a run finishes. |
| B1 | The Comms search timing test reports its 300 ms number in CI and does not block, as ci-stability D2 does for the timeline. The SELECT-count and row-bound assertions block. |
| S1 | The unit lane runs as 3 pytest-split jobs, `-n 4` each, with its own durations file. Each part has its own evidence, and `combine` needs all parts. |
| S2 | 10 coverage shards with committed integration durations; refresh by [ci-stability.md section 5](ci-stability.md#5-risks). |
| S3 | 8 HTTP shards, 2 workers each. |
| S4 | Each job timeout is about twice the slowest measured job, so it stays a real hang guard. |
| R1 | Each duplicate sample dataset builds once per test process; a digest fails a test that changes shared data. |
| R3 | A deterministic page ceiling on the search SQL blocks in CI. |
| R4 | The stress selection budget uses real minutes from measured runs. |
| R5 | The opening sidebar panel cannot scroll, so its click race ends. |
| R6 | The cold Boards test measures the real order: a cold load reads the list twice when the stream connects late. The 34-request budget stays. |

Other slices (F1, F2, F6, F7, F8, B2, R2) fixed single flakes or setup costs and set no rule.

## 5. Owner decisions

The owner approved steps 1 to 3, B1, and R1, R3 and R6 on 2026-11-06. Timing limits report in CI; wall-clock limits block only in a local gate run. The CI retry stays until first-try green reaches the goal; removing it is an owner decision.

## Open items

- The local gate (`prepush.py`) was removed in `e683f8d0`, so no local run blocks on the timing limits.
- REQ-0005 (search index under row security) blocked the R3 index assertion. The test comment says the D22 definer function now uses the index (REQ-0005).
- The "done when" targets (10 runs in a row at 8 minutes or less, 95% first-try green, empty `flaky.json`, stress green 3 nights) have no recorded result. `flaky.json` holds 3 entries on 2026-11-26.
