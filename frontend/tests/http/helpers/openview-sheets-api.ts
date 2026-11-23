import { answeredHeaders, type Page, type Route } from "./test";
import { wireRecord } from "../../helpers/wire";

// The sheet routes of docs/specs/sheets.md D10 that the frontend calls:
// My sheets (1), a record's sheets (2), a module's sheets (2a), create (3) and
// restore (8). Register it after any catch-all `/api/**` route, so it wins.

export const sheetPeople = {
  viewer: {
    id: "00000000-0000-4000-8000-0000000006a1",
    name: "Andrea Villamor",
  },
  colleague: {
    id: "00000000-0000-4000-8000-0000000006a2",
    name: "Bernard Ocampo",
  },
} as const;

export type WireSheetSummary = ReturnType<typeof wireSheetSummary>;

export function wireSheetSummary(
  id: string,
  title: string,
  options: {
    owner?: "viewer" | "colleague";
    level?: "owner" | "edit" | "view";
    recordId?: string | null;
    moduleId?: string | null;
    rows?: number;
    updatedAt?: string;
    deleted?: boolean;
    deletedAt?: string;
    /** The record's title; a module sheet carries its module's name. */
    recordTitle?: string;
    moduleName?: string;
    /** The owner's sheet has a live share (owner only). */
    shared?: boolean;
    /** The group whose share alone gives the viewer the sheet. */
    accessGroup?: string;
  } = {},
) {
  const owner = sheetPeople[options.owner ?? "viewer"];
  const moduleId = options.moduleId ?? null;
  const moduleName = options.moduleName ?? "Faculty Members";
  const level =
    options.level ?? (options.owner === "colleague" ? "view" : "owner");
  const updatedAt = options.updatedAt ?? "2026-11-21T08:30:00Z";
  return {
    id,
    record_id: moduleId
      ? null
      : (options.recordId ?? "00000000-0000-4000-8000-0000000006b1"),
    module_id: moduleId,
    title,
    owner: { id: owner.id, display_name: owner.name },
    state: "private" as "private" | "open",
    my_level: level,
    live_row_count: options.rows ?? 0,
    revision: 1,
    updated_at: updatedAt,
    is_deleted: options.deleted ?? false,
    deleted_at: options.deleted ? (options.deletedAt ?? updatedAt) : null,
    anchor_title: moduleId
      ? moduleName
      : (options.recordTitle ?? "Andrea Villamor"),
    module_name: moduleName,
    shared: level === "owner" ? (options.shared ?? false) : null,
    access_group: options.accessGroup ?? null,
  };
}

export function wireSheetDetail(summary: WireSheetSummary) {
  return {
    ...summary,
    structure: {
      structureVersion: 1,
      nextColumnSeq: 1,
      columns: [],
      groups: [],
      totals: {},
    },
    etag: `"${summary.id}:${summary.revision}"`,
    created_at: "2026-11-01T08:30:00Z",
  };
}

function listBody(items: WireSheetSummary[], url: URL) {
  return {
    items,
    pagination: {
      limit: Number(url.searchParams.get("limit") ?? 25),
      offset: Number(url.searchParams.get("offset") ?? 0),
      count: items.length,
      total: items.length,
      has_more: false,
      total_is_capped: false,
    },
  };
}

type CreateBody = {
  record_id?: string;
  module_id?: string;
  title: string;
  source: { kind: string };
};

/** A refusal the next create answers with instead of 201. */
export type CreateRefusal = { status: number; code: string; message: string };

