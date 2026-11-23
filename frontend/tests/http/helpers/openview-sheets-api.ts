import { answeredHeaders, type Page } from "./test";
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
    state: "private" as const,
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
          ],
          new URL(route.request().url()),
        ),
      }),
  );
  return state;
}
