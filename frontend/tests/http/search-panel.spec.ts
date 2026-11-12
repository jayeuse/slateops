import type { Page } from "@playwright/test";
import {
  answeredHeaders,
  answeredReference,
  authMeBody,
  controlledSession,
  defaultOrganization,
  defaultSignedInIdentity,
  expect,
  settleReact,
  test,
} from "./helpers/test";
import { installCommsSearchApi } from "./helpers/comms-search-api";
import { installProfileApi } from "./helpers/profile-api";

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
  // A person the reader cannot open is plain text, not an option (DR-4.6);
  // the message marks its match.
  await expect(panel(page).getByText("Mara Harborne")).toBeVisible();
  await expect(
    panel(page).getByRole("option", { name: /Mara Harborne/ }),
  ).toHaveCount(0);
  await expect(
    panel(page)
      .getByRole("option", { name: /Harbor delivery/ })
      .locator("mark"),
  ).toHaveText("Harbor");
  await expect(
    panel(page).getByRole("link", {
      name: "Show all results for “harbor”",
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
  await expect(panel(page)).toContainText("Nothing matches “zzz”.");
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

// UF-C4.5 and DR-4.8: the Search page shows all results. "Show all results"
// opens it with the typed words in `q`; it seeds its field once and has a
// card for each of the six kinds.
const card = (page: Page, name: string) =>
  page.getByRole("region", { name: `${name} search results`, exact: true });
const pageField = (page: Page) =>
  page
    .getByRole("main")
    .getByRole("searchbox", { name: "Search workspace", exact: true });

test("UF-C4.5 a picked record opens its record, and Show all results opens the Search page with the words and their results", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await installSearch(page);
  await openStart(page);
  await searchButton(page).click();
  await field(page).fill("harbor");
  await panel(page)
    .getByRole("option", { name: /Harbor record 2/ })
    .click();
  await expect(panel(page)).toBeHidden();
  await expect(page).toHaveURL(
    `/openview?section=views&module=${MODULE}&record=${id("50", 2)}`,
  );

  await openStart(page);
  await searchButton(page).click();
  await field(page).fill("harbor");
  await panel(page)
    .getByRole("link", { name: "Show all results for “harbor”", exact: true })
    .click();
  await expect(page).toHaveURL("/platform?section=search&q=harbor");
  await expect(pageField(page)).toHaveValue("harbor");
  await expect(
    card(page, "Records").getByRole("link", { name: /Harbor record 1/ }),
  ).toBeVisible();
});

test("UF-C4.5 the Search page seeds its field from q once, and an address without q opens empty", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const reads = await installSearch(page);
  await page.goto("/platform?section=search&q=harbor");
  await expect(pageField(page)).toHaveValue("harbor");
  await expect(
    card(page, "Files").getByRole("link", { name: /harbor-rate-card/ }),
  ).toBeVisible();
  expect(
    reads.every(
      (url) =>
        (url.searchParams.get("search") ?? url.searchParams.get("q")) ===
        "harbor",
    ),
  ).toBe(true);
  // Editing the words does not bring the address's words back.
  await pageField(page).fill("harbor rates");
  await expect(
    card(page, "Records").getByRole("link", { name: /Harbor record 1/ }),
  ).toBeVisible();
  await expect
    .poll(() =>
      reads.some((url) => url.searchParams.get("search") === "harbor rates"),
    )
    .toBe(true);
  await expect(pageField(page)).toHaveValue("harbor rates");

  const before = reads.length;
  await page.goto("/platform?section=search");
  await expect(pageField(page)).toHaveValue("");
  await expect(card(page, "Records")).toContainText(
    "Enter a search to find records.",
  );
  await expect(card(page, "Messages")).toContainText(
    "Enter a search to find messages.",
  );
  expect(reads).toHaveLength(before);
});

test("UF-C4.5 Messages and Files cards list their rows with totals, open their pages, and each fails alone", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  let messagesFail = true;
  const reads = await installSearch(page, (kind) =>
    kind === "message" && messagesFail
      ? { status: 500, body: { detail: "Private database detail" } }
      : harbor(kind),
  );
  await page.goto("/platform?section=search&q=harbor");
  const files = card(page, "Files");
  await expect(
    files.getByRole("link", { name: /harbor-rate-card-2026\.pdf/ }),
  ).toHaveAttribute(
    "href",
    `/platform?section=files&department=${DEPARTMENT}&search=harbor-rate-card-2026.pdf`,
  );
  await expect(files).toContainText("1 result · showing 1");
  const messages = card(page, "Messages");
  await expect(messages.getByRole("alert")).toContainText(
    "Messages could not be searched.",
  );
  await expect(messages).toContainText(answeredReference);
  await expect(messages).not.toContainText("Private database detail");
  await expect(
    card(page, "Records").getByRole("link", { name: /Harbor record 1/ }),
  ).toBeVisible();
  messagesFail = false;
  await messages
    .getByRole("button", { name: "Try again", exact: true })
    .click();
  const message = messages.getByRole("link", { name: /Harbor delivery/ });
  await expect(message).toHaveAttribute(
    "href",
    `/comms?conversation=${CONVERSATION}&message=${MESSAGE}`,
  );
  await expect(message.locator("mark")).toHaveText("Harbor");
  await expect(messages).toContainText("sales-desk · Ana Cruz");
  expect(
    reads.some(
      (url) =>
        url.pathname === "/api/comms/search" &&
        url.searchParams.get("q") === "harbor" &&
        url.searchParams.get("limit") === "10",
    ),
  ).toBe(true);
  await expect(pageField(page)).toHaveAttribute(
    "placeholder",
    "Search records, people, posts, events, messages, and files…",
  );
});

