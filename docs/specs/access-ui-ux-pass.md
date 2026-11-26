# Access UI and UX pass

> **Status: done (2026-10-23), PR #60.** Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/access-ui-ux-pass.md`. Access is the second page of the page pass, after the Sandbox (`docs/specs/sandbox-ui-ux-pass.md`, `docs/specs/sandbox-followup-pass.md`, and "The page pass (pattern kit)" in `DESIGN.md`).

## Outcome

Access (`/access`: Overview, People, Groups, Security, the person and group sheets, and their dialogs) never loses an unsaved form. The Overview is a dashboard of who is here and what needs attention. Rows are 40px, risky actions sit in one closed **Advanced** block in danger ink, and every action gives feedback before, during and after. Departments show their marks. Every page stays still from 1280px; only panel bodies scroll. Access introduced the slim controls (32px from 1280px, the sunken-well field skin in Slate), later shared as `.slim-ui`. Code: `frontend/src/components/systems/access/` (`components/overview-blocks.tsx`, `helpers/overview-dashboard.ts`, `hooks/use-scroll-cue.ts`). Role gating is unchanged: administrators see all four sections, department managers see Groups only, others see "Access is managed by administrators".

## Decisions

| ID | Decision |
| --- | --- |
| A1 | Window return (R1): Access keeps its views mounted while the session check runs. Manage was checked and does not unmount. |
| A2 | The person sheet gets **Add to group**; both membership paths use `mergeMembers`. |
| A3 | The Overview is a dashboard (owner, 2026-10-23): Who's here, Recent sign-ins, Needs attention, Access by department. |
| A4 | The inactivity period becomes a People filter; invitation settings move next to **Invite person** on People. |
| A5 | Deleting a person shows "… deleted · Undo"; Undo runs Restore. The confirmation stays. |
| A6 | Access levels Read, Write, Manage use `LevelBadge`; OpenComms keeps its own words. |
| A7 | No daily trend chart: it needs a new aggregate endpoint. |
| A8 | Slim controls first in Access only (the `access-ui` class), so a rollout is one class per page (owner, 2026-10-23). |

## Findings

Data-safety risks R1 to R19 (state trace): R1 (P1) a window return unmounted the views and lost open forms; R2 Back and Forward had no guard; R3 a sheet Discard wiped every draft; R4 a running save did not block Discard; R6 one journal slot per kind; R7 a maybe-completed save was not kept; R8 a notice that never cleared; R9 own-role demotion without a question; R10 focus on a gone control; R11 results far from the control; R12 Discard with no Undo; R13 a retry could duplicate; R16 tabs not keyed by person; R17 cleared filters came back; R18 a failed Discard was silent; R19 a cancelled security action. R5, R14 (privacy wipe on sign-out) and R15 stay as they are. The baseline critique scored 24/40.

## Phases (in priority order)

### Phase 0: baseline gaps

Z1 manager view captured (Groups only; members editable); Z2 non-owner administrator and no-access views captured; Z3 server checks: the last administrator cannot be demoted, a repeated Invite returns 409, group names are not unique; Z4 Manage does not unmount on a window return.

### Phase 1: data safety

| ID | Change |
| --- | --- |
| S1 | A window return keeps every open form, dialog, tab and filter (A1): the last trusted view stays mounted and inert during the role check. |
| S2 | Back and Forward never lose an unsaved form: Invite, Create group and invitation settings drafts live in the session journal. |
| S3 | Discard in a sheet discards only that sheet's draft. |
| S4 | Discard and close wait while a save runs. |
| S5 | The journal keeps one draft per person and per group. |
| S6 | A save that may have completed stays in the journal; only sign-out or an organization switch asks (shell guard `workspace-navigation-guard.tsx`). |
| S7 | Changing one's own role asks first and names the result. |
| S8 | A failed Discard shows its error; the "Finish the current change" notice clears. |
| S9 | After a lost answer, Create group and Invite check the server before Retry (same-name groups compared before and after). |

### Phase 2: row, button, and control grammar

P1 People rows: 40px, one avatar, one open target, name and email on one line; P2 Groups and Sessions rows the same; P3 status quick filters with counts (All, Active, Invited, Ending soon, Disabled), filters in the URL; P4 `xl:` sizes, search icons and placeholders; P5 slim controls inside `access-ui`, label-left rows in sheet Details.

