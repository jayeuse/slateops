import {
  answeredHeaders,
  authMeBody,
  defaultOrganization,
  isEventStream,
  type Page,
  type Route,
} from "./test";
import { installOpenViewEventSource } from "./openview-event-source";
import { keysetPageOf, pageOf } from "../../helpers/pagination";
import { emptyWireQuery } from "../../helpers/query-definitions";
import { wireField, wireRecord, wireView } from "../../helpers/wire";

// A Contacts module for the OpenView list actions (candidates 1 and 5 of
// docs/specs/subtle-interactions.md). The mock keeps the server's rules that
// the browser must meet: the records query applies the view's conditions and
// returns only its columns; `batch-update` refuses a stale revision per item
// (`stale`), gives each write a new `updated_at`, and keeps the other values.

export const listIds = {
  user: "00000000-0000-4000-8000-000000000a01",
  department: "00000000-0000-4000-8000-000000000a02",
  module: "00000000-0000-4000-8000-000000000a03",
  view: "00000000-0000-4000-8000-000000000a04",
  name: "00000000-0000-4000-8000-000000000a11",
  status: "00000000-0000-4000-8000-000000000a12",
  paid: "00000000-0000-4000-8000-000000000a13",
  owner: "00000000-0000-4000-8000-000000000a14",
  person: "00000000-0000-4000-8000-000000000a21",
} as const;

export const recordId = (index: number) =>
  `00000000-0000-4000-8000-${String(2800 + index).padStart(12, "0")}`;

const statusOptions = [
  { id: "active", label: "Active" },
  { id: "former", label: "Former" },
  { id: "prospect", label: "Prospect" },
];
export const statusLabel = (id: unknown) =>
  statusOptions.find((option) => option.id === id)?.label;

const fields = [
  wireField({
    id: listIds.name,
    module_id: listIds.module,
    name: "Name",
    type: "text",
    required: true,
    position: 0,
  }),
  wireField({
    id: listIds.status,
    module_id: listIds.module,
    name: "Status",
    type: "select",
    required: true,
    position: 1,
    config: { options: statusOptions },
  }),
  wireField({
    id: listIds.paid,
    module_id: listIds.module,
    name: "Paid",
    type: "boolean",
    position: 2,
  }),
  wireField({
    id: listIds.owner,
    module_id: listIds.module,
    name: "Owner",
    type: "user",
    position: 3,
  }),
];
type WireQuery = ReturnType<typeof emptyWireQuery>;
type WireFilter = WireQuery["filters"][number];

const columns: WireQuery["columns"] = [
  { field_id: listIds.name, expected_type: "text" },
  { field_id: listIds.status, expected_type: "select" },
  { field_id: listIds.paid, expected_type: "boolean" },
  { field_id: listIds.owner, expected_type: "user" },
];
const columnIds = columns.map((column) => column.field_id);

/** The names of the first records, in list order. */
export const recordNames = [
  "Ana Cruz",
  "Ben Ortiz",
  "Chen Wu",
  "Dana Lim",
  "Eli Park",
  "Fay Moss",
  "Gil Santos",
  "Hana Ito",
  "Ivo Brandt",
  "Jo Reyes",
  "Kai Lund",
  "Lea Novak",
];
/** Each record's Status, in list order: Former only on the 2nd and 5th. */
const statusOrder = [
  "active",
  "former",
  "prospect",
  "active",
  "former",
  "active",
  "prospect",
  "active",
  "prospect",
  "active",
  "active",
  "prospect",
];

type Stored = {
  data: Record<string, unknown>;
  updated_at: string;
  is_deleted: boolean;
};

type BatchItem = {
  record_id: string;
  revision: string;
  field_id: string;
  value: unknown;
};

export type Viewer = "admin" | "writer" | "reader" | "guest" | "manager";

const viewerAccess: Record<Viewer, { role: string; access: unknown[] }> = {
  admin: { role: "admin", access: [] },
  writer: {
    role: "member",
    access: [
      {
        department_id: listIds.department,
        module_id: listIds.module,
        level: "write",
      },
    ],
  },
  reader: {
    role: "member",
    access: [
      { department_id: listIds.department, module_id: null, level: "read" },
    ],
  },
  guest: {
    role: "guest",
    access: [
      { department_id: listIds.department, module_id: null, level: "read" },
    ],
  },
  manager: {
    role: "member",
    access: [
      { department_id: listIds.department, module_id: null, level: "manage" },
    ],
  },
};

/** A forced item result: what the server answers for that record. */
export type ForcedResult =
  | { status: "forbidden" }
  | { status: "invalid"; field_id: string | null; message: string };

