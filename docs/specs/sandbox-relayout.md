# Sandbox relayout: the Access grammar

> **Status: done (2026-10-24), PR #61.** Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/sandbox-relayout.md`.

## Outcome

The Sandbox (`/sandbox`: header, Build, Triggers, Test, History, dialogs, menus, 390px layouts) uses the Access grammar: slim controls, 40px rows, label-left rows, quick filters, Advanced last, summary first then detail. Each section has one main action, and every button says what it does. The canvas drawing is unchanged. Only administrators reach the Sandbox. Code: `frontend/src/components/systems/sandbox/` (`trigger-list.tsx`, `trigger-rail.tsx`, `version-list.tsx`, `version-detail.tsx`, `version-comparison.tsx`, `designer-properties.tsx`, `designer-summary.tsx`, `sandbox-attention.tsx`, `sandbox-page-header.tsx`, `domain/version-history.ts`, `domain/build-summary.ts`). Preserved: URLs and `?section=build|triggers|test|history`; draft, autosave, conflict and publish behavior; the explicit **Save triggers** (October D1); Restore's confirmation.

## Layout direction

- Slim controls from 1280px (32px fields and buttons); the 44px floor stays below 1280px.
- The page title names the section; the save-state chip sits under it. Review & Publish is the one primary.
- Triggers and History are two panes, list and detail. Test is two panes, Setup and Result.
- Build with nothing selected shows a Summary with "needs attention" rows.

### Dialogs

Every Sandbox dialog uses one frame (`ui/dialog-frame.tsx`): the content is the one scroller, a sticky header with a named close, a sticky footer (S23).

## Decisions

| ID | Decision |
| --- | --- |
| S1 | One shared slim control set: the control skin moved from `.access-ui` to `.slim-ui`. Access roots carry both classes; Sandbox panels, dialogs and menus carry `.slim-ui`. |
| S2 | The section title names the section, and the chip sits under it. |
| S3 | Undo, Redo and ⋯ are quiet icon buttons; disabled ones give a reason. |
| S4 | The Sandbox nav is hidden for non-administrators; a direct link shows "Sandbox is not available to your account." |
| S5 | Triggers use two panes; the When/If/Then rail is the editor. The flow preview column is gone. |
| S6 | Trigger Status is a label-left row whose word reads On or Off; every list row shows a dot and a word. |
| S7 | Trigger list quick filters: All, On, Off. |
| S8 | History uses two panes, with Compare inside the version detail; the selects are Older and Newer, ordered older to newer. |
| S9 | Automatic saves fold into one row, inferred from the system labels "Before restore" and "Before discard". |
| S10 | Restore is a quiet button in the version header and keeps its confirmation; Delete stays in Advanced. |
| S11 | Test shows a result only for the current setup; no error before a run; Run test checks required values first. |
| S12 | Build "nothing selected" is a summary with "needs attention" rows; Properties uses label-left rows; Advanced names its contents; one relationships list. |
| S13 | Phone header: one title row and the chip. |
| S14 | A button with `h-auto` keeps its own height under the slim sizes. |
| S15 | Slim switches keep a 44px hit area at every width. |
| S16 | The slim class sits on the Sandbox panels, not the page root, so the canvas keeps its look. |
| S17 | The non-administrator notice links to the first workspace the account can open. |
| S18 | The page-wide "needs attention" banner folds into one compact control in the header. |
| S19 | Triggers details: region "Trigger details", switch "Trigger status"; × buttons named "Remove condition n" or "Remove action n"; counts are totals; New trigger clears search and filter; the Save bar says "n unsaved changes". |
| S20 | History details: each day folds its automatic saves into one row; the page opens on the newest listed row; another version preselects its own pair; the result is one table per area with added, removed and changed tags; short labels keep the old accessible names. |
| S21 | Test is two panes, Setup and Result, with Field comparison inside Result; "Inputs changed · Run again" marks a stale result; phones keep Setup and Result tabs. |
| S22 | Build: the Summary shows counts, "Needs attention" rows (including a `?status=off` Triggers link) or "All clear", then "Add department"; relationship rows have a ⋯ menu; the canvas opens fitted; Structure follows the canvas selection; Auto-arrange is on the toolbar; the minimap hides while the whole design is in view. |
| S23 | The attention control is a quiet warn-ink button ("n need attention") with a popover. Every dialog uses one frame with named closes ("Close review", "Close checkpoint" …). The review summary counts each kind ("3 module changes · 7 trigger changes"). |
| S24 | Auto-arrange on the toolbar and "Add department" in the Summary are accepted control additions for EXIT-3. |
| S25 | Fix round: an Undo notice ends when triggers save; a new step keeps its required note quiet until changed or left; truncated lines carry their full text in a title; a non-administrator page sends no Sandbox request. |
| S26 | Trigger Undo notices close at the next edit or a save; an unused field deletes at once with Undo; selected rows are tint only; "Enter your password to publish."; Test times use History's format. |
| S27 | With no triggers the list says "No triggers yet."; below 640px the chip shows short words. |
| S28 | Polish: no empty detail head; "[choose a module]" in the When summary; a fixed-height status row; Restore returns focus once. |

