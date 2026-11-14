import { expect, signedOut, test, type Page } from "./helpers/test";

// docs/specs/signed-out-pages.md (TASK-0062). The pages are anonymous: every
// test answers the session check as signed out, then waits for the page's
// settled control before it measures.

const desktop = { width: 1440, height: 900 };
const phone = { width: 390, height: 844 };

// AC-3: "Welcome back" is the sign-in page's one h1 at every width, and the
// empty brand panel (with its own h1) is gone, so the form sits in the
// middle of the window, not in the right half of a split.
for (const viewport of [desktop, phone]) {
  test(`sign-in at ${viewport.width} px has one visible title, Welcome back, over a centered form`, async ({
    page,
  }) => {
    await signedOut(page);
    await page.setViewportSize(viewport);
    await page.goto("/login");
    await expect(page.getByLabel("Email", { exact: true })).toBeVisible();
    const titles = page.getByRole("heading", { level: 1 });
    await expect(titles).toHaveCount(1);
    await expect(titles).toHaveText("Welcome back");
    await expect(
      page.getByText("A clear view of what comes next."),
    ).toHaveCount(0);
    const button = await page
      .getByRole("button", { name: "Sign in", exact: true })
      .boundingBox();
    expect(button).not.toBeNull();
    expect(
      Math.abs(button!.x + button!.width / 2 - viewport.width / 2),
    ).toBeLessThanOrEqual(1);
  });
}

const routes = [
  {
    path: "/",
    settled: (page: Page) =>
      page.getByRole("link", { name: "Open workspace", exact: true }),
  },
  {
    path: "/login",
    settled: (page: Page) => page.getByLabel("Email", { exact: true }),
  },
  {
    path: "/auth/recovery",
    settled: (page: Page) =>
      page.getByRole("button", { name: "Request recovery", exact: true }),
  },
] as const;

const overflow = (page: Page) =>
  page.evaluate(() => ({
    sideways: document.documentElement.scrollWidth - window.innerWidth,
    down: document.documentElement.scrollHeight - window.innerHeight,
  }));

// AC-5 ("Wide screens and phones"): the top bar spans the window; no page
// scrolls sideways at 1440 or 390, and at 1440x900 none scrolls at rest.
for (const { path, settled } of routes) {
  test(`${path} shows the full-width top bar and fits 1440x900 and 390x844 without scrolling sideways`, async ({
    page,
  }) => {
    await signedOut(page);
    for (const viewport of [desktop, phone]) {
      await page.setViewportSize(viewport);
      await page.goto(path);
      await expect(settled(page)).toBeVisible();
      const bar = page.getByRole("banner");
      await expect(
        bar.getByRole("link", { name: "Slate Operations", exact: true }),
      ).toHaveAttribute("href", "/");
      const box = await bar.boundingBox();
      expect(box, `${path} ${viewport.width}`).toMatchObject({
        x: 0,
        width: viewport.width,
      });
      await expect
        .poll(async () => (await overflow(page)).sideways, {
          message: `${path} at ${viewport.width} px scrolls sideways`,
        })
        .toBeLessThanOrEqual(0);
      if (viewport === desktop)
        await expect
          .poll(async () => (await overflow(page)).down, {
            message: `${path} at 1440x900 scrolls at rest`,
          })
          .toBeLessThanOrEqual(0);
    }
  });
}
