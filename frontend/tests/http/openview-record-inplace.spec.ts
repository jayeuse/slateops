import {
  answeredHeaders,
  answeredReference,
  authMeBody,
  defaultOrganization,
  expect,
  test,
  type Locator,
  type Page,
  type Route,
  isEventStream,
} from "./helpers/test";
import { installOpenViewEventSource } from "./helpers/openview-event-source";
import { keysetPageOf, pageOf } from "../helpers/pagination";
import { emptyWireQuery } from "../helpers/query-definitions";
import { wireField, wireRecord, wireView } from "../helpers/wire";
import { openedSheet } from "./helpers/settled";

// Values changed in place on the OpenView record sheet (item 2 of
// docs/specs/ux-friction-pass.md, DR-2.2 to DR-2.8). The record PATCH
// replaces every active value, so this mock keeps the server's rules that the
// browser must meet: it refuses a stale If-Match with 412, gives each save a
// new updated_at, and a records query returns only the view's columns.

const userId = "00000000-0000-4000-8000-000000000801";
const departmentId = "00000000-0000-4000-8000-000000000802";
const moduleId = "00000000-0000-4000-8000-000000000803";
const viewId = "00000000-0000-4000-8000-000000000804";
const recordId = "00000000-0000-4000-8000-000000000805";
const nameId = "00000000-0000-4000-8000-000000000811";
const statusId = "00000000-0000-4000-8000-000000000812";
const paidId = "00000000-0000-4000-8000-000000000813";
const dueId = "00000000-0000-4000-8000-000000000814";
// In the module but not in the view: only the complete record holds it.
const notesId = "00000000-0000-4000-8000-000000000815";

const statusOptions = [
  { id: "active", label: "Active" },
  { id: "former", label: "Former" },
  { id: "paused", label: "Paused" },
];

const fields = [
  wireField({
    id: nameId,
    module_id: moduleId,
    name: "Name",
    type: "text",
    required: true,
    position: 0,
  }),
  wireField({
    id: statusId,
    module_id: moduleId,
    name: "Status",
    type: "select",
    required: true,
    position: 1,
    config: { options: statusOptions },
  }),
  wireField({
    id: paidId,
    module_id: moduleId,
    name: "Paid",
    type: "boolean",
    position: 2,
  }),
  wireField({
    id: dueId,
    module_id: moduleId,
    name: "Due",
    type: "date",
    position: 3,
  }),
  wireField({
    id: notesId,
    module_id: moduleId,
    name: "Notes",
    type: "text",
    position: 4,
  }),
];
const columnIds = [nameId, statusId, paidId, dueId];

type StoredRecord = { data: Record<string, unknown>; updated_at: string };

function wire(stored: StoredRecord, keys?: readonly string[]) {
  const data = keys
    ? Object.fromEntries(
        Object.entries(stored.data).filter(([key]) => keys.includes(key)),
      )
    : stored.data;
  const label = statusOptions.find(
    (option) => option.id === stored.data[statusId],
  )?.label;
  return wireRecord({
    id: recordId,
    module_id: moduleId,
    data,
    display_values: label ? { [statusId]: label } : {},
    created_at: "2026-11-01T08:00:00Z",
    updated_at: stored.updated_at,
    performed_by: userId,
  });
}

type Write = { ifMatch: string | null; data: Record<string, unknown> };

