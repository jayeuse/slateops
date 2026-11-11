import {
  answeredHeaders,
  expect,
  test,
  type Locator,
  type Page,
} from "./helpers/test";
import {
  addInEntry,
  createEntry,
  elementBar,
  expectPinnedDialog,
  openAuthenticatedSandbox,
} from "./helpers/sandbox-api";
import {
  initialDesign,
  type Design,
  type Field,
} from "../../src/components/systems/sandbox/domain/model";
import type { SandboxDocumentV4 } from "../../src/components/systems/sandbox/domain/document";

// Build's create surface (docs/specs/sandbox-ux-redesign.md, "Build: find and
// create"): the canvas toolbar's Add department, the element bars, the
// Structure add items, the add-next entry, and Connect, end to end.

function textField(id: string, name: string): Field {
  return {
    id,
    name,
    type: "Text",
    required: false,
    value: "",
    options: "",
    closed: false,
  };
}

/** A module at its own canvas spot: the saved layout comes from `x` and `y`. */
function module(
  id: string,
  department: string,
  name: string,
  at: { x: number; y: number },
  fields: Field[] = [],
): Design["modules"][number] {
  return { id, department, name, closed: false, fields, ...at };
}

/**
 * Sales with Orders, Customers and Shipments in one column; Finance with
 * Invoices to its right, so no card covers another.
 */
function salesAndFinance(): Design {
  return {
    departments: [
      { id: "sales", name: "Sales", closed: false },
      { id: "finance", name: "Finance", closed: false },
    ],
    modules: [
      module("orders", "sales", "Orders", { x: 0, y: 48 }, [
        textField("orders-customer", "Customer"),
      ]),
      module("customers", "sales", "Customers", { x: 0, y: 160 }),
      module("shipments", "sales", "Shipments", { x: 0, y: 272 }),
      module("invoices", "finance", "Invoices", { x: 400, y: 48 }),
    ],
    relationships: [
      {
        id: "orders-shipments",
        name: "Orders to Shipments",
        source: "orders",
        target: "shipments",
        cardinality: "One-to-many",
        fieldMappings: [],
      },
      {
        id: "invoices-orders",
        name: "Invoices to Orders",
        source: "invoices",
        target: "orders",
        cardinality: "One-to-many",
        fieldMappings: [],
      },
    ],
    rules: [],
  };
}

/** The canvas card of a module or the frame of a department, by its id. */
function canvasNode(page: Page, id: string): Locator {
  return page.locator(`[data-sandbox-node="${id}"]`);
}

/** The last document the page saved. */
async function savedDesign(
  sandbox: Awaited<ReturnType<typeof openAuthenticatedSandbox>>,
): Promise<SandboxDocumentV4["design"]> {
  return sandbox.document().design;
}

