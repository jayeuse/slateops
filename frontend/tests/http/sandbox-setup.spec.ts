import { expect, test, type Page } from "./helpers/test";
import {
  addDepartmentsFromToolbar,
  createEntry,
  elementBar,
  liveBinding,
  openAuthenticatedSandbox,
} from "./helpers/sandbox-api";
import type { Design } from "../../src/components/systems/sandbox/domain/model";
import type { SandboxDocumentV4 } from "../../src/components/systems/sandbox/domain/document";

// Setup choices (docs/specs/sandbox-ux-redesign.md, "Setup choices"; FIT-1,
// FIT-3; plan section 11.3): a new department's Setup in Build and in the
// review edits one draft value through the Build save.

const FINANCE_LIVE_ID = "00000000-0000-4000-8000-0000000000f1";

/** Sales is new (no live binding); Finance is published. */
function salesAndFinance(
  salesSetup?: Design["departments"][number]["setup"],
): Design {
  return {
    departments: [
      {
        id: "sales",
        name: "Sales",
        closed: false,
        ...(salesSetup ? { setup: salesSetup } : {}),
      },
      { id: "finance", name: "Finance", closed: false },
    ],
    modules: [
      {
        id: "orders",
        department: "sales",
        name: "Orders",
        closed: false,
        fields: [],
        x: 0,
        y: 48,
      },
      {
        id: "invoices",
        department: "finance",
        name: "Invoices",
        closed: false,
        fields: [],
        x: 400,
        y: 48,
      },
    ],
    relationships: [],
    rules: [],
  };
}

const published = [liveBinding("department", "finance", FINANCE_LIVE_ID)];

/** The setup that the saved draft holds for Sales; absent means all on. */
function savedSalesSetup(document: SandboxDocumentV4) {
  return document.design.departments.find((item) => item.id === "sales")?.setup;
}

/** Every create or Setup control a person can see now (UXD-2 count). */
function barControls(page: Page) {
  return page
    .getByRole("button", {
      name: /^(Add (department|module|field)|Connect |Setup for )/,
    })
    .filter({ visible: true });
}

/**
 * The review of Sales as the planner answers it: the full setup, less the
 * items the saved draft clears (SD13; the Board always stays).
 */
function salesReview(document: SandboxDocumentV4) {
  const setup = savedSalesSetup(document) ?? {
    groups: true,
    dashboard: true,
    category: true,
    channel: true,
  };
  const row = (kind: string, role: string, label: string) => ({
    kind,
    action: "create",
    sandboxId: `sales#${role}`,
    label,
  });
  return [
    {
      kind: "department",
      action: "create",
      sandboxId: "sales",
      label: "Sales",
    },
    ...(setup.groups
      ? [
          row("group", "managers", "Sales managers · manage"),
          row("group", "members", "Sales members · write"),
          row("group", "viewers", "Sales viewers · read"),
        ]
      : []),
    ...(setup.dashboard
      ? [row("dashboard", "dashboard", "Sales dashboard")]
      : []),
    row("board", "board", "Sales"),
    ...(setup.category ? [row("category", "category", "Sales")] : []),
    ...(setup.channel ? [row("channel", "channel", "Sales")] : []),
  ];
}

// UX-C29 (FIT-1, B3, B9), UXD-2 department state re-measured with Setup.
test("a new department's bar holds Setup; one toggle saves once and Undo restores it; a published one has none", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const sandbox = await openAuthenticatedSandbox(page, salesAndFinance(), {
    bindings: published,
    path: "/sandbox?department=sales",
  });
  // B3: + Module and Setup on the selected new department, +2 at most.
  const bar = elementBar(page, "Sales");
  const setup = bar.getByRole("button", {
    name: "Setup for Sales",
    exact: true,
  });
  await expect(setup).toHaveText("Setup");
  await expect(barControls(page)).toHaveText([
    "Add department",
    "Module",
    "Setup",
  ]);

  await setup.click();
  const popover = page.getByRole("dialog", { name: "Setup for Sales" });
  await expect(popover.getByText("Created at publish")).toBeVisible();
  await expect(popover.getByText("Board · always created")).toBeVisible();
  const writes = sandbox.documentWrites();
  await popover.getByRole("checkbox", { name: "Channel" }).click();
  await expect
    .poll(() => savedSalesSetup(sandbox.document()))
    .toEqual({
      groups: true,
      dashboard: true,
      category: true,
      channel: false,
    });
  expect(sandbox.documentWrites()).toBe(writes + 1);
  await expect(
    bar.getByRole("button", { name: "Setup for Sales: 1 item cleared" }),
  ).toHaveText(/^Setup\s*·\s*1 cleared$/);
  await expect(
    popover.getByRole("checkbox", { name: "Channel" }),
  ).not.toBeChecked();

  // One toggle is one Undo step: the draft is back to no setup value.
  await page.keyboard.press("Escape");
  await expect(popover).toBeHidden();
  await page.getByRole("button", { name: "Undo", exact: true }).click();
  await expect.poll(() => savedSalesSetup(sandbox.document())).toBeUndefined();
  await expect(setup).toHaveText("Setup");

  // A published department shows no Setup.
  await page.goto("/sandbox?department=finance");
  await expect(elementBar(page, "Finance")).toBeVisible();
  await expect(barControls(page)).toHaveText(["Add department", "Module"]);
});

