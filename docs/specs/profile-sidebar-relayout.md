# Profile, Account settings, and sidebar relayout: the slim identity

> **Status: done (2026-10-25), PR #67.** The owner approved the spec, the comps and the result in the live app (2026-10-25). Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/profile-sidebar-relayout.md`.

## Outcome

The slim grammar of Access, the Sandbox and Manage became the product identity: 32px controls and 40px one-line rows from 1280px, label-left rows, summary then detail in two panes, still pages from 1280px, one primary action, framed dialogs, and 44px targets on phones. The pass applied it to the app shell (`frontend/src/components/app-shell.tsx`, `app-navigation.tsx`, `organization-menu.tsx`, sidebar rules in `frontend/src/app/globals.css`). `/profile` and `/profile?person=<id>` became a read-only Profile view (`frontend/src/components/profile/`) backed by `GET /api/users/{id}/profile` (`profile_person` in `backend/app/systems/access/users/person_visibility.py`). All editing moved to Account settings at `/settings` (`frontend/src/components/settings/`).

Preserved: every capability of the old Profile page stays reachable in Account settings; sidebar width and collapsed state persist; the navigation model and its descriptions do not change; organization isolation stays; `visible_person_ids` (Comms) does not change.

## Decisions

| ID | Decision |
| --- | --- |
| PD1 | The shell is slim from 1280px and keeps the 44px floor below. |
| PD2 | The header stays 56px; only its controls are slim. |
| PD3 | Sidebar rows are one line; descriptions show as `title` and `aria-description`, and as a second line in the drawer. |
| PD4 | Default sidebar width 240px (range 220–360px); the organization name does not truncate at the default. |
| PD5 | The footer account row links to the person's own profile, with an active state. Collapse is a 32px icon in the sidebar header. |
| PD6 | Search is a quiet 32px button that says "Search". |
| PD7 | Drawer rows carry their own size and active classes through one navigation hook shared with the sidebar. |
| PD8 | The resize separator keeps keyboard control, with a visible 4px handle and a focus ring. |
| PD9 | Account settings (`/settings`) is a still two-pane page from 1280px; the route declares its layout mode. `/settings/appearance` opens `/settings#look`. |
| PD10 | Identity saves through one pinned footer ("Save profile"). Appearance and Regional save at once with one status line. Timezone uses the searchable select. |
| PD11 | Sign-in is label-left rows with status words. Sessions are 40px rows with a named "End session". |
| PD12 | Email, password and two-step use the shared dialog frame. The password dialog states the sign-out before the action. |
| PD13 | Preview shows how others see you, your formats and an appearance sample, and repeats no fact. |
| PD14 | Color is a three-option segmented control; Motion and Keyboard are switch rows with 44px phone targets. |
| PD15 | The Account settings header uses the Manage sizes: the title and one meta line. |
| PD16 | Profile is read-only: photo, name, job title, phone, bio, role, groups. Only the own profile has an "Account settings" button. The URL uses a query value because the app is a static export. |
| PD17 | Who can view a profile (owner decision): administrators and members see every active member of the bound organization; guests keep `visible_person` and see photo, name and job title only; no cross-organization view. The avatar read follows the same rule. |
| PD18 | Profile layout: a quiet band, photo and name on the left, About and Bio label-left panels on the right, empty fields hidden. |
| PD19 | Entry points: sidebar account row and header account menu open your profile; the menu also opens Account settings; the person card gets "View profile". |
| PD20 | An unavailable profile shows "This profile is not available." with "Go to your profile" and no Retry. |
| PD21 | Search kept its link role with the name "Search workspace". Later changed by `docs/specs/ux-friction-pass.md` item 4 (APR-0003): Search opens a search panel over the page. |
| PD22 | A stored 271px width opens at 240px. Double-click resets to 240px; Home and End go to 220 and 360px. |
| PD23 | The sidebar header keeps the 24px mark as a workspace-home link, the organization menu and the collapse button. A long name wraps to two lines, then truncates. |
| PD24 | The rail is 3.5rem and scales with text size; rail targets are 44px below 1280px and 32px from 1280px. |
| PD25 | The account row is named "Your profile, <name>", with the role as a muted second line. |
| PD26 | In the rail the organization mark is the organization menu trigger ("Organization: <name>"); the menu's first item is "Workspace home". |
| PD27 | The Profile view cancels the page padding so the band spans the content area; no shell pathname branch. |
| PD28 | `/settings/appearance` and `/profile#look` open `/settings#look`; the old `/profile` anchors open the same anchor on `/settings`. |
| PD29 | Gate links read "Account settings" and open `/settings`; the no-organization frame renders `/profile` and `/settings`. |
| PD30 | Help has an "Account settings" guide and a three-entry Profile guide. |
| PD31 | Role labels live in `src/lib/auth-api.ts` beside `AccountRole`. |
| PD32 | The 96px photo uses the 256px avatar thumbnail; initials show with no photo. |
| PD33 | The profile read joins the sample profile control and the seeder route list. |
| PD34 | "View profile" shows in every loaded person card, guests included. |
| PD35 | On the own profile only, with job title, phone and bio empty, one muted line links to `/settings#identity`. |
| PD36 | A control's accessible name starts with its visible word and may be longer ("Display name", "Change email", "Manage two-step verification", "Start page after sign-in"). |
| PD37 | Four groups, named by their headings: Identity, Sign-in, Appearance, Regional, with anchors `#identity`, `#security`, `#look`, `#regional`. |
| PD38 | Read failures show one Identity alert with Retry, which reads and never writes. A failed text save keeps the draft. |
| PD39 | Session rows show "Last active", the address or "Unknown address", "This device", and named actions ("End session, <device>"). |
| PD40 | The two-step dialog gets the framed header; its steps stay in the shared `MfaPresentation` body. |
| PD41 | Color is a radio group drawn as a segmented rail (28px from 1280px, 44px below). |
| PD42 | In a switch row the row label names the setting and the switch label names the switch (Reduce motion, Use shortcuts). |
| PD43 | The preference status is mounted once, beside the group changed last. |
| PD44 | Timezone options are "Organization timezone (<zone>)" and every zone as "UTC+08:00 · Asia/Manila", from `src/lib/timezone-options.ts`. |
| PD45 | The Preview card is drawn from the Identity draft and sends no card read. |
| PD46 | Without an organization, `/settings` widens to 75rem from 1280px. |
| PD47 | The page declares its own layout; the shell has no `/settings` branch. |
| PD48 | The Password row shows no "Last changed" date (the server does not send it). |
| PD49 | Below 768px, Profile and Account settings put the page heading as the title row under the bar. |
| PD50 | Below 1280px the account menu items and the fill-hint link are 44px. |
| PD51 | `smallTargets` (`tests/http/helpers/layout.ts`) takes extra selectors for menu items and radios. |
| PD52 | Words follow the Phase 6 glossary; words a decision names stay. |
| PD53 | A successful password change closes the dialog and shows "Password changed. Other devices are signed out." The sign-out warning shows only after no answer or a 5xx. |
| PD54 | The photo saves at once, with its own row status. |
| PD55 | From 1280px searchable-select options are 32px rows with a check mark; the popup is at most 20rem and flips above only when it does not fit. |
| PD56 | `Input`, `Select` and the search box are 16px below 768px so iOS does not zoom. |
| PD57 | The bare-profile hint shows only when the profile has a role. |
| PD58 | Identity labels are "Display name" and "Bio" everywhere. |
| PD59 | On Profile the phone is a `tel:` link; facts use 14px text. |
| PD60 | The end-session confirmation names the device; "Sign out other sessions" says "No other sessions." when disabled. |
| PD61 | The password and email dialogs open on their first field. |
| PD62 | Start page lists only sections the sidebar shows the person; a hidden saved section stays as "<Section> (not available)". |
| PD63 | Account settings uses the `Settings2` icon in the account menu and `UserCog` on the Profile button. |
| PD64 | The preference status shows "Saved" only after a change in this visit; an unloaded value reads "Unavailable". |
| PD65 | The 24px organization mark keeps 9px type; a smaller type token is a design-system item for `impeccable`. |
| PD66 | From 1280px every still-page table fills the remaining height with its pager pinned at the bottom; one `globals.css` rule serves `access-fill` and `manage-fill`. |
| PD67 | The account photo shows on the first load: the notifications list takes `FOR SHARE`, the photo read retries after 50 ms and 200 ms, and a photo read waits for a processing slot. No security control is weaker. |
| PD68 | The shell shows no session UI: the session check runs in the background with no cover, except for MFA material, the organization choice, a refused network and an organization switch. The server still checks every request. |

