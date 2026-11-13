import {
  answeredReference,
  expect,
  test,
  type Locator,
  type Page,
} from "./helpers/test";
import {
  installListApi,
  listIds,
  recordId,
  type Viewer,
} from "./helpers/openview-list-api";

// List actions of the OpenView table (candidates 1 and 5 of
// docs/specs/subtle-interactions.md): a Choice value's menu ("Show only",
// "Change <Field> to"), row selection with the selection bar, and the page
// status with Undo. The rules (when "Show only" is offered, which rows a
// change sends, the words) are owned by
// tests/isolated/openview/record-batch-change.spec.ts; these journeys prove
// the page, the requests, and one example of each refusal.

const contacts = `/openview?section=views&module=${listIds.module}&view=${listIds.view}`;

const table = (page: Page) => page.getByRole("table");
const row = (page: Page, name: string) =>
  table(page).getByRole("row").filter({ hasText: name });
/** The page meta line under the title (G7). */
const metaLine = (page: Page) =>
  page
    .getByRole("heading", { level: 1 })
    .locator("xpath=following-sibling::p[1]");
const pageStatus = (page: Page) => metaLine(page).getByRole("status").first();
const undo = (page: Page) =>
  metaLine(page).getByRole("button", { name: "Undo", exact: true });
const statusValue = (scope: Page | Locator, value: string) =>
  scope.getByRole("button", { name: `Status: ${value}, options` });
const selectionBar = (page: Page) =>
  page.getByRole("toolbar", { name: "Selected records" });
const box = (page: Page, name: string) =>
  page.getByRole("checkbox", { name: `Select ${name}`, exact: true });

async function openContacts(page: Page) {
  await page.goto(contacts);
  await expect(row(page, "Ana Cruz")).toBeVisible();
}

const formerOnly = {
  field_id: listIds.status,
  expected_type: "select",
  operator: "eq",
  value: "former",
} as const;

for (const viewer of ["writer", "reader", "guest"] as const) {
  test(`SI-C1.1 and SI-C1.12: a ${viewer} shows only Former from a Status value, with no unsaved mark`, async ({
    page,
  }) => {
    const api = await installListApi(page, { viewer });
    await openContacts(page);

    await statusValue(row(page, "Ben Ortiz"), "Former").click();
    const menu = page.getByRole("menu");
    // SI-C1.12: readers and guests get only "Show only".
    await expect(menu.getByRole("menuitemradio")).toHaveCount(
      viewer === "writer" ? 3 : 0,
    );
    await menu.getByRole("menuitem", { name: "Show only Former" }).click();

    await expect(table(page).getByRole("row")).toHaveCount(3);
    await expect(row(page, "Ben Ortiz")).toBeVisible();
    await expect(row(page, "Eli Park")).toBeVisible();
    expect(api.state.queries.at(-1)?.filters).toEqual([formerOnly]);
    await expect(page).toHaveURL(/[?&]changes=/);
    // The quick-filter field: its strip shows the choice (SI-1.2).
    await expect(
      page
        .getByRole("group", { name: "Status" })
        .getByRole("button", { name: /^Former/ }),
    ).toHaveAttribute("aria-pressed", "true");
    await expect(
      page.getByText("Unsaved changes", { exact: true }),
    ).toHaveCount(0);
    expect(api.state.viewWrites).toEqual([]);
    expect(api.state.batches).toEqual([]);
  });
}

