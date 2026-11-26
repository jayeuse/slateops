# Signed-out pages: one frame, one mark, the workspace look

> **Status: done (2026-11-14), PR #112.** Company record TASK-0062. Compacted on 2026-11-26 (TASK-0130). Full text: `git show 731947c9:docs/specs/signed-out-pages.md`.

## Outcome

Home `/`, sign-in `/login` and recovery `/auth/recovery` use the workspace tokens, type, fields and buttons in light and dark, inside one shared frame with one product mark. Invitation setup, email change and the setup guide use the frame too. The parts are `ProductMark` (`frontend/src/components/brand/product-mark.tsx`), `SignedOutFrame` (`frontend/src/components/signed-out/signed-out-frame.tsx`) and `SignedOutPanel` (`frontend/src/components/signed-out/signed-out-panel.tsx`). No backend change. No organization name or logo shows before sign-in. The DESIGN.md section "Signed-out pages" holds the visual rules.

## Decisions

| ID | Decision |
|---|---|
| Home words | The home words are the Human Owner's, 2026-11-14: title "Draw your organization as it works.", the outcome line, "Open workspace", "Staff join by invitation from their administrator.", and the "How it works" card with Draw, Test, Work. Do not edit them. |
| Sign-in error | "Wrong email, username or password." (REQ-0024 addition 6). It is the same for a wrong email and a wrong password, and shows no reference. |
| Removed words | The empty brand panel, its `h1`, the sign-in and home footers, and the self-hosted facts are gone. "Slate Ops" on phones became "Slate Operations". |
| No new token | Use the existing `Card`, `Button`, `Input`, `Field` and `Alert` parts. |

## Acceptance criteria

Result rule: "met" means the merged tests name the criterion; otherwise "not recorded".

| ID | Criterion | Result |
|---|---|---|
| AC-2 | One frame and one mark; no page draws its own "SO". | met (`signed-out-frame.spec.ts`) |
| AC-3 | Sign-in has one visible `h1` at every width and no empty panel. | met (`signed-out-pages.spec.ts`) |
| AC-4 | The page parts match the delta list (workspace tokens, card, slim fields, no icon circle). | not recorded |
| AC-5 | At 1440x900 and 390x844: no sideways scroll, no clipped control, visible focus. | met (`signed-out-pages.spec.ts`) |

## Rules

### Frame (SO-F)

- **SO-F1.** Each signed-out page renders `SignedOutFrame` once. The frame owns the only `<header>` and the only `<main>`.
- **SO-F2.** The header is the workspace top bar: 56px, `bg-card`, bottom hairline, `data-skin="topbar"`.
- **SO-F3.** The header holds the product link (`ProductMark` and "Slate Operations", to `/`) and an optional action.
- **SO-F4.** Only home ("Sign in") and the setup guide ("Back to sign in") have a header action.
- **SO-F5.** `main` has `id="main-content"` and `data-skin="page"`, so each look draws its ground and density applies.
- **SO-F6.** Header and `main` sit in the body column; no `min-h-screen` on any part.
- **SO-F7.** The frame adds no `role="status"`, no `role="alert"` and no other "sign in" link.
- **SO-F8.** The frame and the mark are server-safe (no `"use client"`, no hooks).
- **SO-F9.** The page owns the session check. `busy` sets `aria-busy` on `main`; `actionsHidden` hides the action slot. No cover and no "Checking…" text.

### Mark (SO-M)

- **SO-M1.** `ProductMark` is the one product mark: a 32px `rounded-md` square, `bg-foreground`, "SO" at 12px weight 700, the same classes as the `WorkspaceLogo` fallback.
- **SO-M2.** The mark is `aria-hidden`; the words beside it name the product.
- **SO-M3.** No page draws its own "SO" block. `WorkspaceLogo` and the shell do not change.

### Form panel (SO-P)

