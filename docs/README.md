# Documentation index

Read this index first, then open only the documents that the task needs. Rules for these documents are in [AGENTS.md](AGENTS.md).

| Folder | What it holds | Read it when |
|---|---|---|
| [architecture/](architecture/README.md) | The verified architecture, with source paths (21 numbered documents and the glossary) | You explain or change how the system works |
| [customer/](customer/README.md) | Guides for customers: quick start, administrator and user guides, editions, privacy | You change something a customer sees or does |
| [specs/](specs/) | Feature specs: the contract for a feature | You build or change that feature |
| [plans/](plans/) | Engineering plans: how a change was or will be built | You continue that work, or code cites it |
| [release-process.md](release-process.md) | Versions, the Release pull request, tags and publishing | Any release step |
| [hands-on-testing.md](hands-on-testing.md) | Hands-on feature passes and the release smoke pass | A hands-on pass |

States: **proposed** (not approved), **approved** (not built), **in progress**, **done** (compacted to its contract; the full text is in git), **reference** (live data or a contract that other work reads).

## Specs

| Spec | State | Built in |
|---|---|---|
| [access-ui-ux-pass](specs/access-ui-ux-pass.md) | done | #60 |
| [boards-relayout](specs/boards-relayout.md) | done | #69 |
| [editions](specs/editions.md) | done | #123 |
| [manage-relayout](specs/manage-relayout.md) | done | #62 |
| [opencomms-department-access](specs/opencomms-department-access.md) | in progress (slice 5 open) | #56 |
| [openview-dashboard](specs/openview-dashboard.md) | done | #68 |
| [openview-department-pages](specs/openview-department-pages.md) | done | #68 |
| [openview-relayout](specs/openview-relayout.md) | done | #68 |
| [openview-reports-in-modules](specs/openview-reports-in-modules.md) | done | #68 |
| [profile-sidebar-relayout](specs/profile-sidebar-relayout.md) | done | #67 |
| [sample-pack-realism](specs/sample-pack-realism.md) | done | #70, #71, #73 |
| [sandbox-department-setup](specs/sandbox-department-setup.md) | done | #100, #103 |
| [sandbox-followup-pass](specs/sandbox-followup-pass.md) | done | #54 |
| [sandbox-relayout](specs/sandbox-relayout.md) | done | #61 |
| [sandbox-ui-ux-pass](specs/sandbox-ui-ux-pass.md) | done | #54 |
| [sandbox-ux-redesign](specs/sandbox-ux-redesign.md) | done | #100 to #103 |
| [schema-redesign](specs/schema-redesign.md) | done | #24 |
| [sheets](specs/sheets.md) | done (two items deferred) | #117 |
| [signed-out-pages](specs/signed-out-pages.md) | done | #112 |
| [subtle-interactions](specs/subtle-interactions.md) | done | #110 |
| [system-health](specs/system-health.md) | done | #87, #88, #89 |
| [ux-friction-pass](specs/ux-friction-pass.md) | done | #107, #108, #109 |
| [windows-installer-wizard](specs/windows-installer-wizard.md) | done | #115, #121, #122 |

## Plans

| Plan | State | Built in |
|---|---|---|
| [access-functionality-plan](plans/access-functionality-plan.md) | reference (current contracts) | — |
| [access-recovery-compatibility](plans/access-recovery-compatibility.md) | reference (current contracts) | — |
| [api-rate-limits](plans/api-rate-limits.md) | proposed | — |
| [boards-openview-functionality-plan](plans/boards-openview-functionality-plan.md) | reference (current contracts) | — |
| [ci-speed](plans/ci-speed.md) | done | #92, #93 |
| [ci-stability](plans/ci-stability.md) | done (D1 is a live rule) | #72 |
| [cloud-pilot](plans/cloud-pilot.md) | proposed | — |
| [database-improvements](plans/database-improvements.md) | done | #81 to #99 |
| [mutation-survivors](plans/mutation-survivors.md) | reference (read by `mutation.yml`) | — |
| [opencomms](plans/opencomms.md) | in progress (S32, S34, S35 open) | #56 |
| [product-concurrency-fixes](plans/product-concurrency-fixes.md) | done | #71, #73 |
| [rebrand-slate-operations](plans/rebrand-slate-operations.md) | done | #84, #85 |
| [sample-organization-packs](plans/sample-organization-packs.md) | done | #71 |
| [sample-organization-research/](plans/sample-organization-research/) | reference (research for the sample packs) | — |
| [sample-pack-contract](plans/sample-pack-contract.md) | reference | — |
| [schema-redesign-plan](plans/schema-redesign-plan.md) | done | #24 |
| [supabase-foundation](plans/supabase-foundation.md) | approved (Phase 1 built in #52) | #52 |
| [system-completion-tier-1](plans/system-completion-tier-1.md) | done | #32 |
| [system-completion-tier-2](plans/system-completion-tier-2.md) | done | #34 |
| [test-ledger](plans/test-ledger.md) | reference (data for `scripts/assertion_guard.py`; do not read) | — |
| [test-suite-tier-2-5](plans/test-suite-tier-2-5.md) | in progress (items open) | #35 |
| [ui-equivalent-sample-data-plan](plans/ui-equivalent-sample-data-plan.md) | done | #73 |
| [windows-installer](plans/windows-installer.md) | in progress (in-app update open) | #115, #121, #123 |

## Other documents

| Document | State |
|---|---|
| [dynamic-field-validation-test-plan](dynamic-field-validation-test-plan.md) | reference (test plan) |
| [sandbox-designer-template-test-plan](sandbox-designer-template-test-plan.md) | reference (test plan) |
| [reviews/known-gaps](reviews/known-gaps.md) | reference |
