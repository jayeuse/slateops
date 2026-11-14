import { expect, test, type Locator, type Page } from "./helpers/test";
import { installKanbanApi, kanbanHref } from "./helpers/board-kanban-api";
import { installListApi, listIds } from "./helpers/openview-list-api";
import { installProfileApi } from "./helpers/profile-api";

// One selection pill (Human Owner, 2026-11-14). Every rail of choices (tabs,
// link tabs, segmented filters, the phone stage switcher and Color mode) has
// the tab look: a sunken rail with an inset --rule hairline and a 4px pad,
// a raised pill with --lift and an inset --rule hairline at 0.75 of the
// radius, the chosen label in --action-text at weight 600, and one height.

const contacts = `/openview?section=views&module=${listIds.module}&view=${listIds.view}`;

/** Box shadows without Tailwind's empty ring layers. */
const visibleShadow = (shadow: string) =>
  shadow
    .split(/,(?![^(]*\))/)
    .map((layer) => layer.trim())
    .filter((layer) => !layer.startsWith("rgba(0, 0, 0, 0)"))
    .join(", ");

const railLook = (rail: Locator) =>
  rail.evaluate((node) => {
    const style = getComputedStyle(node);
    return {
      fill: style.backgroundColor,
      edge: style.boxShadow,
      corner: style.borderRadius,
      pad: style.padding,
    };
  });

const pillLook = (pill: Locator) =>
  pill.evaluate((node) => {
    const style = getComputedStyle(node);
    return {
      fill: style.backgroundColor,
      edge: style.boxShadow,
      corner: style.borderRadius,
    };
  });

const chosenLook = (option: Locator) =>
  option.evaluate((node) => {
    const style = getComputedStyle(node);
    return { ink: style.color, weight: style.fontWeight };
  });

/** The tab look from the tokens (DESIGN.md, Selection rails and pills). */
const spec = (page: Page) =>
  page.evaluate(() => {
    const probe = document.createElement("div");
    document.body.append(probe);
    const read = (css: Partial<CSSStyleDeclaration>) => {
      Object.assign(probe.style, css);
      const style = getComputedStyle(probe);
      const result = {
        fill: style.backgroundColor,
        edge: style.boxShadow,
        corner: style.borderRadius,
        pad: style.padding,
        ink: style.color,
      };
      probe.removeAttribute("style");
      return result;
    };
    const rail = read({
      backgroundColor: "var(--surface-sunken)",
      boxShadow: "inset 0 0 0 1px var(--rule)",
      borderRadius: "var(--radius)",
      padding: "4px",
    });
    const pill = read({
      backgroundColor: "var(--surface-raised)",
      boxShadow: "var(--lift), inset 0 0 0 1px var(--rule)",
      borderRadius: "calc(var(--radius) * 0.75)",
    });
    const ink = read({ color: "var(--action-text)" }).ink;
    probe.remove();
    return {
      rail: {
        fill: rail.fill,
        edge: rail.edge,
        corner: rail.corner,
        pad: rail.pad,
      },
      pill: { fill: pill.fill, edge: pill.edge, corner: pill.corner },
      chosen: { ink, weight: "600" },
    };
  });

async function expectTabLook(
  page: Page,
  rail: Locator,
  pill: Locator,
  chosen: Locator,
) {
  const want = await spec(page);
  const got = { rail: await railLook(rail), pill: await pillLook(pill) };
  expect({
    rail: { ...got.rail, edge: visibleShadow(got.rail.edge) },
    pill: { ...got.pill, edge: visibleShadow(got.pill.edge) },
    chosen: await chosenLook(chosen),
  }).toEqual(want);
}

test("a segmented filter and the tabs beside it share one look and height, in every look", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await installListApi(page, { viewer: "writer" });
  await page.goto(contacts);
  const filter = page.getByRole("group", { name: "Status" });
  const filterPill = filter.locator('[data-slot="segmented-pill"]');
  const tabs = page.locator('[data-slot="tabs-list"]').first();
  await expect(filterPill).toHaveCount(1);
  await expect(tabs).toBeVisible();

  await expectTabLook(
    page,
    filter,
    filterPill,
    filter.locator('[aria-pressed="true"]'),
  );
  const height = (rail: Locator) =>
    rail.evaluate((node) => Math.round(node.getBoundingClientRect().height));
  expect(await height(filter)).toBe(36);
  expect(await height(tabs)).toBe(36);

  // Each look restyles the filter as it restyles its tabs.
  for (const look of ["whiteboard", "triplicate", "stockroom"]) {
    await page.evaluate((name) => {
      document.documentElement.dataset.theme = name;
    }, look);
    expect(await railLook(filter), `${look} rail`).toEqual(
      await railLook(tabs),
    );
    expect(await pillLook(filterPill), `${look} pill`).toEqual(
      await pillLook(tabs.locator('[data-slot="tabs-indicator"]')),
    );
  }
});

test("Color mode in Account settings has the tab look and height", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await installProfileApi(page);
  await page.goto("/settings");
  const mode = page.getByRole("radiogroup", { name: "Color mode" });
  await expect(mode).toBeVisible();
  const chosen = mode.locator('[role="radio"][aria-checked="true"]');
  await expectTabLook(page, mode, chosen.locator("[data-pill]"), chosen);
  expect(
    await mode.evaluate((node) =>
      Math.round(node.getBoundingClientRect().height),
    ),
  ).toBe(36);
});

test("the phone stage switcher on a Kanban board has the tab look", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installKanbanApi(page, { level: "write" });
  await page.goto(kanbanHref());
  const switcher = page.getByRole("navigation", { name: "Stages" });
  const current = switcher.locator('[aria-current="true"]');
  await expect(current).toBeVisible();
  await expectTabLook(page, switcher, current.locator("[data-pill]"), current);
});