Open questions S9 and S4 were decided with the recommendations: accept the label rule for automatic saves (a server field is a follow-up), and hide the Sandbox from managers.

## Findings

F1 (P1) managers saw a refused Sandbox; F2 (P1) the trigger switch always read "On"; F3 (P1) Test opened on an old result; F4 Compare ordered newest first; F5 automatic saves looked like checkpoints; F6 a full-width Restore; F7 a 1256px Properties panel; F8 an empty "Nothing selected"; F9 header button weights; F10 a repeated flow preview; F11 the Review & Publish summary; F12 a 230px phone header; F13 icon-only Structure buttons; F14 the minimap covered a module card at the default zoom (fixed: the minimap hides while the whole design is in view); F15 Test repeated facts; F16 help only in Build.

## Phases

Phase 0 discovery; Phase 1 S1 to S4; Phase 2 Triggers (S5, S6, S7); Phase 3 History (S8, S9, S10); Phase 4 Test (S11); Phase 5 Build (S12); Phase 6 dialogs and phone (S13); Phase 7 plain words; Phase 8 sweep, critique and hands-on pass.

## Phase 7 glossary (decided under the owner's delegation, 2026-10-24)

Display words only.

| # | Before | Now |
| --- | --- | --- |
| G1 | "One-to-one", "One-to-many", "Many-to-many" | "One match each", "Many matches", "Many on both sides" (`relationshipKind` in `domain/model.ts`) |
| G2 | "Reopen this item and the items included by its original close operation." | "Reopens this and everything its close included." |
| G3 | "Relationship routing", "Inputs used for this result" | "Linked records used", "Values used" |
| G4 | Four help entries for the old screens | One help entry per section |

## Acceptance criteria

| ID | Criterion | Result |
| --- | --- | --- |
| EXIT-1 | A new critique has no P1; heuristics 4 and 8 score 3 or more. | met (25 → 29 of 40) |
| EXIT-2 | Each data-changing action gives feedback before, during and after. | met |
| EXIT-3 | Helper words and default-visible controls are not above the baseline, except recorded additions. | met with S22 and S24 additions |
| EXIT-4 | F1–F16 each have a failing-first test or a reason. | met |
| EXIT-5 | Sandbox isolated and HTTP tests, budget specs and static checks pass. | met |
| EXIT-6 | `ui-reviewer` returns "ship". | met |
| EXIT-7 | Hands-on as `ho-admin` finds no open defect; `ho-manager` sees the notice and no nav. | met |
| EXIT-8 | No page scroll at 1280×720, 1440×900, 1920×1080; no sideways scroll below 1280px. | met |
| EXIT-9 | Field edges at least 3:1; targets at least 44px at 390. | met |
| EXIT-10 | The owner approves the 390px sweep. | met (2026-10-24) |

## Open items

- Automatic saves are inferred from labels (S9); a server field is a follow-up.
- Fit at the 50% zoom floor cannot show the whole Harbor design at 1440 (accepted).
