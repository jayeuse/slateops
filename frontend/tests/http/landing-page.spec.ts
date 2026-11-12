import { expect, signedOut, test } from "./helpers/test";

// docs/specs/ux-friction-pass.md DR-13.5: the landing page speaks to staff;
// the installer guide stays one link away on the sign-in page only.
test("UF-C13.4 the landing page says staff join by invitation, and only sign-in links the setup guide", async ({
  page,
}) => {
  await signedOut(page);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Join", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Your administrator sends you an invitation by email.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByText(/outside the browser/)).toHaveCount(0);
  await expect(page.getByRole("link", { name: /setup guide/i })).toHaveCount(0);
  await expect(page.getByText(/First deployment/)).toHaveCount(0);
  await expect(page.locator('a[href="/setup"]')).toHaveCount(0);

  await page.getByRole("link", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  const guide = page.getByRole("link", {
    name: "Read the setup guide",
    exact: true,
  });
  await expect(guide).toHaveAttribute("href", "/setup");
  await expect(guide.locator("..")).toContainText("First deployment?");
});