// UX-C7 (FAST-3)
test("the reference structure takes 6 clicks and 9 typed names", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const sandbox = await openAuthenticatedSandbox(page, initialDesign);
  let clicks = 0;
  const click = async (target: Locator) => {
    clicks += 1;
    await target.click();
  };
  const typeNames = async (entry: Locator, names: string[]) =>
    addInEntry(entry, names);

  // 1. Toolbar "Add department".
  await click(
    page
      .getByRole("toolbar", { name: "Canvas view controls" })
      .getByRole("button", { name: "Add department", exact: true }),
  );
  await typeNames(createEntry(page, "Add department"), ["Sales"]);
  // 2. Sales bar + Module.
  await click(
    elementBar(page, "Sales").getByRole("button", {
      name: "Add module to Sales",
    }),
  );
  await typeNames(createEntry(page, "Add module to Sales"), [
    "Orders",
    "Customers",
  ]);
  // 3. Customers bar + Field.
  await click(
    elementBar(page, "Customers").getByRole("button", {
      name: "Add field to Customers",
    }),
  );
  await typeNames(createEntry(page, "Add field to Customers"), [
    "Name",
    "Email",
    "Phone",
  ]);
  // 4. Point at Orders: its bar shows; + Field.
  await page
    .locator("[data-sandbox-node]")
    .filter({ hasText: "Orders" })
    .hover();
  await click(
    elementBar(page, "Orders").getByRole("button", {
      name: "Add field to Orders",
    }),
  );
  await typeNames(createEntry(page, "Add field to Orders"), [
    "Number",
    "Status",
    "Total",
  ]);
  // 5. Orders bar Connect; 6. Customers in the target list, then Enter.
  await click(
    elementBar(page, "Orders").getByRole("button", {
      name: "Connect Orders to another module",
    }),
  );
  const connect = page.getByRole("dialog", { name: "Connect Orders to" });
  await click(connect.getByRole("option", { name: "Customers" }));
  const name = connect.getByRole("textbox", { name: "Name" });
  await expect(name).toHaveValue("Orders to Customers");
  await name.press("Enter");
  await expect(connect).toBeHidden();

  expect(clicks).toBe(6);
  await expect
    .poll(async () => (await savedDesign(sandbox)).relationships.length)
    .toBe(1);
  const design = await savedDesign(sandbox);
  expect(design.departments.map((item) => item.name)).toEqual(["Sales"]);
  expect(
    design.modules.map((item) => [
      item.name,
      item.fields.map((field) => [field.name, field.type]),
    ]),
  ).toEqual([
    [
      "Orders",
      [
        ["Number", "Text"],
        ["Status", "Text"],
        ["Total", "Text"],
      ],
    ],
    [
      "Customers",
      [
        ["Name", "Text"],
        ["Email", "Text"],
        ["Phone", "Text"],
      ],
    ],
  ]);
  const [orders, customers] = design.modules;
  expect(design.relationships[0]).toMatchObject({
    name: "Orders to Customers",
    sourceModuleId: orders?.id,
    targetModuleId: customers?.id,
    cardinality: "one-to-many",
  });
});

// UX-C9 (FAST-3)
test("the reference structure can be built from the keyboard alone", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const sandbox = await openAuthenticatedSandbox(page, initialDesign);
  const keys = page.keyboard;
  const typeNames = async (names: string[]) => {
    for (const value of names) {
      await keys.type(value);
      await keys.press("Enter");
    }
    await keys.press("Escape");
  };
  // Focus enters Build on the Structure tab; no pointer from here on.
  const tab = page.getByRole("tab", { name: "Structure" });
  await tab.focus();
  await keys.press("Enter");
  const structure = page.getByRole("complementary", {
    name: "Organization structure",
  });
  const addDepartment = structure.getByRole("button", {
    name: "Add department",
  });
  await addDepartment.focus();
  const item = (name: string) =>
    structure.getByRole("treeitem", { name, exact: true });

  await keys.press("Enter");
  await typeNames(["Sales"]);
  await expect(addDepartment).toBeFocused();
  // Back into the tree, on Sales, then down to its Add module item.
  await keys.press("Shift+Tab");
  await expect(item("Sales")).toBeFocused();
  await keys.press("ArrowDown");
  await expect(item("Add module to Sales")).toBeFocused();
  await keys.press("Enter");
  await typeNames(["Orders", "Customers"]);
  await expect(item("Add module to Sales")).toBeFocused();

  await keys.press("ArrowUp");
  await expect(item("Add field to Customers")).toBeFocused();
  await keys.press("Enter");
  await typeNames(["Name", "Email", "Phone"]);
  await expect(item("Add field to Customers")).toBeFocused();
  for (let step = 0; step < 5; step += 1) await keys.press("ArrowUp");
  await expect(item("Add field to Orders")).toBeFocused();
  await keys.press("Enter");
  await typeNames(["Number", "Status", "Total"]);
  for (let step = 0; step < 4; step += 1) await keys.press("ArrowUp");
  await expect(item("Orders")).toBeFocused();

  // The item menu (context-menu key) of a module offers Connect….
  await keys.press("Shift+F10");
  const menu = page.getByRole("menu", { name: "Actions for module Orders" });
  await expect(menu).toBeVisible();
  await keys.press("End");
  await keys.press("ArrowUp");
  await keys.press("ArrowUp");
  await expect(menu.getByRole("menuitem", { name: "Connect…" })).toBeFocused();
  await keys.press("Enter");
  const connect = page.getByRole("dialog", { name: "Connect Orders to" });
  await expect(
    connect.getByRole("listbox", { name: "Target module" }),
  ).toBeFocused();
  await keys.type("Cus");
  await keys.press("Enter");
  await expect(connect.getByRole("textbox", { name: "Name" })).toHaveValue(
    "Orders to Customers",
  );
  await keys.press("Enter");
  await expect(connect).toBeHidden();

  await expect
    .poll(async () => (await savedDesign(sandbox)).relationships.length)
    .toBe(1);
  const design = await savedDesign(sandbox);
  expect(
    design.modules.map((entry) => [entry.name, entry.fields.length]),
  ).toEqual([
    ["Orders", 3],
    ["Customers", 3],
  ]);
  expect(design.relationships[0]?.name).toBe("Orders to Customers");
});

