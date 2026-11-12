import {
  asRole,
  expect,
  openWorkspace,
  smokeFixture,
  test,
} from "./smoke-fixture";

asRole("admin");

test("The Sandbox designer publishes a change @sandbox", async ({ page }) => {
  await openWorkspace(page, "/sandbox?section=build");
  // Canvas fields are SVG shapes; select one from the keyboard, as a keyboard user does.
  const field = page
    .getByRole("button", { name: "Notes, Long text, optional" })
    .first();
  await field.focus();
  await field.press("Enter");
  const settings = page.getByRole("group", { name: "Notes field settings" });
  await settings.getByRole("button", { name: /^Advanced/ }).click();
  await settings
    .getByRole("textbox", { name: "Notes description" })
    .fill(`Smoke check ${Date.now()}: free text about the customer`);
  await settings.getByRole("button", { name: "Save field changes" }).click();
  await page.getByRole("button", { name: "Review & Publish" }).click();
  const review = page.getByRole("dialog");
  await expect(
    review.getByRole("heading", { name: "Review & Publish" }),
  ).toBeVisible();
  // Publishing asks the administrator to confirm with their password.
  await review
    .getByLabel("Your password")
    .fill(smokeFixture().roles.admin.password);
  await review.getByRole("button", { name: "Publish changes" }).click();
  // The review ends in its Published state (UF-C11.2); Back to Build closes it.
  await expect(
    review.getByRole("heading", { name: "Published", exact: true }),
  ).toBeVisible({ timeout: 30_000 });
  await review.getByRole("button", { name: "Back to Build" }).click();
  await expect(review).toBeHidden();
  await expect(
    page.getByRole("button", { name: "Review & Publish" }),
  ).toBeDisabled();
});
