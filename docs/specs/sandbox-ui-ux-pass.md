# Sandbox UI and UX pass

> **Status: done (2026-10-18), PR #54.** EXIT-1, 2, 4, 5 and 6 are met; EXIT-3 is partial. Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/sandbox-ui-ux-pass.md`. Follow-up: `docs/specs/sandbox-followup-pass.md`.

## Outcome

The Sandbox (`/sandbox`: Build, Triggers, Test, History, the header and its menu, every dialog, and the 390px layouts) shows the controls people use most and folds the rest into one **Advanced** block. Every action tells the user what would happen, that it is happening, and what happened. The screens use few words. The Sandbox is the worked example for the other pages: the rules are in `DESIGN.md` "Disclosure and feedback", and the checklist is "The page pass (pattern kit)".

## Rules

### R1. Essential first, Advanced last

Show what the common task needs; put the rest in one **Advanced** block, last in its panel and closed by default. Advanced remembers its state per viewer and panel, and shows "Advanced · 2 set" when closed. Lifecycle actions (Close, Reopen, Delete, Permanently delete) always live in Advanced. A control that applies in one case appears only in that case.

### R2. Feedback at four moments

Before: a risky action states its consequence; a disabled control states why. During: the control shows progress ("Saving…") and keeps its width. After: use the lowest channel the user can see: inline, then a notice (toast with Undo), then a dialog (only before an action that cannot be undone or changes the live workspace), then a page alert (blocking states only, never success). Context: one save-state chip in the header, which also counts unsaved trigger changes.

### R3. Few words

A label has 3 words or fewer. A helper line is one sentence of 12 words or fewer, only for a consequence, a limit or an error. A fact appears in one place only. First-run guidance lives in empty states and the Help drawer.

## Decisions

| ID | Decision |
| --- | --- |
| D1 | Trigger saving: keep the explicit **Save triggers**; validation runs on save. The chip counts trigger changes, and leaving with unsaved changes asks first. |
| D2 | Advanced remembers its state for each viewer (R1). |
| D3 | Every dialog has Cancel and closes on Escape; only Templates and Review and Publish also get a close (X). |
| D4 | Labels: "Title field", an On/Off switch labeled "On", "Fixed value / Another field"; the footer "Draft" is removed. |
| D5 | Deleting a trigger gives an Undo notice, not a confirmation. |
| D6 | Success messages move from the page alert to inline results or notices. |

Shared parts (Phase 1): `AdvancedSection`, the pending-action button (`aria-busy`), the save-state chip, `DisabledReason` (tooltip, `aria-describedby`, `aria-disabled`), one dialog footer order (Cancel left, commit right), `DepartmentMark` (8px square in `var(--dept-n)`), and single-select filters with a visible selected state.

## Phases

| Phase | Content | Acceptance IDs |
| --- | --- | --- |
| Phase 0 | R1 to R3 into `DESIGN.md`. | DOC-1 |
| Phase 1 | Shared parts; selected filter state. | SH-1 to SH-5 |
| Phase 2 | Mechanical fixes Q1 to Q9. | one per fix |
| Phase 3 | Build: classification, feedback, copy cuts 1 to 4, `DepartmentMark`, field rows. | BLD-1 to BLD-5 |
| Phase 4 | Triggers: option picker (labels shown, option ID stored), leave dialog (D1), Undo on delete (D5), unsaved count, list and detail views with Back below 640px. | TRG-1 to TRG-5 |
| Phase 5 | Test: sticky Run test, stale result on edit, Setup and Result on 390px. | TST-1 to TST-4 |
| Phase 6 | History: full names, Compare with… from the detail, kind filter select, label and delete in Advanced. | HIS-1 to HIS-3 |
| Phase 7 | Header, menu and dialogs: the chip, Discard last, X on two dialogs (D3), successes off the page alert (D6). | HDR-1 to HDR-3 |
| Phase 8 | Sweep: 390px and the four looks in light and dark. | SWP-1, SWP-2 |
| Phase 9 | Exit review, then the pattern kit. | EXIT-1 to EXIT-6 |

