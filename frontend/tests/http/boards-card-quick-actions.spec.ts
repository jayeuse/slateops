import {
  authMeBody,
  expect,
  modalStatus,
  signedInAs,
  signedInSession,
  test,
  type Locator,
  type Page,
} from "./helpers/test";
import {
  installKanbanApi,
  kanbanHref,
  peopleIds,
  stageIds,
  wireCard,
} from "./helpers/board-kanban-api";
import { openedSheet } from "./helpers/settled";

// Two shortcuts in a writer's Kanban card sheet (candidates 4 and 8 of
// docs/specs/subtle-interactions.md): "Me (<name>)" first in the assignee
// picker (SI-4.2, SI-4.3, DR-SI-4.3, DR-SI-4.4), and "Today", "Tomorrow" and
// "Next Monday" under each date input (SI-8.1, SI-8.2, SI-8.4, DR-SI-8.1 to
// DR-SI-8.4). The mocked workspace's today is Friday 2026-09-25, so Tomorrow
// is 2026-09-26 and Next Monday 2026-09-28. The date rules are owned by
// tests/isolated/boards/quick-dates.spec.ts; the record form's "Me" by
// tests/http/record-person-me.spec.ts.

test.use({ trace: "off", screenshot: "off", video: "off" });

type KanbanApi = Awaited<ReturnType<typeof installKanbanApi>>;

const cardPatches = (api: KanbanApi) =>
  api.writes
    .filter(
      (write) => write.method === "PATCH" && /^\/cards\//.test(write.path),
    )
    .map((write) => write.body);

function documentScrollsAcross(page: Page) {
  return page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );
}

/** A quick date of one date row: the row's label is its description. */
function quickDate(sheet: Locator, name: string, row: "Start" | "Due") {
  return sheet.getByRole("button", { name, exact: true, description: row });
}

async function openCard(page: Page, cardId: string, title: string) {
  await page.goto(kanbanHref(`card=${cardId}`));
  return openedSheet(page.getByRole("dialog", { name: title, exact: true }));
}

test("SI-C8.1 a writer presses Tomorrow with the keyboard: one save, and after reload the due date is tomorrow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const renewal = wireCard("Renewal terms", stageIds.doing, 1024);
  const api = await installKanbanApi(page, {
    level: "write",
    cards: [renewal],
  });
  const sheet = await openCard(page, renewal.id, "Renewal terms");
  const tomorrow = quickDate(sheet, "Tomorrow", "Due");
  await tomorrow.focus();
  await page.keyboard.press("Enter");
  await expect(modalStatus(sheet)).toHaveText("Due saved.");
  expect(cardPatches(api)).toEqual([{ revision: 1, due_on: "2026-09-26" }]);
  // The keyboard stays on the pressed button through the save.
  await expect(tomorrow).toBeFocused();

  await page.reload();
  const reloaded = await openedSheet(
    page.getByRole("dialog", { name: "Renewal terms", exact: true }),
  );
  await expect(reloaded.getByLabel("Due", { exact: true })).toHaveValue(
    "2026-09-26",
  );
  await expect(reloaded.getByLabel("Start", { exact: true })).toHaveValue("");
});

test("SI-C8.3 Today on a card already due today sends nothing; the next pick saves once", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const renewal = wireCard("Renewal terms", stageIds.doing, 1024, {
    due_on: "2026-09-25",
  });
  const api = await installKanbanApi(page, {
    level: "write",
    cards: [renewal],
  });
  const sheet = await openCard(page, renewal.id, "Renewal terms");
  await quickDate(sheet, "Today", "Due").click();
  await quickDate(sheet, "Next Monday", "Due").click();
  await expect(modalStatus(sheet)).toHaveText("Due saved.");
  await expect(sheet.getByLabel("Due", { exact: true })).toHaveValue(
    "2026-09-28",
  );
  expect(cardPatches(api)).toEqual([{ revision: 1, due_on: "2026-09-28" }]);
});

test("SI-C8.1 a quick date pressed while a typed date is still in the input saves only the pressed date, once", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const renewal = wireCard("Renewal terms", stageIds.doing, 1024);
  const api = await installKanbanApi(page, {
    level: "write",
    cards: [renewal],
  });
  const sheet = await openCard(page, renewal.id, "Renewal terms");
  // Typed, not yet saved: no Enter, and the input keeps the focus.
  await sheet.getByLabel("Due", { exact: true }).fill("2026-10-30");
  await quickDate(sheet, "Tomorrow", "Due").click();
  await expect(modalStatus(sheet)).toHaveText("Due saved.");
  await expect(sheet.getByLabel("Due", { exact: true })).toHaveValue(
    "2026-09-26",
  );
  expect(cardPatches(api)).toEqual([{ revision: 1, due_on: "2026-09-26" }]);
});