// UX-C6 (FAST-1), N1 rule 1
test("Enter adds modules one after another and Escape on an empty entry ends the flow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const sandbox = await openAuthenticatedSandbox(
    page,
    {
      departments: [{ id: "sales", name: "Sales", closed: false }],
      modules: [],
      relationships: [],
      rules: [],
    },
    { path: "/sandbox?department=sales" },
  );
  const add = elementBar(page, "Sales").getByRole("button", {
    name: "Add module to Sales",
  });
  await add.click();
  const entry = createEntry(page, "Add module to Sales");
  const name = entry.getByRole("textbox", { name: "Module name" });
  for (const value of ["Invoices", "Payments"]) {
    await name.fill(value);
    await name.press("Enter");
    await expect(name).toHaveValue("");
    await expect(name).toBeFocused();
  }
  await expect(
    page.getByText("A Sandbox change is already being saved."),
  ).toHaveCount(0);
  await name.press("Escape");

  await expect(entry).toBeHidden();
  await expect(add).toBeFocused();
  await expect(
    page.getByRole("heading", { level: 2, name: "Payments", exact: true }),
  ).toBeVisible();
  await expect
    .poll(async () => (await savedDesign(sandbox)).modules.length)
    .toBe(2);
  const design = await savedDesign(sandbox);
  expect(design.modules.map((item) => [item.name, item.departmentId])).toEqual([
    ["Invoices", "sales"],
    ["Payments", "sales"],
  ]);
});

// UX-C10 (FAST-4), FIND-2
test("connecting Orders to Customers from the bar adds the relationship with the prefilled name", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const sandbox = await openAuthenticatedSandbox(page, salesAndFinance(), {
    path: "/sandbox?module=orders",
  });
  const open = elementBar(page, "Orders").getByRole("button", {
    name: "Connect Orders to another module",
  });
  await open.click();
  const connect = page.getByRole("dialog", { name: "Connect Orders to" });
  const targets = connect.getByRole("listbox", { name: "Target module" });
  await expect(targets).toBeFocused();
  await expect(
    targets.getByRole("option", { name: "Shipments" }),
  ).toHaveAttribute("aria-disabled", "true");
  // Invoices links to Orders, not from it: still choosable.
  await expect(
    targets.getByRole("option", { name: "Invoices" }),
  ).not.toHaveAttribute("aria-disabled", "true");

  await page.keyboard.type("Cus");
  await page.keyboard.press("Enter");
  const name = connect.getByRole("textbox", { name: "Name" });
  await expect(name).toBeFocused();
  await expect(name).toHaveValue("Orders to Customers");
  await expect(
    canvasNode(page, "customers").locator('rect[data-connect-target="true"]'),
  ).toHaveCount(1);

  await name.fill("Customer");
  await name.press("Enter");
  await expect(connect.getByRole("alert")).toHaveText(
    "Orders already has a field named Customer.",
  );

  await name.fill("Buyer");
  await name.press("Enter");
  await expect(connect).toBeHidden();
  await expect(open).toBeFocused();
  await expect
    .poll(async () => (await savedDesign(sandbox)).relationships.length)
    .toBe(3);
  expect(
    (await savedDesign(sandbox)).relationships.find(
      (item) => item.name === "Buyer",
    ),
  ).toMatchObject({
    sourceModuleId: "orders",
    targetModuleId: "customers",
    cardinality: "one-to-many",
  });
});