async function installInPlaceApi(
  page: Page,
  options: {
    failNextWrite?: boolean;
    /** A reader ("member" with Read) or a guest; an administrator writes. */
    role?: "admin" | "member" | "guest";
  } = {},
) {
  await installOpenViewEventSource(page);
  let revision = 0;
  const nextRevision = () => {
    revision += 1;
    return `2026-11-12T09:${String(revision).padStart(2, "0")}:00Z`;
  };
  const state = {
    stored: {
      data: {
        [nameId]: "Harbor Supplies",
        [statusId]: "active",
        [paidId]: false,
        [dueId]: "2026-11-20",
        [notesId]: "Keep this note",
      },
      updated_at: "2026-11-12T09:00:00Z",
    } as StoredRecord,
    writes: [] as Write[],
    failNextWrite: options.failNextWrite ?? false,
    /** Holds the next PATCH until `release` runs. */
    hold: null as Promise<void> | null,
  };
  const view = wireView({
    id: viewId,
    module_id: moduleId,
    name: "Contacts",
    is_default: true,
    definition: emptyWireQuery({
      columns: [
        { field_id: nameId, expected_type: "text" },
        { field_id: statusId, expected_type: "select" },
        { field_id: paidId, expected_type: "boolean" },
        { field_id: dueId, expected_type: "date" },
      ],
    }),
    presentation: {
      version: 1,
      layout: "table",
      column_field_ids: columnIds,
      pinned_field_ids: [],
      density: "comfortable",
      wrap: false,
      card_size: "comfortable",
      primary_field_id: nameId,
      secondary_field_id: null,
      group_by_field_id: null,
    },
    created_at: "2026-11-01T08:00:00Z",
    updated_at: "2026-11-01T08:00:00Z",
  });

  await page.route("**/api/**", async (route: Route) => {
    if (isEventStream(route)) return route.fallback();
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (url.pathname === "/api/auth/session")
      return route.fulfill({
        json: {
          authenticated: true,
          user_id: userId,
          organization_id: defaultOrganization.org_id,
          setup_required: false,
          default_organization_blocked: null,
        },
      });
    if (url.pathname === "/api/auth/me")
      return route.fulfill({
        json: authMeBody({
          id: userId,
          role: options.role ?? "admin",
          access:
            options.role && options.role !== "admin"
              ? [
                  {
                    department_id: departmentId,
                    module_id: null,
                    level: "read",
                  },
                ]
              : [],
          default_organization_blocked: null,
        }),
      });
    if (url.pathname === "/api/departments")
      return route.fulfill({
        json: pageOf(
          [
            {
              id: departmentId,
              department_name: "Sales",
              created_at: "2026-11-01T08:00:00Z",
              updated_at: "2026-11-01T08:00:00Z",
              deleted_at: null,
              is_deleted: false,
              performed_by: userId,
            },
          ],
          { limit: 100 },
        ),
      });
    if (url.pathname === `/api/modules/${moduleId}`)
      return route.fulfill({
        json: {
          id: moduleId,
          module_name: "Contacts",
          department_id: departmentId,
          title_field_id: nameId,
          is_deleted: false,
        },
      });
    if (url.pathname === "/api/views/data-sources")
      return route.fulfill({
        json: pageOf(
          [
            {
              id: moduleId,
              name: "Contacts",
              department_id: departmentId,
              title_field_id: nameId,
            },
          ],
          { limit: 100 },
        ),
      });
    if (url.pathname === `/api/views/data-sources/${moduleId}/fields`)
      return route.fulfill({ json: pageOf(fields, { limit: 100 }) });
    if (url.pathname === "/api/views" && method === "GET")
      return route.fulfill({ json: pageOf([view], { limit: 100 }) });
    if (url.pathname === `/api/views/${viewId}` && method === "GET")
      return route.fulfill({ json: view });
    if (url.pathname === "/api/fields")
      return route.fulfill({ json: pageOf([], { limit: 100 }) });
    if (url.pathname === "/api/relationships" && method === "GET")
      return route.fulfill({
        json: keysetPageOf([], { limit: 100, offset: 0, total: 0 }),
      });
    if (url.pathname === "/api/records/query" && method === "POST")
      return route.fulfill({
        json: pageOf([wire(state.stored, columnIds)], { limit: 100 }),
      });
    if (url.pathname === `/api/records/${recordId}` && method === "GET")
      return route.fulfill({ json: wire(state.stored) });
    if (url.pathname === `/api/records/${recordId}` && method === "PATCH") {
      const body = request.postDataJSON() as { data: Record<string, unknown> };
      const ifMatch = request.headers()["if-match"] ?? null;
      state.writes.push({ ifMatch, data: body.data });
      if (state.hold) {
        const held = state.hold;
        state.hold = null;
        await held;
      }
      if (state.failNextWrite) {
        state.failNextWrite = false;
        return route.fulfill({
          status: 503,
          headers: answeredHeaders,
          json: { detail: "Service unavailable" },
        });
      }
      if (ifMatch !== `"${state.stored.updated_at}"`)
        return route.fulfill({
          status: 412,
          json: { detail: "Record changed" },
        });
      state.stored = { data: body.data, updated_at: nextRevision() };
      return route.fulfill({ json: wire(state.stored) });
    }
    return route.fulfill({ status: 404, json: { detail: "Not found" } });
  });

  return {
    state,
    /** Holds the next write; the returned function lets it answer. */
    holdNextWrite() {
      let release!: () => void;
      state.hold = new Promise<void>((done) => {
        release = done;
      });
      return release;
    },
    /** Another writer saves a value; this page has not read it yet. */
    changeElsewhere(data: Record<string, unknown>) {
      state.stored = {
        data: { ...state.stored.data, ...data },
        updated_at: nextRevision(),
      };
    },
  };
}

