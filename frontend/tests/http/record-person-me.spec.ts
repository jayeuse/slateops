import {
  authMeBody,
  defaultOrganization,
  expect,
  isEventStream,
  test,
  type Page,
  type Route,
} from "./helpers/test";
import { installOpenViewEventSource } from "./helpers/openview-event-source";
import { keysetPageOf, pageOf } from "../helpers/pagination";
import { emptyWireQuery } from "../helpers/query-definitions";
import { wireField, wireRecord, wireView } from "../helpers/wire";
import { openedSheet } from "./helpers/settled";

// "Me" first in the record form's User picker (candidate 4 of
// docs/specs/subtle-interactions.md, SI-4.1 and SI-4.3, DR-SI-4.1 and
// DR-SI-4.2): when the module's assignable people include the signed-in
// person, the picker lists "Me (<name>)" first after "No one", and the person
// is not listed again. When the first page has more people and the person is
// not on it, the picker reads the list once more with the person's name. The
// Kanban assignee picker is owned by tests/http/boards-card-quick-actions.spec.ts.

const userId = "00000000-0000-4000-8000-000000000a01";
const anaId = "00000000-0000-4000-8000-000000000a02";
const benId = "00000000-0000-4000-8000-000000000a03";
const departmentId = "00000000-0000-4000-8000-000000000a11";
const moduleId = "00000000-0000-4000-8000-000000000a12";
const viewId = "00000000-0000-4000-8000-000000000a13";
const recordId = "00000000-0000-4000-8000-000000000a14";
const nameId = "00000000-0000-4000-8000-000000000a21";
const ownerId = "00000000-0000-4000-8000-000000000a22";

const people = {
  [userId]: { display_name: "Rosa Lim", username: "rosa.lim" },
  [anaId]: { display_name: "Ana Santos", username: "ana.santos" },
  [benId]: { display_name: "Ben Reyes", username: "ben.reyes" },
} as const;

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
    id: ownerId,
    module_id: moduleId,
    name: "Owner",
    type: "user",
    position: 1,
  }),
];

type Stored = { data: Record<string, unknown>; updated_at: string };

function wire(stored: Stored) {
  const owner = stored.data[ownerId];
  const label =
    typeof owner === "string" && owner in people
      ? people[owner as keyof typeof people].display_name
      : null;
  return wireRecord({
    id: recordId,
    module_id: moduleId,
    data: stored.data,
    display_values: label ? { [ownerId]: label } : {},
    created_at: "2026-11-01T08:00:00Z",
    updated_at: stored.updated_at,
    performed_by: userId,
  });
}

/**
 * A Contacts module whose Owner field the signed-in writer, Rosa Lim, edits.
 * `firstPage` is the assignable people read without a search; a read with a
 * search returns the people whose name or username holds it, as the server's
 * search does.
 */
async function installOwnerApi(
  page: Page,
  options: { firstPage: string[]; firstPageHasMore?: boolean },
) {
  await installOpenViewEventSource(page);
  const state = {
    stored: {
      data: { [nameId]: "Harbor Supplies", [ownerId]: null },
      updated_at: "2026-11-12T09:00:00Z",
    } as Stored,
    writes: [] as Record<string, unknown>[],
    /** The `search` of each assignable people read, in order. */
    assignableSearches: [] as string[],
  };
  const view = wireView({
    id: viewId,
    module_id: moduleId,
    name: "Contacts",
    is_default: true,
    definition: emptyWireQuery({
      columns: [
        { field_id: nameId, expected_type: "text" },
        { field_id: ownerId, expected_type: "user" },
      ],
    }),
    presentation: {
      version: 1,
      layout: "table",
      column_field_ids: [nameId, ownerId],
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
  const person = (id: string) => ({ id, ...people[id as keyof typeof people] });

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
        json: authMeBody({ id: userId, role: "admin", ...people[userId] }),
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
    if (url.pathname === `/api/modules/${moduleId}/assignable-users`) {
      const search = url.searchParams.get("search") ?? "";
      state.assignableSearches.push(search);
      if (!search)
        return route.fulfill({
          headers: { "cache-control": "private, no-store" },
          json: pageOf(options.firstPage.map(person), {
            limit: 100,
            total:
              options.firstPage.length + (options.firstPageHasMore ? 1 : 0),
          }),
        });
      const found = Object.keys(people)
        .filter((id) =>
          Object.values(people[id as keyof typeof people]).some((name) =>
            name.toLowerCase().includes(search.toLowerCase()),
          ),
        )
        .map(person);
      return route.fulfill({
        headers: { "cache-control": "private, no-store" },
        json: pageOf(found, { limit: 100 }),
      });
    }
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
        json: pageOf([wire(state.stored)], { limit: 100 }),
      });
    if (url.pathname === `/api/records/${recordId}` && method === "GET")
      return route.fulfill({ json: wire(state.stored) });
    if (url.pathname === `/api/records/${recordId}` && method === "PATCH") {
      const body = request.postDataJSON() as { data: Record<string, unknown> };
      state.writes.push(body.data);
      state.stored = { data: body.data, updated_at: "2026-11-12T09:01:00Z" };
      return route.fulfill({ json: wire(state.stored) });
    }
    return route.fulfill({ status: 404, json: { detail: "Not found" } });
  });
  return state;
}