export async function installSheetsApi(
  page: Page,
  lists: { live?: WireSheetSummary[]; deleted?: WireSheetSummary[] } = {},
  options: { failFirstMyRead?: boolean } = {},
) {
  const state = {
    live: [...(lists.live ?? [])],
    deleted: [...(lists.deleted ?? [])],
    restores: [] as string[],
    creates: [] as CreateBody[],
    refuseNextCreate: null as CreateRefusal | null,
    createdId: "00000000-0000-4000-8000-0000000006d1",
  };
  let failMyRead = options.failFirstMyRead ?? false;
  await page.route(
    (url) =>
      url.pathname === "/api/worksheets" ||
      /^\/api\/(records|modules)\/[^/]+\/worksheets$/.test(url.pathname),
    async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.pathname === "/api/worksheets" && request.method() === "POST") {
        const body = request.postDataJSON() as CreateBody;
        state.creates.push(body);
        const refusal = state.refuseNextCreate;
        if (refusal) {
          state.refuseNextCreate = null;
          return route.fulfill({
            status: refusal.status,
            headers: answeredHeaders,
            json: { detail: { code: refusal.code, message: refusal.message } },
          });
        }
        const created = wireSheetSummary(state.createdId, body.title.trim(), {
          recordId: body.record_id ?? null,
          moduleId: body.module_id ?? null,
          updatedAt: "2026-11-22T08:30:00Z",
        });
        state.live = [created, ...state.live];
        return route.fulfill({
          status: 201,
          headers: {
            Location: `/api/worksheets/${created.id}`,
            ETag: `"${created.id}:1"`,
          },
          json: wireSheetDetail(created),
        });
      }
      if (request.method() !== "GET") return route.fallback();
      if (url.pathname === "/api/worksheets") {
        if (failMyRead && url.searchParams.get("deleted") === "exclude") {
          failMyRead = false;
          return route.fulfill({
            status: 503,
            headers: answeredHeaders,
            json: { detail: "Service unavailable" },
          });
        }
        return route.fulfill({
          headers: { "Cache-Control": "no-store" },
          json: listBody(
            url.searchParams.get("deleted") === "only"
              ? state.deleted
              : state.live,
            url,
          ),
        });
      }
      const [, , kind, anchor] = url.pathname.split("/");
      const items = state.live.filter((sheet) =>
        kind === "records"
          ? sheet.record_id === anchor
          : sheet.module_id === anchor,
      );
      return route.fulfill({
        headers: { "Cache-Control": "no-store" },
        json: listBody(items, url),
      });
    },
  );
  // One sheet (route 4) and its rows (route 9): a sheet this fake holds
  // opens with no rows; any other id is not found.
  await page.route(
    (url) => /^\/api\/worksheets\/[^/]+(\/rows\/query)?$/.test(url.pathname),
    (route) => {
      const [, , , id, rows] = new URL(route.request().url()).pathname.split(
        "/",
      );
      const sheet = state.live.find((item) => item.id === id);
      if (!sheet)
        return route.fulfill({
          status: 404,
          json: {
            detail: { code: "worksheet_not_found", message: "Sheet not found" },
          },
        });
      if (!rows && route.request().method() === "GET")
        return route.fulfill({ json: wireSheetDetail(sheet) });
      return route.fulfill({
        json: {
          items: [],
          pagination: {
            limit: 200,
            offset: 0,
            count: 0,
            total: 0,
            has_more: false,
          },
          totals: {},
        },
      });
    },
  );
  await page.route(
    (url) => /^\/api\/worksheets\/[^/]+\/restore$/.test(url.pathname),
    (route) => {
      const id = new URL(route.request().url()).pathname.split("/")[3];
      const sheet = state.deleted.find((item) => item.id === id);
      if (route.request().method() !== "POST" || !sheet)
        return route.fulfill({ status: 404, json: {} });
      state.restores.push(id);
      state.deleted = state.deleted.filter((item) => item.id !== id);
      const restored = { ...sheet, is_deleted: false };
      state.live = [restored, ...state.live];
      return route.fulfill({ json: wireSheetDetail(restored) });
    },
  );
  return state;
}

// ---------------------------------------------------------------- sheet page

export type WireSheetCell =
  | { value: unknown }
  | { link: { record_id: string; label: string } }
  | { unlinked: string }
  | { state: string };

export type WireSheetRow = {
  id: string;
  revision: number;
  etag: string;
  position: number;
  cells: Record<string, WireSheetCell>;
};

export function wireSheetRow(
  index: number,
  cells: Record<string, WireSheetCell>,
): WireSheetRow {
  const id = `00000000-0000-4000-8000-${String(700000 + index).padStart(12, "0")}`;
  return { id, revision: 1, etag: `"${id}:1"`, position: index, cells };
}

/** The department and module a sheet page names in its crumbs. */
export const sheetPlace = {
  department: "00000000-0000-4000-8000-0000000006e1",
  module: "00000000-0000-4000-8000-0000000006e2",
} as const;

type SheetPageDetail = Omit<ReturnType<typeof wireSheetDetail>, "structure"> & {
  structure: unknown;
};

