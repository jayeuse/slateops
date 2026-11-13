import {
  expect,
  modalStatus,
  test,
  type Locator,
  type Page,
  type Route,
} from "./helpers/test";
import {
  installListApi,
  listIds,
  statusLabel,
} from "./helpers/openview-list-api";
import { pageOf } from "../helpers/pagination";
import { wireRecord } from "../helpers/wire";

// The create flow of OpenView (candidates 2 and 3 of
// docs/specs/subtle-interactions.md): New record starts with the values of
// the applied conditions, and "Create and add another" keeps the dialog open
// for the next record. Which conditions give a starting value is owned by
// tests/isolated/openview/create-starting-values.spec.ts; these journeys
// prove the dialog, the requests, and the "New" rows after it closes.

const contacts = `/openview?section=views&module=${listIds.module}&view=${listIds.view}`;
type ListFilter = NonNullable<
  NonNullable<Parameters<typeof installListApi>[1]>["filters"]
>[number];
const statusIsFormer: ListFilter = {
  field_id: listIds.status,
  expected_type: "select",
  operator: "eq",
  value: "former",
};

const createdId = (index: number) =>
  `00000000-0000-4000-8000-${String(2900 + index).padStart(12, "0")}`;

/**
 * The Contacts list of `installListApi`, plus what the create flow needs: a
 * `POST /api/records` that stores the record, the people a User field
 * offers, and the item 6 match read (an id search under the applied
 * conditions; the server applies both together).
 */
async function installCreateApi(
  page: Page,
  { filters = [statusIsFormer] }: { filters?: ListFilter[] } = {},
) {
  const api = await installListApi(page, { viewer: "writer", filters });
  const creates: { module_id: string; data: Record<string, unknown> }[] = [];
  const matchReads: string[] = [];
  const createdIds = new Set<string>();
  let hold: Promise<void> | null = null;
  const wire = (id: string) => {
    const stored = api.state.records.get(id);
    if (!stored) throw new Error(`No record ${id}`);
    const label = statusLabel(stored.data[listIds.status]);
    return wireRecord({
      id,
      module_id: listIds.module,
      data: stored.data,
      display_values: label ? { [listIds.status]: label } : {},
      created_at: stored.updated_at,
      updated_at: stored.updated_at,
    });
  };
  const matches = (
    data: Record<string, unknown>,
    definition: { logic: string; filters: ListFilter[] },
  ) => {
    const results = definition.filters.map((filter) =>
      filter.operator === "eq"
        ? data[filter.field_id] === filter.value
        : filter.operator === "neq"
          ? data[filter.field_id] !== filter.value
          : true,
    );
    if (results.length === 0) return true;
    return definition.logic === "or"
      ? results.some(Boolean)
      : results.every(Boolean);
  };

  await page.route(
    `**/api/modules/${listIds.module}/assignable-users**`,
    (route) =>
      route.fulfill({
        json: pageOf(
          [
            {
              id: listIds.user,
              display_name: "Wren Writer",
              username: "wren.writer",
            },
            {
              id: listIds.person,
              display_name: "Mara Harbone",
              username: "mara.harbone",
            },
          ],
          { limit: 100 },
        ),
      }),
  );
  await page.route("**/api/records", async (route: Route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = route.request().postDataJSON() as {
      module_id: string;
      data: Record<string, unknown>;
    };
    creates.push(body);
    if (hold) {
      const held = hold;
      hold = null;
      await held;
    }
    const id = createdId(creates.length);
    createdIds.add(id);
    api.state.records.set(id, {
      data: body.data,
      updated_at: `2026-11-13T09:${String(creates.length).padStart(2, "0")}:00Z`,
      is_deleted: false,
    });
    return route.fulfill({ status: 201, json: wire(id) });
  });
  await page.route("**/api/records/query", async (route: Route) => {
    const { definition } = route.request().postDataJSON() as {
      definition: {
        logic: string;
        filters: ListFilter[];
        deleted: string;
        search: string | null;
      };
    };
    const search = definition.search;
    // The sheet reads its record with every condition off (deleted
    // "include"); that read and the list reads stay with the list mock.
    if (
      search === null ||
      !createdIds.has(search) ||
      definition.deleted === "include"
    )
      return route.fallback();
    matchReads.push(search);
    const stored = api.state.records.get(search);
    const items =
      stored && matches(stored.data, definition) ? [wire(search)] : [];
    return route.fulfill({ json: pageOf(items, { limit: 1 }) });
  });

  return {
    creates,
    matchReads,
    /** Holds the next create; the returned function lets it answer. */
    holdNextCreate() {
      let release!: () => void;
      hold = new Promise<void>((done) => {
        release = done;
      });
      return release;
    },
  };
}