test("UF-C4.5 with no organization in the session the Search page shows five cards and no Messages card", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  // A session that names no organization leaves the workspace scope empty,
  // so messages cannot be bound to one: the card does not show (P3-F2
  // decision 2b, the panel's rule for its Messages group).
  await page.route("**/api/auth/session", (route) =>
    route.fulfill({
      json: {
        authenticated: true,
        user_id: defaultSignedInIdentity.id,
        default_organization_blocked: null,
        setup_required: false,
      },
    }),
  );
  await installSearch(page);
  await page.goto("/platform?section=search&q=harbor");
  await expect(
    card(page, "Files").getByRole("link", { name: /harbor-rate-card/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: /search results$/ }),
  ).toHaveCount(5);
  await expect(card(page, "Messages")).toHaveCount(0);
  await expect(page.getByText("Searching messages…")).toHaveCount(0);
});

// Security review S3-3: the guards of the panel that the journeys above do
// not reach.

test("FX-S3-1 Control+K does not open the search panel while another dialog is open", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await installSearch(page);
  await openStart(page);
  // Load the panel once, so a wrong open would show at once.
  await searchButton(page).click();
  await expect(panel(page)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(panel(page)).toBeHidden();
  await header(page).getByRole("button", { name: "Help", exact: true }).click();
  const help = page.getByRole("dialog", { name: "Help", exact: true });
  await expect(help).toBeVisible();
  await page.keyboard.press("Control+K");
  await settleReact(page);
  await expect(panel(page)).toHaveCount(0);
  await expect(help).toBeVisible();
});

test("FX-S3-1 Control+K does not open the search panel while a confirmation is open", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await installProfileApi(page);
  await page.route("**/api/auth/sessions", (route) =>
    route.fulfill({
      json: [true, false].map((current, index) => ({
        id: `00000000-0000-4000-8000-00000000080${index + 1}`,
        created_at: "2026-10-01T00:00:00Z",
        refreshed_at: "2026-10-01T00:00:00Z",
        expires_at: "2099-10-01T00:00:00Z",
        user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128.0",
        ip_address: "10.0.4.21",
        current,
      })),
    }),
  );
  await installSearch(page);
  await page.goto("/settings");
  // The shell, with its Search button and Control+K, is on this page.
  await expect(searchButton(page)).toBeVisible();
  // Load the panel once, so a wrong open would show at once.
  await searchButton(page).click();
  await expect(panel(page)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(panel(page)).toBeHidden();
  await page
    .getByRole("region", { name: "Settings", exact: true })
    .getByRole("button", { name: "Sign out other sessions" })
    .click();
  const confirm = page.getByRole("alertdialog", {
    name: "Sign out other sessions?",
  });
  await expect(confirm).toBeVisible();
  await page.keyboard.press("Control+K");
  await settleReact(page);
  await expect(panel(page)).toHaveCount(0);
  await expect(confirm).toBeVisible();
});

