# Signed-out pages: one frame, one mark, the workspace look

> **Status: Proposed 2026-11-14 (TASK-0062).** Design spec by the Product Designer. No product code has changed. Base revision `296c890f` on `feat/signed-out-pages`.

**Contract, confirmed.**
1. Outcome: home `/`, sign-in `/login`, and recovery `/auth/recovery` use the workspace tokens, type, fields, and buttons in light and dark, inside one shared frame with one product mark.
2. Keep every field, flow, route, message, and accessible name that the tests pin; change no backend; show no organization name or logo before sign-in.
3. Acceptance: AC-2 (one frame, one mark, no page draws "SO"), AC-3 (sign-in has one `h1`, no empty panel), AC-4 (delta list below), AC-5 (1440x900 and 390x844 with no sideways scroll, no clipped control, visible focus).

## Current state (observed 2026-11-14)

Paths are under `frontend/src/`. Screens were taken at 1440x900 and 390x844, light and dark, on the dev app.

| Page | Now | Source |
| --- | --- | --- |
| Home `/` | A borderless header inside `main`, a 48px hero `h1`, a primary "Open workspace", two feature lines with action-blue icons, a "A guided start" card with fake check circles, and a footer. The page has two primary buttons that go to `/login`. | `app/page.tsx` |
| Sign-in `/login` | A split grid from 1024px. The left panel is `bg-sidebar`, which is `--ground` in light and dark, so it looks empty. The only `h1` ("A clear view of what comes next.") is in that panel. Below 1024px the panel is `display: none`, so phones have no `h1`. The visible title "Welcome back" is an `h2`. | `app/login/page.tsx` |
| Recovery `/auth/recovery` | A centered 24rem column on the ground, a blue "SO" block, an icon circle, an `h1`, and bare fields (no card). | `app/auth/recovery/page.tsx` |
| Other signed-out pages | `/auth/setup` copies recovery. `/auth/email-change` is a card with `rounded-xl shadow-sm`. `/setup` has its own header. | `app/auth/setup/page.tsx`, `app/auth/email-change/page.tsx`, `app/setup/page.tsx` |
| Workspace brand | The shell draws the organization logo, or the organization's mark in a `bg-foreground` square, then the organization name. | `components/app-shell.tsx` (`AppSidebarHeader`), `components/systems/shared/runtime/workspace-logo.tsx` |
| Signed-out look | The root provider applies the last organization's look before paint and reads `/api/workspace/appearance?org=`. No page has `data-skin="page"`, so no look ground (board, ruled paper, wall) shows. | `components/organization-theme-provider.tsx`, `app/layout.tsx` |

The "SO" block has four styles now: `size-9 bg-foreground` (home, `/setup`), `size-9` and `size-8 bg-foreground` (sign-in), and `size-8 bg-primary` (recovery, `/auth/setup`). The blue block breaks the One Meaning Rule: action blue acts and never decorates.

## Rules

### Frame (SO-F)

- **SO-F1.** Each signed-out page renders `SignedOutFrame` once. The frame owns the only `<header>` and the only `<main>` of the page.
- **SO-F2.** The header is the workspace top bar: 56px tall (`h-14`), `bg-card`, a `border-b border-border` hairline, `px-4 sm:px-5`, and `data-skin="topbar"`. Each look then styles it as it styles the workspace top bar.
- **SO-F3.** The header holds the product link on the left and an optional action on the right. The product link is the `ProductMark` and the words "Slate Operations" (14px, weight 600). It goes to `/`. Its accessible name is "Slate Operations".
- **SO-F4.** Only two pages give the header an action: home ("Sign in") and the setup guide ("Back to sign in"). Sign-in, recovery, invitation setup, and email change have no header action.
- **SO-F5.** `main` has `id="main-content"` and `data-skin="page"`. Each look then draws its page ground, and the device's page spacing (density), the 44px floor on `min-h-11` controls, and the high-contrast and forced-color borders apply as in the workspace.
- **SO-F6.** The header and `main` sit in the root `body` column (`flex min-h-full flex-col`). The header is `shrink-0`; `main` is `flex flex-1 flex-col`. Do not set `min-h-screen` on any part: with the 56px header it makes every page scroll by 56px.
- **SO-F7.** The frame adds no `role="status"`, no `role="alert"`, and no other link with "sign in" in its name. Tests find these by role in strict mode.
- **SO-F8.** The frame and the mark are server-safe (no `"use client"`, no hooks), because `/setup` is a server component with `metadata`.
- **SO-F9.** The page owns the session check. The frame takes `busy` (sets `aria-busy` on `main`) and `actionsHidden` (sets `invisible` on the action slot, so the header keeps its layout). Nothing covers the page, and no "Checking…" text shows.