- **SO-P1.** Sign-in and recovery use `SignedOutPanel`: one column, at most 24rem, centered with `m-auto`.
- **SO-P2.** Order: title (`h1`), description, card, footer line.
- **SO-P3.** The title uses the `PageHeader` title classes with `data-slot="page-title"`.
- **SO-P4.** The description is 14px muted, 6px under the title; the card starts 24px under it.
- **SO-P5.** The card is the shared `Card` with `slim-ui`, `w-full` and `p-5`; notices sit at its top.
- **SO-P6.** Form groups are 16px apart; a label is 8px over its field.
- **SO-P7.** The footer line is one `<p>` that holds the sentence and its link.
- **SO-P8.** `contentHidden` hides the card content and the footer line but keeps their space.
- **SO-P9.** No icon circle over the title.

### Home `/` (SO-H)

- **SO-H1.** The header action "Sign in" is an outline button with no icon; "Open workspace" stays the one primary action.
- **SO-H2.** One region, at most 72rem; from 1024px two panes (hero and "How it works" card).
- **SO-H3.** From 1024px the region is centered vertically under the header.
- **SO-H4.** The hero title "Draw your organization as it works." is 36px, 48px from 1024px, the one title above 30px in the product.
- **SO-H5.** Under it: "Slate Operations turns the drawing into one system your people use every day."
- **SO-H6.** "Open workspace" is the large primary button with its arrow, the only signed-out button with an icon.
- **SO-H7.** Under the button, one muted line with no icon: "Staff join by invitation from their administrator." Home has no `/setup` link (UF-C13.4).
- **SO-H8.** "How it works" is a `Card` with a `CardTitle` (`h2`) and no header icon.
- **SO-H9.** The three steps are an `ol`: "01" Draw, "02" Test, "03" Work, each with an `h3` and one sentence, rows split by a hairline, no check circles.
- **SO-H10.** No footer.

### Sign-in `/login` (SO-S)

- **SO-S1.** The page is the form panel. "Welcome back" is the one `h1`; description "Sign in to continue to your workspace."
- **SO-S2.** No brand panel and no split layout at any width.
- **SO-S3.** Card order: password-set notice, error notice, Email, Password, "Forgot password?", Sign in.
- **SO-S4.** "Forgot password?" is a link under Password with a 44px target below 1280px.
- **SO-S5.** Sign in is a full-width primary, 44px below 1280px and 32px from 1280px, no icon; it reads "Signing in…" while it runs.
- **SO-S6.** Footer: "First deployment? Read the setup guide", linked to `/setup`.
- **SO-S7.** During the session check the form content is hidden; a signed-in visitor is redirected.

### Recovery `/auth/recovery` (SO-R)

- **SO-R1.** The page is the form panel; its titles and descriptions do not change.
- **SO-R2.** Before hydration the card holds only "Preparing password recovery…" (`role="status"`).
- **SO-R3.** Request state: sent notice, error notice with its reference, Email, "Request recovery".
- **SO-R4.** Completion state: error notice, "New password", "Confirm new password", "Reset password".
- **SO-R5.** Footer: "Remembered your password? Return to sign in", linked to `/login`.
- **SO-R6.** Form buttons are full-width primaries with no icon, sized as SO-S5.

### Other signed-out pages (SO-O)

- **SO-O1.** `/setup` takes the frame only; "Back to sign in" moves to the header action slot. The eyebrow uses `text-action-text` and the Terminal icon is muted.
- **SO-O2.** `/auth/setup` and `/auth/email-change` take the frame and the mark only; their content does not change.
- **SO-O3 (not built).** Move those two pages into `SignedOutPanel` too. It needed a separate go-ahead.

## Wide screens and phones (AC-5)

Signed-out pages are not still pages. The header band spans the width. Sign-in and recovery center one 24rem form. Home has two panes from 1024px. At 1440x900 no page scrolls at rest; at 390x844 each page is one column and only home scrolls. No page scrolls sideways from 320px wide.

## Open items

- SO-O3 is not built: `/auth/setup` and `/auth/email-change` use `SignedOutFrame` without `SignedOutPanel`.
- AC-4 has no test that names it.
