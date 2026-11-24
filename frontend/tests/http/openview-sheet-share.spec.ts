import { expect, signedInAs, test, type Page } from "./helpers/test";
import {
  installSheetActionsApi,
  installSheetPageApi,
  installSheetsApi,
  sheetPeople,
  sheetPlace,
  wireSheetDetail,
  wireSheetRow,
  wireSheetSummary,
  type WireSheetShare,
} from "./helpers/openview-sheets-api";

// docs/specs/sheets.md V2, V5, V8, V9 (SH-8, SH-9, SH-10 UI halves, SH-12)
// and Screens 3 and 4: the header's actions per level, the Share dialog,
// rename and delete. Words and role rules are owned by
// tests/isolated/openview/sheet-share.spec.ts.

const sheetId = "00000000-0000-4000-8000-0000000008a1";
const recordId = "00000000-0000-4000-8000-0000000008a2";
const diego = {
  id: "00000000-0000-4000-8000-0000000008b1",
  display_name: "Diego Navarro",
  is_guest: false,
};
// Listed as a member, but a guest by the time the share is sent: the
// server's refusal is the last word.
const carmela = {
  id: "00000000-0000-4000-8000-0000000008b2",
  display_name: "Carmela Reyes",
  is_guest: false,
};
const gil = {
  id: "00000000-0000-4000-8000-0000000008b3",
  display_name: "Gil Tan",
  is_guest: true,
};
const faculty = {
  id: "00000000-0000-4000-8000-0000000008c1",
  name: "CCS Faculty",
  member_count: 12,
};
const diegoShare: WireSheetShare = {
  id: "00000000-0000-4000-8000-0000000008d1",
  subject: "user",
  user: diego,
  group: null,
  level: "edit",
  created_at: "2026-11-20T08:00:00Z",
};

const member = {
  id: sheetPeople.viewer.id,
  role: "member",
  access: [
    { department_id: sheetPlace.department, module_id: null, level: "write" },
  ],
} as const;

function sheet(level: "owner" | "edit" | "view" = "owner", shared = true) {
  const summary = wireSheetSummary(sheetId, "Class roster", {
    recordId,
    recordTitle: "Ana Cruz",
    moduleName: "Contacts",
    owner: level === "owner" ? "viewer" : "colleague",
    level,
    shared,
    rows: 2,
  });
  return {
    detail: {
      ...wireSheetDetail(summary),
      structure: {
        structureVersion: 1,
        nextColumnSeq: 2,
        columns: [{ key: "c1", name: "Name", type: "text" }],
        groups: [],
        totals: {},
      },
    },
    rows: [
      wireSheetRow(0, { c1: { value: "Alyssa" } }),
      wireSheetRow(1, { c1: { value: "Bryan" } }),
    ],
    totals: {},
  };
}

const address = `/openview?sheet=${sheetId}`;

function header(page: Page) {
  return page.locator("header").filter({
    has: page.getByRole("heading", { level: 1 }),
  });
}