const newRecord = (page: Page) =>
  page.getByRole("dialog", { name: "New record" });
const createButton = (dialog: Locator) =>
  dialog.getByRole("button", { name: "Create Contacts record", exact: true });
const addAnother = (dialog: Locator) =>
  dialog.getByRole("button", { name: "Create and add another", exact: true });
const nameInput = (dialog: Locator) =>
  dialog.getByRole("textbox", { name: /^Name/ });
const statusSelect = (dialog: Locator) =>
  dialog.getByRole("combobox", { name: /^Status/ });
const ownerSelect = (dialog: Locator) =>
  dialog.getByRole("combobox", { name: /^Owner/ });
const metaLine = (page: Page) =>
  page
    .getByRole("heading", { level: 1 })
    .locator("xpath=following-sibling::p[1]");
const pageStatus = (page: Page) => metaLine(page).getByRole("status").first();
const bodyRows = (page: Page) =>
  page
    .getByRole("table")
    .getByRole("row")
    .filter({ hasNot: page.getByRole("columnheader") });

async function openNewRecord(page: Page) {
  await page.goto(contacts);
  // The rows are read before New record, so the dialog opens on a listed page.
  await expect(page.getByText("Eli Park").first()).toBeVisible();
  await page.getByRole("button", { name: "New record" }).click();
  const dialog = newRecord(page);
  await expect(nameInput(dialog)).toBeVisible();
  return dialog;
}

test("SI-C2.1: New record starts with the applied Status and the signed-in Owner; nothing is sent before Create", async ({
  page,
}) => {
  const api = await installCreateApi(page, {
    filters: [
      statusIsFormer,
      {
        field_id: listIds.owner,
        expected_type: "user",
        operator: "eq",
        value: listIds.user,
      },
    ],
  });
  await page.goto(contacts);
  await page.getByRole("button", { name: "New record" }).click();
  const dialog = newRecord(page);

  await expect(statusSelect(dialog)).toHaveValue("former");
  // The User value is the signed-in person's id (its label is P4-F4's).
  await expect(ownerSelect(dialog)).toHaveValue(listIds.user);
  await expect(nameInput(dialog)).toHaveValue("");
  await expect(
    dialog.getByRole("checkbox", { name: "Paid" }),
  ).not.toBeChecked();
  expect(api.creates).toEqual([]);

  await nameInput(dialog).fill("Nia Cole");
  await createButton(dialog).click();
  await expect(page).toHaveURL(new RegExp(`record=${createdId(1)}`));
  expect(api.creates[0]?.data).toMatchObject({
    [listIds.name]: "Nia Cole",
    [listIds.status]: "former",
    [listIds.owner]: listIds.user,
  });
});

test("SI-C2.4: an untouched New record with starting values closes with no question; a typed value keeps it open", async ({
  page,
}) => {
  await installCreateApi(page);
  const dialog = await openNewRecord(page);
  await expect(statusSelect(dialog)).toHaveValue("former");
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  await page.getByRole("button", { name: "New record" }).click();
  await nameInput(dialog).fill("Nia Cole");
  await page.keyboard.press("Escape");
  // UF-1.4: the modal form keeps a typed value.
  await expect(nameInput(dialog)).toHaveValue("Nia Cole");
});