test("SI-C1.2: a click on another cell opens the record; the Status value opens its menu instead", async ({
  page,
}) => {
  await installListApi(page);
  await openContacts(page);

  await statusValue(row(page, "Chen Wu"), "Prospect").click();
  await expect(page.getByRole("menu")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(statusValue(row(page, "Chen Wu"), "Prospect")).toBeFocused();
  await expect(page).not.toHaveURL(/[?&]record=/);

  // A real click on the Paid cell, outside every control of the row; the
  // row's open button covers the cell, as on the page.
  const cell = await row(page, "Chen Wu")
    .getByRole("cell")
    .nth(3)
    .boundingBox();
  if (!cell) throw new Error("The Paid cell has no box");
  await page.mouse.click(cell.x + cell.width / 2, cell.y + cell.height / 2);
  await expect(page).toHaveURL(new RegExp(`[?&]record=${recordId(2)}`));
  await expect(
    page.getByRole("dialog", { name: "Record details" }),
  ).toBeVisible();
});

test("SI-C1.3: a department manager's Show only marks Unsaved changes and offers Save view", async ({
  page,
}) => {
  await installListApi(page, { viewer: "manager" });
  await openContacts(page);
  await statusValue(row(page, "Ben Ortiz"), "Former").click();
  await page.getByRole("menuitem", { name: "Show only Former" }).click();
  await expect(table(page).getByRole("row")).toHaveCount(3);
  await expect(
    page.getByText("Unsaved changes", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Save view", exact: true }),
  ).toBeVisible();
});

test("SI-C1.4: browser Back after Show only lists every record again", async ({
  page,
}) => {
  const api = await installListApi(page);
  await openContacts(page);
  await statusValue(row(page, "Ben Ortiz"), "Former").click();
  await page.getByRole("menuitem", { name: "Show only Former" }).click();
  await expect(table(page).getByRole("row")).toHaveCount(3);
  await expect(page).toHaveURL(/[?&]changes=/);
  await page.goBack();

  await expect(table(page).getByRole("row")).toHaveCount(13);
  await expect(page).not.toHaveURL(/[?&]changes=/);
  await expect(page).toHaveURL(new RegExp(`module=${listIds.module}`));
  expect(api.state.queries.at(-1)?.filters).toEqual([]);
});

test("SI-C1.6: on a phone the status chip opens its menu by tap and by keyboard, and the row still opens the record", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installListApi(page);
  await page.goto(contacts);
  const rows = page.getByRole("list", { name: "Records" });
  const chip = statusValue(
    rows.getByRole("listitem").filter({ hasText: "Ben Ortiz" }),
    "Former",
  );
  await chip.click();
  await expect(
    page.getByRole("menuitem", { name: "Show only Former" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(chip).toBeFocused();
  expect((await chip.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);

  const other = statusValue(
    rows.getByRole("listitem").filter({ hasText: "Ana Cruz" }),
    "Active",
  );
  await other.focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("menuitem", { name: "Show only Active" }),
  ).toBeVisible();
  await page.keyboard.press("Escape");

  await rows.getByRole("button", { name: "Chen Wu" }).click();
  await expect(page).toHaveURL(new RegExp(`[?&]record=${recordId(2)}`));
});

test("SI-C1.7 and SI-C1.8: a writer changes Status from the list with one item, and Undo sends the previous value with the returned revision", async ({
  page,
}) => {
  const api = await installListApi(page, {
    filters: [{ ...formerOnly, value: "active" }],
  });
  await openContacts(page);

  await statusValue(row(page, "Ana Cruz"), "Active").click();
  await page
    .getByRole("group", { name: "Change Status to" })
    .getByRole("menuitemradio", { name: "Former" })
    .click();

  await expect(pageStatus(page)).toHaveText("Status changed to Former.");
  expect(api.state.batches).toEqual([
    {
      module_id: listIds.module,
      items: [
        {
          record_id: recordId(0),
          revision: "2026-11-13T08:00:00Z",
          field_id: listIds.status,
          value: "former",
        },
      ],
    },
  ]);
  expect(api.stored(0)?.[listIds.status]).toBe("former");
  // The record no longer matches "Status is Active": the next read drops
  // it, and Undo stays offered (DR-SI-1.7).
  await expect(row(page, "Ana Cruz")).toHaveCount(0);
  await expect(undo(page)).toBeVisible();
  await expect(page).not.toHaveURL(/[?&]record=/);

  await undo(page).click();

  await expect(pageStatus(page)).toHaveText("Status changed back to Active.");
  expect(api.state.batches[1]?.items).toEqual([
    {
      record_id: recordId(0),
      revision: "2026-11-13T10:01:00Z",
      field_id: listIds.status,
      value: "active",
    },
  ]);
  expect(api.stored(0)?.[listIds.status]).toBe("active");
  await expect(undo(page)).toHaveCount(0);
  await expect(statusValue(row(page, "Ana Cruz"), "Active")).toBeVisible();
});

test("SI-C1.9: a change after someone else's is refused, shows their value and the reason, and overwrites nothing", async ({
  page,
}) => {
  const api = await installListApi(page);
  await openContacts(page);
  api.changeElsewhere(0, { [listIds.status]: "former" });

  await statusValue(row(page, "Ana Cruz"), "Active").click();
  await page.getByRole("menuitemradio", { name: "Prospect" }).click();

  await expect(pageStatus(page)).toHaveText(
    "Status not changed. Someone changed this record; it shows their value now.",
  );
  await expect(statusValue(row(page, "Ana Cruz"), "Former")).toBeVisible();
  await expect(undo(page)).toHaveCount(0);
  expect(api.stored(0)?.[listIds.status]).toBe("former");
});

test("SI-C1.10: Undo after someone changed the record again is refused and keeps their value", async ({
  page,
}) => {
  const api = await installListApi(page);
  await openContacts(page);
  await statusValue(row(page, "Ana Cruz"), "Active").click();
  await page.getByRole("menuitemradio", { name: "Former" }).click();
  await expect(pageStatus(page)).toHaveText("Status changed to Former.");
  api.changeElsewhere(0, { [listIds.status]: "prospect" });

  await undo(page).click();

  await expect(pageStatus(page)).toHaveText(
    "Not undone. Someone changed this record after you.",
  );
  await expect(undo(page)).toHaveCount(0);
  expect(api.stored(0)?.[listIds.status]).toBe("prospect");
});

for (const refusal of [
  {
    case: "forbidden",
    forced: { status: "forbidden" } as const,
    words: "Status not changed. You cannot change this record.",
  },
  {
    case: "invalid on another field",
    forced: {
      status: "invalid",
      field_id: listIds.owner,
      message: "Choose a person who can read this module",
    } as const,
    words:
      "Status not changed. Owner: Choose a person who can read this module.",
  },
  {
    case: "an unconfirmed outcome",
    failure: { status: 503, detail: "Batch outcome could not be confirmed" },
    words: "The result could not be confirmed.",
  },
  {
    case: "a failed request",
    failure: { status: 500, detail: "Internal error" },
    words: "Status not changed. Try again.",
    reference: true,
  },
]) {
  test(`SI-C1.11: ${refusal.case} shows the stored value and the reason, with no Undo`, async ({
    page,
  }) => {
    const api = await installListApi(page);
    await openContacts(page);
    if ("forced" in refusal && refusal.forced)
      api.state.forced.set(recordId(0), refusal.forced);
    if ("failure" in refusal && refusal.failure)
      api.state.failNext = refusal.failure;

    await statusValue(row(page, "Ana Cruz"), "Active").click();
    await page.getByRole("menuitemradio", { name: "Former" }).click();

    await expect(pageStatus(page)).toHaveText(refusal.words);
    await expect(statusValue(row(page, "Ana Cruz"), "Active")).toBeVisible();
    await expect(undo(page)).toHaveCount(0);
    expect(api.state.batches).toHaveLength(1);
    expect(api.stored(0)?.[listIds.status]).toBe("active");
    if ("reference" in refusal)
      await expect(metaLine(page)).toContainText(answeredReference);
  });
}

async function selectFirstTen(page: Page) {
  await box(page, "Ana Cruz").click();
  await box(page, "Jo Reyes").click({ modifiers: ["Shift"] });
  await expect(selectionBar(page)).toContainText("10 selected");
}

test("SI-C5.1: a writer selects ten rows by Shift-click and by keyboard; the bar offers Status and Paid only", async ({
  page,
}) => {
  await installListApi(page);
  await openContacts(page);
  // The results panel, not the table, which scrolls inside it.
  const results = page.getByLabel("Record results");
  const restingTop = (await results.boundingBox())?.y;

  await selectFirstTen(page);
  // DR-SI-5.4: the bar takes the toolbar row's place in the same height.
  expect((await results.boundingBox())?.y).toBe(restingTop);
  await expect(box(page, "Kai Lund")).not.toBeChecked();
  await expect(
    page.getByRole("searchbox", { name: "Search Contacts" }),
  ).toHaveCount(0);
  await selectionBar(page).getByRole("button", { name: "Change" }).click();
  await expect(page.getByRole("menu").getByRole("menuitem")).toHaveText([
    "Status",
    "Paid",
  ]);
  await page.keyboard.press("Escape");
  await selectionBar(page)
    .getByRole("button", { name: "Clear selection" })
    .click();
  await expect(selectionBar(page)).toHaveCount(0);
  // The toolbar row returns in the bar's place, and so does focus.
  await expect(
    page.getByRole("searchbox", { name: "Search Contacts" }),
  ).toBeFocused();

  // The keyboard path: the header box selects the page, Space each row.
  await page.getByRole("checkbox", { name: "Select all on this page" }).focus();
  await page.keyboard.press("Space");
  await expect(selectionBar(page)).toContainText("12 selected");
  await box(page, "Kai Lund").focus();
  await page.keyboard.press("Space");
  await box(page, "Lea Novak").focus();
  await page.keyboard.press("Space");
  await expect(selectionBar(page)).toContainText("10 selected");
  await expect(page).not.toHaveURL(/[?&]record=/);
});

test("SI-C5.2 and SI-C5.3: Change Status on ten rows sends only the eight that change, and Undo puts each one back", async ({
  page,
}) => {
  const api = await installListApi(page);
  await openContacts(page);
  await selectFirstTen(page);

  await selectionBar(page).getByRole("button", { name: "Change" }).click();
  await page.getByRole("menuitem", { name: "Status" }).click();
  const panel = page.getByRole("dialog", { name: "Change Status" });
  await expect(
    panel.getByRole("button", { name: "Change records" }),
  ).toBeDisabled();
  await panel.getByRole("radio", { name: "Former" }).click();
  const final = panel.getByRole("button", { name: "Change 8 records" });
  await expect(final).toBeEnabled();
  expect(api.state.batches).toEqual([]);

  await final.click();

  await expect(pageStatus(page)).toHaveText("Status changed on 8 records.");
  await expect(selectionBar(page)).toHaveCount(0);
  const changed = [0, 2, 3, 5, 6, 7, 8, 9];
  expect(api.state.batches[0]?.items.map((item) => item.record_id)).toEqual(
    changed.map(recordId),
  );
  for (const index of [...changed, 1, 4])
    expect(api.stored(index)?.[listIds.status]).toBe("former");

  await undo(page).click();

  await expect(pageStatus(page)).toHaveText(
    "Status changed back on 8 records.",
  );
  expect(api.state.batches[1]?.items).toEqual(
    [
      [0, "active"],
      [2, "prospect"],
      [3, "active"],
      [5, "active"],
      [6, "prospect"],
      [7, "active"],
      [8, "prospect"],
      [9, "active"],
    ].map(([index, value], position) => ({
      record_id: recordId(index as number),
      revision: `2026-11-13T10:0${position + 1}:00Z`,
      field_id: listIds.status,
      value,
    })),
  );
  expect(api.stored(2)?.[listIds.status]).toBe("prospect");
  // The two that already held Former stay.
  expect(api.stored(1)?.[listIds.status]).toBe("former");
  expect(api.stored(4)?.[listIds.status]).toBe("former");
});

async function changePaidOnFirstFive(page: Page) {
  await box(page, "Ana Cruz").click();
  await box(page, "Eli Park").click({ modifiers: ["Shift"] });
  await selectionBar(page).getByRole("button", { name: "Change" }).click();
  await page.getByRole("menuitem", { name: "Paid" }).click();
  const panel = page.getByRole("dialog", { name: "Change Paid" });
  await panel.getByRole("radio", { name: "On" }).click();
  await panel.getByRole("button", { name: "Change 5 records" }).click();
}

test("SI-C5.4 and SI-C5.6: a bulk change lists each record that did not change with its reason, and Undo covers only the changed ones", async ({
  page,
}) => {
  const api = await installListApi(page);
  await openContacts(page);
  api.changeElsewhere(1, { [listIds.status]: "prospect" });
  api.state.forced.set(recordId(2), { status: "forbidden" });
  api.state.forced.set(recordId(3), {
    status: "invalid",
    field_id: listIds.owner,
    message: "Choose a person who can read this module",
  });

  await changePaidOnFirstFive(page);

  await expect(pageStatus(page)).toHaveText(
    "Paid changed on 2 records. 3 not changed.",
  );
  await metaLine(page).getByRole("button", { name: "3 not changed" }).click();
  await expect(
    page
      .getByRole("dialog", { name: "Records not changed" })
      .getByRole("listitem"),
  ).toHaveText([
    /^Ben Ortiz\s*Someone changed it$/,
    /^Chen Wu\s*You cannot change it$/,
    /^Dana Lim\s*Not valid: Owner: Choose a person who can read this module\.$/,
  ]);
  await page.keyboard.press("Escape");
  // B's value stays.
  expect(api.stored(1)).toMatchObject({
    [listIds.status]: "prospect",
    [listIds.paid]: false,
  });

  await undo(page).click();

  await expect(pageStatus(page)).toHaveText("Paid changed back on 2 records.");
  expect(api.state.batches[1]?.items.map((item) => item.record_id)).toEqual([
    recordId(0),
    recordId(4),
  ]);
  expect(api.state.batches[1]?.items.map((item) => item.value)).toEqual([
    false,
    false,
  ]);
});

test("SI-C5.5: Undo after someone changed one record puts back the others and names that one", async ({
  page,
}) => {
  const api = await installListApi(page);
  await openContacts(page);
  await changePaidOnFirstFive(page);
  await expect(pageStatus(page)).toHaveText("Paid changed on 5 records.");
  api.changeElsewhere(2, { [listIds.status]: "former" });

  await undo(page).click();

  await expect(pageStatus(page)).toHaveText(
    "4 changed back. 1 not changed back.",
  );
  await metaLine(page)
    .getByRole("button", { name: "1 not changed back" })
    .click();
  await expect(
    page
      .getByRole("dialog", { name: "Records not changed" })
      .getByRole("listitem"),
  ).toHaveText([/^Chen Wu\s*Someone changed it$/]);
  expect(api.state.batches[1]?.items).toHaveLength(5);
  expect(api.stored(2)).toMatchObject({
    [listIds.status]: "former",
    [listIds.paid]: true,
  });
  for (const index of [0, 1, 3, 4])
    expect(api.stored(index)?.[listIds.paid]).toBe(false);
});

test("SI-C5.7: the selection clears on another page and after a filter change", async ({
  page,
}) => {
  await installListApi(page, { count: 30 });
  await openContacts(page);
  await box(page, "Ana Cruz").click();
  await box(page, "Ben Ortiz").click();
  await expect(selectionBar(page)).toContainText("2 selected");

  await page.getByRole("button", { name: "Go to next page" }).click();

  await expect(selectionBar(page)).toHaveCount(0);
  await expect(page.getByRole("checkbox", { checked: true })).toHaveCount(0);
  const onPageTwo = table(page).getByRole("row").nth(1);
  await onPageTwo.getByRole("checkbox").click();
  await expect(selectionBar(page)).toContainText("1 selected");

  const value = onPageTwo.getByRole("button", { name: /^Status: / });
  await value.click();
  await page.getByRole("menuitem", { name: /^Show only / }).click();

  await expect(selectionBar(page)).toHaveCount(0);
  await expect(page.getByRole("checkbox", { checked: true })).toHaveCount(0);
});

for (const reader of [
  { case: "a reader", viewer: "reader" as Viewer },
  { case: "a guest", viewer: "guest" as Viewer },
  {
    case: "a writer with the Deleted filter",
    viewer: "writer" as Viewer,
    deleted: "include" as const,
  },
]) {
  test(`SI-C5.8: ${reader.case} gets no selection checkboxes`, async ({
    page,
  }) => {
    await installListApi(page, {
      viewer: reader.viewer,
      deleted: reader.deleted,
    });
    await openContacts(page);
    await expect(table(page).getByRole("row")).toHaveCount(13);
    await expect(table(page).getByRole("checkbox")).toHaveCount(0);
  });
}

/** The width and height of a box's hit area, its `::after` included. */
async function hitArea(target: Locator) {
  return target.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const after = getComputedStyle(element, "::after");
    const outside = (value: string) => Math.max(0, -parseFloat(value) || 0);
    return {
      width: rect.width + outside(after.left) + outside(after.right),
      height: rect.height + outside(after.top) + outside(after.bottom),
    };
  });
}

test("SI-C5.9: on a phone a writer selects two rows with 44 px boxes and changes a Checkbox field", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const api = await installListApi(page);
  await page.goto(contacts);
  const list = page.getByRole("list", { name: "Records" });
  const first = box(page, "Ana Cruz");
  await expect(first).toBeVisible();
  const restingTop = (await list.boundingBox())?.y;
  await first.click();
  await box(page, "Ben Ortiz").click();
  const area = await hitArea(first);
  expect(area.width).toBeGreaterThanOrEqual(44);
  expect(area.height).toBeGreaterThanOrEqual(44);
  await expect(selectionBar(page)).toContainText("2 selected");
  // DR-SI-5.4: the rows do not move when the bar replaces the search row.
  expect((await list.boundingBox())?.y).toBe(restingTop);
  const change = selectionBar(page).getByRole("button", { name: "Change" });
  expect((await change.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);

  await change.click();
  await page.getByRole("menuitem", { name: "Paid" }).click();
  const sheet = page.getByRole("dialog", { name: "Change Paid" });
  await sheet.getByRole("radio", { name: "On" }).click();
  await sheet.getByRole("button", { name: "Change 2 records" }).click();

  await expect(pageStatus(page)).toHaveText("Paid changed on 2 records.");
  expect(api.state.batches[0]?.items.map((item) => item.value)).toEqual([
    true,
    true,
  ]);
  expect(api.stored(0)?.[listIds.paid]).toBe(true);
  expect(api.stored(1)?.[listIds.paid]).toBe(true);
  await expect(page).not.toHaveURL(/[?&]record=/);
});
