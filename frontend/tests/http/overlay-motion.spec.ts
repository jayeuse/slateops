import { expect, test, type Locator } from "@playwright/test";

import { installProfileApi } from "./helpers/profile-api";

// Menus, popovers, selects and tooltips grow from their trigger and go back
// to it (Human Owner, 2026-11-13): they start clear at 95%, ease out over
// --motion-base held to at most 250ms, and leave 20% faster with ease-in.
// Base UI sets data-starting-style and data-ending-style for the two ends;
// the test sets them by hand so it reads the rules, not a running frame.

const motion = (popup: Locator, state?: "starting" | "ending") =>
  popup.evaluate((node, end) => {
    const element = node as HTMLElement;
    if (end) element.setAttribute(`data-${end}-style`, "");
    const style = getComputedStyle(element);
    const timing = {
      property: style.transitionProperty,
      duration: style.transitionDuration,
      easing: style.transitionTimingFunction,
    };
    // The end state's values, read with transitions held off.
    element.style.transition = "none";
    const look = { opacity: style.opacity, scale: style.scale };
    const box = element.getBoundingClientRect();
    const origin = style.transformOrigin;
    element.style.transition = "";
    if (end) element.removeAttribute(`data-${end}-style`);
    return {
      ...timing,
      ...look,
      origin,
      center: `${box.width / 2}px ${box.height / 2}px`,
    };
  }, state);

test("a menu grows from its trigger with ease-out and leaves faster toward it with ease-in", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installProfileApi(page);
  await page.goto("/settings");
  await page
    .locator('[data-skin="topbar"]')
    .getByRole("button", { name: "Account", exact: true })
    .click();
  const menu = page.getByRole("menu", { name: "Account", exact: true });
  await expect(menu).toBeVisible();

  const open = await motion(menu);
  expect(open).toMatchObject({
    property: "opacity, scale",
    duration: "0.22s",
    easing: "cubic-bezier(0.16, 1, 0.3, 1)",
    opacity: "1",
  });
  // It grows from the trigger's side, not from its own middle.
  expect(open.origin).not.toBe(open.center);

  expect(await motion(menu, "starting")).toMatchObject({
    opacity: "0",
    scale: "0.95",
  });
  expect(await motion(menu, "ending")).toMatchObject({
    duration: "0.176s",
    easing: "cubic-bezier(0.55, 0, 1, 0.45)",
    opacity: "0",
    scale: "0.95",
  });
});

test("keyboard, Escape and tooltip hand-offs are instant, and Reduce motion stills overlays", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installProfileApi(page);
  await page.goto("/settings");
  await page
    .locator('[data-skin="topbar"]')
    .getByRole("button", { name: "Account", exact: true })
    .click();
  const menu = page.getByRole("menu", { name: "Account", exact: true });
  await expect(menu).toBeVisible();
  const duration = (instant?: string) =>
    menu.evaluate((node, value) => {
      if (value) node.setAttribute("data-instant", value);
      const result = getComputedStyle(node).transitionDuration;
      node.removeAttribute("data-instant");
      return result;
    }, instant);

  // Base UI marks a keyboard open ("click"), an Escape close ("dismiss"), a
  // focus-opened tooltip ("focus") and a tooltip hand-off ("delay"): those
  // are instant, so focus moves at once. A pointer open grows (above).
  for (const instant of ["click", "dismiss", "focus", "delay"])
    expect(await duration(instant), instant).toBe("0s");

  // Reduce motion, from Appearance or from the device, stills the overlay.
  await page.evaluate(() => {
    document.documentElement.dataset.motion = "reduced";
  });
  expect(
    await menu.evaluate((node) => getComputedStyle(node).transitionProperty),
  ).toBe("none");
  await page.evaluate(() => {
    delete document.documentElement.dataset.motion;
  });
  expect(await duration()).toBe("0.22s");
  await page.emulateMedia({ reducedMotion: "reduce" });
  expect(
    await menu.evaluate((node) => getComputedStyle(node).transitionProperty),
  ).toBe("none");
});
