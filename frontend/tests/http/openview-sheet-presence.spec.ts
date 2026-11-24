import {
  defaultOrganization,
  expect,
  signedInAs,
  test,
  type Page,
} from "./helpers/test";
import {
  installSheetPageApi,
  sheetPeople,
  sheetPlace,
  wireSheetDetail,
  wireSheetRow,
  wireSheetSummary,
} from "./helpers/openview-sheets-api";
import { installSheetPresenceApi } from "./helpers/sheet-presence-api";

// docs/specs/sheets.md PR1-PR6, D13 (SH-63 to SH-66): who has the sheet open
// now. Avatars in the header, each person's cell outlined in their colour,
// only a cell position sent, and the channel left when the person leaves.

const sheetId = "00000000-0000-4000-8000-0000000009d1";
const recordId = "00000000-0000-4000-8000-0000000009d2";
const person = (n: number) =>
  `00000000-0000-4000-8000-${String(990000 + n).padStart(12, "0")}`;
const people = [
  { id: sheetPeople.colleague.id, name: sheetPeople.colleague.name },
  { id: person(1), name: "Carmela Reyes" },
  { id: person(2), name: "Dino Santos" },
  { id: person(3), name: "Elena Cruz" },
  { id: person(4), name: "Felix Tan" },
  { id: person(5), name: "Gina Lopez" },
];
const stranger = person(9);

const reader = {
  id: sheetPeople.viewer.id,
  role: "member",
  access: [
    { department_id: sheetPlace.department, module_id: null, level: "read" },
  ],
} as const;

function sheet() {
  const summary = wireSheetSummary(sheetId, "Class roster", {
    recordId,
    recordTitle: "Ana Cruz",
    moduleName: "Contacts",
    owner: "viewer",
    level: "owner",
    rows: 5,
  });
  return {
    detail: {
      ...wireSheetDetail(summary),
      structure: {
        structureVersion: 1,
        nextColumnSeq: 4,
        columns: [
          { key: "c1", name: "Student", type: "text" },
          { key: "c2", name: "Quiz 1", type: "int" },
          { key: "c3", name: "Remarks", type: "text" },
        ],
        groups: [],
        totals: {},
      },
    },
    rows: Array.from({ length: 5 }, (_, index) =>
      wireSheetRow(index, {
        c1: { value: `Student ${index + 1}` },
        c2: { value: index * 3 },
        c3: { value: "On track" },
      }),
    ),
    totals: {},
  };
}

async function openSheet(
  page: Page,
  options: { status?: number; viewers?: string[] } = {},
) {
  await signedInAs(page, reader);
  await installSheetPageApi(page, sheet());
  const names = new Map(people.map((entry) => [entry.id, entry.name]));
  await page.route("**/api/users/*/card", (route) => {
    const id = new URL(route.request().url()).pathname.split("/")[3];
    return route.fulfill({
      headers: { "Cache-Control": "private, no-store" },
      json: {
        display_name: names.get(id) ?? "Someone",
        job_title: null,
        avatar_url: null,
        email: null,
        phone: null,
        bio: null,
      },
    });
  });
  const presence = await installSheetPresenceApi(page, {
    sheetId,
    viewers: options.viewers ?? [reader.id, ...people.map((entry) => entry.id)],
    status: options.status,
  });
  return presence;
}

const cell = (page: Page, index: number, key: string) =>
  page
    .getByRole("grid", { name: "Class roster" })
    .locator(`[data-cell="${index}:${key}"]`);

/** Whether a cell carries a person's outline (an inset ring). */
const outline = (page: Page, index: number, key: string) =>
  cell(page, index, key).evaluate((element) =>
    getComputedStyle(element).boxShadow.includes("inset")
      ? "outlined"
      : "plain",
  );

test("people on the sheet show in the header, each cell they are on is outlined, and only a position is sent", async ({
  page,
}) => {
  const presence = await openSheet(page);
  presence.present = {
    [people[0].id]: { row_id: wireSheetRow(1, {}).id, column_key: "c2" },
    ...Object.fromEntries(
      people
        .slice(1)
        .map((entry) => [entry.id, { row_id: null, column_key: null }]),
    ),
    // Not one of the token's viewers: never shown.
    [stranger]: { row_id: wireSheetRow(0, {}).id, column_key: "c1" },
  };
  await page.goto(`/openview?sheet=${sheetId}`);

  const here = page.getByRole("group", { name: "On this sheet now" });
  // Four avatars, then "+2" for the rest.
  await expect(here.getByRole("button")).toHaveCount(5);
  await expect(
    here.getByRole("button", { name: "Bernard Ocampo", exact: true }),
  ).toBeVisible();
  await expect(
    here.getByRole("button", { name: "2 more: Felix Tan, Gina Lopez" }),
  ).toHaveText("+2");
  await here.getByRole("button", { name: "Bernard Ocampo" }).focus();
  await expect(page.locator('[data-slot="tooltip-content"]')).toHaveText(
    "Bernard Ocampo",
  );

  await expect.poll(() => outline(page, 1, "c2")).toBe("outlined");
  expect(await outline(page, 0, "c1")).toBe("plain");

  // This person's own cell goes out as its row id and column key.
  await cell(page, 2, "c3").click();
  await expect
    .poll(() => presence.tracked().at(-1))
    .toEqual({ row_id: wireSheetRow(2, {}).id, column_key: "c3" });
  // Nothing but a position ever goes out.
  for (const sent of presence.tracked())
    expect(Object.keys(sent as object).sort()).toEqual([
      "column_key",
      "row_id",
    ]);

  // Bernard moves on; his outline follows.
  presence.present[people[0].id] = {
    row_id: wireSheetRow(3, {}).id,
    column_key: "c1",
  };
  presence.sync();
  await expect.poll(() => outline(page, 3, "c1")).toBe("outlined");
  expect(await outline(page, 1, "c2")).toBe("plain");
});