test("SI-C2.5: on a phone New record starts with the applied Status", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await installCreateApi(page);
  await page.goto(contacts);
  await page.getByRole("button", { name: "New record" }).click();
  await expect(statusSelect(newRecord(page))).toHaveValue("former");
});

test("SI-C3.1: Create and add another keeps the dialog open with the starting values and focus in the first field; Create still opens the sheet", async ({
  page,
}) => {
  const api = await installCreateApi(page);
  const dialog = await openNewRecord(page);

  await nameInput(dialog).fill("Nia Cole");
  const release = api.holdNextCreate();
  await addAnother(dialog).click();
  // DR-SI-3.2: while it runs, the pressed button reads "Creating…" and both
  // create buttons wait.
  await expect(
    dialog.getByRole("button", { name: "Creating…", exact: true }),
  ).toBeDisabled();
  await expect(createButton(dialog)).toBeDisabled();
  release();

  const status = modalStatus(dialog).filter({ hasText: "created." });
  await expect(status).toHaveText(/^Nia Cole created\.\s*Open record$/);
  await expect(
    status.getByRole("button", { name: "Open record", exact: true }),
  ).toBeVisible();
  await expect(nameInput(dialog)).toBeFocused();
  await expect(nameInput(dialog)).toHaveValue("");
  await expect(statusSelect(dialog)).toHaveValue("former");
  expect(api.creates).toEqual([
    {
      module_id: listIds.module,
      data: expect.objectContaining({
        [listIds.name]: "Nia Cole",
        [listIds.status]: "former",
      }),
    },
  ]);

  // A second success replaces the line.
  await nameInput(dialog).fill("Omar Diaz");
  await addAnother(dialog).click();
  await expect(status).toHaveText(/^Omar Diaz created\./);

  await nameInput(dialog).fill("Pia Lund");
  await createButton(dialog).click();
  await expect(page).toHaveURL(new RegExp(`record=${createdId(3)}`));
  await expect(dialog).toBeHidden();
  await page.keyboard.press("Escape");

  // SI-3.4: every record made in the dialog shows first, tagged New, newest
  // first (DR-SI-3.6): the last one made takes the place one created record
  // takes. One match read each.
  const rows = bodyRows(page);
  await expect(rows.nth(0)).toContainText("Pia Lund");
  await expect(rows.nth(1)).toContainText("Omar Diaz");
  await expect(rows.nth(2)).toContainText("Nia Cole");
  for (const index of [0, 1, 2])
    await expect(rows.nth(index)).toContainText("New");
  await expect(pageStatus(page)).toHaveText("3 records created.");
  expect([...api.matchReads].sort()).toEqual([
    createdId(1),
    createdId(2),
    createdId(3),
  ]);
});

test("SI-C3.2: Open record closes the dialog and opens the record just created", async ({
  page,
}) => {
  const api = await installCreateApi(page);
  const dialog = await openNewRecord(page);
  await nameInput(dialog).fill("Nia Cole");
  await addAnother(dialog).click();
  await modalStatus(dialog)
    .getByRole("button", { name: "Open record", exact: true })
    .click();

  await expect(dialog).toBeHidden();
  await expect(page).toHaveURL(new RegExp(`record=${createdId(1)}`));
  await expect(
    page
      .getByRole("dialog", { name: "Record details" })
      .getByRole("heading", { name: "Nia Cole" }),
  ).toBeVisible();
  expect(api.creates).toHaveLength(1);
});