// B10 (FIND-5): Connect on a phone is a bottom sheet with 44 px rows.
test("on a phone Connect opens as a bottom sheet and Escape returns to Connect", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openAuthenticatedSandbox(page, salesAndFinance(), {
    path: "/sandbox?module=orders",
  });
  await page.getByRole("tab", { name: "Canvas" }).click();
  const open = elementBar(page, "Orders").getByRole("button", {
    name: "Connect Orders to another module",
  });
  await open.click();
  const connect = page.getByRole("dialog", { name: "Connect Orders to" });
  await expect(connect).toBeVisible();
  // A bottom sheet: its lower edge settles on the bottom of the screen.
  await expect
    .poll(async () => {
      const sheet = await connect.boundingBox();
      return sheet ? Math.round(sheet.y + sheet.height) : null;
    })
    .toBe(844);
  for (const option of await connect.getByRole("option").all()) {
    const box = await option.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
  }
  await page.keyboard.press("Escape");
  await expect(connect).toBeHidden();
  await expect(open).toBeFocused();
});

// FAST-6: a new element shows the saving mark until its save confirms.
test("a new department shows the saving mark until its save confirms", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openAuthenticatedSandbox(page, initialDesign);
  let confirm: () => void = () => {};
  await page.route("**/api/sandbox/document", async (route) => {
    if (route.request().method() !== "PUT") return route.fallback();
    const body = route.request().postDataJSON() as {
      document: SandboxDocumentV4;
    };
    await new Promise<void>((resolve) => {
      confirm = resolve;
    });
    await route.fulfill({
      headers: answeredHeaders,
      json: {
        document: body.document,
        revision: 2,
        contentHash: "b".repeat(64),
        byteCount: JSON.stringify(body.document).length,
        issues: [],
        latestPublishedVersion: null,
        publishedHash: null,
        hasUnpublishedChanges: true,
      },
    });
  });
  await page
    .getByRole("toolbar", { name: "Canvas view controls" })
    .getByRole("button", { name: "Add department", exact: true })
    .click();
  await addInEntry(createEntry(page, "Add department"), ["Finance"]);
  const frame = page
    .locator("[data-sandbox-node]")
    .filter({ hasText: "Finance" });
  const mark = frame.locator('[data-sandbox-part="saving-mark"]');
  await expect(mark).toHaveCount(1);
  confirm();
  await expect(mark).toHaveCount(0);
});

// FIND-6 (B11): right-click opens the Structure item menu on the canvas.
test("right-click on a module opens its item menu, and Connect… opens Connect", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openAuthenticatedSandbox(page, salesAndFinance());
  await canvasNode(page, "orders").click({
    button: "right",
    position: { x: 40, y: 12 },
  });
  const menu = page.getByRole("menu", { name: "Actions for module Orders" });
  await expect(menu.getByRole("menuitem")).toHaveText([
    "Rename module",
    "Close module",
    "Duplicate module",
    "Connect…",
    "New trigger",
    "Delete module",
  ]);
  await menu.getByRole("menuitem", { name: "Connect…" }).click();
  const connect = page.getByRole("dialog", { name: "Connect Orders to" });
  await expect(
    connect.getByRole("listbox", { name: "Target module" }),
  ).toBeFocused();
});