type RowsQuery = {
  limit: number;
  offset: number;
  sort?: { key: string; order: "asc" | "desc" };
  search?: string;
};

/**
 * One sheet's page: its detail (route 4), its rows (route 9, which applies
 * search to link labels and text, sorts by one column and answers pages),
 * the record it sits on, and the department and module the crumbs name.
 * Totals are fixed and cover every row, as the server's do.
 */
export async function installSheetPageApi(
  page: Page,
  sheet: {
    /** The detail as route 4 answers it; the structure is the test's own. */
    detail: SheetPageDetail;
    rows: WireSheetRow[];
    totals: Record<
      string,
      { fn: string; value: unknown; hidden_count: number }
    >;
    recordTitle?: string;
    /** More readable modules, for link columns. */
    modules?: { id: string; name: string; titleFieldId: string }[];
  },
) {
  const state = {
    detail: sheet.detail as SheetPageDetail | null,
    rows: sheet.rows,
    queries: [] as RowsQuery[],
    detailReads: 0,
  };
  const text = (cell: WireSheetCell | undefined) =>
    !cell
      ? ""
      : "link" in cell
        ? cell.link.label
        : "unlinked" in cell
          ? cell.unlinked
          : "value" in cell && cell.value !== null
            ? String(cell.value)
            : "";
  await page.route(
    (url) =>
      url.pathname === `/api/worksheets/${sheet.detail.id}` ||
      url.pathname === `/api/worksheets/${sheet.detail.id}/rows/query`,
    (route) => {
      const request = route.request();
      if (request.method() === "GET") {
        state.detailReads += 1;
        return state.detail
          ? route.fulfill({
              headers: { ETag: state.detail.etag },
              json: state.detail,
            })
          : route.fulfill({
              status: 404,
              json: {
                detail: {
                  code: "worksheet_not_found",
                  message: "Sheet not found",
                },
              },
            });
      }
      if (!state.detail)
        return route.fulfill({
          status: 404,
          json: {
            detail: { code: "worksheet_not_found", message: "Sheet not found" },
          },
        });
      const query = request.postDataJSON() as RowsQuery;
      state.queries.push(query);
      const needle = query.search?.trim().toLowerCase() ?? "";
      let rows = state.rows.filter(
        (row) =>
          !needle ||
          Object.values(row.cells).some((cell) =>
            text(cell).toLowerCase().includes(needle),
          ),
      );
      if (query.sort) {
        const { key, order } = query.sort;
        rows = [...rows].sort((a, b) => {
          const left = Number(text(a.cells[key])) || 0;
          const right = Number(text(b.cells[key])) || 0;
          return order === "asc" ? left - right : right - left;
        });
      }
      const items = rows.slice(query.offset, query.offset + query.limit);
      return route.fulfill({
        json: {
          items,
          pagination: {
            limit: query.limit,
            offset: query.offset,
            count: items.length,
            total: rows.length,
            has_more: query.offset + items.length < rows.length,
          },
          totals: sheet.totals,
        },
      });
    },
  );
  const recordId = sheet.detail.record_id;
  if (recordId)
    await page.route(
      (url) => url.pathname === `/api/records/${recordId}`,
      (route) =>
        route.fulfill({
          json: wireRecord({
            id: recordId,
            module_id: sheetPlace.module,
            data: {},
            created_at: "2026-11-01T08:00:00Z",
            updated_at: "2026-11-01T08:00:00Z",
          }),
        }),
    );
  const page100 = (items: unknown[], url: URL) => ({
    items,
    pagination: {
      limit: Number(url.searchParams.get("limit") ?? 100),
      offset: 0,
      count: items.length,
      total: items.length,
      has_more: false,
      total_is_capped: false,
    },
  });
  await page.route(
    (url) => url.pathname === "/api/departments",
    (route) =>
      route.fulfill({
        json: page100(
          [
            {
              id: sheetPlace.department,
              department_name: "Sales",
              created_at: "2026-11-01T08:00:00Z",
              updated_at: "2026-11-01T08:00:00Z",
              deleted_at: null,
              is_deleted: false,
              performed_by: null,
            },
          ],
          new URL(route.request().url()),
        ),
      }),
  );
  await page.route(
    (url) => url.pathname === "/api/views/data-sources",
    (route) =>
      route.fulfill({
        json: page100(
          [
            {
              id: sheetPlace.module,
              name: "Contacts",
              department_id: sheetPlace.department,
              title_field_id: null,
            },
            ...(sheet.modules ?? []).map((module) => ({
              id: module.id,
              name: module.name,
              department_id: sheetPlace.department,
              title_field_id: module.titleFieldId,
            })),
          ],
          new URL(route.request().url()),
        ),
      }),
  );
  return state;
}