test("FX-S3-2 a change of account closes the open panel, and its results do not come back", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const next = "00000000-0000-4000-8000-000000000301";
  const session = await controlledSession(page, {
    id: defaultSignedInIdentity.id,
    role: "admin",
  });
  // The next account's reads wait, so any row shown meanwhile is old data.
  let releaseNext = () => {};
  const nextHeld = new Promise<void>((resolve) => (releaseNext = resolve));
  await installSearch(page, async (kind) => {
    if (session.identity.id === next) {
      await nextHeld;
      return { items: [] };
    }
    return harbor(kind);
  });
  await openStart(page);
  await searchButton(page).click();
  await field(page).fill("harbor");
  await expect(
    panel(page).getByRole("option", { name: /Harbor record 1/ }),
  ).toBeVisible();
  // Another account signs in to this browser; the next session check sees it.
  session.identity = { id: next, role: "admin" };
  const checked = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/auth/session",
  );
  await page.evaluate(() =>
    window.dispatchEvent(new Event("slateops:session-recheck")),
  );
  await checked;
  await expect(searchButton(page)).toBeEnabled();
  await settleReact(page, 5);
  await expect(panel(page)).toHaveCount(0);
  await expect(page.getByText("Harbor record 1")).toHaveCount(0);
  await searchButton(page).click();
  await expect(field(page)).toHaveValue("");
  const nextRead = page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname === "/api/search" &&
      session.identity.id === next,
  );
  await field(page).fill("harbor");
  // The reads wait: the panel shows its loading rows, not old results.
  await expect(panel(page).getByText("Searching records…")).toBeAttached();
  await expect(panel(page).getByRole("option")).toHaveCount(0);
  await nextRead;
  releaseNext();
  await expect(panel(page)).toContainText("Nothing matches “harbor”.");
});

test("FX-S3-2 after a change of organization the panel opens empty and shows only the new organization's results", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const other = {
    org_id: "00000000-0000-4000-8000-000000000202",
    name: "Other organization",
    slug: "other",
    role: "admin" as const,
  };
  const home = { ...defaultOrganization, role: "admin" as const };
  await page.route("**/api/auth/me", (route) => {
    const tab = route.request().headers()["x-org"];
    const current = tab === other.org_id ? other : home;
    return route.fulfill({
      json: authMeBody({
        id: defaultSignedInIdentity.id,
        role: "admin",
        memberships: [home, other],
        current_organization: { ...current, access: [] },
      }),
    });
  });
  await page.route("**/api/auth/session/organization", (route) =>
    route.fulfill({
      json: authMeBody({
        id: defaultSignedInIdentity.id,
        role: "admin",
        memberships: [home, other],
        current_organization: { ...other, access: [] },
      }),
    }),
  );
  let releaseOther = () => {};
  const otherHeld = new Promise<void>((resolve) => (releaseOther = resolve));
  // The other organization has no match for "harbor".
  await installSearch(page, (kind) => harbor(kind));
  await page.route(
    (url) =>
      url.pathname === "/api/search" || url.pathname === "/api/comms/search",
    async (route) => {
      if (route.request().headers()["x-org"] !== other.org_id)
        return route.fallback();
      // The other organization's reads wait, so any row shown meanwhile is
      // the first organization's data.
      await otherHeld;
      return route
        .fulfill({
          json: {
            items: [],
            pagination: {
              limit: Number(
                new URL(route.request().url()).searchParams.get("limit"),
              ),
              offset: 0,
              count: 0,
              total: 0,
              has_more: false,
              total_is_capped: false,
            },
          },
        })
        .catch(() => undefined);
    },
  );
  await openStart(page);
  await searchButton(page).click();
  await field(page).fill("harbor");
  await expect(
    panel(page).getByRole("option", { name: /Harbor record 1/ }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", {
      name: "Organization: Slate Operations",
      exact: true,
    })
    .click();
  const switched = page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname === "/api/auth/session/organization",
  );
  await page.getByRole("menuitem", { name: /Other organization/ }).click();
  expect((await switched).postDataJSON()).toEqual({ org_id: other.org_id });
  // The switch opens the workspace home of the other organization.
  await expect(page).toHaveURL(/\/openview/);
  await searchButton(page).click();
  await expect(field(page)).toHaveValue("");
  await expect(panel(page).getByRole("option")).toHaveCount(0);
  const otherRead = page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname === "/api/search" &&
      request.headers()["x-org"] === other.org_id,
  );
  await field(page).fill("harbor");
  // The reads wait: the panel shows its loading rows, not old results.
  await expect(panel(page).getByText("Searching records…")).toBeAttached();
  await expect(panel(page).getByRole("option")).toHaveCount(0);
  await otherRead;
  await expect(panel(page).getByText("Harbor record 1")).toHaveCount(0);
  releaseOther();
  await expect(panel(page)).toContainText("Nothing matches “harbor”.");
});