### Phase 3b: filters (owner, 2026-10-23)

F1 Filters opens a popover (bottom sheet on phones) with label-left rows and "Clear all"; F2 Group and Department are searchable dropdowns; F3 Status lives only in the strip, rare statuses under "More"; F4 active filters show as removable chips and stay in the URL; F5 Groups and Sessions use the same Filters, popover and chips.

### Phase 3: person and group sheets

H1 lifecycle actions in one closed Advanced block, danger ink; H2 Save and Discard only with edits, named pending labels; H3 every disabled control states why (`DisabledReason`); H4 Delete and Discard give Undo (A5); H5 Security results next to the action, focus to a live control; H6 `DepartmentMark` and `LevelBadge` (A6); H7 Add to group (A2); H8 Groups rows named "Manage <group>".

### Phase 4: Overview dashboard

O1 Who's here: the line, the people signed in now, and the last-sign-in bar (Under a day, 1–7 days, 7–30 days as text); O2 Recent sign-ins with a link to Manage › Audit; O3 Needs attention shows only counts above zero, then one "All clear" line; O4 Access by department with marks and level bars, each opening filtered People; O5 `PageHeader`, Invite person as the one primary, still page from 1280px.

### Phase 4b: overflow in the Overview cards (owner, 2026-10-23)

A card that scrolls always shows that it does. V1 Recent sign-ins shows the rows that fit and pages with "‹ Newer · Older ›" (time cursors); V2 Needs attention keeps every item, with a bottom fade and edge shadow when it scrolls; V3 Access by department scrolls with a fade and a footer count ("2 of 14 shown"); V4 `DESIGN.md` records the rule.

### Phase 5: Security and the account policy

Y1 the policy dialog shows two-step per role, grace days and session timeout; the rest is in "Advanced · n set"; Y2 installation rules the viewer cannot change show as text, and the viewer's own two-step setup moved to the Security page; Y3 End all remote sessions in danger ink with a count; Y4 sessions open at 10 rows with display names, the policy success shows inside the dialog.

### Phase 6: plain-language pass

Glossary (owner, 2026-10-23), display words only: G1 two-step **On / Off / Unknown**; G2 **Invited** everywhere; G3 **Everyone, including deleted**; G4 **Allowed addresses**; G5 **Address or range**; G6 **Sign-in address**; G7 **Rules for every organization on this server**; G8 **Days to set up two-step**; G9 **Longest session** / **Sessions per person**; G10 **Keep session history (days)** / **Keep security events (days)**; G11 **Within (minutes)** / **Lock for (minutes)**; G12 helper sentences cut or shown only on an error.

### Phase 7: phone sweep and exit

A 390px and 1440px sweep in the four looks, a hands-on pass as `ho-admin` and `ho-manager`, `ui-reviewer`, and a re-run critique; all defects fixed.

## Acceptance criteria

| ID | Criterion | Result |
| --- | --- | --- |
| EXIT-1 | A re-run critique has no P1; heuristics 4 and 8 score 3 or more. | met (24 → 28 of 40) |
| EXIT-2 | Every data-changing action has feedback before, during and after. | met |
| EXIT-3 | Helper words and default-visible controls are below the baseline in every state; every capability is reachable. | met with recorded exceptions: Overview words and some controls rose from owner-approved additions |
| EXIT-4 | Every Phase 1 risk has a failing-first test. | met |
| EXIT-5 | Access isolated and HTTP tests and static checks pass. | met |
| EXIT-6 | `ui-reviewer` returns "ship". | met |
| EXIT-7 | A hands-on pass as `ho-admin` and `ho-manager` finds no open defect. | met |
| EXIT-8 | From 1280px no section, sheet or dialog scrolls the page; no sideways scroll below. | met |
| EXIT-9 | Field edges at least 3:1; targets at least 44px at 390. | met |
| EXIT-10 | The owner approves the 390px sweep. | met (2026-10-23) |

## Open items

- Outside Access: Platform › Account and Manage › Audit still use the old words ("Sign-in IP", "Attempt window").
- A cold Overview makes 17 Access reads; an aggregate endpoint is out of scope (A7).
- Needs attention stays whole at 1366×768 only up to 4 items.