### Mark (SO-M)

- **SO-M1.** `ProductMark` is the one product mark: a 32px square (`size-8`), `rounded-md`, `bg-foreground` with `text-background`, "SO" at 12px weight 700, centered. These are the classes of the `WorkspaceLogo` fallback, so the product mark and the default organization mark look the same.
- **SO-M2.** The mark is `aria-hidden="true"`. The words beside it name the product.
- **SO-M3.** No page draws its own "SO" block. `WorkspaceLogo` and the shell do not change: they show the organization, which is a different thing from the product.

### Form panel (SO-P)

- **SO-P1.** Sign-in and recovery use `SignedOutPanel` (and invitation setup and email change only after SO-O3): one centered column, at most 24rem wide (`max-w-sm`), centered in the space under the header with `m-auto`. Do not center with `items-center` on `main`: a tall form would lose its top on a short window.
- **SO-P2.** The column holds, in order: the page title (`h1`), the description, the card, and the footer line.
- **SO-P3.** The title uses the workspace page title: `data-slot="page-title"`, the display face, weight 700, 24px below 640px and 30px from 640px, tracking -0.025em, `leading-tight`. These are the `PageHeader` title classes. The panel renders its own heading so `PageHeader` does not change. The title takes `id={titleId}` (default `signed-out-title`).
- **SO-P4.** The description is 14px, line height 24px, `text-muted-foreground`, 6px under the title. The card starts 24px under the description.
- **SO-P5.** The card is the shared `Card` (`data-slot="card"`, `--card-edge`, `--card-lift`, the large radius), with `slim-ui`, `w-full` (the base `Card` class has `self-start`, which would shrink it to its content in a flex column), and 20px padding (`p-5`) at every width. Notices sit at the top of the card, then the form.
- **SO-P6.** Inside the form, groups are 16px apart (`gap-4`); a label is 8px over its field (the `Field` gap).
- **SO-P7.** The footer line sits 24px under the card: 14px, `text-muted-foreground`, centered, with its link in `text-action-text` weight 500. The sentence and its link stay in one `<p>`.
- **SO-P8.** The panel takes `contentHidden`. When it is on, the title, the description, and the empty card show; the card's content and the footer line are `invisible` and keep their space.
- **SO-P9.** No icon circle shows over the title.

### Home `/` (SO-H)

- **SO-H1.** The header action is "Sign in" as an outline button (`variant="outline"`, `min-h-11 xl:min-h-8`), 44px below 1280px and 32px from 1280px, with no icon. "Open workspace" stays the page's one primary action.
- **SO-H2.** Under the header, one region at most 72rem wide (`max-w-6xl`), with 16px side padding below 640px and 28px from 640px. From 1024px it has two panes: the hero (`minmax(0,1fr)`) and the guided-start card (`minmax(0,28rem)`), 64px apart, centered on the same middle line. Below 1024px the hero comes first, then the card, 40px apart.
- **SO-H3.** From 1024px the region is vertically centered in the space under the header (`my-auto`), with at least 48px above and below. Below 1024px it starts 40px under the header.
- **SO-H4.** The hero title keeps its size: 36px below 1024px and 48px from 1024px, `leading-[1.1]`, weight 700, tracking -0.025em, with `data-slot="page-title"`. This is the one title step above 30px in the product (proposed DESIGN.md text below).
- **SO-H5.** The hero text is 16px with a 28px line height, `text-muted-foreground`, at most 36rem wide, 20px under the title.
- **SO-H6.** "Open workspace" is the primary button with `size="lg"` and `min-h-11` (44px at every width and every page spacing; `h-11` alone shrinks under compact spacing), 32px under the text, with its arrow icon. It is the only button with an icon on the signed-out pages: it leaves the page.
- **SO-H7.** The two facts ("Self-hosted access", "Your records stay on your server") stay as one line of 14px muted text, 24px under the button, each after a 16px icon in `text-muted-foreground`, not action blue.
- **SO-H8.** "A guided start" is a `Card` with a `CardHeader` that holds a `CardTitle` (`h2`, 16px weight 600). There is no header icon. The card takes `w-full` below 1024px and `lg:self-center` from 1024px, because the base `Card` class has `self-start`.
- **SO-H9.** The three steps are an ordered list (`ol`) in the card body. Each row has 20px side padding and 16px top and bottom padding, with a `border-border` hairline between rows. A row is the step number ("01") in the code face at 12px, `text-muted-foreground`, tabular figures; then the step title as an `h3` (14px weight 600) over its sentence (14px muted, 20px line). No check circle shows.
- **SO-H10.** No footer.

