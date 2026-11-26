# Hands-on testing

Claude owns hands-on testing: using the real app as each role would, on the live development stack. It complements the automated suites and never replaces them; mocked HTTP suites passed while hands-on tests found lost messages and wrong author names.

Run two kinds of passes:

- **Feature pass**, right after each feature or slice that changes user-visible behavior is implemented (including a cutover from mocks to real APIs, and after a defect fix lands). Purpose: find errors, bugs and UX issues early, so they are fixed inside the implementation phase, not after it.
- **Release smoke pass**, once implementation is essentially done and before the push. Purpose: smoke out underlying and cross-feature issues before anything is pushed. Cover every role end to end on both a fresh organization (create a new one; never reset development data for this) and an existing sample-pack organization (Harbor, and School when its pack is loaded), plus the flows that span features.

Fresh organizations expose first-run and empty-state defects; sample-pack organizations expose defects that need real volume, many people, groups, records and history. A feature pass uses the sample-pack organization by default, and adds a fresh organization when the feature touches first-run or empty states. Order: smoke pass, then its fixes, then the push; CI runs the full suites. Never run the smoke pass beside a local heavy suite (rule zero).

1. Check preconditions: owned dev stack up (`python3 scripts/dev.py db`), database at head (provision role, `uv run alembic upgrade head`), API `/api/ready` ready. Start nothing beside a heavy test lane or a measurement run (rule zero in `AGENTS.md`).
2. Use one Next dev server per checkout. If another agent needs the port, stop yours; stop it after the pass either way.
3. Sign in with the hands-on accounts below. Use the second account of a two-account test in the playwright MCP browser so its cookies stay separate.
4. Before testing, write down what each account should see and do for the feature under test; then check it against what the app does.
5. A feature pass covers the changed feature for the account levels it affects. A release smoke pass covers, per account level: first-run and empty states, the core flow, permission edges, two-account real-time delivery with measured latency, persistence after reload, desktop 1440x900 and mobile 390x844, console errors, and API request counts on a cold load.
6. Report each defect with steps, expected versus actual, evidence (network, console, screenshot), and severity.
7. Every defect becomes a failing-first automated test in its fix commit. The implementing agent fixes it; Claude retests it by hand.
8. Leave test data in the development database and list what was created.

## Hands-on accounts

The operator account (`openslate.business@outlook.com`) belongs to the owner. Use it only to run sample packs (the operator credential of `seed_sample_data.py`), never for hands-on tests. The only accounts Claude may use are the testing accounts of each sample-pack organization. They are permanent: never delete, rename or demote them, and leave the sample people untouched.

`<org>` is the pack key with hyphens (`harbor`, `school`, `clinic`, `nonprofit`, `local-government`, `fmcg-distributor`, `manufacturer`); `<dept>` is the department key.

| Account | Level | Expected |
|---|---|---|
| `admin@<org>.test` | Organization admin (the pack administrator; it ran the population) | Manages the organization; cannot read others' DMs or private channels (D43) |
| `<dept>.manager@<org>.test` | Member, manage on that department | Manages that department's conversations only |
| `<dept>.writer@<org>.test` | Member, write on that department's modules | Posts where readable; no admin or manager tools |
| `<dept>.reader@<org>.test` | Member, read only | Reads; cannot post where posting needs write |
| `general.noaccess@<org>.test` | Member, no group access | Sees only conversations they belong to |
| `<dept>.guest@<org>.test` | Guest in one group | Read-capped; no admin or manager actions |

- All testing accounts share one password chosen by the owner. It lives only in `~/.config/openslate-handson/accounts.json` (every testing account) and `~/.config/openslate-handson/administrator-password.json` (the pack administrators; a populate run passes it with `--administrator-password-file`). Both are mode 600, outside the repo. Never repeat it in chat, tracked files or memory.
- A populate run creates `admin@<org>.test`. The admin invites the other testing accounts in Access → People, and each invitation is completed through Mailpit (`127.0.0.1:<SUPABASE_MAIL_PORT>`).
- Never read `.env` or sample-run credential files (SEC-R3).
- The guarded reset removes these accounts with their organizations; recreate them afterwards.
- Never run the installation-wide guarded reset (`reset_application_data.py`) on the dev database. It wipes every sample pack, and each Large pack takes 1.5 to 3 hours to populate (4 or more hours when two run together, so populate one at a time). To redo one pack: stop the dev API, run `seed_sample_data.py remove --organization <pack>` (dry run, then `--execute --confirm-digest`), start the API, and populate that pack alone. Check the current pack sizes in the database before you rely on them.
- The operator credential is saved at `~/.config/openslate-handson/operator-password.json` (mode 600). Pass it to populate runs with `--admin-password-file`; never read it, and never ask the owner for it again.

Wrong: `Ran reset_application_data.py to get a clean database for the test.`

Correct: `Admin in the pane, invited member in playwright MCP: delivery 250 ms, reply live; B7 first send after load dropped with no POST and no "Not sent" (high); sent to the implementer as a failing-first test; retest after the fix.`
Correct: `Release smoke pass on a fresh organization and on Harbor before the push: admin, member and guest end to end in both; one cross-feature defect (scheduled message ignores a later block) fixed with a failing-first test; then pushed, and CI passed.`
Wrong: `HTTP suite is green, so the cutover works.`
Wrong: `Ran the release smoke pass while a full backend suite was running.`
Wrong: `Logged in as a sample person using the password from the sample-run file.`
Wrong: `Ran the admin hands-on pass as the operator account.`
Wrong: `Tested only as admin; the feature works.`
