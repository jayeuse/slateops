import { answeredHeaders, type Page } from "./test";

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