### Sign-in `/login` (SO-S)

- **SO-S1.** The page is the form panel. The title "Welcome back" is the page's one `h1`. The description is "Sign in to continue to your workspace."
- **SO-S2.** The brand panel goes, with its `h1`, paragraph, and footer line. No split layout exists at any width.
- **SO-S3.** In the card, in order: the password-set notice (success, when `?completed=password`), the error notice (destructive, `role="alert"`), Email, Password, "Forgot password?", and Sign in.
- **SO-S4.** "Forgot password?" is a link under the Password field, left-aligned, `text-action-text` weight 500, with a 44px target below 1280px (`inline-flex min-h-11 items-center xl:min-h-6`).
- **SO-S5.** Sign in is the full-width primary button: 44px below 1280px, 32px from 1280px (the slim size), with no icon. While it runs it reads "Signing in…" and keeps its width.
- **SO-S6.** The footer line is "First deployment? Read the setup guide", with the link to `/setup`.
- **SO-S7.** Session check: `busy` and `contentHidden` are on until the check ends. A signed-in visitor sees the header, the title, the description, and the empty card, then the redirect. An anonymous visitor, or a failed check, gets the full form.

### Recovery `/auth/recovery` (SO-R)

- **SO-R1.** The page is the form panel. The titles and descriptions stay: "Reset password" with "Enter your email to get recovery instructions."; "Choose a new password" with "Choose a strong password for your Slate Operations account."
- **SO-R2.** Before hydration, the card holds only the line "Preparing password recovery…" (`role="status"`, 14px muted). It is the page's only status before the request.
- **SO-R3.** Request state: in the card, the sent notice (success, `role="status"`), the error notice (destructive, `role="alert"`, with its reference), Email (autofocus stays), and "Request recovery" (pending "Requesting…").
- **SO-R4.** Completion state: in the card, the error notice, "New password" with its requirement line and its field error, "Confirm new password" with its field error, and "Reset password" (pending "Saving…"). A field error shows under its field in `text-destructive`.
- **SO-R5.** The footer line is "Remembered your password? Return to sign in", with the link to `/login`.
- **SO-R6.** Form buttons are full-width primaries with no icon, sized as in SO-S5.

### Other signed-out pages (SO-O)

- **SO-O1.** `/setup` (setup guide) takes the frame only. Its "Back to sign in" ghost button moves into the header action slot. Its body (eyebrow, title, notice, card, "Continue to sign in") does not change. One body spacing changes: the top and bottom padding from 640px goes from 96px to 64px (`sm:py-16`), so the page fits 1440x900 under the 56px top bar without scrolling at rest. Two colors change: the eyebrow uses `text-action-text`, the text-safe shade, because `text-primary` was 4.45:1 at 12px, below AA; the Terminal icon uses `text-muted-foreground`, as the home facts do (SO-H7), because action blue never decorates (One Meaning Rule). The header "Back to sign in" takes the home header action's sizes (`h-8 min-h-11 xl:min-h-8`).
- **SO-O2.** `/auth/setup` and `/auth/email-change` take the frame and the mark only (the scope stated to the Human Owner). Each page drops its own `<main>`, its `min-h-screen`, and its own "SO" block; its current content sits in the frame's `main`, centered with `m-auto` and `px-4 py-8 sm:py-12`. Its words, controls, classes, order, and states do not change. It gets no `slim-ui` and no panel.
- **SO-O3 (proposed, needs a go-ahead).** Move these two pages into `SignedOutPanel` too, so all four form pages look the same. This is more than a container: inside `slim-ui`, from 1280px, the email change buttons, the invitation list, and the outline "Go to your workspace" button become 32px slim controls, and the icon tiles go. No other rule depends on this choice.

## Shared components

| Component | File | Props | Notes |
| --- | --- | --- | --- |
| `ProductMark` | `frontend/src/components/brand/product-mark.tsx` | `className?` | Server-safe. SO-M1, SO-M2. |
| `SignedOutFrame` | `frontend/src/components/signed-out/signed-out-frame.tsx` | `children`, `actions?: ReactNode`, `actionsHidden?: boolean`, `busy?: boolean` | Server-safe. Renders the header (product link and actions) and `main`. SO-F1 to SO-F9. |
| `SignedOutPanel` | `frontend/src/components/signed-out/signed-out-panel.tsx` | `title: string`, `titleId?: string`, `description?: ReactNode`, `children` (the card content), `footer?: ReactNode`, `contentHidden?: boolean` | Server-safe. Renders the column, title, description, `Card` with `slim-ui`, and footer line. SO-P1 to SO-P9. |

