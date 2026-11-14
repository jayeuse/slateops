import { expect, test, type Page } from "./helpers/test";
import { mockAccessApi } from "./helpers/access-api";
import { installListApi, listIds } from "./helpers/openview-list-api";

// A strip that scrolls sideways (filters, tabs, toolbars) never scrolls up
// and down (Human Owner, 2026-11-14). `overflow-x: auto` alone turns on
// vertical scrolling too, so a 1px rounding at some zoom or text size shows
// a scrollbar; each strip sets `overflow-y: hidden`.

const sidewaysStrips = (page: Page) =>
  page.evaluate(() =>
    [...document.querySelectorAll<HTMLElement>("main *")]
      .filter((node) => {
        const style = getComputedStyle(node);
        // A strip: one short row that scrolls sideways.
        return (
          /^(auto|scroll)$/.test(style.overflowX) &&
          node.getBoundingClientRect().height > 0 &&
          node.getBoundingClientRect().height < 120
        );
      })
      .map((node) => ({
        name:
          node.getAttribute("aria-label") ??
          node.getAttribute("data-slot") ??
          node.className.toString().slice(0, 40),
        overflowY: getComputedStyle(node).overflowY,
      })),
  );

test("the OpenView status filter strip scrolls sideways only", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await installListApi(page, { viewer: "writer" });
  await page.goto(
    `/openview?section=views&module=${listIds.module}&view=${listIds.view}`,
  );
  await expect(page.getByRole("group", { name: "Status" })).toBeVisible();
  const strips = await sidewaysStrips(page);
  expect(strips.length).toBeGreaterThan(0);
  expect(strips.filter((strip) => strip.overflowY !== "hidden")).toEqual([]);
});

test("the Access people status strip scrolls sideways only, also on a phone", async ({
  page,
}) => {
  await mockAccessApi(page);
  for (const size of [
    { width: 1440, height: 900 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(size);
    await page.goto("/access?view=people");
    await expect(page.getByRole("group", { name: "Status" })).toBeVisible();
    const strips = await sidewaysStrips(page);
    expect(strips.length).toBeGreaterThan(0);
    expect(strips.filter((strip) => strip.overflowY !== "hidden")).toEqual([]);
  }
});
