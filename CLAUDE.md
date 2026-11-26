@AGENTS.md

# Claude Code in Slate Operations

Everything in `AGENTS.md` above applies. This section only covers where Claude Code differs from the Codex setup.

This codebase is yours: what it's for and how it's built are your call, and you'll keep building on it.

## Codex-to-Claude mapping

- **Skills.** Skills are local and not in Git. Claude Code and Codex load the same skill files by name; use a skill by its name, as `AGENTS.md` does. Edit a skill once, in the shared local skill folder.
- **Orchestration.** The company role subagents do delegated work. They are user-level subagents in `~/.claude/agents/`, and the delegation policy that the user-level `CLAUDE.md` names decides which role takes a task. Follow the orchestration rules in `AGENTS.md` with these subagents.
- **Subagents.**
  - Utility workers (user-level): `explore` (read-only search) and `check_runner` (runs prescribed checks). The company roles are the other user-level subagents.
  - `ui-reviewer` (project): fresh-context visual and accessibility review of a finished UI change. It covers visual quality; the code review covers the diff and the acceptance criteria. Both may run on the same change.
  - `impeccable-finish-reviewer`, `impeccable-documenter`, `impeccable-manual-edit-applier` (project): spawned by the impeccable skill itself. The impeccable skill generates them; regenerate them after an Impeccable update.
  - Built-in `Explore` and `Plan` are different from the utility worker `explore`. For repository tracing, use the utility worker `explore`.
- **MCP servers** (`.mcp.json`): `playwright` (browser and screenshots, output in `.playwright-mcp/`), `shadcn` (component registry and source), `context7` (current library docs). There is no PostgreSQL MCP for Claude; use the documented CLI path when database evidence is authorized.

## Library facts

- This is Next.js 16, React 19, and Tailwind v4 (CSS-first). Before writing framework code from memory, check `node_modules/next/dist/docs/` (per `frontend/AGENTS.md`) or Context7. For a shadcn primitive, check `src/components/ui/` first, then the shadcn MCP.

Correct: `Checked Context7 for the Tailwind v4 @theme syntax, then added the token to globals.css.`
Wrong: `Added a tailwind.config.ts with the new color.` (v4 here has no config file.)

## Visual verification loop

Required for every change that affects rendered UI. Code review alone is not verification.

1. Start the dev server with `npm run dev` in `frontend/`, in the background. Reuse it if it already runs. The port is `FRONTEND_DEV_PORT` (default 3000).
2. Use the playwright MCP to open the changed route and take screenshots at desktop (1440x900) and mobile (390x844).
3. Compare the screenshots with the request. Fix material problems.
4. Take at most two screenshot rounds. Batch fixes between rounds; do not screenshot after each small edit.
5. For a non-trivial change, spawn `ui-reviewer` with the request, the changed files, and the screenshot paths. Skip this when `impeccable-finish-reviewer` already reviewed the build.
6. Run the frontend static checks once the work unit stabilizes, following the testing rules in `AGENTS.md`.

Correct: `Screenshots at 1440 and 390 show the toolbar wraps on mobile; moved actions into the overflow menu; second round clean; ui-reviewer: ship.`
Wrong: `Updated the toolbar styles; should look good on mobile now.`

## Hands-on testing

Claude owns hands-on testing on the live development stack: a feature pass after each user-visible change or fix, and a release smoke pass before the push. Read [docs/hands-on-testing.md](docs/hands-on-testing.md) before either pass; it holds the testing accounts, the credential rules, and the steps. Never use the operator account for hands-on tests, and never run the installation-wide reset on the development database.

## Advisor (Fable)

The advisor is Fable, set with `/advisor fable` in user settings. Subagents inherit it. Fable has its own weekly limit, separate from the normal limit, so consult it at real decision points; do not ration it to zero, and do not call it on routine turns. Each call reads the full transcript again, so a call late in a long session costs more.

Consult the advisor:

1. Before you choose the layout approach or component structure for a new or rebuilt surface.
2. After two screenshot rounds that still show a material problem, or when the same error repeats after a fix.
3. Before reporting a large UI change as done, after `ui-reviewer` or `impeccable-finish-reviewer` has returned. Give it the reviewer's findings and your fixes.
4. When a reviewer and your own evidence disagree.

Do not consult it for token or copy tweaks, lint and format fixes, single-component styling changes, or questions that the repository's files already answer.

If the advisor is unavailable or declines, continue and state it in one line in the final report.

Correct: `Three layout options for /boards: dense table, card grid, split view. Consulting the advisor before choosing.`
Wrong: `Changed the button padding from 8 to 10; consulting the advisor to confirm.`

Correct: `Mobile toolbar still overflows after two rounds. Consulting the advisor with both screenshots and the two attempted fixes.`
Wrong: `Toolbar still overflows. Trying a third and fourth variation.`

## PR review findings

When you fix findings from the Codex reviewer (`chatgpt-codex-connector`) or another reviewer on the active PR, close each thread after the fix is pushed:

1. Push the fix to the PR branch first. Never reply on or resolve a thread for a fix that is only local.
2. Reply on the thread with one brief line: the commit SHA, what changed, and the test that covers it. Use `gh api repos/<owner>/<repo>/pulls/<pr>/comments/<comment_id>/replies`.
3. Resolve the thread with the GraphQL `resolveReviewThread` mutation (find thread ids with `reviewThreads`).
4. If you did not fix a finding, or you fixed it in a different way than it suggests, say so and why in the reply. Leave the thread unresolved if the user must decide.

SEC-R1 still applies: describe only problems in the PR's unmerged changes.

Correct: `Fixed in f7637283: owners can no longer be deleted, disabled, or demoted (409); covered by test_another_administrator_cannot_remove_disable_or_demote_an_owner.` Then resolve the thread.
Wrong: Push the fix and leave the thread open with no reply, or resolve it with no reply.
Wrong: `Thanks for the review! I took a careful look and made several improvements to the code, which should address the concern.`