// UX-C29 keyboard route: "Setup…" in the Structure tree's item menu.
test("Setup… in a new department's tree menu opens Setup, and Escape returns to the row", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openAuthenticatedSandbox(page, salesAndFinance(), {
    bindings: published,
  });
  await page.getByRole("tab", { name: "Structure" }).click();
  const structure = page.getByRole("complementary", {
    name: "Organization structure",
  });
  const sales = structure.getByRole("treeitem", { name: "Sales", exact: true });
  await sales.focus();
  await page.keyboard.press("Shift+F10");
  const menu = page.getByRole("menu", { name: "Actions for department Sales" });
  await menu.getByRole("menuitem", { name: "Setup…" }).click();
  const popover = page.getByRole("dialog", { name: "Setup for Sales" });
  await expect(popover.getByRole("checkbox", { name: "Groups" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(popover).toBeHidden();
  await expect(sales).toBeFocused();

  const finance = structure.getByRole("treeitem", {
    name: "Finance",
    exact: true,
  });
  await finance.focus();
  await page.keyboard.press("Shift+F10");
  const financeMenu = page.getByRole("menu", {
    name: "Actions for department Finance",
  });
  await expect(
    financeMenu.getByRole("menuitem", { name: "Rename department" }),
  ).toBeVisible();
  await expect(
    financeMenu.getByRole("menuitem", { name: "Setup…" }),
  ).toHaveCount(0);
});

// UX-C30 (FIT-3, SD-C18; plan 11.3 R1, R2, R4).
test("turning the channel back on in the review saves the draft, reviews again in place, and Build agrees", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  let releaseSave = () => {};
  const saveDelay = new Promise<void>((resolve) => {
    releaseSave = resolve;
  });
  const sandbox = await openAuthenticatedSandbox(
    page,
    salesAndFinance({
      groups: true,
      dashboard: true,
      category: true,
      channel: false,
    }),
    { bindings: published, previewChangesFor: salesReview, saveDelay },
  );
  await page.getByRole("button", { name: "Review & Publish" }).click();
  const dialog = page.getByRole("dialog", { name: "Review & Publish" });
  const salesSetup = dialog.getByRole("list", {
    name: "Setup for Sales",
    exact: true,
  });
  // R1: no Channel row while the draft clears it.
  await expect(salesSetup.getByRole("listitem")).toHaveCount(6);
  await expect(salesSetup).not.toContainText("Channel");

  const control = dialog.getByRole("button", {
    name: "Setup for Sales: 1 item cleared",
  });
  await control.click();
  const popover = page.getByRole("dialog", { name: "Setup for Sales" });
  const channel = popover.getByRole("checkbox", { name: "Channel" });
  const writes = sandbox.documentWrites();
  await channel.click();
  // R4: while the save runs, the list stays and Publish says why it waits.
  await expect(
    dialog.getByRole("button", { name: "Publish changes" }),
  ).toHaveAccessibleDescription("Saving…");
  await expect(salesSetup.getByRole("listitem")).toHaveCount(6);
  releaseSave();
  // R2: the draft takes the value through one save, and the new review
  // brings the Channel row back in the same list.
  await expect
    .poll(() => savedSalesSetup(sandbox.document()))
    .toEqual({
      groups: true,
      dashboard: true,
      category: true,
      channel: true,
    });
  expect(sandbox.documentWrites()).toBe(writes + 1);
  await expect(salesSetup.getByRole("listitem")).toHaveCount(7);
  await expect(salesSetup.getByRole("listitem").last()).toHaveText(
    /^Channel\s*Sales$/,
  );
  await expect(
    dialog.getByRole("button", { name: "Setup for Sales", exact: true }),
  ).toBeVisible();
  await expect(channel).toBeFocused();

  // Escape closes the popover first, then the review.
  await page.keyboard.press("Escape");
  await expect(popover).toBeHidden();
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  // Build reads the same draft value.
  await page.goto("/sandbox?department=sales");
  await expect(
    elementBar(page, "Sales").getByRole("button", {
      name: "Setup for Sales",
      exact: true,
    }),
  ).toHaveText("Setup");
});

// B10 at 390: Setup opens as a bottom sheet with 44px rows.
test("on a phone Setup opens as a bottom sheet with 44 px rows", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openAuthenticatedSandbox(page, salesAndFinance(), {
    bindings: published,
    path: "/sandbox?department=sales",
  });
  await page.getByRole("tab", { name: "Canvas" }).click();
  await elementBar(page, "Sales")
    .getByRole("button", { name: "Setup for Sales", exact: true })
    .click();
  const sheet = page.getByRole("dialog", { name: "Setup for Sales" });
  await expect(sheet).toBeVisible();
  const sheetBox = await sheet.boundingBox();
  if (!sheetBox) throw new Error("The Setup sheet has no box");
  expect(Math.round(sheetBox.y + sheetBox.height)).toBe(844);
  for (const name of ["Groups", "Dashboard", "Category", "Channel"]) {
    const row = await sheet
      .getByRole("checkbox", { name })
      .locator("xpath=..")
      .boundingBox();
    expect(row?.height ?? 0, name).toBeGreaterThanOrEqual(44);
  }
});