// ------------------------------------------------------------- sheet edits

type CellChange = { value: unknown; expected: WireSheetCell | undefined };
type ColumnWire = { key: string; type: string; [option: string]: unknown };

/** The one comparison the server makes for `expected` (`_canonical`). */
function canonical(cell: WireSheetCell | undefined): string {
  if (!cell) return JSON.stringify(["value", null]);
  if ("link" in cell) return JSON.stringify(["link", cell.link.record_id]);
  if ("unlinked" in cell) return JSON.stringify(["unlinked", cell.unlinked]);
  if ("state" in cell) return JSON.stringify(["state", cell.state]);
  return JSON.stringify(["value", cell.value ?? null]);
}

/** A record a link column can point to: its module, id and title. */
export type SheetLinkTarget = {
  moduleId: string;
  titleFieldId: string;
  id: string;
  title: string;
};

/**
 * The writes of an editable sheet page (routes 6, 10, 12 and 13) on top of
 * `installSheetPageApi`, keeping the server's rules: a cell save compares
 * `expected` with the stored cell and answers 412 `cell_changed` with the
 * current row; each write bumps the revision; deletes and structure saves
 * need the current ETag; a new column's key comes from `nextColumnSeq`.
 * Numbers arrive as text in the en-US locale here.
 */
export async function installSheetEditApi(
  page: Page,
  sheetState: Awaited<ReturnType<typeof installSheetPageApi>>,
  options: {
    linkTargets?: SheetLinkTarget[];
    moduleFields?: Record<string, { id: string; name: string; type: string }[]>;
    /** People the editor can see (the people route). */
    people?: { id: string; display_name: string }[];
  } = {},
) {
  const sheetId = sheetState.detail?.id ?? "";
  const writes = {
    patches: [] as { rowId: string; cells: Record<string, CellChange> }[],
    creates: [] as Record<string, unknown>[],
    deletes: [] as { rowId: string; ifMatch: string | null }[],
    structures: [] as {
      ifMatch: string | null;
      body: Record<string, unknown>;
    }[],
    searches: [] as string[],
    refuseNextPatch: null as null | {
      status: number;
      code: string;
      message: string;
    },
    /** Who a 412 names (null: someone the editor cannot see). */
    changedBy: null as null | { id: string; display_name: string },
    peopleSearches: [] as string[],
  };
  const columns = () =>
    ((sheetState.detail?.structure as { columns?: ColumnWire[] } | undefined)
      ?.columns ?? []) as ColumnWire[];
  const stored = (key: string, value: unknown): WireSheetCell => {
    const column = columns().find((item) => item.key === key);
    if (value === null || value === "") return { value: null };
    if (column?.type === "link" && typeof value === "object" && value) {
      const id = (value as { record_id?: string }).record_id ?? "";
      const target = options.linkTargets?.find((item) => item.id === id);
      return { link: { record_id: id, label: target?.title ?? id } };
    }
    if (column?.type === "int" && typeof value === "string")
      return { value: Number(value.replaceAll(",", "")) };
    if (column?.type === "decimal" && typeof value === "string")
      return { value: value.replaceAll(",", "") };
    return { value };
  };
  const bump = (row: WireSheetRow) => {
    row.revision += 1;
    row.etag = `"${row.id}:${row.revision}"`;
  };
  await page.route(
    (url) =>
      url.pathname.startsWith(`/api/worksheets/${sheetId}/rows`) &&
      !url.pathname.endsWith("/query"),
    async (route) => {
      const request = route.request();
      const method = request.method();
      const rowId = new URL(request.url()).pathname.split("/")[5];
      if (method === "POST" && !rowId) {
        const body = (request.postDataJSON() ?? {}) as Record<string, unknown>;
        writes.creates.push(body);
        const created = wireSheetRow(sheetState.rows.length + 1000, {});
        if (body.after_row_id === null) sheetState.rows.unshift(created);
        else sheetState.rows.push(created);
        return route.fulfill({ status: 201, json: created });
      }
      const row = sheetState.rows.find((item) => item.id === rowId);
      if (!row)
        return route.fulfill({
          status: 404,
          json: { detail: { code: "row_not_found", message: "Row not found" } },
        });
      if (method === "DELETE") {
        const ifMatch = request.headers()["if-match"] ?? null;
        writes.deletes.push({ rowId, ifMatch });
        if (ifMatch !== row.etag)
          return route.fulfill({
            status: 412,
            json: {
              detail: { code: "row_changed", message: "The row changed" },
            },
          });
        sheetState.rows.splice(sheetState.rows.indexOf(row), 1);
        return route.fulfill({ status: 204, body: "" });
      }
      const body = request.postDataJSON() as {
        cells: Record<string, CellChange>;
      };
      writes.patches.push({ rowId, cells: body.cells });
      const refusal = writes.refuseNextPatch;
      if (refusal) {
        writes.refuseNextPatch = null;
        return route.fulfill({
          status: refusal.status,
          json: {
            detail: {
              code: refusal.code,
              message: refusal.message,
              key: Object.keys(body.cells)[0],
            },
          },
        });
      }
      const changed = Object.entries(body.cells)
        .filter(
          ([key, change]) =>
            canonical(change.expected) !== canonical(row.cells[key]),
        )
        .map(([key]) => key)
        .sort();
      if (changed.length)
        return route.fulfill({
          status: 412,
          json: {
            detail: {
              code: "cell_changed",
              message: "Someone changed these cells",
              keys: changed,
              current: row,
              changed_by: writes.changedBy,
            },
          },
        });
      for (const [key, change] of Object.entries(body.cells))
        row.cells[key] = stored(key, change.value);
      bump(row);
      return route.fulfill({ json: row });
    },
  );
  await page.route(
    (url) => url.pathname === `/api/worksheets/${sheetId}/people`,
    (route) => {
      const needle = (
        new URL(route.request().url()).searchParams.get("q") ?? ""
      ).toLowerCase();
      writes.peopleSearches.push(needle);
      return route.fulfill({
        json: {
          people: (options.people ?? []).filter((person) =>
            person.display_name.toLowerCase().includes(needle),
          ),
        },
      });
    },
  );
  await page.route(
    (url) => url.pathname === `/api/worksheets/${sheetId}/structure`,
    (route) => {
      const request = route.request();
      const ifMatch = request.headers()["if-match"] ?? null;
      const body = request.postDataJSON() as {
        columns: ColumnWire[];
        groups: unknown[];
        totals: Record<string, string>;
      };
      writes.structures.push({ ifMatch, body });
      const detail = sheetState.detail;
      if (!detail || ifMatch !== detail.etag)
        return route.fulfill({
          status: 412,
          json: {
            detail: {
              code: "worksheet_changed",
              message: "The sheet changed; reload it",
            },
          },
        });
      const previous = detail.structure as { nextColumnSeq: number };
      let next = previous.nextColumnSeq;
      for (const column of body.columns) {
        const sequence = Number(/^c(\d+)$/.exec(column.key)?.[1] ?? 0);
        if (sequence >= next) next = sequence + 1;
      }
      detail.structure = {
        structureVersion: 1,
        nextColumnSeq: next,
        columns: body.columns,
        groups: body.groups,
        totals: body.totals,
      };
      detail.revision += 1;
      detail.etag = `"${detail.id}:${detail.revision}"`;
      return route.fulfill({ headers: { ETag: detail.etag }, json: detail });
    },
  );
  await page.route(
    (url) => url.pathname === "/api/records/query",
    (route) => {
      const body = route.request().postDataJSON() as {
        module_id: string;
        definition: { search?: string | null };
      };
      const needle = body.definition.search?.toLowerCase() ?? "";
      writes.searches.push(needle);
      const items = (options.linkTargets ?? [])
        .filter(
          (target) =>
            target.moduleId === body.module_id &&
            target.title.toLowerCase().includes(needle),
        )
        .map((target) =>
          wireRecord({
            id: target.id,
            module_id: target.moduleId,
            data: { [target.titleFieldId]: target.title },
            created_at: "2026-11-01T08:00:00Z",
            updated_at: "2026-11-01T08:00:00Z",
          }),
        );
      return route.fulfill({
        json: {
          items,
          pagination: {
            limit: 50,
            offset: 0,
            count: items.length,
            total: items.length,
            has_more: false,
            total_is_capped: false,
          },
        },
      });
    },
  );
  await page.route(
    (url) => /^\/api\/views\/data-sources\/[^/]+\/fields$/.test(url.pathname),
    (route) => {
      const moduleId = new URL(route.request().url()).pathname.split("/")[4];
      const fields = options.moduleFields?.[moduleId] ?? [];
      return route.fulfill({
        json: {
          items: fields.map((field, position) => ({
            ...field,
            module_id: moduleId,
            required: false,
            position,
            config: {},
          })),
          pagination: {
            limit: 100,
            offset: 0,
            count: fields.length,
            total: fields.length,
            has_more: false,
            total_is_capped: false,
          },
        },
      });
    },
  );
  return writes;
}