## Findings

Each finding was closed by a decision above.

- Old Profile page: P-F1 free-text timezone; P-F2 4–6 screens of scroll; P-F3 three save models; P-F4 hidden two-step status and identical sessions; P-F5 unstated password sign-out; P-F6 double status; P-F7 233 helper words; P-F8 wide native file input; P-F9 labels above fields; P-F10 heavy heading; P-F11 small phone switches.
- Profile view: P-F12 no view of another person; P-F13 role and groups visible only to administrators.
- Shell: S-F1 drawer outside the 44px rule; S-F2 gear "Your profile" button; S-F3 field-shaped search link; S-F4 two-line rows; S-F5 mixed footer weights; S-F6 invisible resize tab stop; S-F7 design-file mismatch.

## Server read (Phase 2)

`GET /api/users/{user_id}/profile`: administrators and members get `display_name`, `job_title`, `phone`, `bio`, `avatar_url`, `role` and `groups`; guests get `display_name`, `job_title` and `avatar_url`. Any other case returns 404 `person_not_found`. `Cache-Control: private, no-store`. `GET /api/users/{user_id}/avatar` follows the same rule. Tests: `backend/tests/users/test_person_profile_visibility.py`.

## Phases

| Phase | Content |
| --- | --- |
| 0 | Discovery and baseline |
| 1 | The slim shell (PD1–PD8, PD21–PD26) |
| 2 | Profile read and Profile view (PD16–PD20, PD27–PD35) |
| 3–4 | Account settings layout, saving and Sign-in (PD9–PD15, PD36–PD48) |
| 5 | Phones and the no-organization frame (PD49–PD51) |
| 6 | Plain words: the glossary below and the guard `frontend/tests/http/account-plain-words.spec.ts` |
| 7 | Review fixes (PD53–PD65, PG27–PG35) |