// Plan 11.3 "Second review fails": the review's error and Try again.
test("a second review that fails shows the review error with Try again, which brings the list back", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openAuthenticatedSandbox(page, salesAndFinance(), {
    bindings: published,
    previewChangesFor: salesReview,
  });
  // The second review request fails once; every other one passes through.
  let reviews = 0;
  await page.route("**/api/sandbox/publication-previews", async (route) => {
    reviews += 1;
    if (reviews === 2)
      await route.fulfill({
        status: 503,
        json: { detail: "Review unavailable" },
      });
    else await route.fallback();
  });
  await page.getByRole("button", { name: "Review & Publish" }).click();
  const dialog = page.getByRole("dialog", { name: "Review & Publish" });
  await dialog
    .getByRole("button", { name: "Setup for Sales", exact: true })
    .click();
  await page
    .getByRole("dialog", { name: "Setup for Sales" })
    .getByRole("checkbox", { name: "Dashboard" })
    .click();

  await expect(dialog.getByRole("alert")).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Publish changes" }),
  ).toHaveCount(0);
  await page.keyboard.press("Escape");
  await dialog.getByRole("button", { name: "Try again" }).click();
  await expect(
    dialog
      .getByRole("list", { name: "Setup for Sales", exact: true })
      .getByRole("listitem"),
  ).toHaveCount(6);
});

// SD-C20 (BE-SD6, FIT-4, UX-C34): with the Manage default "channel: no", a
// department added by the entry, a template, or Duplicate starts with the
// channel cleared and the rest on; the administrator turns it back on before
// publish. The default comes from the workspace read the page already made.
test("with the Manage default channel off, new departments start with the channel cleared and it can be turned back on", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const workspaceReads: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "GET" &&
      new URL(request.url()).pathname === "/api/workspace"
    )
      workspaceReads.push(request.url());
  });
  const channelOff = {
    groups: true,
    dashboard: true,
    category: true,
    channel: false,
  };
  const sandbox = await openAuthenticatedSandbox(page, salesAndFinance(), {
    bindings: published,
    setupDefaults: channelOff,
  });
  await expect.poll(() => workspaceReads.length).toBeGreaterThan(0);
  const departmentSetup = (name: string) =>
    sandbox.document().design.departments.find((item) => item.name === name)
      ?.setup;

  // The entry. Adds read the default from the page's cached workspace read:
  // no add sends a workspace request of its own.
  let readsBefore = workspaceReads.length;
  await addDepartmentsFromToolbar(page, ["Legal"]);
  await expect.poll(() => departmentSetup("Legal")).toEqual(channelOff);
  expect(workspaceReads).toHaveLength(readsBefore);

  // A template department, from a fresh Build page.
  await page.goto("/sandbox");
  await page
    .getByRole("toolbar", { name: "Canvas view controls" })
    .getByRole("button", { name: "Add department", exact: true })
    .click();
  await createEntry(page, "Add department")
    .getByRole("button", { name: "From a template" })
    .click();
  const template = page.getByRole("dialog", { name: "Add from a template" });
  await template
    .getByRole("listbox", { name: "Template departments" })
    .getByRole("option", { name: /^Sales, 3 modules$/ })
    .click();
  readsBefore = workspaceReads.length;
  await template.getByRole("button", { name: "Add department" }).click();
  await expect(template).toBeHidden();
  await expect.poll(() => departmentSetup("Sales 2")).toEqual(channelOff);

  // Duplicate of Sales, whose own value is "all on".
  await page.getByRole("tab", { name: "Structure" }).click();
  const structure = page.getByRole("complementary", {
    name: "Organization structure",
  });
  await structure.getByRole("treeitem", { name: "Sales", exact: true }).focus();
  await page.keyboard.press("Shift+F10");
  await page
    .getByRole("menu", { name: "Actions for department Sales" })
    .getByRole("menuitem", { name: "Duplicate department" })
    .click();
  await expect.poll(() => departmentSetup("Sales Copy")).toEqual(channelOff);
  expect(departmentSetup("Sales")).toBeUndefined();
  expect(workspaceReads).toHaveLength(readsBefore);

  // Before publish, Legal's channel goes back on from its Setup (the tree
  // route; Legal's frame sits past the visible canvas).
  await structure.getByRole("treeitem", { name: "Legal", exact: true }).focus();
  await page.keyboard.press("Shift+F10");
  await page
    .getByRole("menu", { name: "Actions for department Legal" })
    .getByRole("menuitem", { name: "Setup…" })
    .click();
  const channel = page
    .getByRole("dialog", { name: "Setup for Legal" })
    .getByRole("checkbox", { name: "Channel" });
  await expect(channel).not.toBeChecked();
  await channel.click();
  await expect
    .poll(() => departmentSetup("Legal"))
    .toEqual({ ...channelOff, channel: true });
});
