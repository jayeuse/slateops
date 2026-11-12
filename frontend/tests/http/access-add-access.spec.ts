import {
  answeredHeaders,
  expect,
  expectAnsweredReference,
  expectNoHorizontalScroll,
  heldResponse,
  test,
  type Page,
} from "./helpers/test";
import type { Locator } from "@playwright/test";

import {
  expectNoWrites,
  fixtureId,
  ids,
  mockAccessApi,
  person,
  type Api,
  type User,
} from "./helpers/access-api";
import { openedSheet } from "./helpers/settled";

// "Add access" in a person's Access tab (item 10 of
// docs/specs/ux-friction-pass.md) against the mocked Access API. The rules
// (exact fit, names, retry reuse, guest levels) are owned by
// isolated/access/add-access.spec.ts; these journeys prove the tab.

/** The id the mocked API gives every group that a POST makes. */
const made = "00000000-0000-4000-8000-0000000000a9";
const rank = { read: 1, write: 2, manage: 3 } as const;

/**
 * Answer the person's effective access from the mocked groups, as the
 * server does: per department or module, the highest level of the groups
 * that hold the person; a guest is capped at Read.
 */
function accessFromGroups(api: Api, userId: string, role: User["role"]) {
  api.on("GET", `/api/users/${userId}/access`, (route) => {
    type Level = keyof typeof rank;
    const entries = new Map<
      string,
      {
        department_id: string;
        module_id: string | null;
        level: Level;
        groups: { group_id: string; name: string; level: Level }[];
      }
    >();
    for (const item of api.groups.values()) {
      if (item.is_deleted || !item.member_ids.includes(userId)) continue;
      for (const row of item.access) {
        const key = `${row.department_id}:${row.module_id ?? "*"}`;
        const entry = entries.get(key) ?? {
          department_id: row.department_id,
          module_id: row.module_id,
          level: "read" as Level,
          groups: [],
        };
        entry.groups.push({
          group_id: item.id,
          name: item.name,
          level: row.level,
        });
        if (role !== "guest" && rank[row.level] > rank[entry.level])
          entry.level = row.level;
        entries.set(key, entry);
      }
    }
    return route.fulfill({
      json: {
        user_id: userId,
        role,
        unrestricted: false,
        entries: [...entries.values()],
      },
    });
  });
}

async function openAccessTab(page: Page, name: string, userId: string) {
  await page.goto(`/access?view=people&user=${userId}`);
  const sheet = await openedSheet(page.getByRole("dialog", { name }));
  await sheet.getByRole("tab", { name: "Access" }).click();
  return sheet;
}

async function chooseDepartment(
  page: Page,
  sheet: Locator,
  department: string,
) {
  await sheet
    .getByRole("combobox", { name: "Department", exact: true })
    .click();
  await page.getByRole("option", { name: department, exact: true }).click();
}

/** The group requests sent since `from`, as "METHOD path". */
function groupRequests(api: Api, from: number) {
  return api.calls
    .slice(from)
    .filter((call) => call.path.startsWith("/api/access/groups"))
    .map((call) => `${call.method} ${call.path}`);
}