test("the owner shares with a group, changes a person's level and removes them", async ({
  page,
}) => {
  await signedInAs(page, member);
  const sheetState = await installSheetPageApi(page, sheet());
  const api = await installSheetActionsApi(page, sheetState, {
    shares: [diegoShare],
    candidates: { people: [diego, carmela, gil], groups: [faculty] },
  });
  await page.goto(address);

  await expect(header(page).getByText("Shared with 1 person")).toBeVisible();
  const share = header(page).getByRole("button", {
    name: "Share",
    exact: true,
  });
  await share.click();
  const dialog = page.getByRole("dialog", { name: "Share Class roster" });
  await expect(dialog).toContainText(
    "View reads and exports. Edit also changes rows and columns.",
  );
  const people = dialog.getByRole("list", {
    name: "People and groups with access",
  });
  await expect(people.getByRole("listitem").first()).toContainText(
    `${sheetPeople.viewer.name} (you)`,
  );
  await expect(people.getByRole("listitem").first()).toContainText("Owner");
  await expect(
    people.getByRole("combobox", { name: "Level for Diego Navarro" }),
  ).toHaveValue("edit");
  await expect(dialog).toContainText(
    "People see this sheet only while they can read Ana Cruz's record.",
  );
  await expect(dialog).toContainText(
    "If you leave Slate Operations, this sheet opens read-only to everyone who can read Ana Cruz's record.",
  );

  // Share is quiet until someone is chosen.
  const send = dialog.getByRole("button", { name: "Share", exact: true });
  await expect(send).toHaveAttribute("aria-disabled", "true");
  await expect(send).toHaveAccessibleDescription(
    "Choose a person or group first.",
  );
  await send.focus();
  await page.keyboard.press("Enter");
  expect(api.shareWrites).toEqual([]);

  // A guest is offered View only before anything is sent.
  const level = dialog.getByRole("combobox", { name: "Level", exact: true });
  await dialog.getByRole("combobox", { name: "Add people or groups" }).click();
  await expect(page.getByRole("option", { name: /Gil Tan/ })).toContainText(
    "Guest · View only",
  );
  await page.getByRole("option", { name: /Gil Tan/ }).click();
  await expect(level).toHaveValue("view");
  await expect(level.getByRole("option", { name: "Edit" })).toBeDisabled();

  await dialog.getByRole("combobox", { name: "Add people or groups" }).click();
  await page
    .getByRole("combobox", { name: "Search add people or groups" })
    .fill("ccs");
  await expect(page.getByRole("option", { name: /CCS Faculty/ })).toContainText(
    "Group · 12 people",
  );
  await page.getByRole("option", { name: /CCS Faculty/ }).click();
  await expect(level.getByRole("option", { name: "Edit" })).toBeEnabled();
  await expect(send).not.toHaveAttribute("aria-disabled", "true");
  await send.click();
  await expect(
    people.getByRole("listitem").filter({ hasText: "CCS Faculty" }),
  ).toContainText("Group · 12 people");

  await people
    .getByRole("combobox", { name: "Level for Diego Navarro" })
    .selectOption("view");
  await people.getByRole("button", { name: "Remove Diego Navarro" }).click();
  await expect(people.getByText("Diego Navarro")).toHaveCount(0);
  expect(api.shareWrites).toEqual([
    {
      method: "POST",
      path: `/api/worksheets/${sheetId}/shares`,
      body: { subject: "group", group_id: faculty.id, level: "view" },
    },
    {
      method: "PATCH",
      path: `/api/worksheets/${sheetId}/shares/${diegoShare.id}`,
      body: { level: "view" },
    },
    {
      method: "DELETE",
      path: `/api/worksheets/${sheetId}/shares/${diegoShare.id}`,
      body: null,
    },
  ]);

  await dialog.getByRole("button", { name: "Done" }).click();
  await expect(dialog).toBeHidden();
  await expect(share).toBeFocused();
  // The chip counts what is left once the dialog closes.
  await expect(header(page).getByText("Shared with 1 group")).toBeVisible();
});

test("a refused share says why and keeps the choice", async ({ page }) => {
  await signedInAs(page, member);
  const sheetState = await installSheetPageApi(page, sheet("owner", false));
  const api = await installSheetActionsApi(page, sheetState, {
    candidates: { people: [diego, carmela], groups: [] },
  });
  await page.goto(address);
  await expect(
    header(page).getByText("Only you", { exact: true }),
  ).toBeVisible();
  await header(page)
    .getByRole("button", { name: "Share", exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "Share Class roster" });
  const send = dialog.getByRole("button", { name: "Share", exact: true });
  const level = dialog.getByRole("combobox", { name: "Level", exact: true });

  // Invalid: a guest can only get View, so the level goes back to View.
  await dialog.getByRole("combobox", { name: "Add people or groups" }).click();
  await page.getByRole("option", { name: "Carmela Reyes" }).click();
  await level.selectOption("edit");
  api.refuseNextShare = {
    status: 422,
    code: "guest_view_only",
    message: "A guest can only get View",
  };
  await send.click();
  await expect(dialog.getByRole("alert")).toHaveText(
    "Carmela Reyes is a guest and can only get View. Share again to give View.",
  );
  await expect(level).toHaveValue("view");

  // Conflict: the share exists already.
  api.refuseNextShare = {
    status: 409,
    code: "share_exists",
    message: "This share exists already",
  };
  await send.click();
  await expect(dialog.getByRole("alert")).toHaveText(
    "Carmela Reyes already has access.",
  );

  // Not found: the person left or cannot be seen any more.
  api.refuseNextShare = {
    status: 404,
    code: "share_target_not_found",
    message: "Person or group not found",
  };
  await send.click();
  await expect(dialog.getByRole("alert")).toHaveText(
    "This person or group is no longer available. Choose someone else.",
  );
  expect(api.shareWrites.map((write) => write.body)).toEqual([
    { subject: "user", user_id: carmela.id, level: "edit" },
    { subject: "user", user_id: carmela.id, level: "view" },
    { subject: "user", user_id: carmela.id, level: "view" },
  ]);
});