Use the existing `Card`, `CardHeader`, `CardTitle`, `Button`, `Input`, `Field`, `FieldLabel`, `FieldDescription`, `FieldError`, and `Alert`. Add no new token.

## Control sizes

Sizes are at the default page spacing. Spacious spacing makes the `h-*` sizes larger; compact spacing (from 1280px, fine pointer only) makes them smaller. `min-h-11` without an `xl:min-h-*` class keeps a fixed 44px floor in `#main-content`.

| Control | Below 640px | 640 to 1279px | From 1280px | How |
| --- | --- | --- | --- | --- |
| Field (inside the panel card) | 44px, 16px text | 44px (16px text below 768px, 14px from 768px) | 32px, 14px text | `Input` with `className="min-h-11"`; `slim-ui` sets 32px from 1280px (as Account settings does) |
| Field label | 14px weight 500 | 14px weight 500 | 12px weight 500 | `slim-ui` |
| Form primary button | 44px, full width | 44px, full width | 32px, full width | `Button` with `className="min-h-11 w-full"`, as Account settings does; `slim-ui` sets 32px from 1280px |
| "Forgot password?" | 44px target | 44px target | 24px target | `inline-flex min-h-11 items-center xl:min-h-6` |
| Home header "Sign in" | 44px | 44px | 32px | `variant="outline"`, `min-h-11 xl:min-h-8` (the shell header control sizes) |
| Home "Open workspace" | 44px | 44px | 44px | `size="lg"` with `min-h-11`; no `slim-ui` on home |
| Product link | 44px tall target | 44px | 32px | `min-h-11 xl:min-h-8`, `rounded-md`, focus outline |

The Slate field skin (sunken well and bottom rule) applies at every width inside `slim-ui`; only the heights change at 1280px. Whiteboard, Triplicate, and Stockroom keep their own field skins at these sizes.

## Delta list (AC-4)

"Now" names the current classes; "Target" names the workspace tokens and parts. Light and dark use the same token names; the "Dark" column lists only what differs.

| Part | Now | Target | Dark |
| --- | --- | --- | --- |
| Page ground | `bg-background` (`--ground`) with no skin hook; sign-in panel `bg-sidebar`, which is also `--ground` | `main` with `data-skin="page"` on `bg-background`; each look draws its ground | Same tokens. The empty panel is ground on ground in both modes; it goes. |
| Top bar | Home: borderless strip in `main`, `max-w-7xl`, `py-5`. Others: none. | Workspace top bar: `h-14 bg-card border-b border-border px-4 sm:px-5`, `data-skin="topbar"` | Same. |
| Product mark | Four styles: `size-9`/`size-8`, `bg-foreground` or `bg-primary`, radius `--radius` or `md` | `ProductMark`: `size-8 rounded-md bg-foreground text-background`, 12px weight 700 | Now: the recovery mark is light action blue. Target: a light `--foreground` square with dark text, as in the dark shell. |
| Page title | Home 36/48px weight 600 (renders 700); sign-in `h1` hidden on phones, visible title is an `h2` in Geist; recovery `h1` 24px. None has `data-slot="page-title"`. | Panel pages: `PageHeader` title classes (24px, 30px from 640px, weight 700, -0.025em, display face) with `data-slot="page-title"`. Home: 36/48px weight 700, -0.025em, with `data-slot="page-title"`. | Same. Looks restyle the title (Whiteboard underline, Triplicate width, Stockroom stencil). |
| Description | `mt-2 text-sm text-muted-foreground`; home `text-lg leading-8` | `mt-1.5 text-sm leading-6 text-muted-foreground`; home `text-base leading-7` | Same. |
| Icon over title | `size-11 rounded-full` on `bg-muted` or `bg-accent` | None | Same. |
| Form surface | No card (sign-in, recovery); email change `rounded-xl shadow-sm p-6 sm:p-8` | `Card` with `slim-ui`, `p-5`, `--card-edge`, `--card-lift`, the large radius | Same. |
| Field | `Input` box: `h-10 bg-card border-input rounded-[var(--radius)]`; focus border `--action` | Slate slim skin: `--surface-sunken` well, small top corners, square bottom, bottom rule; `--action` rule on keyboard focus only; `--danger` rule when invalid. Sizes in "Control sizes". | Light rule `--ink-muted`; dark rule `--control-edge` (globals.css slim skin). |
| Field label | `text-sm font-medium` | 14px below 1280px, 12px weight 500 from 1280px (`slim-ui`) | Same. |
| Primary button | `size="lg"` 44px, full width, arrow icon | 44px below 1280px, 32px from 1280px, full width, no icon; pending label keeps its width | `--action` fill, `--action-ink` text in both modes. |
| Link | `text-primary` (the action fill color) `font-medium hover:underline` | `text-action-text` weight 500, `hover:underline`, `underline-offset-4`, the 2px `--focus` outline | `--action-text` is the text-safe shade in both modes. |
| Notices | `Alert` with `mb-5` above the form, on the ground | `Alert` inside the card at the top, 16px over the first field | Same component, same variants. |
| Field spacing | `space-y-5` (20px) | `gap-4` (16px) between groups; 8px label to field | Same. |
| Home header action | Primary `size="sm"` with arrow | Outline, no icon (SO-H1) | `--button-edge` and `--button-ink` per look. |
| Home feature icons | `text-primary` | `text-muted-foreground` | Same. |
| Home guided-start card | Hand-made card, `rounded-[calc(var(--radius)*1.5)]`, `p-5 sm:p-7`, `h2` 20px, header icon, check circles | `Card`, `CardHeader`, `CardTitle` (16px weight 600), `ol` rows (SO-H9), no icons | Same. |
| Layout | Sign-in: split grid from 1024px. Recovery: centered column with `min-h-screen` | One frame; panel column `max-w-sm m-auto`; home two panes from 1024px; no `min-h-screen` | Same. |
| Footers | Home and sign-in footers | None | Same. |

