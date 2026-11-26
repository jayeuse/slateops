# UI-equivalent sample data plan

> **Status: done (2026-10-31) for the operator tool, simulated activity runs and all seven organization packs; PR #25 (seeder, Harbor and School), PR #71 (other packs) and PR #73 (Large packs and one-pack removal).** Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/plans/ui-equivalent-sample-data-plan.md`.

## Outcome

`backend/operations/seed_sample_data.py` populates an installation with sample organizations through the same authenticated APIs that the UI controls use (`plan` admits and prints counts, `populate` writes, `verify` reads back counts, states, access and audit). Populated data reads like a working organization: many people act, work is interleaved, records have a history, planned refusals happen, and text uses each business area's terms. Each pack's data files in `backend/operations/sample/packs/<key>/` are the source of truth; the current admission rules are in the [sample-pack contract](sample-pack-contract.md).

## Contract

- Every populated value must be enterable through an existing supported UI control, and population uses that control's authenticated API with the same validation, authorization, concurrency and audit behavior.
- Do not insert application rows directly, call internal services, provision identities through provider-admin APIs, or fabricate audit entries.
- Record edits read the complete record and send all active values (PATCH replaces). Relationship writers need write access to the source module and read access to the target module; a cross-department link is a relationship, and the source record links itself after both records exist.
- Empty results and failures stay honest; no fallback example stands in for a seeded record. A timeout is an incomplete outcome.
- Credentials stay in an owner-only roster, separate from the journal and manifest. The seeder never retries an uncertain POST blindly; a relationship write that returns the known busy 503 is retried once, only after a read shows the edge is absent.
- The development Compose overlay raises the Supabase Auth email, token and verify limits; production settings do not change.

## Acceptance criteria

| ID | Criterion |
| --- | --- |
| SIM-1 | For the same seed, anchor and profile, `plan` prints the same episode count, per-user write counts and planned rejections on every run. |
| SIM-2 | Every create, update and relationship audit row matches the planned actor for that write. No write comes from a user without the required access. |
| SIM-3 | At least 80% of active internal members make at least one write in Small, and all of them do in Standard. |
| SIM-4 | Record, edge and content totals equal the counts the run manifest records. |
| SIM-5 | Each planned rejection returns its expected status and detail. Read-back shows no change from these requests. |
| SIM-6 | No generated value contains a deny-listed word or brand. Title repetition stays under the configured limit in each module. |
| SIM-7 | A Standard run longer than the access-token lifetime completes without a 401 or a Supabase 429. |
| SIM-8 | An interrupted run stops with a readable manifest and never resumes by itself. |

## Decisions

- Work sessions: a user does two to six episodes in a row (create and link, update, Board activity, planned rejection), with business journeys running through the sessions.
- About 40% of records receive one to three updates that follow each module's status order.
- Harbor identity emails use the reserved domain `@harbor-ops.example` with natural local parts.
- A run draws a fresh seed unless `--seed` is set; the manifest records it. Golden masters keep seed 42.
- The marker check (`tests/operations/sample/test_sample_text.py`) blocks `sample`, `test`, `demo`, `dummy`, `fake`, `placeholder`, `lorem`, `ipsum`, `scenario` and `synthetic`, except each pack's `TRADE_PHRASES`.

## Proposed: run sizes and organization packs

This section is done; its heading stays because other documents link to it.

| Profile | Records | Use |
| --- | --- | --- |
| Standard | 5,000 to 7,000 per pack | The normal run for each organization |
| Small | Each Standard module count divided by five, rounded upward, minimum one | A quick check while a pack is being built |
| Large | Four times Standard | Opt-in scale check; the permanent development data since 2026-10-31 |

A pack is data, not code hooks: one complete organization with its departments, modules, fields, relationships, automations, people, groups, access, vocabulary, status paths, named scenario, country, locale, currency and time zone. Planned rejections derive their actors and targets from the pack. Version 2 manifests record the pack, profile, span, sampling scope, exact module counts and planned totals, so `verify` rebuilds from the recorded counts. The pack designs are in [sample-organization-packs.md](sample-organization-packs.md).

The end-of-run admin and reorganization phases (promote, move, disable and re-enable, end a session; archive and restore views, Dashboards, reports and a project Board; purge one extra project Board; Sandbox field, rename, option and empty-module close and reopen) use a separate seeded generator and never close a populated module.

## Open items

None.