export async function installListApi(
  page: Page,
  options: {
    viewer?: Viewer;
    /** How many records the module holds (12 by default). */
    count?: number;
    /** The saved view's conditions and their logic. */
    filters?: WireFilter[];
    logic?: "and" | "or";
    deleted?: "exclude" | "include" | "only";
    /** Pin the Name column, so its cells and the boxes are sticky. */
    pinned?: boolean;
  } = {},
) {
  await installOpenViewEventSource(page);
  let revision = 0;
  const nextRevision = () => {
    revision += 1;
    return `2026-11-13T10:${String(revision).padStart(2, "0")}:00Z`;
  };
  const records = new Map<string, Stored>();
  for (let index = 0; index < (options.count ?? 12); index += 1)
    records.set(recordId(index), {
      data: {
        [listIds.name]: recordNames[index] ?? `Contact ${index + 1}`,
        [listIds.status]: statusOrder[index % statusOrder.length],
        [listIds.paid]: false,
        [listIds.owner]: listIds.person,
      },
      updated_at: `2026-11-13T08:${String(index).padStart(2, "0")}:00Z`,
      is_deleted: false,
    });
  const state = {
    records,
    /** Every `batch-update` body, in order. */
    batches: [] as { module_id: string; items: BatchItem[] }[],
    /** The definitions the records query read. */
    queries: [] as { filters: WireFilter[]; logic: string }[],
    /** Requests that would change a saved view. */
    viewWrites: [] as string[],
    /** Results forced for the next batch, by record id. */
    forced: new Map<string, ForcedResult>(),
    /** Answers the next batch with this status instead of results. */
    failNext: null as null | { status: number; detail: string },
    hold: null as Promise<void> | null,
  };

  const wire = (id: string, stored: Stored, keys?: readonly string[]) => {
    const data = keys
      ? Object.fromEntries(
          Object.entries(stored.data).filter(([key]) => keys.includes(key)),
        )
      : stored.data;
    const label = statusLabel(stored.data[listIds.status]);
    return wireRecord({
      id,
      module_id: listIds.module,
      data,
      display_values: {
        ...(label ? { [listIds.status]: label } : {}),
        [listIds.owner]: "Mara Harbone",
      },
      created_at: "2026-11-01T08:00:00Z",
      updated_at: stored.updated_at,
      is_deleted: stored.is_deleted,
      deleted_at: stored.is_deleted ? "2026-11-12T08:00:00Z" : null,
    });
  };

  const matches = (
    stored: Stored,
    definition: { logic: string; filters: WireFilter[]; deleted: string },
  ) => {
    if (definition.deleted === "exclude" && stored.is_deleted) return false;
    if (definition.deleted === "only" && !stored.is_deleted) return false;
    const results = definition.filters.map((filter) => {
      const value = stored.data[filter.field_id];
      if (filter.operator === "eq") return value === filter.value;
      if (filter.operator === "neq") return value !== filter.value;
      return true;
    });
    if (results.length === 0) return true;
    return definition.logic === "or"
      ? results.some(Boolean)
      : results.every(Boolean);
  };

  const view = wireView({
    id: listIds.view,
    module_id: listIds.module,
    name: "All contacts",
    is_default: true,
    definition: emptyWireQuery({
      logic: options.logic ?? "and",
      columns,
      filters: options.filters ?? [],
      deleted: options.deleted ?? "exclude",
    }),
    presentation: {
      version: 1,
      layout: "table",
      column_field_ids: columnIds,
      pinned_field_ids: options.pinned ? [listIds.name] : [],
      density: "comfortable",
      wrap: false,
      card_size: "comfortable",
      primary_field_id: listIds.name,
      secondary_field_id: null,
      group_by_field_id: null,
    },
    created_at: "2026-11-01T08:00:00Z",
    updated_at: "2026-11-01T08:00:00Z",
  });
  const viewer = viewerAccess[options.viewer ?? "writer"];

  await page.route("**/api/**", async (route: Route) => {
    if (isEventStream(route)) return route.fallback();
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    const path = url.pathname;
    if (path === "/api/auth/session")
      return route.fulfill({
        json: {
          authenticated: true,
          user_id: listIds.user,
          organization_id: defaultOrganization.org_id,
          setup_required: false,
          default_organization_blocked: null,
        },
      });
    if (path === "/api/auth/me")
      return route.fulfill({
        json: authMeBody({
          id: listIds.user,
          role: viewer.role,
          access: viewer.access,
          default_organization_blocked: null,
        }),
      });
    if (path === "/api/departments")
      return route.fulfill({
        json: pageOf(
          [
            {
              id: listIds.department,
              department_name: "Sales",
              created_at: "2026-11-01T08:00:00Z",
              updated_at: "2026-11-01T08:00:00Z",
              deleted_at: null,
              is_deleted: false,
              performed_by: listIds.user,
            },
          ],
          { limit: 100 },
        ),
      });
    if (path === `/api/modules/${listIds.module}`)
      return route.fulfill({
        json: {
          id: listIds.module,
          module_name: "Contacts",
          department_id: listIds.department,
          title_field_id: listIds.name,
          is_deleted: false,
        },
      });
    if (path === "/api/views/data-sources")
      return route.fulfill({
        json: pageOf(
          [
            {
              id: listIds.module,
              name: "Contacts",
              department_id: listIds.department,
              title_field_id: listIds.name,
            },
          ],
          { limit: 100 },
        ),
      });
    if (path === `/api/views/data-sources/${listIds.module}/fields`)
      return route.fulfill({ json: pageOf(fields, { limit: 100 }) });
    if (path.startsWith("/api/views") && method !== "GET") {
      state.viewWrites.push(`${method} ${path}`);
      return route.fulfill({ status: 403, json: { detail: "Forbidden" } });
    }
    if (path === "/api/views" && method === "GET")
      return route.fulfill({ json: pageOf([view], { limit: 100 }) });
    if (path === `/api/views/${listIds.view}` && method === "GET")
      return route.fulfill({ json: view });
    if (path === "/api/fields")
      return route.fulfill({ json: pageOf([], { limit: 100 }) });
    if (path === "/api/relationships" && method === "GET")
      return route.fulfill({
        json: keysetPageOf([], { limit: 100, offset: 0, total: 0 }),
      });
    if (path === "/api/records/aggregate-query" && method === "POST") {
      // The quick-filter strip's counts for Status, under the other conditions.
      const body = request.postDataJSON() as {
        definition: { logic: string; filters: WireFilter[]; deleted: string };
        limit: number;
        offset: number;
      };
      const items = statusOptions.flatMap((option) => {
        const count = [...records.values()].filter(
          (stored) =>
            matches(stored, body.definition) &&
            stored.data[listIds.status] === option.id,
        ).length;
        return count > 0
          ? [
              {
                key: option.id,
                label: option.label,
                value: String(count),
                record_count: count,
              },
            ]
          : [];
      });
      return route.fulfill({
        json: pageOf(items, { limit: body.limit, offset: body.offset }),
      });
    }
    if (path === "/api/records/query" && method === "POST") {
      const body = request.postDataJSON() as {
        definition: {
          logic: string;
          filters: WireFilter[];
          deleted: string;
          search: string | null;
        };
        limit: number;
        offset: number;
      };
      state.queries.push({
        filters: body.definition.filters,
        logic: body.definition.logic,
      });
      // An open record's sheet reads that record by its id.
      const search = body.definition.search;
      const listed = [...records.entries()].filter(([id, stored]) =>
        search && records.has(search)
          ? id === search
          : matches(stored, body.definition),
      );
      return route.fulfill({
        json: pageOf(
          listed
            .slice(body.offset, body.offset + body.limit)
            .map(([id, stored]) => wire(id, stored, columnIds)),
          { limit: body.limit, offset: body.offset, total: listed.length },
        ),
      });
    }
    const single = /^\/api\/records\/([0-9a-f-]{36})$/.exec(path);
    if (single && method === "GET") {
      const stored = records.get(single[1]);
      return stored
        ? route.fulfill({ json: wire(single[1], stored) })
        : route.fulfill({ status: 404, json: { detail: "Not found" } });
    }
    if (path === "/api/records/batch-update" && method === "POST") {
      const body = request.postDataJSON() as {
        module_id: string;
        items: BatchItem[];
      };
      state.batches.push(body);
      if (state.hold) {
        const held = state.hold;
        state.hold = null;
        await held;
      }
      if (state.failNext) {
        const failure = state.failNext;
        state.failNext = null;
        return route.fulfill({
          status: failure.status,
          headers: answeredHeaders,
          json: { detail: failure.detail },
        });
      }
      const results = body.items.map((item) => {
        const stored = records.get(item.record_id);
        const forced = state.forced.get(item.record_id);
        if (forced?.status === "forbidden" || !stored)
          return { status: "forbidden", record_id: item.record_id };
        if (forced?.status === "invalid")
          return {
            status: "invalid",
            record_id: item.record_id,
            errors: [
              {
                code: "invalid_value",
                field_id: forced.field_id,
                message: forced.message,
              },
            ],
            truncated: false,
          };
        if (Date.parse(item.revision) !== Date.parse(stored.updated_at))
          return { status: "stale", record_id: item.record_id };
        const next: Stored = {
          ...stored,
          data: { ...stored.data, [item.field_id]: item.value },
          updated_at: nextRevision(),
        };
        records.set(item.record_id, next);
        return {
          status: "updated",
          record_id: item.record_id,
          record: wire(item.record_id, next),
        };
      });
      state.forced.clear();
      return route.fulfill({ json: { results } });
    }
    return route.fulfill({ status: 404, json: { detail: "Not found" } });
  });

  return {
    state,
    /** Another writer saves values; this page has not read them yet. */
    changeElsewhere(index: number, data: Record<string, unknown>) {
      const stored = records.get(recordId(index));
      if (!stored) throw new Error(`No record ${index}`);
      records.set(recordId(index), {
        ...stored,
        data: { ...stored.data, ...data },
        updated_at: nextRevision(),
      });
    },
    /** Holds the next batch; the returned function lets it answer. */
    holdNextBatch() {
      let release!: () => void;
      state.hold = new Promise<void>((done) => {
        release = done;
      });
      return release;
    },
    stored(index: number) {
      return records.get(recordId(index))?.data;
    },
  };
}