test("UF-C10.2 Add access joins the group that gives exactly this, makes no group, and lists the new row", async ({
  page,
}) => {
  const api = await mockAccessApi(page);
  const readers = api.groups.get(ids.readers)!;
  api.groups.set(ids.readers, { ...readers, member_ids: [] });
  accessFromGroups(api, ids.ben, "member");
  const hold = heldResponse();
  api.on("PUT", `/api/access/groups/${ids.readers}/members`, async () => {
    hold.enter();
    await hold.released;
    return "next" as const;
  });
  const sheet = await openAccessTab(page, "Ben Cruz", ids.ben);
  const list = sheet.getByRole("list", { name: "Access by department" });
  await expect(list).toContainText("Inventory");
  await expect(list).not.toContainText("Finance");

  await sheet.getByRole("button", { name: "Add access", exact: true }).click();
  const form = sheet.getByRole("form", { name: "Add access" });
  await chooseDepartment(page, sheet, "Finance");
  await expect(
    form.getByRole("radio", { name: "Read", exact: true }),
  ).toBeChecked();
  await expect(
    form.getByRole("radio", { name: "Manage", exact: true }),
  ).toHaveAccessibleDescription(
    "Also manage its views, dashboard, and group members.",
  );
  await expect(form).toContainText("Finance readers gives exactly this.");
  const action = form.getByRole("button", { name: "Add to Finance readers" });
  const cancel = form.getByRole("button", { name: "Cancel" });
  const at = await action.boundingBox();
  const from = api.calls.length;
  await action.click();

  // In progress: the action says so; nothing else moves or changes.
  await hold.entered;
  const adding = form.getByRole("button", { name: "Adding…" });
  await expect(adding).toBeVisible();
  expect(await adding.boundingBox()).toEqual(at);
  await expect(cancel).toBeDisabled();
  await expect(list).not.toContainText("Finance");
  hold.release();

  await expect(form).toBeHidden();
  await expect(list).toContainText("From Finance readers (Read)");
  await expect(
    sheet.getByText("Added Finance · Read, from Finance readers.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    sheet.getByRole("button", { name: "Add access", exact: true }),
  ).toBeFocused();
  // P3F3-2: the groups are read, then the person joins; no group is made.
  const sent = groupRequests(api, from);
  expect(
    sent.slice(
      0,
      sent.indexOf(`PUT /api/access/groups/${ids.readers}/members`) + 1,
    ),
  ).toEqual([
    "GET /api/access/groups",
    `GET /api/access/groups/${ids.readers}`,
    `PUT /api/access/groups/${ids.readers}/members`,
  ]);
  expect(api.sent("POST", "/api/access/groups")).toHaveLength(0);
  expect(
    api.sent("PUT", `/api/access/groups/${ids.readers}/members`)[0]?.body,
  ).toEqual({ member_ids: [ids.ben] });
});

test("UF-C10.3 with no group that gives exactly this, Add access makes the named group with exactly that access and adds the person", async ({
  page,
}) => {
  const api = await mockAccessApi(page);
  accessFromGroups(api, ids.ben, "member");
  const sheet = await openAccessTab(page, "Ben Cruz", ids.ben);
  await sheet.getByRole("button", { name: "Add access", exact: true }).click();
  const form = sheet.getByRole("form", { name: "Add access" });
  await chooseDepartment(page, sheet, "Finance");
  // DR-10.6: Ben has Finance Read from Finance readers already.
  const have = form.getByText(
    "Already has Read in Finance, from Finance readers.",
    {
      exact: true,
    },
  );
  await expect(have).toBeVisible();
  const join = form.getByRole("button", { name: "Add to Finance readers" });
  await expect(join).toHaveAttribute("aria-disabled", "true");
  await expect(join).toHaveAccessibleDescription(
    "Already has Read in Finance, from Finance readers.",
  );
  await form.getByRole("radio", { name: "Write", exact: true }).check();
  await expect(have).toBeHidden();
  await expect(form).toContainText("No group gives exactly this.");
  const from = api.calls.length;
  await form
    .getByRole("button", { name: 'Make group "Finance write access" and add' })
    .click();

  await expect(
    sheet.getByText("Added Finance · Write, from Finance write access.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    sheet.getByRole("list", { name: "Access by department" }),
  ).toContainText("Finance write access (Write)");
  const sent = groupRequests(api, from);
  expect(
    sent.slice(0, sent.indexOf(`PUT /api/access/groups/${made}/members`) + 1),
  ).toEqual([
    "GET /api/access/groups",
    "POST /api/access/groups",
    `PUT /api/access/groups/${made}/access`,
    `GET /api/access/groups/${made}`,
    `PUT /api/access/groups/${made}/members`,
  ]);
  expect(api.sent("POST", "/api/access/groups")[0]?.body).toEqual({
    name: "Finance write access",
  });
  expect(api.sent("PUT", `/api/access/groups/${made}/access`)[0]?.body).toEqual(
    {
      access: [{ department_id: ids.finance, module_id: null, level: "write" }],
    },
  );
});

test("UF-C10.6 after the add step is refused, the reason shows, and Try again joins the made group with no second group", async ({
  page,
}) => {
  const api = await mockAccessApi(page);
  accessFromGroups(api, ids.ben, "member");
  let refused = false;
  api.on("PUT", `/api/access/groups/${made}/members`, (route) => {
    if (refused) return "next";
    refused = true;
    return route.fulfill({
      status: 409,
      headers: answeredHeaders,
      json: { detail: "Group membership is being changed" },
    });
  });
  const sheet = await openAccessTab(page, "Ben Cruz", ids.ben);
  await sheet.getByRole("button", { name: "Add access", exact: true }).click();
  const form = sheet.getByRole("form", { name: "Add access" });
  await chooseDepartment(page, sheet, "Finance");
  await form.getByRole("radio", { name: "Write", exact: true }).check();
  await form
    .getByRole("button", { name: 'Make group "Finance write access" and add' })
    .click();

  const failure = form.getByRole("alert");
  await expect(failure).toContainText(
    "Finance write access was made, but this person was not added. Try again.",
  );
  await expect(failure).toContainText("Group membership is being changed.");
  await expectAnsweredReference(failure);
  const from = api.calls.length;
  await form.getByRole("button", { name: "Try again" }).click();

  await expect(
    sheet.getByText("Added Finance · Write, from Finance write access.", {
      exact: true,
    }),
  ).toBeVisible();
  const sent = groupRequests(api, from);
  expect(
    sent.slice(0, sent.indexOf(`PUT /api/access/groups/${made}/members`) + 1),
  ).toEqual([
    "GET /api/access/groups",
    `GET /api/access/groups/${made}`,
    `PUT /api/access/groups/${made}/members`,
  ]);
  expect(api.sent("POST", "/api/access/groups")).toHaveLength(1);
  expect(api.sent("PUT", `/api/access/groups/${made}/access`)).toHaveLength(1);

  await page.goto("/access?view=groups");
  await expect(
    page
      .getByRole("table", { name: "Groups" })
      .getByRole("row", { name: /Finance write access/ }),
  ).toHaveCount(1);
});

test("P3F3-1 an administrator gets Add access for a member or guest, a guest only Read, and none for an administrator", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const api = await mockAccessApi(page);
  const fay = fixtureId(181);
  api.users.set(
    fay,
    person({ id: fay, username: "fay", display_name: "Fay Ong" }),
  );
  // An active member in no group: "No access yet." over Add access.
  let sheet = await openAccessTab(page, "Fay Ong", fay);
  await expect(
    sheet.getByText("No access yet.", { exact: true }),
  ).toBeVisible();
  await sheet.getByRole("button", { name: "Add access", exact: true }).click();
  let form = sheet.getByRole("form", { name: "Add access" });
  await expect(form.getByRole("radio")).toHaveCount(3);
  // On a phone each level row and both buttons are 44px targets.
  for (const target of [
    ...(await form.getByRole("radiogroup").locator("label").all()),
    form.getByRole("button", { name: "Add", exact: true }),
    form.getByRole("button", { name: "Cancel" }),
  ])
    expect((await target.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  await expectNoHorizontalScroll(page);
  await sheet.getByRole("button", { name: "Close" }).click();

  sheet = await openAccessTab(page, "Ana Santos", ids.ana);
  await expect(sheet).toContainText("Guests can only read.");
  await sheet.getByRole("button", { name: "Add access", exact: true }).click();
  form = sheet.getByRole("form", { name: "Add access" });
  // UF-C10.4: the guest cap leaves Read only.
  await expect(form.getByRole("radio")).toHaveCount(1);
  await expect(
    form.getByRole("radio", { name: "Read", exact: true }),
  ).toBeChecked();
  await form.getByRole("button", { name: "Cancel" }).click();
  await expect(form).toBeHidden();
  await expect(
    sheet.getByRole("button", { name: "Add access", exact: true }),
  ).toBeFocused();
  await sheet.getByRole("button", { name: "Close" }).click();

  sheet = await openAccessTab(page, "Dee Lim", ids.dee);
  await expect(sheet.getByText("Full access", { exact: true })).toBeVisible();
  await expect(
    sheet.getByRole("button", { name: "Add access", exact: true }),
  ).toHaveCount(0);
  expectNoWrites(api);
});

test("P3F3-8 while Add access runs, the sheet holds close and tab changes, and a later failure still shows in the form", async ({
  page,
}) => {
  const api = await mockAccessApi(page);
  const readers = api.groups.get(ids.readers)!;
  api.groups.set(ids.readers, { ...readers, member_ids: [] });
  accessFromGroups(api, ids.ben, "member");
  const hold = heldResponse();
  api.on("PUT", `/api/access/groups/${ids.readers}/members`, async (route) => {
    hold.enter();
    await hold.released;
    return route.fulfill({
      status: 409,
      headers: answeredHeaders,
      json: { detail: "Group membership is being changed" },
    });
  });
  const sheet = await openAccessTab(page, "Ben Cruz", ids.ben);
  await sheet.getByRole("button", { name: "Add access", exact: true }).click();
  const form = sheet.getByRole("form", { name: "Add access" });
  await chooseDepartment(page, sheet, "Finance");
  await form.getByRole("button", { name: "Add to Finance readers" }).click();
  await hold.entered;

  await sheet.getByRole("button", { name: "Close", exact: true }).click();
  await expect(
    sheet.getByText(
      "Finish the current change before closing or switching tabs.",
      { exact: true },
    ),
  ).toBeVisible();
  await sheet.getByRole("tab", { name: "Details", exact: true }).click();
  await expect(sheet.getByRole("tab", { name: "Access" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  hold.release();

  const failure = form.getByRole("alert");
  await expect(failure).toContainText("Group membership is being changed.");
  await expectAnsweredReference(failure);
  await expect(sheet).toBeVisible();
});

test("P3F3-9 when the groups changed after the line was shown, the click makes and joins nothing, shows the new plan, and the next click runs it", async ({
  page,
}) => {
  const api = await mockAccessApi(page);
  const readers = api.groups.get(ids.readers)!;
  api.groups.set(ids.readers, { ...readers, member_ids: [] });
  accessFromGroups(api, ids.ben, "member");
  const sheet = await openAccessTab(page, "Ben Cruz", ids.ben);
  await sheet.getByRole("button", { name: "Add access", exact: true }).click();
  const form = sheet.getByRole("form", { name: "Add access" });
  await chooseDepartment(page, sheet, "Finance");
  await expect(form).toContainText("Finance readers gives exactly this.");
  // Someone else gives Finance readers Write: it no longer fits Read.
  api.groups.set(ids.readers, {
    ...readers,
    member_ids: [],
    revision: readers.revision + 1,
    access: [{ ...readers.access[0], level: "write" }],
  });
  await form.getByRole("button", { name: "Add to Finance readers" }).click();

  await expect(
    form.getByText(
      "The groups changed. Check what happens now before you add.",
      {
        exact: true,
      },
    ),
  ).toBeVisible();
  await expect(form).toContainText("No group gives exactly this.");
  const make = form.getByRole("button", {
    name: 'Make group "Finance read access" and add',
  });
  await expect(make).toBeVisible();
  expect(api.sent("POST", "/api/access/groups")).toHaveLength(0);
  expect(api.calls.filter((call) => call.method === "PUT")).toEqual([]);

  await make.click();
  await expect(
    sheet.getByText("Added Finance · Read, from Finance read access.", {
      exact: true,
    }),
  ).toBeVisible();
  expect(api.sent("POST", "/api/access/groups")[0]?.body).toEqual({
    name: "Finance read access",
  });
  expect(
    api.sent("PUT", `/api/access/groups/${ids.readers}/members`),
  ).toHaveLength(0);
});