// ---------------------------------------------------------- sheet actions

export type WireSheetShare = {
  id: string;
  subject: "user" | "group";
  user: { id: string; display_name: string } | null;
  group: { id: string; name: string } | null;
  level: "view" | "edit";
  created_at: string;
};

export type WireSheetRevision = {
  id: string;
  row_id: string;
  revision: number;
  action: "create" | "update" | "delete" | "restore";
  changed_keys: string[];
  cells: Record<string, unknown>;
  author: { id: string; display_name: string } | null;
  created_at: string;
};

type Refusal = { status: number; code: string; message: string };

/**
 * The sheet actions of docs/specs/sheets.md D10: rename (5), delete (7),
 * history (15), shares (16 to 19), export (20) and share candidates (25).
 * Register it after `installSheetPageApi`, so its routes win.
 */
export async function installSheetActionsApi(
  page: Page,
  sheetState: Awaited<ReturnType<typeof installSheetPageApi>>,
  options: {
    shares?: WireSheetShare[];
    candidates?: {
      people: { id: string; display_name: string }[];
      groups: { id: string; name: string }[];
    };
    history?: WireSheetRevision[];
  } = {},
) {
  const sheetId = sheetState.detail?.id ?? "";
  const base = `/api/worksheets/${sheetId}`;
  const state = {
    shares: [...(options.shares ?? [])],
    shareReads: 0,
    shareWrites: [] as { method: string; path: string; body: unknown }[],
    renames: [] as { ifMatch: string | null; body: unknown }[],
    deletes: [] as (string | null)[],
    exports: [] as unknown[],
    historyReads: [] as string[],
    candidateSearches: [] as string[],
    refuseNextShare: null as Refusal | null,
    refuseNextExport: null as Refusal | null,
    refuseNextRename: null as Refusal | null,
  };
  // An empty code answers the plain detail FastAPI's `forbidden()` sends.
  const refuse = (route: Route, refusal: Refusal) =>
    route.fulfill({
      status: refusal.status,
      json: {
        detail: refusal.code
          ? { code: refusal.code, message: refusal.message }
          : refusal.message,
      },
    });
  await page.route(
    (url) => url.pathname === base,
    async (route) => {
      const request = route.request();
      const method = request.method();
      const detail = sheetState.detail;
      if (method !== "PATCH" && method !== "DELETE") return route.fallback();
      const ifMatch = request.headers()["if-match"] ?? null;
      if (!detail)
        return refuse(route, {
          status: 404,
          code: "worksheet_not_found",
          message: "Sheet not found",
        });
      if (method === "DELETE") {
        state.deletes.push(ifMatch);
        if (ifMatch !== detail.etag)
          return refuse(route, {
            status: 412,
            code: "worksheet_changed",
            message: "The sheet changed",
          });
        sheetState.detail = null;
        return route.fulfill({ status: 204, body: "" });
      }
      const body = request.postDataJSON() as { title: string };
      state.renames.push({ ifMatch, body });
      const refusal = state.refuseNextRename;
      if (refusal) {
        state.refuseNextRename = null;
        return refuse(route, refusal);
      }
      if (ifMatch !== detail.etag)
        return refuse(route, {
          status: 412,
          code: "worksheet_changed",
          message: "The sheet changed",
        });
      detail.title = body.title;
      detail.revision += 1;
      detail.etag = `"${detail.id}:${detail.revision}"`;
      return route.fulfill({ headers: { ETag: detail.etag }, json: detail });
    },
  );
  await page.route(
    (url) =>
      url.pathname === `${base}/shares` ||
      url.pathname.startsWith(`${base}/shares/`),
    async (route) => {
      const request = route.request();
      const method = request.method();
      const url = new URL(request.url());
      if (method === "GET") {
        state.shareReads += 1;
        return route.fulfill({
          json: {
            items: state.shares,
            pagination: {
              limit: Number(url.searchParams.get("limit") ?? 25),
              offset: 0,
              count: state.shares.length,
              total: state.shares.length,
              has_more: false,
              total_is_capped: false,
            },
          },
        });
      }
      const body = method === "DELETE" ? null : request.postDataJSON();
      state.shareWrites.push({ method, path: url.pathname, body });
      const refusal = state.refuseNextShare;
      if (refusal) {
        state.refuseNextShare = null;
        return refuse(route, refusal);
      }
      if (method === "POST") {
        const wire = body as {
          subject: "user" | "group";
          user_id?: string;
          group_id?: string;
          level: "view" | "edit";
        };
        const person = options.candidates?.people.find(
          (item) => item.id === wire.user_id,
        );
        const group = options.candidates?.groups.find(
          (item) => item.id === wire.group_id,
        );
        const share: WireSheetShare = {
          id: `00000000-0000-4000-8000-${String(900000 + state.shareWrites.length).padStart(12, "0")}`,
          subject: wire.subject,
          user: person ?? null,
          group: group ?? null,
          level: wire.level,
          created_at: "2026-11-24T08:00:00Z",
        };
        state.shares.push(share);
        if (sheetState.detail) sheetState.detail.shared = true;
        return route.fulfill({ status: 201, json: share });
      }
      const shareId = url.pathname.split("/").at(-1);
      const share = state.shares.find((item) => item.id === shareId);
      if (!share)
        return refuse(route, {
          status: 404,
          code: "share_not_found",
          message: "Share not found",
        });
      if (method === "DELETE") {
        state.shares.splice(state.shares.indexOf(share), 1);
        if (sheetState.detail)
          sheetState.detail.shared = state.shares.length > 0;
        return route.fulfill({ status: 204, body: "" });
      }
      share.level = (body as { level: "view" | "edit" }).level;
      return route.fulfill({ json: share });
    },
  );
  await page.route(
    (url) => url.pathname === `${base}/share-candidates`,
    (route) => {
      const needle = (
        new URL(route.request().url()).searchParams.get("q") ?? ""
      ).toLowerCase();
      state.candidateSearches.push(needle);
      const people = (options.candidates?.people ?? []).filter((person) =>
        person.display_name.toLowerCase().includes(needle),
      );
      const groups = (options.candidates?.groups ?? []).filter((group) =>
        group.name.toLowerCase().includes(needle),
      );
      return route.fulfill({ json: { people, groups } });
    },
  );
  await page.route(
    (url) => url.pathname === `${base}/history`,
    (route) => {
      const url = new URL(route.request().url());
      state.historyReads.push(url.search);
      const items = options.history ?? [];
      return route.fulfill({
        json: {
          items,
          pagination: {
            limit: Number(url.searchParams.get("limit") ?? 25),
            offset: Number(url.searchParams.get("offset") ?? 0),
            count: items.length,
            total: items.length,
            has_more: false,
            total_is_capped: false,
          },
        },
      });
    },
  );
  await page.route(
    (url) => url.pathname === `${base}/export`,
    (route) => {
      const body = route.request().postDataJSON() as { format: string };
      state.exports.push(body);
      const refusal = state.refuseNextExport;
      if (refusal) {
        state.refuseNextExport = null;
        return refuse(route, refusal);
      }
      const files: Record<string, [string, string, string]> = {
        csv: [
          "text/csv; charset=utf-8",
          "class-roster-2026-11-24.csv",
          "Student\r\n",
        ],
        xlsx: [
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          "class-roster-2026-11-24.xlsx",
          "PK",
        ],
        template: ["application/json", "class-roster-template.json", "{}"],
      };
      const [type, name, content] = files[body.format] ?? files.csv;
      return route.fulfill({
        status: 200,
        headers: {
          "Content-Type": type,
          "Content-Disposition": `attachment; filename="${name}"`,
          "Cache-Control": "no-store",
          "X-Content-Type-Options": "nosniff",
        },
        body: content,
      });
    },
  );
  return state;
}