## Wide screens and phones (AC-5)

The Still Page Rule is for workspace pages; signed-out pages are not still pages. They follow these rules instead:

1. The header band spans the full window width at every size.
2. Sign-in and recovery center one 24rem form. A single centered task does not leave a blank column, so they do not fill the width.
3. Home fills the window from 1024px: two panes side by side under the band, centered in the space that is left.
4. At 1440x900 no signed-out page scrolls at rest. On a shorter window the page scrolls as one; no pane scrolls on its own.
5. At 390x844 every page is one column. Sign-in and recovery fit without scroll at rest; home scrolls.
6. No page scrolls sideways at any width from 320px. The panel gives each `Alert` in its card `wrap-anywhere`, so a long email or reference in a notice wraps.
7. Every link and button shows the 2px `--focus` outline with a 2px offset on keyboard focus. Fields show the keyboard focus rule (delta list, Field). The product link in the header shows the outline too.

## Words

Kept (tests pin most of them): "Welcome back", "Sign in to continue to your workspace.", "Email", "Password", "Forgot password?", "Sign in", "Signing in…", "First deployment?", "Read the setup guide", "Password set. Sign in.", "Finish setup using the link in your invitation email.", "Reset password", "Choose a new password", both recovery descriptions, "Preparing password recovery…", "Request recovery", "Requesting…", "Saving…", "New password", "Confirm new password", the requirement line and the field errors, both recovery notices, "Remembered your password?", "Return to sign in", "Make the next action obvious.", the hero sentence, "Open workspace", "Self-hosted access", "Your records stay on your server", "A guided start", "Join", "Model", "Operate", and their three sentences.

**Error message.** "Invalid email or password." (commit `296c890f`): **confirmed**. It is the same for a wrong email and a wrong password, so it does not tell anyone which accounts exist. It is short, it ends with a period like the other notices, and it shows no reference because the person can fix it alone.

Changed or removed (each needs no new word):

| Words | Change | Reason | Where it goes |
| --- | --- | --- | --- |
| "A clear view of what comes next." and "Design your operating model once, then keep every team working from the same source of truth." | Removed | They live only in the empty brand panel, which AC-3 removes. | Nowhere. The home hero already says what the product does. |
| "Self-hosted by default · Slate Operations" (sign-in footer) | Removed | Footer of the removed panel; the header names the product. | The home line "Self-hosted access" keeps the fact. |
| "Slate Operations" and "Self-hosted by default" (home footer) | Removed | The header names the product, and the hero line already says self-hosted (one fact, one place). | Header; hero facts line. |
| "Use the email and password for your Slate Operations account." | Removed | It explains how to use the fields and repeats the description (the Few Words Rule). No test pins it. | Nowhere. |
| "Slate Ops" (home header on phones) | Becomes "Slate Operations" | One product link on every page; the full name fits at 390px beside "Sign in". | Header. |
| "Welcome back" | `h2` becomes `h1` | AC-3: the sign-in page gets one visible `h1` at every width. | Same place. |

