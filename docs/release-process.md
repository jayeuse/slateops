# Releases and versions

A published release reaches customers: every installation polls `releases/latest` of this repository (`backend/operations/backup_runner.py:74`) and offers it as an update. Treat publishing as irreversible.

**Choose the version (`MAJOR.MINOR.PATCH`) from what an installed customer experiences.** When unsure, take the higher bump.

| Bump | When | Examples |
|---|---|---|
| Patch `0.1.0 → 0.1.1` | Fixes only. No new feature, no new limit, no change a customer must learn. | A bug fix, a security fix, copy fixes, a dependency update with no behavior change |
| Minor `0.1.1 → 0.2.0` | New or changed features that keep every installation working and need no manual step. | A new module or screen, a new setting, a forward-only migration, a new Office or Headquarters gate on a new feature |
| Major `0.x → 1.0.0`, `1.x → 2.0.0` | An installed customer loses something or must act. Needs the owner's approval before the tag. | A removed feature, a new edition limit on an existing feature, a license file format a current license cannot pass, a backup that an older version cannot restore, a new Windows or hardware requirement, an update that needs a manual step |

Before `1.0.0`, a major-class change still needs the owner's approval, and the owner decides whether it becomes `1.0.0` or the next minor. The release notes then start with a "Before you update" section.

**Rules for every release:**

1. The Git tag is the version. `backend/pyproject.toml` and `frontend/package.json` hold the same `X.Y.Z`; the release workflow refuses a tag that does not match (`scripts/check_release_version.py`).
2. Bump both manifests in a pull request titled `Release vX.Y.Z` with only the version change and any release-only docs. That pull request renames `## [Unreleased]` in `CHANGELOG.md` to `## [X.Y.Z] - <date>`, adds a one-line summary for the version and a one-line entry for each merged Dependabot pull request, and opens a new empty `## [Unreleased]`. It merges to `main` after green CI.
3. A stable tag `vX.Y.Z` goes on a commit of `main`. A test tag `vX.Y.Z-rc.N` goes on any pushed commit and makes a draft titled "Test build, not for customers". Use an rc tag first when the release changes the installer, the engine, the Linux image or a migration, and let the owner install it.
4. Never re-run a failed release workflow, never move a tag, and never reuse a version. Fix the cause and push the next rc number; a failed stable tag burns its version, so the fix ships as the next patch.
5. The workflow always creates a draft. Before publishing, download the assets, run `sha256sum --check SHA256SUMS` and the `cosign verify-blob` command from the release notes, and add a short "What changed" section in customer words (no vulnerability details, SEC-R1). Publish only after the owner says so in chat.
6. Migrations must upgrade every published stable version to the new one with no manual step. Never edit or delete a migration that a published release contains.
7. A license file that worked on the last published version keeps working on a patch or minor release.
8. After a stable release is published, delete its rc drafts and rc tags. Never delete or edit a published release or its tag; a bad release is replaced by the next patch.

Correct: "Fixed the backup retry bug only; bumped to 0.1.1 in `Release v0.1.1`; CI green; tagged `v0.1.1` on main; checksums and cosign pass; owner approved; published."
Wrong: "The v0.2.0 release job failed, so re-ran it and moved the tag to the fixed commit."
Wrong: "Removed the Office export from Desk in 0.2.1 because it is only a small change."