// FIND-6: only a department, module, or field has an item menu; elsewhere
// the browser's own menu opens.
test("right-click on empty canvas leaves the browser's own menu", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openAuthenticatedSandbox(page, salesAndFinance());
  await page.evaluate(() => {
    const seen = window as unknown as { contextMenus: Event[] };
    seen.contextMenus = [];
    window.addEventListener(
      "contextmenu",
      (event) => seen.contextMenus.push(event),
      true,
    );
  });
  const cancelled = () =>
    page.evaluate(() =>
      (window as unknown as { contextMenus: Event[] }).contextMenus.map(
        (event) => event.defaultPrevented,
      ),
    );
  const canvas = page.getByRole("region", { name: "Organization canvas" });
  const box = await canvas.boundingBox();
  if (!box) throw new Error("The canvas has no box");
  await canvas.click({
    button: "right",
    position: { x: box.width - 30, y: 30 },
  });
  await expect(page.getByRole("menu")).toHaveCount(0);
  await canvasNode(page, "orders").click({
    button: "right",
    position: { x: 40, y: 12 },
  });
  await expect(
    page.getByRole("menu", { name: "Actions for module Orders" }),
  ).toBeVisible();
  expect(await cancelled()).toEqual([false, true]);
});

test.describe("touch on a phone canvas", () => {
  test.use({ hasTouch: true, viewport: { width: 390, height: 844 } });

  // FIND-6 (B11): a long press opens the item menu; a tap still selects and
  // a touch drag still moves the card.
  test("a long press on a module opens its item menu, a tap selects it, and a drag moves it", async ({
    page,
  }) => {
    await openAuthenticatedSandbox(page, salesAndFinance());
    const cdp = await page.context().newCDPSession(page);
    const touch = (
      type: "touchStart" | "touchMove" | "touchEnd",
      x: number,
      y: number,
    ) =>
      cdp.send("Input.dispatchTouchEvent", {
        type,
        touchPoints: type === "touchEnd" ? [] : [{ x, y }],
      });
    const orders = canvasNode(page, "orders");
    await expect(orders).toBeVisible();
    const header = async () => {
      const box = await orders.boundingBox();
      if (!box) throw new Error("The Orders card has no box");
      return { x: box.x + box.width / 2, y: box.y + 6 };
    };
    const menu = page.getByRole("menu", { name: "Actions for module Orders" });

    const tap = await header();
    await touch("touchStart", tap.x, tap.y);
    await touch("touchEnd", tap.x, tap.y);
    await expect(elementBar(page, "Orders")).toBeVisible();
    await expect(page.getByRole("menu")).toHaveCount(0);

    const press = await header();
    await touch("touchStart", press.x, press.y);
    await expect(menu).toBeVisible();
    await touch("touchEnd", press.x, press.y);
    await expect(
      menu.getByRole("menuitem", { name: "Connect…" }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(menu).toBeHidden();

    const start = await header();
    await touch("touchStart", start.x, start.y);
    for (const step of [10, 25, 40, 60])
      await touch("touchMove", start.x + step, start.y + step);
    await touch("touchEnd", start.x + 60, start.y + 60);
    await expect
      .poll(async () => (await header()).x)
      .toBeGreaterThan(start.x + 20);
    await expect(page.getByRole("menu")).toHaveCount(0);
  });
});

// B5d (Product Designer review): Add says why it cannot add, where the
// problem is: under Choices for a choice problem, under the name otherwise.
test("Add in the entry shows a choice problem under Choices and an empty name under the name", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openAuthenticatedSandbox(page, salesAndFinance(), {
    path: "/sandbox?module=orders",
  });
  await elementBar(page, "Orders")
    .getByRole("button", { name: "Add field to Orders" })
    .click();
  const entry = createEntry(page, "Add field to Orders");
  const name = entry.getByRole("textbox", { name: "Field name" });
  const choices = () => entry.getByRole("textbox", { name: "Choices" });
  await name.fill("Status");
  await entry.getByRole("radio", { name: "Choice list" }).click();
  await entry.getByRole("button", { name: "Add field" }).click();
  await expect(choices()).toBeFocused();
  await expect(choices()).toHaveAttribute("aria-invalid", "true");
  await expect(choices()).toHaveAccessibleDescription(
    "Add at least one choice.",
  );
  await expect(name).not.toHaveAttribute("aria-invalid", "true");

  await name.fill("");
  await entry.getByRole("button", { name: "Add field" }).click();
  await expect(name).toBeFocused();
  await expect(name).toHaveAccessibleDescription("Enter a name.");
});

/** Opens "Add from a template" from the toolbar's department entry (FAST-7). */
async function openTemplateDialog(page: Page): Promise<Locator> {
  await page
    .getByRole("toolbar", { name: "Canvas view controls" })
    .getByRole("button", { name: "Add department", exact: true })
    .click();
  await createEntry(page, "Add department")
    .getByRole("button", { name: "From a template" })
    .click();
  const dialog = page.getByRole("dialog", { name: "Add from a template" });
  await expect(dialog).toBeVisible();
  return dialog;
}

// UX-C13 (FAST-7)
test("adding Sales from a template saves it once as Sales 2, selects it, and Undo removes it", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const sandbox = await openAuthenticatedSandbox(page, salesAndFinance());
  const dialog = await openTemplateDialog(page);
  const name = dialog.getByRole("textbox", { name: "Name" });
  await expect(name).toBeFocused();

  const list = dialog.getByRole("listbox", { name: "Template departments" });
  await list.getByRole("option", { name: /^Sales, 3 modules$/ }).click();
  // Arrows move the choice; the name follows it until it is typed.
  await page.keyboard.press("ArrowDown");
  await expect(
    list.getByRole("option", { name: /^Finance, 2 modules$/ }).first(),
  ).toHaveAttribute("aria-selected", "true");
  await expect(name).toHaveValue("Finance 2");
  await page.keyboard.press("ArrowUp");
  await expect(
    list.getByRole("option", { name: /^Sales, 3 modules$/ }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(name).toHaveValue("Sales 2");
  await expect(name).toHaveAccessibleDescription(
    "Sales is taken in this design.",
  );
  await expect(
    dialog.getByText("Adds 3 modules and 3 links, without triggers."),
  ).toBeVisible();

  await dialog.getByRole("button", { name: "Add department" }).click();
  await expect(dialog).toBeHidden();
  await expect
    .poll(async () => (await savedDesign(sandbox)).departments.length)
    .toBe(3);
  expect(sandbox.documentWrites()).toBe(1);
  const saved = sandbox.document();
  const added = saved.design.departments[2]!;
  // A new id and the chosen name; no setup value (the default setup).
  expect(Object.keys(added).sort()).toEqual(["closed", "id", "name"]);
  expect(added.name).toBe("Sales 2");
  expect(added.id).not.toBe("sales");
  expect(
    saved.design.modules
      .filter((item) => item.departmentId === added.id)
      .map((item) => item.name),
  ).toEqual(["Customers", "Opportunities", "Sales orders"]);
  expect(saved.design.relationships.map((item) => item.name)).toEqual([
    "Orders to Shipments",
    "Invoices to Orders",
    "Customer opportunities",
    "Customer sales orders",
    "Opportunity sales orders",
  ]);
  expect(saved.triggers).toEqual([]);
  // The added department is the selection: its bar shows.
  await expect(elementBar(page, "Sales 2")).toBeVisible();

  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect
    .poll(async () =>
      (await savedDesign(sandbox)).departments.map((item) => item.name),
    )
    .toEqual(["Sales", "Finance"]);
  expect((await savedDesign(sandbox)).modules).toHaveLength(4);
});

// FAST-7 at 390: the Sandbox dialog rule on phones.
test("on a phone Add from a template is one scroller with its close button and Add department in view", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openAuthenticatedSandbox(page, salesAndFinance());
  const dialog = await openTemplateDialog(page);
  // The department list comes before the preview.
  const list = dialog.getByRole("listbox", { name: "Template departments" });
  const preview = dialog.getByRole("list", { name: "Procurement modules" });
  const [listBox, previewBox] = await Promise.all([
    list.boundingBox(),
    preview.boundingBox(),
  ]);
  expect(previewBox!.y).toBeGreaterThan(listBox!.y + listBox!.height);
  await expectPinnedDialog(
    dialog,
    "Close add from a template",
    dialog.getByRole("button", { name: "Add department" }),
  );
});
