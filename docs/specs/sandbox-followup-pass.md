# Sandbox follow-up pass

> **Status: done (2026-10-18), PR #54.** Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/sandbox-followup-pass.md`. It continues `docs/specs/sandbox-ui-ux-pass.md`.

## Outcome

The Sandbox keeps unsaved trigger edits safe in every exit path, warns when departments or modules overlap on the canvas, and Auto-arrange never makes an overlap. Desktop controls render at their designed size. The Structure outline works fully from the keyboard. Customer copy uses plain words. Display labels changed only; stored values and wire formats did not.

## Decisions

| ID | Decision |
| --- | --- |
| F1 | Triggers keep the explicit **Save triggers** (D1 stands), with stronger guardrails. No autosave. |
| F2 | Overlap covers departments and modules. A canvas notice offers **Auto-arrange**; frames are never moved by force. |
| F3 | The selected trigger step uses the grey ink tint on its flow card and a thin grey rule on its settings section. No blue edges or rings. |
| F4 | Resolve every open item from the exit reviews. |
| F5 | Do the three follow-up cards here: desktop sizes, the outline tree, the plain-language pass. |

Findings R1 to R8: R1 Back dropped unsaved trigger edits; R2 a fresh draft replaced them; R3 they lived only in memory; R4 incompleteness showed only at Save; R5 Auto-arrange made overlaps; R6 a shell rule held desktop controls at 44px; R7 the outline had no tree semantics; R8 technical words.

## Phase 1: trigger guardrails (data safety)

- G1: the page owns the trigger draft (`useTriggerDraft`), so Back and Forward keep edits; no Back dialog.
- G2: edits clear only after a confirmed save; Reload no longer drops them after a failed save.
- G3: unsaved trigger edits survive a reload in session storage (keyed by user, organization and draft), with "Restore unsaved trigger changes?".
- G4: an **Unsaved** badge on each changed trigger; an incomplete step shows its missing part in warning ink.
- G5: Ctrl+S (Cmd+S) saves triggers.

## Phase 2: desktop sizes

S1: the `#main-content` 44px floor stays, but skips an element that sets its own desktop size (`xl:min-h-*`, `xl:min-w-*`, `xl:size-*`). Touch tablets below 1280px keep 44px.

## Phase 3: canvas overlap (decision F2)

- O1: one overlap check on drawn boxes, frame against frame and module against module.
- O2: the notice "Some departments or modules overlap." with **Auto-arrange** and **Dismiss** (holds until the layout changes).
- O3: Auto-arrange spaces rows by the real table height.

## Phase 4: Structure outline as a tree

T1 `tree` and `treeitem` roles with one Tab stop; T2 arrow, Home, End, type-ahead, Enter and F2 keys; T3 canvas help matches.

## Phase 5: polish

P1 grey step selection (F3); P2 template cards as a radio group; P3 version rows with `aria-current`; P4 "Compare with" without the `v3 ·` prefix; P5 History hides paging when one page fits; P6 quiet "Remove condition"; P7 Test hides Field comparison until the first run; P8 the import button reads as an import; P9 dialog headings use `data-slot="section-title"` where it fits; P10 the "On" switch lines up with the name; P11 a lighter save chip in Stockroom.

## Phase 6: plain-language pass

Owner decisions (2026-10-18), display words only:

| # | Word | Decision |
| --- | --- | --- |
| G1 | module | Kept "module": "table" means a real database table elsewhere, and "list" clashes with "Choice list", "Trigger list", "Record list". |
| G2 | One-to-one · One-to-many · Many-to-many | Kept. |
| G3 | Integer · Date/Time · URL · Select | Whole number · Date and time · Web link · Choice list. |
| G4 | equals, does not equal, is greater than … | is, is not, is more than, is at least, is less than, is at most. |
| G5 | Live state | Kept "live state". |
| G6 | Save conflict text | "Not saved: someone else changed this draft. Your edits are still here." |
| G7 | Export JSON · Import from file | Download a backup · Load a backup. |
| G8 | Enter a simulated user UUID | Paste the person's ID. |
| G9 | Event module | Kept with G1. |
| G10 | relationship field mapping | linked field. |
| G11 | "" | (empty). |

## Acceptance criteria

| ID | Criterion | Result |
| --- | --- | --- |
| Exit 1 | The Sandbox batch and frontend static checks pass. | met (220 isolated, 149 Sandbox HTTP) |
| Exit 2 | Screenshots at 1440 and 390, light and dark. | met |
| Exit 3 | `ui-reviewer` returns "ship". | met (c10b3b8b) |
| Exit 4 | The owner approves the 390px screens. | met (2026-10-18) |

## Open items

- On dense templates, relationship label chips can cover field rows on the canvas (pre-existing).
- A people picker for Test values of a User field (G8 follow-up).