test("FX-S3-3 a file name with & # and markup stays one search value and shows as text", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const name = "a&search=x#y<b>.pdf";
  await installSearch(page, (kind) =>
    kind === "file"
      ? {
          items: [
            item("file", 31, {
              title: name,
              context_label: "Sales",
              department_id: DEPARTMENT,
            }),
          ],
        }
      : { items: [] },
  );
  await openStart(page);
  await searchButton(page).click();
  await field(page).fill("search");
  const row = panel(page).getByRole("option", { name: /a&search=x#y<b>\.pdf/ });
  await expect(row).toContainText(name);
  await expect(row.locator("b")).toHaveCount(0);

  await page.goto("/platform?section=search&q=search");
  const link = card(page, "Files").getByRole("link", {
    name: /a&search=x#y<b>\.pdf/,
  });
  await expect(link).toContainText(name);
  await expect(link.locator("b")).toHaveCount(0);
  const href = new URL((await link.getAttribute("href")) ?? "", "http://x");
  expect(href.searchParams.getAll("search")).toEqual([name]);
  expect(href.hash).toBe("");
});

// PR3 screen review (docs/specs/ux-friction-pass.md DR-4.2, DR-4.6, DR-4.8).

test("FX-SR-1 the field row shows a 2 px focus line inside the panel while the field has focus", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await installSearch(page);
  await openStart(page);
  await searchButton(page).click();
  await expect(field(page)).toBeFocused();
  const line = () =>
    field(page).evaluate((input) => {
      const row = input.parentElement as HTMLElement;
      const after = getComputedStyle(row, "::after");
      const probe = document.createElement("span");
      probe.style.color = "var(--ring)";
      row.append(probe);
      const ring = getComputedStyle(probe).color;
      probe.remove();
      const panel = row.closest('[role="dialog"]') as HTMLElement;
      return {
        color: after.backgroundColor,
        ring,
        height: after.height,
        bottom: after.bottom,
        inside:
          row.getBoundingClientRect().bottom <=
          panel.getBoundingClientRect().bottom,
      };
    });
  // The line: the focus colour, 2 px high, at the bottom of the row, inside
  // the panel.
  const focused = await line();
  expect(focused.color).toBe(focused.ring);
  expect(focused.height).toBe("2px");
  expect(focused.bottom).toBe("0px");
  expect(focused.inside).toBe(true);
  // Close has its own focus ring; the line shows only for the field.
  await page.keyboard.press("Tab");
  await expect(
    panel(page).getByRole("button", { name: "Close", exact: true }),
  ).toBeFocused();
  expect((await line()).color).toBe("rgba(0, 0, 0, 0)");
});

test("FX-SR-2 pointer hover moves the active row, so only one row is highlighted", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await installSearch(page);
  await openStart(page);
  await searchButton(page).click();
  await field(page).fill("harbor");
  const first = panel(page).getByRole("option", { name: /Harbor record 1/ });
  const third = panel(page).getByRole("option", { name: /Harbor record 3/ });
  await expect(first).toHaveAttribute("aria-selected", "true");
  await third.hover();
  await expect(third).toHaveAttribute("aria-selected", "true");
  await expect(first).toHaveAttribute("aria-selected", "false");
  await expect(field(page)).toHaveAttribute(
    "aria-activedescendant",
    (await third.getAttribute("id")) ?? "",
  );
  // One highlighted row: the active one.
  const highlighted = await panel(page)
    .getByRole("option")
    .evaluateAll(
      (rows) =>
        rows.filter(
          (row) => getComputedStyle(row).backgroundColor !== "rgba(0, 0, 0, 0)",
        ).length,
    );
  expect(highlighted).toBe(1);
  // Enter opens the row under the pointer.
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(
    `/openview?section=views&module=${MODULE}&record=${id("50", 3)}`,
  );
});

test("FX-SR-5 the Search page lays out all six cards in its first frame", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  // Count the cards when the first card enters the page, before any read
  // answers, so a card that arrives later shows as a shift.
  await page.addInitScript(() => {
    const seen = window as unknown as { firstCards?: number };
    new MutationObserver((_, observer) => {
      const cards = document.querySelectorAll(
        'section[aria-label$=" search results"]',
      ).length;
      if (!cards) return;
      seen.firstCards = cards;
      observer.disconnect();
    }).observe(document, { childList: true, subtree: true });
  });
  await installSearch(page);
  await page.goto("/platform?section=search&q=harbor");
  await expect(card(page, "Messages")).toBeVisible();
  expect(
    await page.evaluate(
      () => (window as unknown as { firstCards?: number }).firstCards,
    ),
  ).toBe(6);
});

