# Documentation Guide

- `docs/architecture/README.md` is the authoritative verified architecture index, mapping checked-in manifests, routes, models, migrations, configuration, scripts, workflows, and tests to 21 numbered documents.
- Before explaining architecture, read and cite the relevant numbered document.
- Keep implemented/partial/planned/absent/unknown classifications honest. When documented behavior changes, update the smallest existing document with source paths/symbols and rerun its documented checks.
- Do not create a document when an existing one has the right scope; do not update documentation for internal refactors that preserve documented behavior.
- Docs explain system architecture, behavior, contracts, and workflows. Do not add test-run results, review findings, dated verification snapshots, task handoffs, or task-specific waivers. Test plans describe how testing works and its boundaries; they are not execution logs.
- Target deployment is single-tenant per client (micro–medium SMB, on-premise first, hosted later). This is design intent, not implemented hosted deployment; never describe multi-tenant SaaS as existing.
- `docs/specs/` holds feature specs and `docs/plans/` holds plans. Proposed behavior stays there, never in the verified architecture documents.
- Terminology lives in `docs/architecture/21-glossary.md`. Use its preferred terms in new docs and plans; add a row there when a new term appears.

## Specs and plans: lifecycle and size

Agents read specs and plans for context, so each one stays as small as its state allows.

1. **Status line.** The first line under the title is `> **Status: <state> (<date>)[, PR #n].**`. States: proposed, approved, in progress, done, superseded, reference (a live contract or data that other work reads). Update it in the pull request that changes the state.
2. **Index.** [`docs/README.md`](README.md) lists every spec and plan with its state. Add or update the row in the same pull request. Agents read the index first and open only the docs they need.
3. **Size while active.** Keep a proposed or active spec or plan under 8,000 words. Put each comp, measurement log, or review round in the pull request or the company task record, not in the doc.
4. **Compact when done.** The pull request that finishes the work, or the next docs pass, compacts the doc in place to its contract: status with PR numbers, outcome, decision table, acceptance criteria table, each section or label that code or docs cite, and open items. Add `Full text: git show <sha>:<path>`. Keep the path and every cited ID, label, and heading; code and tests cite them. Target: 3,000 words or less.
5. **Read only what you need.** For a large doc (for example `DESIGN.md`), read the section that the task needs. Do not read `docs/plans/test-ledger.md` (data for `scripts/assertion_guard.py`) or `docs/plans/sample-organization-research/` unless the task is about them.
6. **Skills by name.** Skills are local and not in Git. Name a skill; never write a skill file path in a doc.

Correct: "Sheets shipped in PR #117; the same PR set the status to done and compacted `docs/specs/sheets.md` to 2,400 words, with every cited P and D label kept."
Wrong: "Moved the finished spec to `docs/archive/`." (breaks the paths that code cites)
Wrong: "Added the third review round's findings to the spec."

## Skills

- Spec files: the `sdd-workflow` skill. Use it to write or update a spec under `docs/specs/`.