## Phase 6 glossary (decided under the owner's delegation, 2026-10-25)

Display words only. Stored values, API fields and URLs stay the same.

| # | Rule |
| --- | --- |
| PG1 | Sandbox canvas note: "Shortcuts are off. Turn on Use shortcuts in Account settings › Appearance, or use the Fit and View buttons." |
| PG2 | "Shortcuts are available once your preferences load." |
| PG3 | Help: "Shortcuts are off. Turn on Use shortcuts in Account settings › Appearance." |
| PG4 | "Your shortcut preference could not be loaded. Retry it in Account settings."; "Loading your shortcut preference…" |
| PG5 | Photo size shows "up to 2 MB"; the limit stays 2 MiB. |
| PG6 | "The photo may not have saved. Retry to check which photo is saved." |
| PG7 | "Profile saved, but the old photo could not be deleted. Ask your administrator to delete it." |
| PG8 | Start page before preferences load: "Not loaded" (replaced by PG29). |
| PG9 | "Applied to this page only: this browser cannot keep it." |
| PG10 | Change email errors in plain words; a 409 still does not say whether the address belongs to another account. |
| PG11 | Pending send reads "Sending…". |
| PG12 | Confirmation titles "End session?" and "Sign out other sessions?"; "Every other device signs out. This device stays signed in." |
| PG13 | Confirmation buttons repeat the opening action: "End session", "End session and sign out", "Sign out other sessions". |
| PG14 | "Session ended. That device signs out."; "Other sessions ended. This device stays signed in." |
| PG15 | "Password changed. Other devices are signed out; this device stays signed in."; "Other devices may be signed out. Check Sessions." |
| PG16 | Shell sign-out failure: "You are still signed in. Try again." |
| PG17 | Two-step note: "You can keep working until then." |
| PG18 | Help Profile guide: "…holds your profile details, sign-in, appearance, and regional preferences." |
| PG19 | Help: "Save profile saves only the fields you changed". |
| PG20 | Kept: the group heading "Identity" (PD37). |
| PG21 | Kept: row label "Two-step" (the dialog title spells it out). |
| PG22 | Kept: "Sessions" and the session action names (PD11, PD39). |
| PG23 | Kept: shell "workspace" words; a rename is a later shell-wide decision. |
| PG24 | Kept: "Your profile" names your own profile; "Profile" names the page. |
| PG25 | Kept: navigation descriptions. |
| PG26 | Kept: PNG, JPEG, MB, IP addresses, zone labels (technical names). |
| PG27 | "Short bio" becomes "Bio" (PD58). |
| PG28 | Help: "…and your sessions." |
| PG29 | Start page before preferences load: "Unavailable" (PD64); replaces PG8. |
| PG30 | Appearance status: nothing at rest; "Saved" after a change (PD64). |
| PG31 | End-session title: "End the session on <browser>, <system>?" (PD60). |
| PG32 | Password success: the notice "Password changed. Other devices are signed out." and the dialog closes (PD53). |
| PG33 | Photo row words: "Uploading…", "Removing…", "Photo saved", "Photo removed" (PD54). |
| PG34 | Disabled "Sign out other sessions" says "No other sessions." (PD60). |
| PG35 | "Name" becomes "Display name"; Help: "…photo, display name, …bio…" (PD58). |

## Acceptance criteria

| ID | Criterion | Result |
| --- | --- | --- |
| EXIT-1 | New critique finds no P1; Account settings heuristics 4 and 8, and the shell's heuristic 4, score 3 or more. | met |
| EXIT-2 | Every Account settings data change gives feedback before, during and after. | met |
| EXIT-3 | Account settings helper words 60 or fewer; every capability reachable. | met (227 → 19 words; default-visible controls not re-measured) |
| EXIT-4 | Each finding P-F1 to P-F13 and S-F1 to S-F7 has a failing-first test or a recorded reason. | met |
| EXIT-5 | Profile, Account settings, shell, backend, still-page, budget and static checks pass. | met |
| EXIT-6 | `ui-reviewer` returns "ship". | not met as written: two rounds returned fix-first; the fixes were done and no third round ran |
| EXIT-7 | Hands-on pass finds no open defect across member, guest and other-organization views. | met |
| EXIT-8 | Profile and Account settings do not scroll at 1280×720, 1440×900, 1920×1080; no sideways scroll below 1280px. | met |
| EXIT-9 | Targets at least 44px at 390; field edges at least 3:1 in the four looks. | met |
| EXIT-10 | The owner approves the result in the live app. | met (2026-10-25) |

## Open items

- Browser Back from `/settings` can lose an unsaved Identity edit; a shell-wide Back guard needs its own spec.
- "Reload person card" shows at rest; the owner decides whether the card reads again on each open.
- The 24px organization mark needs a smaller type token (PD65).
- Shell "workspace" words stay until a shell-wide rename decision (PG23).