test("FX-SR-7 the Search page writes the settled words to q with replace, and an empty field removes it", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await installSearch(page);
  await page.goto("/platform?section=search&q=harbor");
  await expect(pageField(page)).toHaveValue("harbor");
  const entries = await page.evaluate(() => history.length);
  await pageField(page).fill("harbor rates");
  await expect(page).toHaveURL("/platform?section=search&q=harbor+rates");
  // The written q does not fill the field again over later typing.
  await pageField(page).pressSequentially(" card");
  await expect(page).toHaveURL("/platform?section=search&q=harbor+rates+card");
  await expect(pageField(page)).toHaveValue("harbor rates card");
  expect(await page.evaluate(() => history.length)).toBe(entries);
  await page.reload();
  await expect(pageField(page)).toHaveValue("harbor rates card");
  await pageField(page).fill("");
  await expect(page).toHaveURL("/platform?section=search");
});

// FX-SR-8 (parent decision (a)): one account's or organization's search
// words never carry to the next. The address keeps `q` across an account
// change in the tab, or comes back with Back after an organization change;
// the Search page then opens empty, removes `q`, and reads nothing with the
// old words.
async function installTwoOrganizations(page: Page) {
  const other = {
    org_id: "00000000-0000-4000-8000-000000000202",
    name: "Other organization",
    slug: "other",
    role: "admin" as const,
  };
  const home = { ...defaultOrganization, role: "admin" as const };
  const identity = (current: typeof home | typeof other) =>
    authMeBody({
      id: defaultSignedInIdentity.id,
      role: "admin",
      memberships: [home, other],
      current_organization: { ...current, access: [] },
    });
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      json: identity(
        route.request().headers()["x-org"] === other.org_id ? other : home,
      ),
    }),
  );
  await page.route("**/api/auth/session/organization", (route) =>
    route.fulfill({ json: identity(other) }),
  );
  return other;
}

async function switchOrganization(page: Page) {
  await page
    .getByRole("button", {
      name: "Organization: Slate Operations",
      exact: true,
    })
    .click();
  await page.getByRole("menuitem", { name: /Other organization/ }).click();
  await expect(page).toHaveURL(/\/openview/);
}

test("FX-SR-8 after an account change the Search page drops the previous account's q and reads nothing with it", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const session = await controlledSession(page, {
    id: defaultSignedInIdentity.id,
    role: "admin",
  });
  const reads = await installSearch(page);
  await page.goto("/platform?section=search&q=harbor");
  await expect(pageField(page)).toHaveValue("harbor");
  await expect(
    card(page, "Records").getByRole("link", { name: /Harbor record 1/ }),
  ).toBeVisible();
  const entries = await page.evaluate(() => history.length);
  const before = reads.length;
  session.identity = {
    id: "00000000-0000-4000-8000-000000000301",
    role: "admin",
  };
  await page.evaluate(() =>
    window.dispatchEvent(new Event("slateops:session-recheck")),
  );
  await expect(page).toHaveURL("/platform?section=search");
  await expect(pageField(page)).toHaveValue("");
  await expect(card(page, "Records")).toContainText(
    "Enter a search to find records.",
  );
  expect(await page.evaluate(() => history.length)).toBe(entries);
  expect(reads.slice(before)).toEqual([]);
});

test("FX-SR-8 after an organization change the Search page drops the previous organization's q and reads nothing with it", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const other = await installTwoOrganizations(page);
  const reads = await installSearch(page);
  const otherReads: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (
      (url.pathname === "/api/search" ||
        url.pathname === "/api/comms/search") &&
      request.headers()["x-org"] === other.org_id
    )
      otherReads.push(url.href);
  });
  await page.goto("/platform?section=search&q=harbor");
  await expect(pageField(page)).toHaveValue("harbor");
  await expect(
    card(page, "Records").getByRole("link", { name: /Harbor record 1/ }),
  ).toBeVisible();
  await switchOrganization(page);
  // Back brings the address with the first organization's words.
  await page.goBack();
  await expect(page).toHaveURL("/platform?section=search");
  await expect(pageField(page)).toHaveValue("");
  await expect(card(page, "Records")).toContainText(
    "Enter a search to find records.",
  );
  expect(otherReads).toEqual([]);
  expect(reads.length).toBeGreaterThan(0);
});