Phase 2 fixes: Q1 option labels in trigger summaries; Q2 weekday names; Q3 operator words with symbols; Q4 no "Create relationship" on edit; Q5 Cancel on Save checkpoint; Q6 Escape cancels a History label edit; Q7 footer order in Import or export; Q8 a changed compare selection clears the old result; Q9 title-field and delete errors shown.

### Phase 9 decisions

| ID | Decision |
| --- | --- |
| X1 | Trigger settings that cannot publish are issues on their trigger, listed in the page's attention list with "Open trigger". |
| X2 | The review always loads its change list; each blocker has a button that opens it. |
| X3 | Version confirmations read "Restore version" and "Delete version" and state the consequence. |
| X4 | The Structure outline marks only the selected row (`aria-current`). |
| X5 | A disabled menu item says why on a second line. |

## Acceptance criteria

| ID | Criterion | Result |
| --- | --- | --- |
| EXIT-1 | A re-run critique has no P1, and heuristics 4 and 8 score 3 or more. | met |
| EXIT-2 | No data-changing action lacks feedback. | met |
| EXIT-3 | In every section, visible helper words and default-visible controls are below the baseline; every capability is reachable. | partial: department controls stayed equal; Triggers has two more controls |
| EXIT-4 | All Sandbox isolated and HTTP tests and the static checks pass. | met |
| EXIT-5 | `ui-reviewer` returns "ship". | met |
| EXIT-6 | The owner approves the 390px sweep. | met |

Phase criteria (all phases are complete; no separate result per criterion is recorded):

| ID | Criterion |
| --- | --- |
| DOC-1 | `DESIGN.md` has "Disclosure and feedback" with R1 to R3. |
| SH-1 | Advanced opens and closes by keyboard and remembers its state after reload. |
| SH-2 | Advanced shows "n set" when closed. |
| SH-3 | A disabled control with a reason exposes it on focus and to screen readers. |
| SH-4 | Every Sandbox dialog uses the footer order. |
| SH-5 | The selected filter is visible in all four looks. |
| BLD-1 | A module panel shows the essentials and a closed Advanced block. |
| BLD-2 | Delete is reachable from Properties. |
| BLD-3 | Every Build action has feedback per the feedback table. |
| BLD-4 | Copy cuts 1 to 4 are done. |
| BLD-5 | 390px shows the panel without horizontal scroll. |
| TRG-1 | A select condition or action shows option labels and stores the option ID. |
| TRG-2 | Leaving with unsaved changes asks Save, Discard, or Stay. |
| TRG-3 | Delete shows "Trigger deleted · Undo", and Undo restores it. |
| TRG-4 | The chip shows the unsaved count. |
| TRG-5 | On 390px, choosing a trigger shows its detail first; below a 640px studio width the list and detail are separate views with Back. |
| TST-1 | Run test stays visible while the setup scrolls. |
| TST-2 | Editing an input marks the result stale at once. |
| TST-3 | On 390px, a run shows the result. |
| TST-4 | Run test disabled without a module says why. |
| HIS-1 | Names show in full or wrap; no "Before r…" at 1440. |
| HIS-2 | Compare with… opens the comparison with that version preselected. |
| HIS-3 | Delete uses danger ink. |
| HDR-1 | The chip shows saving, saved and not-saved states. |
| HDR-2 | Review and Publish, when disabled, says why. |
| HDR-3 | No success message uses the page alert. |
| SWP-1 | No horizontal scroll and no clipped control at 390px. |
| SWP-2 | Every new part follows each look. |

## Open items

- EXIT-3 is partial.
- Trigger autosave, canvas overlap, the outline as a tree and the vocabulary pass moved to `docs/specs/sandbox-followup-pass.md`.