test("SI-C8.5 at 390 px each date row shows its three quick dates in one line of 44 px targets, under the date input", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const renewal = wireCard("Renewal terms", stageIds.doing, 1024);
  await installKanbanApi(page, { level: "write", cards: [renewal] });
  const sheet = await openCard(page, renewal.id, "Renewal terms");
  for (const row of ["Start", "Due"] as const) {
    const input = sheet.getByLabel(row, { exact: true });
    await expect(input).toBeVisible();
    const inputBox = await input.boundingBox();
    const tops = new Set<number>();
    for (const name of ["Today", "Tomorrow", "Next Monday"]) {
      const button = quickDate(sheet, name, row);
      await expect(button).toBeVisible();
      const box = await button.boundingBox();
      expect(box!.height).toBeGreaterThanOrEqual(44);
      expect(box!.y).toBeGreaterThanOrEqual(inputBox!.y + inputBox!.height);
      expect(box!.x + box!.width).toBeLessThanOrEqual(390);
      tops.add(Math.round(box!.y));
    }
    expect(tops.size).toBe(1);
  }
  expect(await documentScrollsAcross(page)).toBe(false);
});

test("SI-C4.2 at 390 px a writer picks Me first with the keyboard; it is not listed twice, and after reload the writer is the assignee", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const renewal = wireCard("Renewal terms", stageIds.doing, 1024);
  const api = await installKanbanApi(page, {
    level: "write",
    cards: [renewal],
  });
  // The writer is Ben Reyes, one of the board's readers.
  await signedInSession(page, peopleIds.ben);
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      json: authMeBody({
        id: peopleIds.ben,
        role: "member",
        display_name: "Ben Reyes",
        username: "ben.reyes",
      }),
    }),
  );
  const sheet = await openCard(page, renewal.id, "Renewal terms");
  const assignee = sheet.getByRole("combobox", {
    name: "Assignee",
    exact: true,
  });
  await assignee.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("option")).toHaveText([
    "Me (Ben Reyes)",
    "No one",
    "Ana Santos",
    "Carla Diaz",
  ]);
  const me = page.getByRole("option", { name: "Me (Ben Reyes)", exact: true });
  expect((await me.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await expect(
    page.getByRole("combobox", { name: "Search assignee", exact: true }),
  ).toBeFocused();
  // The list opens on the current choice, "No one"; Me is one up from it.
  await page.keyboard.press("ArrowUp");
  await page.keyboard.press("Enter");
  await expect(modalStatus(sheet)).toHaveText("Assignee saved.");
  expect(cardPatches(api)).toEqual([
    { revision: 1, assignee_id: peopleIds.ben },
  ]);

  await page.reload();
  const reloaded = await openedSheet(
    page.getByRole("dialog", { name: "Renewal terms", exact: true }),
  );
  await expect(
    reloaded.getByRole("combobox", { name: "Assignee", exact: true }),
  ).toContainText("Ben Reyes");
});

test("SI-C4.2 while a search is typed, Me shows only when the text matches the writer's name", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const renewal = wireCard("Renewal terms", stageIds.doing, 1024);
  await installKanbanApi(page, { level: "write", cards: [renewal] });
  // The default writer, signed_in_person, can read the board but is not on
  // the people page the mock returns: Me still comes first (DR-SI-4.3).
  const sheet = await openCard(page, renewal.id, "Renewal terms");
  await sheet.getByRole("combobox", { name: "Assignee", exact: true }).click();
  const options = page.getByRole("option");
  await expect(options).toHaveText([
    "Me (signed_in_person)",
    "No one",
    "Ana Santos",
    "Ben Reyes",
    "Carla Diaz",
  ]);
  const search = page.getByRole("combobox", {
    name: "Search assignee",
    exact: true,
  });
  await search.fill("car");
  await expect(options).toHaveText(["Carla Diaz"]);
  await search.fill("SIGNED");
  await expect(options).toHaveText(["Me (signed_in_person)"]);
});

for (const who of [
  { name: "reader", role: "member" },
  { name: "guest", role: "guest" },
] as const)
  test(`SI-C4.4 SI-C8.4 a board ${who.name} sees the assignee and dates as text, with no picker and no quick dates`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const renewal = wireCard("Renewal terms", stageIds.doing, 1024, {
      assignee_id: peopleIds.ana,
      due_on: "2026-09-25",
    });
    await installKanbanApi(page, { level: "read", cards: [renewal] });
    await signedInAs(page, { id: peopleIds.carla, role: who.role });
    const sheet = await openCard(page, renewal.id, "Renewal terms");
    // The due date reads as text; the assignee row has no picker.
    await expect(sheet.getByText("Sep 25", { exact: true })).toBeVisible();
    await expect(sheet.getByText("Assignee", { exact: true })).toBeVisible();
    await expect(sheet.getByRole("combobox")).toHaveCount(0);
    await expect(sheet.getByRole("option")).toHaveCount(0);
    for (const name of ["Today", "Tomorrow", "Next Monday"])
      await expect(
        sheet.getByRole("button", { name, exact: true }),
      ).toHaveCount(0);
  });