/** Opens the record sheet and its Edit form; returns the sheet and Owner. */
async function editOwner(page: Page) {
  await page.goto(
    `/openview?section=views&module=${moduleId}&view=${viewId}&record=${recordId}`,
  );
  const sheet = await openedSheet(
    page.getByRole("dialog", { name: "Record details" }),
  );
  await sheet.getByRole("button", { name: "Edit record", exact: true }).click();
  const owner = sheet.getByRole("combobox", { name: "Owner", exact: true });
  await expect(owner).toBeEnabled();
  return { sheet, owner };
}

test("SI-C4.1 the writer picks Me first in the Owner picker, and after Save changes the record shows the writer", async ({
  page,
}) => {
  const api = await installOwnerApi(page, {
    firstPage: [anaId, benId, userId],
  });
  const { sheet, owner } = await editOwner(page);
  // "Me" follows the empty choice, and the writer is not listed again.
  await expect(owner.getByRole("option")).toHaveText([
    "No one",
    "Me (Rosa Lim)",
    "Ana Santos",
    "Ben Reyes",
  ]);
  await owner.selectOption({ label: "Me (Rosa Lim)" });
  await expect(owner).toHaveValue(userId);
  await sheet
    .getByRole("button", { name: "Save changes", exact: true })
    .click();
  await expect(
    sheet.getByRole("button", { name: "Save changes", exact: true }),
  ).toHaveCount(0);
  // The Details tab names the writer as the Owner.
  await expect(
    sheet
      .getByRole("tabpanel", { name: "Details" })
      .getByRole("definition")
      .filter({ hasText: "Rosa Lim" }),
  ).toBeVisible();
  expect(api.writes).toEqual([
    { [nameId]: "Harbor Supplies", [ownerId]: userId },
  ]);
  // The writer was on the first page: no second read.
  expect(api.assignableSearches).toEqual([""]);
});

test("SI-C4.1 when the first page has more people and the writer is not on it, one read by the writer's username finds them", async ({
  page,
}) => {
  const api = await installOwnerApi(page, {
    firstPage: [anaId, benId],
    firstPageHasMore: true,
  });
  const { owner } = await editOwner(page);
  await expect(owner.getByRole("option")).toHaveText([
    "No one",
    "Me (Rosa Lim)",
    "Ana Santos",
    "Ben Reyes",
  ]);
  expect(api.assignableSearches).toEqual(["", "rosa.lim"]);
});

test("SI-C4.3 when the assignable people exclude the writer, the Owner picker has no Me", async ({
  page,
}) => {
  const api = await installOwnerApi(page, { firstPage: [anaId, benId] });
  const { owner } = await editOwner(page);
  await expect(owner.getByRole("option")).toHaveText([
    "No one",
    "Ana Santos",
    "Ben Reyes",
  ]);
  // The complete list has no writer, so no read by name follows.
  expect(api.assignableSearches).toEqual([""]);
});