test("leaving the sheet leaves its channel, and a tab hidden past the grace period leaves until it is shown", async ({
  page,
}) => {
  await page.clock.install();
  const presence = await openSheet(page);
  presence.present = {
    [people[0].id]: { row_id: null, column_key: null },
  };
  await page.goto(`/openview?sheet=${sheetId}`);
  const here = page.getByRole("group", { name: "On this sheet now" });
  await expect(here.getByRole("button")).toHaveCount(1);
  expect(presence.opened).toBe(1);

  const visibility = (state: "hidden" | "visible") =>
    page.evaluate((value) => {
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        get: () => value,
      });
      document.dispatchEvent(new Event("visibilitychange"));
    }, state);
  // A short look away keeps the place.
  await visibility("hidden");
  await page.clock.runFor(10_000);
  await visibility("visible");
  await page.clock.runFor(25_000);
  expect(presence.closed).toBe(0);
  // A long one leaves; coming back joins again.
  await visibility("hidden");
  await page.clock.runFor(31_000);
  await expect.poll(() => presence.closed).toBe(1);
  await expect(here).toHaveCount(0);
  await visibility("visible");
  await expect.poll(() => presence.opened).toBe(2);
  await expect(here.getByRole("button")).toHaveCount(1);

  await page.getByRole("link", { name: "My sheets" }).first().click();
  await expect.poll(() => presence.closed).toBe(2);
});

test("a tab opened in the background leaves after the grace period", async ({
  page,
}) => {
  await page.clock.install();
  await page.addInitScript(() =>
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "hidden",
    }),
  );
  const presence = await openSheet(page);
  await page.goto(`/openview?sheet=${sheetId}`);
  await expect.poll(() => presence.opened).toBe(1);
  await page.clock.runFor(31_000);
  await expect.poll(() => presence.closed).toBe(1);
});

test("signing out leaves the sheet's channel with the rest of the account's connections", async ({
  page,
}) => {
  const presence = await openSheet(page);
  presence.present = {
    [people[0].id]: { row_id: null, column_key: null },
  };
  let signedOut = false;
  await page.route("**/api/auth/logout", (route) => {
    signedOut = true;
    return route.fulfill({ status: 204 });
  });
  await page.route("**/api/auth/session", (route) =>
    route.fulfill({
      json: signedOut
        ? { authenticated: false }
        : {
            authenticated: true,
            user_id: reader.id,
            organization_id: defaultOrganization.org_id,
            default_organization_blocked: null,
            setup_required: false,
          },
    }),
  );
  await page.goto(`/openview?sheet=${sheetId}`);
  const here = page.getByRole("group", { name: "On this sheet now" });
  await expect(here.getByRole("button")).toHaveCount(1);
  await page.getByRole("button", { name: "Account", exact: true }).click();
  await page.getByRole("menuitem", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect.poll(() => presence.closed).toBe(1);
  expect(presence.opened).toBe(1);
});

test("a sheet the token route refuses opens no channel and shows no one", async ({
  page,
}) => {
  const presence = await openSheet(page, { status: 404 });
  await page.goto(`/openview?sheet=${sheetId}`);
  await expect(cell(page, 0, "c1")).toBeVisible();
  await expect.poll(() => presence.tokens).toBe(1);
  await expect(
    page.getByRole("group", { name: "On this sheet now" }),
  ).toHaveCount(0);
  expect(presence.opened).toBe(0);
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the header shows who is here, and no cell is outlined", async ({
    page,
  }) => {
    const presence = await openSheet(page);
    presence.present = {
      [people[0].id]: { row_id: wireSheetRow(0, {}).id, column_key: "c1" },
    };
    await page.goto(`/openview?sheet=${sheetId}`);
    const here = page.getByRole("group", { name: "On this sheet now" });
    await expect(
      here.getByRole("button", { name: "Bernard Ocampo" }),
    ).toBeVisible();
    await expect(cell(page, 0, "c1")).toBeVisible();
    expect(await outline(page, 0, "c1")).toBe("plain");
  });
});
