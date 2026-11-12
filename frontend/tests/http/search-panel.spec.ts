import type { Page } from "@playwright/test";
import {
  answeredHeaders,
  answeredReference,
  defaultSignedInIdentity,
  expect,
  settleReact,
  test,
} from "./helpers/test";
import { installCommsSearchApi } from "./helpers/comms-search-api";

// The header search panel (docs/specs/ux-friction-pass.md item 4, DR-4.1 to
// DR-4.9). The panel reads five Platform kinds from /api/search and messages
// from /api/comms/search, five rows each, after typing settles. Its rules
// (order, totals, rows, destinations, active-row order) are owned by
// tests/isolated/platform/search-panel.spec.ts; these journeys show them on
// the page. The panel's field shares the accessible name "Search workspace"
// with the Search page's field, so every locator stays inside the dialog.

const id = (prefix: string, n: number) =>
  `${prefix}000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const MODULE = id("10", 1);
const BOARD = id("40", 1);
const DEPARTMENT = id("61", 1);
const CONVERSATION = id("7b", 1);
const MESSAGE = id("7b", 2);
const START = "/platform?section=notifications";

type Reply = {
  status?: number;
  body?: unknown;
  items?: unknown[];
  total?: number;
  capped?: boolean;
};

function item(kind: string, n: number, overrides: Record<string, unknown>) {
  return {
    kind,
    id: id("50", n),
    module_id: null,
    board_id: null,
    department_id: null,
    can_open: true,
    ...overrides,
  };
}

/** What "harbor" finds: five records of a capped total, a person the reader
 * cannot open, a post, no event, a message and a library file. */
function harbor(kind: string): Reply {
  switch (kind) {
    case "record":
      return {
        items: [1, 2, 3, 4, 5].map((n) =>
          item("record", n, {
            title: `Harbor record ${n}`,
            context_label: "Customers · Sales",
            module_id: MODULE,
          }),
        ),
        total: 1000,
        capped: true,
      };
    case "person":
      return {
        items: [
          item("person", 11, {
            title: "Mara Harborne",
            context_label: "Sales coordinator",
            can_open: false,
          }),
        ],
      };
    case "post":
      return {
        items: [
          item("post", 21, {
            title: "New Harbor account terms",
            context_label: "Sales Announcements",
            board_id: BOARD,
          }),
        ],
      };
    case "file":
      return {
        items: [
          item("file", 31, {
            title: "harbor-rate-card-2026.pdf",
            context_label: "Sales",
            department_id: DEPARTMENT,
          }),
        ],
      };
    case "message":
      return {
        items: [
          {
            message_id: MESSAGE,
            conversation_id: CONVERSATION,
            conversation_name: "sales-desk",
            seq: 4,
            author_id: defaultSignedInIdentity.id,
            author_name: "Ana Cruz",
            created_at: "2026-11-10T09:00:00Z",
            excerpt: "the Harbor delivery moves to Friday",
            matches: [{ start: 4, end: 10 }],
            parent_id: null,
          },
        ],
      };
    default:
      return { items: [] };
  }
}

/** Answers the six panel reads; `reply` decides each kind's answer. */
async function installSearch(
  page: Page,
  reply: (kind: string, search: string) => Reply | Promise<Reply> = (kind) =>
    harbor(kind),
) {
  const reads: URL[] = [];
  const answer = async (
    route: Parameters<Parameters<Page["route"]>[1]>[0],
    kind: string,
    url: URL,
    search: string,
  ) => {
    reads.push(url);
    const result = await reply(kind, search);
    const items = result.items ?? [];
    const total = result.total ?? items.length;
    // A read the panel cancelled has no one left to answer.
    await route
      .fulfill({
        status: result.status ?? 200,
        headers: answeredHeaders,
        json: result.body ?? {
          items,
          pagination: {
            limit: Number(url.searchParams.get("limit")),
            offset: 0,
            count: items.length,
            total,
            has_more: total > items.length,
            total_is_capped: result.capped ?? false,
          },
        },
      })
      .catch(() => undefined);
  };
  await page.route(
    (url) => url.pathname === "/api/search",
    (route) => {
      const url = new URL(route.request().url());
      return answer(
        route,
        url.searchParams.get("kind") ?? "",
        url,
        url.searchParams.get("search") ?? "",
      );
    },
  );
  await page.route(
    (url) => url.pathname === "/api/comms/search",
    (route) => {
      const url = new URL(route.request().url());
      return answer(route, "message", url, url.searchParams.get("q") ?? "");
    },
  );
  return reads;
}

const header = (page: Page) => page.locator('[data-skin="topbar"]');
const searchButton = (page: Page) =>
  header(page).getByRole("button", { name: "Search workspace", exact: true });
const panel = (page: Page) =>
  page.getByRole("dialog", { name: "Search workspace", exact: true });
const field = (page: Page) =>
  panel(page).getByRole("combobox", { name: "Search workspace", exact: true });

async function openStart(page: Page) {
  await page.goto(START);
  await expect(page.getByText("No notifications on this page.")).toBeVisible();
}

test("UF-C4.1 Search opens a panel over the page, reads six groups once typing settles, and Escape keeps the page", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.clock.install();
  const reads = await installSearch(page);
  await openStart(page);
  const address = page.url();

  await expect(searchButton(page)).toHaveAttribute("aria-haspopup", "dialog");
  await expect(searchButton(page)).toHaveText("Search");
  await searchButton(page).click();
  await expect(panel(page)).toBeVisible();
  await expect(field(page)).toBeFocused();
  await expect(panel(page)).toContainText(
    "Records · People · Posts · Events · Messages · Files",
  );
  expect(page.url()).toBe(address);
  // From 768 px the panel is 640 px wide and 96 px below the window top.
  const box = await panel(page).boundingBox();
  expect(box?.width).toBe(640);
  expect(box?.y).toBe(96);

  // No read starts while typing; one read per group starts once it settles.
  await page.clock.pauseAt(await page.evaluate(() => Date.now() + 1_000));
  await field(page).pressSequentially("harb");
  await page.clock.runFor(200);
  expect(reads).toHaveLength(0);
  await field(page).pressSequentially("or");
  await page.clock.runFor(250);
  await page.clock.resume();

  const headings = panel(page).getByRole("heading", { level: 3 });
  await expect(headings).toHaveText([
    "Records · 1,000+",
    "People · 1",
    "Posts · 1",
    "Messages · 1",
    "Files · 1",
  ]);
  // UF-C4.3 (panel side, contributor): messages come from one
  // GET /api/comms/search, and the group lists the rows it returns; the
  // server owner of D43 is test_comms_search_routes.py.
  expect(
    reads
      .map(
        (url) =>
          `${url.pathname} ${url.searchParams.get("kind") ?? "messages"} ${url.searchParams.get("search") ?? url.searchParams.get("q")} ${url.searchParams.get("limit")}`,
      )
      .sort(),
  ).toEqual([
    "/api/comms/search messages harbor 5",
    "/api/search event harbor 5",
    "/api/search file harbor 5",
    "/api/search person harbor 5",
    "/api/search post harbor 5",
    "/api/search record harbor 5",
  ]);
  const records = panel(page).getByRole("listbox", { name: /^Records/ });
  await expect(records.getByRole("option")).toHaveCount(5);
  // A person the reader cannot open is plain text; the message marks its match.
  await expect(
    panel(page).getByRole("option", { name: /Mara Harborne/ }),
  ).toHaveAttribute("aria-disabled", "true");
  await expect(
    panel(page)
      .getByRole("option", { name: /Harbor delivery/ })
      .locator("mark"),
  ).toHaveText("Harbor");
  await expect(
    panel(page).getByRole("link", {
      name: 'Show all results for "harbor"',
      exact: true,
    }),
  ).toHaveAttribute("href", "/platform?section=search&q=harbor");

  await page.keyboard.press("Escape");
  await expect(panel(page)).toBeHidden();
  await expect(searchButton(page)).toBeFocused();
  expect(page.url()).toBe(address);
  await expect(page.getByText("No notifications on this page.")).toBeVisible();
});

test("UF-C4.1 arrow keys move the active row across groups, and Enter opens the file in Files", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await installSearch(page);
  await openStart(page);
  await searchButton(page).click();
  await field(page).fill("harbor");
  const first = panel(page).getByRole("option", { name: /Harbor record 1/ });
  await expect(first).toHaveAttribute("aria-selected", "true");
  await expect(field(page)).toHaveAttribute(
    "aria-activedescendant",
    (await first.getAttribute("id")) ?? "",
  );
  // Up from the first row wraps to the last row that opens: the file.
  await page.keyboard.press("ArrowUp");
  const file = panel(page).getByRole("option", {
    name: /harbor-rate-card-2026\.pdf/,
  });
  await expect(file).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("ArrowDown");
  await expect(first).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("Enter");
  await expect(panel(page)).toBeHidden();
  await expect(page).toHaveURL(
    `/platform?section=files&department=${DEPARTMENT}&search=harbor-rate-card-2026.pdf`,
  );
});

test("UF-C4.1 Enter waits for the results of the words now typed and never opens a row of the previous words", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.clock.install();
  await installSearch(page);
  await openStart(page);
  const address = page.url();
  await searchButton(page).click();
  await field(page).fill("harbor");
  const first = panel(page).getByRole("option", { name: /Harbor record 1/ });
  await expect(first).toHaveAttribute("aria-selected", "true");
  // The rows of "harbor" stay on screen while "harbor rates" settles, but
  // they are not the answer to it, so Enter opens nothing.
  await page.clock.pauseAt(await page.evaluate(() => Date.now() + 1_000));
  await field(page).fill("harbor rates");
  await expect(field(page)).not.toHaveAttribute("aria-activedescendant");
  await page.keyboard.press("Enter");
  // A paused clock also pauses animation frames, so the check waits for the
  // new results instead: an Enter that opened a row has left the page by then.
  await page.clock.resume();
  await expect(first).toHaveAttribute("aria-selected", "true");
  await expect(panel(page)).toBeVisible();
  expect(page.url()).toBe(address);
});

test("UF-C4.4 Control+K is Switch conversation in OpenComms and opens the search panel on other pages", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await installCommsSearchApi(page);
  await page.goto("/comms");
  const switcher = page.getByRole("dialog", {
    name: "Switch conversation",
    exact: true,
  });
  await expect(
    page.getByRole("button", { name: /Switch conversation/ }),
  ).toBeVisible();
  await page.keyboard.press("Control+K");
  await expect(switcher).toBeVisible();
  await expect(panel(page)).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(switcher).toBeHidden();

  await openStart(page);
  await page.keyboard.press("Control+K");
  await expect(panel(page)).toBeVisible();
  await expect(field(page)).toBeFocused();
  await expect(switcher).toHaveCount(0);
});

test("UF-C4.4 Control+K does nothing while Use shortcuts is off", async ({
  page,
}) => {
  await page.route(
    `**/api/users/${defaultSignedInIdentity.id}/preferences`,
    (route) =>
      route.fulfill({
        headers: { "Cache-Control": "no-store" },
        json: {
          user_id: defaultSignedInIdentity.id,
          theme: "light",
          appearance: { motion: "system", keyboard_shortcuts: false },
        },
      }),
  );
  await installSearch(page);
  await openStart(page);
  await expect(searchButton(page)).not.toHaveAttribute("aria-keyshortcuts");
  // The button opens it; the panel code is then loaded.
  await searchButton(page).click();
  await expect(panel(page)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(panel(page)).toBeHidden();
  await page.keyboard.press("Control+K");
  await settleReact(page);
  await expect(panel(page)).toHaveCount(0);
});

test("UF-C4.1 each group fails alone with Try again and its reference, and a refused admission rechecks the session", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(() => {
    const counted = window as unknown as { rechecks: number };
    counted.rechecks = 0;
    window.addEventListener("slateops:session-recheck", () => {
      counted.rechecks += 1;
    });
  });
  let recordsFail = true;
  await installSearch(page, (kind, search) =>
    kind === "record" && recordsFail
      ? { status: 500, body: { detail: "Private database detail" } }
      : kind === "message" && search === "admission"
        ? {
            status: 403,
            body: {
              detail: {
                code: "mfa_required",
                message: "Two-step verification is required",
              },
            },
          }
        : harbor(kind),
  );
  await openStart(page);
  await searchButton(page).click();
  await field(page).fill("harbor");
  await expect(panel(page)).toContainText("Records could not be searched.");
  await expect(panel(page)).toContainText(answeredReference);
  await expect(panel(page)).not.toContainText("Private database detail");
  // The other groups still show.
  await expect(
    panel(page).getByRole("heading", { name: "Files · 1", exact: true }),
  ).toBeVisible();
  recordsFail = false;
  await panel(page)
    .getByRole("button", { name: "Try again", exact: true })
    .click();
  await expect(
    panel(page).getByRole("heading", { name: "Records · 1,000+", exact: true }),
  ).toBeVisible();
  await expect(panel(page)).not.toContainText("could not be searched.");

  await field(page).fill("admission");
  await expect(panel(page)).toContainText("Messages could not be searched.");
  await expect
    .poll(() =>
      page.evaluate(() => (window as unknown as { rechecks: number }).rechecks),
    )
    .toBeGreaterThan(0);
});

test("UF-C4.1 a new query cancels the previous reads, and nothing found reads as a plain sentence", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  let releaseOld = () => {};
  const held = new Promise<void>((resolve) => (releaseOld = resolve));
  await installSearch(page, async (kind, search) => {
    if (search === "old" && kind === "record") await held;
    return search === "old" ? harbor(kind) : { items: [] };
  });
  await openStart(page);
  await searchButton(page).click();
  const oldRead = page.waitForRequest(
    (request) =>
      request.url().includes("kind=record") &&
      request.url().includes("search=old"),
  );
  await field(page).fill("old");
  await oldRead;
  const cancelled = page.waitForEvent(
    "requestfailed",
    (request) =>
      request.url().includes("kind=record") &&
      request.url().includes("search=old"),
  );
  await field(page).fill("zzz");
  await cancelled;
  await expect(panel(page)).toContainText('Nothing matches "zzz".');
  await expect(panel(page)).toContainText(
    "Check the spelling, or try fewer words.",
  );
  await expect(panel(page).getByRole("heading", { level: 3 })).toHaveCount(0);
  releaseOld();
  await expect(panel(page).getByText("Harbor record 1")).toHaveCount(0);
});

test("UF-C4.1 on a phone the panel fills the screen with 44 px rows and Close at the top", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installSearch(page);
  await openStart(page);
  await searchButton(page).click();
  await field(page).fill("harbor");
  const option = panel(page).getByRole("option", { name: /Harbor record 1/ });
  await expect(option).toBeVisible();
  expect(await panel(page).boundingBox()).toEqual({
    x: 0,
    y: 0,
    width: 390,
    height: 844,
  });
  expect((await option.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  const close = panel(page).getByRole("button", { name: "Close", exact: true });
  const closeBox = await close.boundingBox();
  expect(closeBox?.y).toBeLessThan(60);
  expect(closeBox?.height).toBeGreaterThanOrEqual(44);
  await close.click();
  await expect(panel(page)).toBeHidden();
  await expect(searchButton(page)).toBeFocused();
});
