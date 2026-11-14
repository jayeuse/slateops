import { expect, test } from "@playwright/test";

import { installProfileApi } from "./helpers/profile-api";

// Light mode has no white fill, and a hover is a clear step from the fill
// under it (Human Owner, 2026-11-13). The theme contrast guard
// (tooling/check-theme-contrast.mjs) owns the token values in every look;
// this test owns the wiring: cards read the off-white surface, and a quiet
// control hovers with the ink tint of the current mode, not the sunken fill.

for (const [scheme, share] of [
  ["light", "0.1"],
  ["dark", "0.09"],
] as const) {
  test(`${scheme}: a card is not white, a ghost button hovers with the ${share} ink tint, and a filled button keeps its fill`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    // The person's own theme choice sets the mode.
    const api = await installProfileApi(page);
    api.theme = scheme;
    await page.goto("/settings");
    await expect(page.getByLabel("Job title", { exact: true })).toBeVisible();

    const card = page.locator('[data-slot="card"]:visible').first();
    await expect(card).toBeVisible();
    expect(
      await card.evaluate((node) => getComputedStyle(node).backgroundColor),
    ).not.toBe("rgb(255, 255, 255)");

    const ghost = page
      .locator('[data-slot="button"][data-variant="ghost"]:visible')
      .first();
    await expect(ghost).toBeVisible();
    await ghost.hover();
    // The fill eases in; poll until it settles at the tint.
    await expect
      .poll(() =>
        ghost.evaluate((node) => getComputedStyle(node).backgroundColor),
      )
      .toMatch(new RegExp(`^oklab\\(.* / ${share}\\)$`));

    // A button with its own fill keeps it under the pointer: the tint is
    // laid over the fill, so the button darkens a step instead of turning
    // into the bare tint.
    const outline = page
      .locator('[data-slot="button"][data-variant="outline"]:visible')
      .first();
    await expect(outline).toBeVisible();
    const fill = await outline.evaluate(
      (node) => getComputedStyle(node).backgroundColor,
    );
    await outline.hover();
    await expect
      .poll(() =>
        outline.evaluate((node) => {
          const style = getComputedStyle(node);
          return [style.backgroundColor, style.backgroundImage];
        }),
      )
      .toEqual([
        fill,
        expect.stringMatching(
          new RegExp(`^linear-gradient\\(oklab\\(.* / ${share}\\), oklab`),
        ),
      ]);
  });
}