test("SI-C3.3: records made in the dialog list as New rows when they match; the status counts the hidden one; each record shows once", async ({
  page,
}) => {
  const api = await installCreateApi(page);
  const dialog = await openNewRecord(page);
  await nameInput(dialog).fill("Nia Cole");
  await addAnother(dialog).click();
  await expect(modalStatus(dialog)).toContainText("Nia Cole created.");
  await nameInput(dialog).fill("Omar Diaz");
  await statusSelect(dialog).selectOption("active");
  await addAnother(dialog).click();
  await expect(modalStatus(dialog)).toContainText("Omar Diaz created.");
  await nameInput(dialog).fill("Pia Lund");
  await addAnother(dialog).click();
  await expect(modalStatus(dialog)).toContainText("Pia Lund created.");
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(dialog).toBeHidden();

  await expect(pageStatus(page)).toHaveText(
    "3 records created. 1 hidden by your filters.",
  );
  const rows = bodyRows(page);
  await expect(rows.nth(0)).toContainText("Pia Lund");
  await expect(rows.nth(0)).toContainText("New");
  await expect(rows.nth(1)).toContainText("Nia Cole");
  await expect(rows.nth(1)).toContainText("New");
  // The two Former contacts of the module, then nothing else: the server
  // rows that hold the new records do not show them a second time.
  await expect(rows).toHaveCount(4);
  await expect(rows.nth(2)).toContainText("Ben Ortiz");
  await expect(rows.nth(3)).toContainText("Eli Park");
  await expect(page.getByRole("table")).not.toContainText("Omar Diaz");
  // DR-6.4: the pager keeps the server total of the filtered list.
  await expect(page.getByText(/^Showing 1–4 of 4/)).toBeVisible();
  expect(api.matchReads).toHaveLength(3);
});

test("SI-C3.4: a refused Create and add another keeps the typed values and creates nothing", async ({
  page,
}) => {
  const api = await installCreateApi(page);
  const dialog = await openNewRecord(page);
  await statusSelect(dialog).selectOption("active");
  await addAnother(dialog).click();

  await expect(dialog.getByText("Enter a value.")).toBeVisible();
  await expect(statusSelect(dialog)).toHaveValue("active");
  await expect(modalStatus(dialog).filter({ hasText: "created." })).toHaveCount(
    0,
  );
  expect(api.creates).toEqual([]);
});

test("SI-C3.5: after Create and add another the guard counts only values typed after it; one record then shows with the single-record words", async ({
  page,
}) => {
  await installCreateApi(page);
  const dialog = await openNewRecord(page);
  await nameInput(dialog).fill("Nia Cole");
  await addAnother(dialog).click();
  await expect(modalStatus(dialog)).toContainText("Nia Cole created.");
  // Nothing typed after the create: closing asks nothing.
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(pageStatus(page)).toHaveText("Record created.");
  await expect(bodyRows(page).nth(0)).toContainText("Nia Cole");
  await expect(bodyRows(page).nth(0)).toContainText("New");

  await page.getByRole("button", { name: "New record" }).click();
  await nameInput(dialog).fill("Omar Diaz");
  await addAnother(dialog).click();
  await expect(modalStatus(dialog)).toContainText("Omar Diaz created.");
  await nameInput(dialog).fill("Pia");
  await page.keyboard.press("Escape");
  // UF-1.4: a value typed after the create keeps the dialog open.
  await expect(nameInput(dialog)).toHaveValue("Pia");
});

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 390, height: 844 },
]) {
  test(`SI-C3.6: at ${viewport.width}px Tab and Enter on Create and add another create the record; Create stays the primary and Enter in a field means Create`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    const api = await installCreateApi(page);
    const dialog = await openNewRecord(page);
    await nameInput(dialog).fill("Nia Cole");
    await dialog.getByRole("button", { name: "Cancel", exact: true }).focus();
    await page.keyboard.press("Tab");
    await expect(addAnother(dialog)).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(modalStatus(dialog)).toContainText("Nia Cole created.");
    expect(api.creates).toHaveLength(1);

    const another = await addAnother(dialog).boundingBox();
    const create = await createButton(dialog).boundingBox();
    if (!another || !create) throw new Error("The footer buttons have no box.");
    if (viewport.width < 640) {
      // DR-SI-3.1: stacked at full width, 44 px, Create first.
      expect(another.height).toBeGreaterThanOrEqual(44);
      expect(Math.round(another.width)).toBe(Math.round(create.width));
      expect(create.y).toBeLessThan(another.y);
    } else {
      expect(create.x).toBeGreaterThan(another.x);
    }

    await nameInput(dialog).fill("Omar Diaz");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(new RegExp(`record=${createdId(2)}`));
  });
}