## Preserved behavior

| Behavior | Test | What keeps it |
| --- | --- | --- |
| No sign-in flash on `/` and `/login` for a signed-in visitor | `http/auth-sign-in-destination.spec.ts` "an authenticated visitor to … waits …" | Home: `actionsHidden` hides the header "Sign in", and the hero CTA stays `invisible` until the check ends. Sign-in: `contentHidden` hides Email and Sign in. `main` stays visible. |
| Public actions after an anonymous or failed check | same file, "keeps its public actions …" | The page clears `actionsHidden` and `contentHidden` in both paths, as now. |
| The error alert inside `main`; "Invalid email or password." | same file, "login explains …" | The `Alert` sits in the card, inside `main`; the frame adds no alert (SO-F7). |
| Setup guide link only on sign-in | `http/landing-page.spec.ts` | Home has no `/setup` link; "First deployment?" and the link share one `<p>` (SO-P7). |
| Recovery request and completion, one status | `http/auth-setup.spec.ts`, `fullstack/auth-session.spec.ts` | Words kept; the frame adds no `role="status"`. |
| One "sign in" link on email change | `http/auth-email-change.spec.ts` (`/sign in/i`) | No header action on that page (SO-F4). |
| Headings "Welcome back", "Reset password", "Choose a new password" | `fullstack/auth-session.spec.ts` | Words kept. |
| Signed-out look and theme read | `http/organization-theme.spec.ts`, `http/user-theme-preferences.spec.ts` | Unchanged provider; the frame only adds `data-skin` hooks. |
| Invitation setup words and states | `http/auth-setup.spec.ts` | SO-O2: frame and mark only; the content does not change. |

**Risk.** `id="main-content"` turns on the device's page spacing (density) on signed-out pages. With "spacious", the form spacing grows by about a quarter. No test checks this on a signed-out page; check the sign-in page at 390x844 with spacious density once.

## Backend changes

None.

## Planned verification

1. The fast frontend checks (`npm run check`) and the specs above: `auth-sign-in-destination`, `landing-page`, `auth-setup`, `auth-email-change`, `organization-theme`, and `user-theme-preferences`.
2. One new HTTP check per criterion: AC-2 (no element with the text "SO" outside `ProductMark` on the six pages), AC-3 (`/login` has exactly one `h1`, visible at 1440 and 390), and AC-5 (no sideways scroll at 390 on the three pages).
3. Screens of the three pages at 1440x900 and 390x844, light and dark, in Slate, plus sign-in in Whiteboard and Stockroom, and home at 390 in Stockroom (the uppercase stencil title on two or three lines), for the ui-reviewer.

## Proposed DESIGN.md text (for the documenter)

Add under "Components", after "Profile and Account settings (relayout)":

> ### Signed-out pages
>
> Home, sign-in, recovery, invitation setup, email change, and the setup guide share one frame (`components/signed-out/signed-out-frame.tsx`): the workspace top bar (56px, card fill, hairline, `data-skin="topbar"`) with the product link on the left, and `main#main-content` with `data-skin="page"`, so each look draws its ground. Before sign-in the page knows only the look, not the organization, so the product link shows `ProductMark` (`components/brand/product-mark.tsx`: the "SO" square in `--foreground`, 32px) and "Slate Operations". No page draws its own mark.
>
> Sign-in and recovery use `SignedOutPanel`: one centered 24rem column with the page title (24px, 30px from 640px), a muted description, a `slim-ui` card that holds the notices and the form, and one muted footer line with its link. Fields and buttons are 44px below 1280px and 32px from 1280px. Home has a 36px title (48px from 1024px), the one title above 30px in the product, and two panes from 1024px: the hero with "Open workspace", the only primary, and the guided-start card. Signed-out pages are not still pages: the band spans the width, forms stay centered, and at 1440x900 nothing scrolls at rest.
>
> Correct: the sign-in page at 390px shows the band with the mark, "Welcome back" as the page's one `h1`, and the card with Email, Password, and Sign in.
>
> Wrong: a split sign-in page whose left half is ground on ground and holds the only `h1`, or a blue "SO" block on one page and a black one on the next.