for (const [level, chip] of [
  ["edit", "You can edit · shared by Bernard Ocampo"],
  ["view", "You can view · shared by Bernard Ocampo"],
] as const)
  test(`a recipient with ${level} sees Export and More, and no Share, Rename or Delete`, async ({
    page,
  }) => {
    await signedInAs(page, member);
    const sheetState = await installSheetPageApi(page, sheet(level));
    const api = await installSheetActionsApi(page, sheetState);
    await page.goto(address);
    await expect(header(page).getByText(chip)).toBeVisible();
    await expect(
      header(page).getByRole("button", { name: "Export" }),
    ).toBeVisible();
    await expect(
      header(page).getByRole("button", { name: "Share", exact: true }),
    ).toHaveCount(0);
    await header(page)
      .getByRole("button", { name: "More sheet actions" })
      .click();
    const menu = page.getByRole("menu");
    await expect(menu.getByRole("menuitem")).toHaveText([
      "Sheet history",
      /^New sheet from this structure/,
    ]);
    // A recipient never reads the owner's shares.
    expect(api.shareReads).toBe(0);
  });

test("the owner renames and deletes a sheet with its version, and My sheets offers Restore", async ({
  page,
}) => {
  await signedInAs(page, member);
  // My sheets first: the sheet page's routes, registered later, win.
  await installSheetsApi(page, {
    deleted: [
      wireSheetSummary(sheetId, "Class 1B", {
        recordId,
        recordTitle: "Ana Cruz",
        deleted: true,
      }),
    ],
  });
  const sheetState = await installSheetPageApi(page, sheet("owner", false));
  const api = await installSheetActionsApi(page, sheetState);
  await page.goto(address);
  const etag = `"${sheetId}:1"`;

  await header(page)
    .getByRole("button", { name: "More sheet actions" })
    .click();
  await expect(page.getByRole("menu").getByRole("menuitem")).toHaveText([
    "Rename",
    "Make a copy",
    "Sheet history",
    /^New sheet from this structure/,
    "Delete sheet",
  ]);
  await page.getByRole("menuitem", { name: "Rename" }).click();
  const rename = page.getByRole("dialog", { name: "Rename sheet" });
  const name = rename.getByRole("textbox", { name: "Name" });
  await expect(name).toHaveValue("Class roster");
  await name.fill("Class 1B");
  await name.press("Enter");
  await expect(rename).toBeHidden();
  await expect(
    page.getByRole("heading", { level: 1, name: "Class 1B" }),
  ).toBeVisible();
  expect(api.renames).toEqual([{ ifMatch: etag, body: { title: "Class 1B" } }]);

  await header(page)
    .getByRole("button", { name: "More sheet actions" })
    .click();
  await page.getByRole("menuitem", { name: "Delete sheet" }).click();
  const confirm = page.getByRole("alertdialog", { name: "Delete Class 1B?" });
  await expect(confirm).toContainText(
    "It disappears for everyone it is shared with. You can restore it from My sheets.",
  );
  await confirm.getByRole("button", { name: "Delete sheet" }).click();
  await expect(page).toHaveURL(/section=sheets/);
  expect(api.deletes).toEqual([`"${sheetId}:2"`]);
  await page
    .getByRole("group", { name: "Show" })
    .getByRole("button", { name: "Deleted 1" })
    .click();
  await expect(
    page.getByRole("button", { name: "Restore Class 1B" }),
  ).toBeVisible();
});
