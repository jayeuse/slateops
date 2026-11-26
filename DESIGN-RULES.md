# Design rules

Rules for design work in this repository: user experience, layout, visual design, the design system, UI copy, and graphics. The Product Designer and the Frontend Engineer read this file. Moved here from `CLAUDE.md` and `AGENTS.md` on 2026-11-02.

## Skills

- **Design skills: `ui-ux-pro-max` and `impeccable` only. `ui-ux-pro-max` always has priority over `impeccable`.** `ui-ux-pro-max` owns system layout, information architecture, flows, interface and UI changes, interaction patterns, responsive behavior, accessibility, and UX improvements that make the product easier to use. `impeccable` owns design choices and visual presentation inside that structure: typography, color, tokens, spacing rhythm, motion, polish, and brand voice. `impeccable` stays the only writer of the design-system files (`DESIGN.md`, `.impeccable/design.json`) and records `ui-ux-pro-max` layout decisions there. On any conflict, the `ui-ux-pro-max` decision wins and `impeccable` adjusts the visuals; `impeccable` never overrides a layout, flow, or usability decision. Load no other design skill for any design operation, including plugin and personal skills (`design:*`, `frontend-design*`, `artifact-design` outside Artifact pages). `react-frontend-patterns` holds implementation rules, not design direction.

Correct: `Settled the /boards filter layout and keyboard flow with ui-ux-pro-max, then had impeccable choose type, color, and spacing within that layout.`
Wrong: `Let impeccable move the /boards filters into a side panel for visual balance, against the ui-ux-pro-max layout.`
Wrong: `Ran design:design-critique on /boards, then design:accessibility-review.`

## Sources of truth

- **Design truth** lives in `frontend/src/app/globals.css` (the tokens), `DESIGN.md` and its sidecar `.impeccable/design.json` (the design system), and `PRODUCT.md`. On a token difference, `globals.css` wins; update `DESIGN.md` through `impeccable`. `.impeccable/` is ignored by Git, so the sidecar exists only on this machine. Point to these files; never copy token values into other documents. `DESIGN.md` is long (about 22,000 words): read its front matter and only the section that the task needs, for example `## Components` for one component.

## Graphics

- **No image generation** exists in this harness. Build code-led: SVG for marks, icons, and illustrations; CSS and canvas for texture and motion. The existing comps in `.impeccable/mocks/` are valid references. If a flow needs a new raster comp or asset, say so and continue code-led; never fake one.

## Impeccable hook

The impeccable design hook runs after each Edit/Write on UI files and again at Stop (configured in `.claude/settings.json`). Treat its findings with the hook triage rules of the `impeccable` skill: fix real problems, never add an ignore to skip a fix, and ask before `ignore-file` or `ignore-rule`.