/** The record header's in-place status (DR-2.5). */
function headerStatus(sheet: Locator) {
  return sheet.locator("header").getByRole("status");
}

async function openRecord(page: Page) {
  await page.goto(
    `/openview?section=views&module=${moduleId}&view=${viewId}&record=${recordId}`,
  );
  const sheet = await openedSheet(
    page.getByRole("dialog", { name: "Record details" }),
  );
  await expect(sheet.getByRole("tab", { name: "Details" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  return sheet;
}

test("UF-C2.2 a Choice list and a Checkbox save in place, each with the complete record and the last revision", async ({
  page,
}) => {
  const api = await installInPlaceApi(page);
  const sheet = await openRecord(page);
  const status = sheet.getByRole("combobox", { name: "Status", exact: true });
  await expect(status).toHaveValue("active");
  // A required Choice list offers no "None" in place (DR-2.3).
  await expect(status.getByRole("option")).toHaveText([
    "Active",
    "Former",
    "Paused",
  ]);
  await status.selectOption("former");
  await expect.poll(() => api.state.writes.length).toBe(1);
  expect(api.state.writes[0]).toEqual({
    ifMatch: '"2026-11-12T09:00:00Z"',
    data: {
      [nameId]: "Harbor Supplies",
      [statusId]: "former",
      [paidId]: false,
      [dueId]: "2026-11-20",
      [notesId]: "Keep this note",
    },
  });
  await expect(status).toHaveValue("former");
  await expect(status).toBeEnabled();
  // The next commit sends the revision of the last response (DR-2.13).
  await sheet.getByRole("checkbox", { name: "Paid", exact: true }).click();
  await expect.poll(() => api.state.writes.length).toBe(2);
  expect(api.state.writes[1]).toEqual({
    ifMatch: '"2026-11-12T09:01:00Z"',
    data: {
      [nameId]: "Harbor Supplies",
      [statusId]: "former",
      [paidId]: true,
      [dueId]: "2026-11-20",
      [notesId]: "Keep this note",
    },
  });
  await expect(
    sheet.getByRole("checkbox", { name: "Paid", exact: true }),
  ).toBeChecked();
  // Text values stay plain; only Edit changes them (DR-2.9).
  await expect(sheet.getByRole("textbox", { name: "Name" })).toHaveCount(0);
  await expect(sheet.getByRole("button", { name: "Save changes" })).toHaveCount(
    0,
  );
});

test("UF-C2.2 a Date commits on Enter, and Escape puts back the stored value", async ({
  page,
}) => {
  const api = await installInPlaceApi(page);
  const sheet = await openRecord(page);
  const due = sheet.getByLabel("Due", { exact: true });
  await expect(due).toHaveValue("2026-11-20");
  await due.fill("2026-11-25");
  await due.press("Escape");
  await expect(due).toHaveValue("2026-11-20");
  await due.fill("2026-11-27");
  await due.press("Enter");
  await expect.poll(() => api.state.writes.length).toBe(1);
  expect(api.state.writes[0]?.data[dueId]).toBe("2026-11-27");
  await expect(due).toHaveValue("2026-11-27");
});

test("UF-C2.6 a value someone else changed is not overwritten: the field shows theirs and says why", async ({
  page,
}) => {
  const api = await installInPlaceApi(page);
  const sheet = await openRecord(page);
  const status = sheet.getByRole("combobox", { name: "Status", exact: true });
  await expect(status).toHaveValue("active");
  api.changeElsewhere({ [statusId]: "former" });
  await status.selectOption("paused");
  await expect.poll(() => api.state.writes.length).toBe(1);
  await expect(status).toHaveValue("former");
  await expect(status).toHaveAccessibleDescription(
    "Someone changed this record. It shows their value now.",
  );
  expect(api.state.stored.data[statusId]).toBe("former");
  await expect(headerStatus(sheet)).toHaveCount(0);
});

test("UF-C2.6 a failed save puts back the stored value with Not saved and the reference", async ({
  page,
}) => {
  const api = await installInPlaceApi(page, { failNextWrite: true });
  const sheet = await openRecord(page);
  const status = sheet.getByRole("combobox", { name: "Status", exact: true });
  await status.selectOption("paused");
  await expect.poll(() => api.state.writes.length).toBe(1);
  await expect(status).toHaveValue("active");
  await expect(status).toHaveAccessibleDescription(/^Not saved\. Try again\./);
  await expect(sheet.getByText(answeredReference)).toBeVisible();
  await expect(headerStatus(sheet)).toHaveCount(0);
});

test("UF-C2.2 while a value saves, the header reads Saving and the other controls and Edit wait", async ({
  page,
}) => {
  const api = await installInPlaceApi(page);
  const sheet = await openRecord(page);
  const status = sheet.getByRole("combobox", { name: "Status", exact: true });
  const release = api.holdNextWrite();
  await status.selectOption("former");
  await expect(headerStatus(sheet)).toHaveText("Saving…");
  await expect(status).toBeDisabled();
  await expect(status).toHaveAttribute("aria-busy", "true");
  await expect(
    sheet.getByRole("checkbox", { name: "Paid", exact: true }),
  ).toBeDisabled();
  await expect(
    sheet.getByRole("button", { name: "Edit record", exact: true }),
  ).toBeDisabled();
  release();
  await expect(headerStatus(sheet)).toHaveText("Status changed to Former.");
  await expect(
    sheet.getByRole("button", { name: "Undo", exact: true }),
  ).toBeVisible();
  await expect(
    sheet.getByRole("button", { name: "Edit record", exact: true }),
  ).toBeEnabled();
  expect(api.state.writes).toHaveLength(1);
  // The page reads the record again: the Updated date and the list row follow.
  await expect(sheet.locator("header time")).toHaveAttribute(
    "datetime",
    "2026-11-12T09:01:00Z",
  );
  await expect(page.locator(`[data-record-id="${recordId}"]`)).toContainText(
    "Former",
  );
});

test("UF-C2.3 Undo writes the previous value back with the revision of the last response", async ({
  page,
}) => {
  const api = await installInPlaceApi(page);
  const sheet = await openRecord(page);
  const status = sheet.getByRole("combobox", { name: "Status", exact: true });
  await status.selectOption("former");
  await expect(headerStatus(sheet)).toHaveText("Status changed to Former.");
  await sheet.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(headerStatus(sheet)).toHaveText(
    "Status changed back to Active.",
  );
  await expect(sheet.getByRole("button", { name: "Undo" })).toHaveCount(0);
  await expect(status).toHaveValue("active");
  await expect(status).toBeFocused();
  expect(api.state.writes).toHaveLength(2);
  expect(api.state.writes[1]).toEqual({
    ifMatch: '"2026-11-12T09:01:00Z"',
    data: {
      [nameId]: "Harbor Supplies",
      [statusId]: "active",
      [paidId]: false,
      [dueId]: "2026-11-20",
      [notesId]: "Keep this note",
    },
  });
  expect(api.state.stored.data[statusId]).toBe("active");
});

test("UF-C2.6 an Undo after someone else's change is not undone, and the field shows their value", async ({
  page,
}) => {
  const api = await installInPlaceApi(page);
  const sheet = await openRecord(page);
  const status = sheet.getByRole("combobox", { name: "Status", exact: true });
  await status.selectOption("former");
  await expect(headerStatus(sheet)).toHaveText("Status changed to Former.");
  api.changeElsewhere({ [statusId]: "paused" });
  await sheet.getByRole("button", { name: "Undo", exact: true }).click();
  await expect(headerStatus(sheet)).toHaveText(
    "Not undone. Someone changed this record after you.",
  );
  await expect(sheet.getByRole("button", { name: "Undo" })).toHaveCount(0);
  await expect(status).toHaveValue("paused");
  expect(api.state.writes).toHaveLength(2);
  expect(api.state.stored.data[statusId]).toBe("paused");
});

for (const role of ["member", "guest"] as const) {
  test(`UF-C2.5 a ${role === "member" ? "reader" : "guest"} sees plain values and no in-place control`, async ({
    page,
  }) => {
    const api = await installInPlaceApi(page, { role });
    const sheet = await openRecord(page);
    await expect(sheet.getByText("Read-only", { exact: true })).toBeVisible();
    await expect(sheet.getByText("Active", { exact: true })).toBeVisible();
    await expect(sheet.getByRole("combobox")).toHaveCount(0);
    await expect(sheet.getByRole("checkbox")).toHaveCount(0);
    await expect(sheet.getByRole("textbox")).toHaveCount(0);
    await sheet.getByText("Active", { exact: true }).click();
    await expect(sheet.getByRole("combobox")).toHaveCount(0);
    await expect(headerStatus(sheet)).toHaveCount(0);
    expect(api.state.writes).toEqual([]);
  });
}

test("UF-C2.2 UF-C2.3 focus stays on the used control through each in-place save and Undo", async ({
  page,
}) => {
  const api = await installInPlaceApi(page);
  const sheet = await openRecord(page);
  // Counts each time focus falls back to the sheet itself: the control the
  // person used was blurred, removed, or disabled under them.
  await page.evaluate(() => {
    const dialog = document.querySelector('[role="dialog"]');
    const counter = { lost: 0 };
    Object.assign(window, { focusFallbacks: counter });
    dialog?.addEventListener("focusin", (event) => {
      if (event.target === dialog) counter.lost += 1;
    });
  });
  const fallbacks = () =>
    page.evaluate(
      () =>
        (window as unknown as { focusFallbacks: { lost: number } })
          .focusFallbacks.lost,
    );
  const paid = sheet.getByRole("checkbox", { name: "Paid", exact: true });
  await paid.focus();
  const release = api.holdNextWrite();
  await page.keyboard.press("Space");
  await expect(headerStatus(sheet)).toHaveText("Saving…");
  await expect(paid).toBeFocused();
  release();
  await expect(headerStatus(sheet)).toHaveText("Paid turned on.");
  await expect(paid).toBeFocused();

  const status = sheet.getByRole("combobox", { name: "Status", exact: true });
  await status.focus();
  await status.selectOption("former");
  await expect(headerStatus(sheet)).toHaveText("Status changed to Former.");
  await expect(status).toBeFocused();

  const due = sheet.getByLabel("Due", { exact: true });
  await due.fill("2026-11-27");
  await due.press("Enter");
  await expect(headerStatus(sheet)).toHaveText(/^Due changed to /);
  await expect(due).toBeFocused();

  // Undo removes its own button; focus goes to the field it changes back.
  await sheet.getByRole("button", { name: "Undo", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(headerStatus(sheet)).toHaveText(/^Due changed back to /);
  await expect(due).toBeFocused();
  expect(api.state.writes).toHaveLength(4);
  expect(await fallbacks()).toBe(0);
});
