import { expect, test, type Locator } from "@playwright/test";

import { installProfileApi } from "./helpers/profile-api";

// Fields show no focus mark after a pointer press, on every page (Human
// Owner, 2026-11-13). Keyboard focus keeps the mark, so a person who moves
// with Tab still sees where they are.

const marks = (field: Locator) =>
  field.evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      outline: style.outlineStyle,
      shadow: style.boxShadow,
      border: style.borderBottomColor,
    };
  });

test("a clicked field shows no focus mark, also while typing; Tab shows the mark again", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await installProfileApi(page);
  await page.goto("/settings");
  const title = page.getByLabel("Job title", { exact: true });
  const phone = page.getByLabel("Phone", { exact: true });
  await expect(title).toBeVisible();

  // A clicked field looks like the unfocused field beside it. The pointer
  // moves off, so hover does not count; edges ease, so poll.
  await title.click();
  await expect(title).toBeFocused();
  await page.mouse.move(4, 4);
  await expect
    .poll(async () => [await marks(title), await marks(phone)])
    .toEqual([await marks(phone), await marks(phone)]);
  await expect.poll(() => marks(title)).toMatchObject({ outline: "none" });
  await page.keyboard.type("Lead");
  await expect
    .poll(
      async () => (await marks(title)).border === (await marks(phone)).border,
    )
    .toBe(true);
  expect(await marks(title)).toMatchObject({ outline: "none", shadow: "none" });

  // Tab is keyboard focus: the next control shows the mark.
  await page.keyboard.press("Tab");
  const next = page.locator(":focus");
  await expect(next).toHaveCount(1);
  await expect.poll(async () => (await marks(next)).outline).toBe("solid");

  // A click hides it again.
  await phone.click();
  await expect(phone).toBeFocused();
  await page.mouse.move(4, 4);
  await expect.poll(async () => (await marks(phone)).outline).toBe("none");
});
