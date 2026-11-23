import { z } from "zod";
import {
  ApiError,
  apiContractError,
  apiFetch,
  apiRequest,
  keepRequestId,
} from "@/lib/api";
import { requestSessionRecheck } from "@/lib/auth-api";
import { openViewReadFetch } from "./openview-access";

// Sheet routes (docs/specs/sheets.md D10). Code says "worksheet"; users read
// "sheet" (P7). Add routes here only as a unit needs them.

const uuid = z.string().uuid();
const timestamp = z.iso.datetime({ offset: true });
const columnKey = z.string().regex(/^c[0-9a-z]{1,8}$/);
const places = z.number().int().min(0).max(18);
const totalFunction = z.enum(["sum", "average", "min", "max", "count"]);

const worksheetLevelSchema = z.enum(["owner", "edit", "view"]);
export type WorksheetLevel = z.output<typeof worksheetLevelSchema>;

const summaryFields = {
  id: uuid,
  record_id: uuid.nullable(),
  module_id: uuid.nullable(),
  title: z.string().min(1).max(200),
  owner: z.object({ id: uuid, display_name: z.string() }).strict(),
  state: z.enum(["private", "open"]),
  my_level: worksheetLevelSchema,
  live_row_count: z.number().int().min(0),
  revision: z.number().int().min(0),
  updated_at: timestamp,
  is_deleted: z.boolean(),
  deleted_at: timestamp.nullable(),
  // The record's title, or the module's name for a module sheet.
  anchor_title: z.string(),
  module_name: z.string(),
  // Whether the owner's sheet has a live share; null for anyone else.
  shared: z.boolean().nullable(),
  // The group whose share alone gives the viewer the sheet, else null.
  access_group: z.string().nullable(),
};

type SummaryWire = z.output<z.ZodObject<typeof summaryFields>>;

function toSummary(wire: SummaryWire) {
  return {
    id: wire.id,
    recordId: wire.record_id,
    moduleId: wire.module_id,
    title: wire.title,
    owner: { id: wire.owner.id, displayName: wire.owner.display_name },
    state: wire.state,
    myLevel: wire.my_level,
    liveRowCount: wire.live_row_count,
    revision: wire.revision,
    updatedAt: wire.updated_at,
    isDeleted: wire.is_deleted,
    deletedAt: wire.deleted_at,
    anchorTitle: wire.anchor_title,
    moduleName: wire.module_name,
    shared: wire.shared,
    accessGroup: wire.access_group,
  };
}

export type WorksheetSummary = ReturnType<typeof toSummary>;

const summarySchema = z.object(summaryFields).strict().transform(toSummary);

// The structure as the viewer may see it (D1.7, D14 S1).
const columnBase = { key: columnKey, name: z.string().max(150) };
const columnSchema = z.discriminatedUnion("type", [
  z
    .object({
      ...columnBase,
      type: z.enum([
        "text",
        "long_text",
        "email",
        "url",
        "number",
        "int",
        "boolean",
        "date",
        "datetime",
        "user",
      ]),
    })
    .strict(),
  z
    .object({
      ...columnBase,
      type: z.literal("decimal"),
      decimal: z.object({ places, currency: z.boolean() }).strict(),
    })
    .strict(),
  z
    .object({
      ...columnBase,
      type: z.literal("select"),
      select: z
        .object({
          options: z
            .array(
              z
                .object({
                  id: z.string().regex(/^o[0-9a-z]{1,8}$/),
                  label: z.string().max(100),
                })
                .strict(),
            )
            .min(1),
        })
        .strict(),
    })
    .strict(),
  z
    .object({
      ...columnBase,
      type: z.literal("link"),
      link: z.object({ moduleId: uuid }).strict(),
    })
    .strict(),
  z
    .object({
      ...columnBase,
      type: z.literal("lookup"),
      lookup: z.object({ linkKey: columnKey, fieldId: uuid }).strict(),
    })
    .strict(),
  z
    .object({
      ...columnBase,
      type: z.literal("computed"),
      computed: z
        .object({
          expression: z.string().min(1).max(1000),
          places: places.nullable().optional(),
        })
        .strict(),
    })
    .strict(),
  // A From another sheet column: the full options when the viewer can see
  // the source sheet, its key and name only when not.
  z
    .object({
      ...columnBase,
      type: z.literal("sheet_lookup"),
      sheet_lookup: z
        .object({
          sourceWorksheetId: uuid,
          sourceColumnKey: columnKey,
          linkKey: columnKey,
          sourceLinkKey: columnKey,
        })
        .strict()
        .optional(),
      state: z.literal("no_access").optional(),
    })
    .strict(),
]);

const structureSchema = z
  .object({
    structureVersion: z.number().int(),
    nextColumnSeq: z.number().int().min(1),
    columns: z.array(columnSchema),
    groups: z.array(
      z
        .object({ name: z.string().max(150), keys: z.array(columnKey).min(1) })
        .strict(),
    ),
    // The server checks that each key is a column key; the contract names only
    // the function.
    totals: z.record(z.string(), totalFunction),
  })
  .strict();

export type WorksheetStructure = z.output<typeof structureSchema>;

const detailSchema = z
  .object({
    ...summaryFields,
    structure: structureSchema,
    etag: z.string().min(1),
    created_at: timestamp,
  })
  .strict()
  .transform((wire) => ({
    ...toSummary(wire),
    structure: wire.structure,
    etag: wire.etag,
    createdAt: wire.created_at,
  }));

export type WorksheetDetail = z.output<typeof detailSchema>;

const pageSchema = z
  .object({
    items: z.array(summarySchema),
    pagination: z
      .object({
        limit: z.number().int().min(1).max(100),
        offset: z.number().int().min(0),
        count: z.number().int().min(0),
        total: z.number().int().min(0),
        has_more: z.boolean(),
        total_is_capped: z.boolean(),
      })
      .strict(),
  })
  .strict();

/** One person's sheets, complete (route 1). */
export type MyWorksheets = { items: WorksheetSummary[]; total: number };

const MY_SHEETS_PAGE = 100;
// A bound on the read, so a server that keeps answering has_more cannot loop it.
const MY_SHEETS_MAX_PAGES = 50;

type SheetPage = z.output<typeof pageSchema>;

/** Reads every page of a sheet list, newest change first. */
async function readEveryPage(
  read: (query: URLSearchParams) => Promise<SheetPage>,
  deleted: "exclude" | "only" = "exclude",
): Promise<MyWorksheets> {
  const items: WorksheetSummary[] = [];
  let total = 0;
  for (let page = 0; page < MY_SHEETS_MAX_PAGES; page += 1) {
    const result = await read(
      new URLSearchParams({
        limit: String(MY_SHEETS_PAGE),
        offset: String(items.length),
        sort_by: "updated_at",
        sort_order: "desc",
        deleted,
      }),
    );
    items.push(...result.items);
    total = result.pagination.total;
    if (!result.pagination.has_more || result.items.length === 0) break;
  }
  return { items, total };
}

/**
 * My sheets (route 1): the sheets the person owns or that are shared with
 * them, or with `deleted: "only"` their own deleted sheets. It reads every
 * page, so the screen can count and filter the whole list. It needs no
 * records.read, so it does not report to the OpenView access latch.
 */
export function listMyWorksheets(options: {
  deleted: "exclude" | "only";
  signal?: AbortSignal;
}): Promise<MyWorksheets> {
  return readEveryPage(
    (query) =>
      apiFetch(`/worksheets?${query}`, pageSchema, {
        cache: "no-store",
        signal: options.signal,
      }),
    options.deleted,
  );
}

/** The sheets on a record that the person can see (route 2, Sheets tab). */
export function listRecordWorksheets(
  recordId: string,
  signal?: AbortSignal,
): Promise<MyWorksheets> {
  return readEveryPage((query) =>
    openViewReadFetch(
      `/records/${encodeURIComponent(recordId)}/worksheets?${query}`,
      pageSchema,
      { cache: "no-store", signal },
    ),
  );
}

/** The module sheets that the person can see (route 2a, module page). */
export function listModuleWorksheets(
  moduleId: string,
  signal?: AbortSignal,
): Promise<MyWorksheets> {
  return readEveryPage((query) =>
    openViewReadFetch(
      `/modules/${encodeURIComponent(moduleId)}/worksheets?${query}`,
      pageSchema,
      { cache: "no-store", signal },
    ),
  );
}

const createSchema = z
  .object({
    title: z.string().trim().min(1).max(200),
    recordId: uuid.optional(),
    moduleId: uuid.optional(),
  })
  .refine((input) => Boolean(input.recordId) !== Boolean(input.moduleId));

/**
 * A new blank sheet on exactly one record or one module (route 3); the
 * person who creates it owns it (C5). Templates and data files come later.
 */
export function createWorksheet(
  raw: { title: string } & (
    | { recordId: string; moduleId?: never }
    | { moduleId: string; recordId?: never }
  ),
): Promise<WorksheetDetail> {
  const input = createSchema.parse(raw);
  return apiFetch("/worksheets", detailSchema, {
    method: "POST",
    body: JSON.stringify({
      ...(input.recordId
        ? { record_id: input.recordId }
        : { module_id: input.moduleId }),
      title: input.title,
      source: { kind: "blank" },
    }),
  });
}

/** One sheet the person can see (route 4); a hidden sheet answers 404 (P6). */
export function getWorksheet(
  id: string,
  signal?: AbortSignal,
): Promise<WorksheetDetail> {
  return apiFetch(`/worksheets/${encodeURIComponent(id)}`, detailSchema, {
    cache: "no-store",
    signal,
  });
}

/** The owner restores their deleted sheet while its record is live (route 8). */
export function restoreWorksheet(id: string): Promise<WorksheetDetail> {
  return apiFetch(
    `/worksheets/${encodeURIComponent(id)}/restore`,
    detailSchema,
    { method: "POST" },
  );
}

// ------------------------------------------------------------------- rows

const jsonValue: z.ZodType<unknown> = z.unknown();

// A cell as the viewer may see it (D10 `Cell`, D7.3): a value, a link, text
// that matched no record, a state with no value, or a computed cell that
// cannot be worked out (D7.2).
const cellSchema = z.union([
  z.object({ value: jsonValue }).strict(),
  z.object({ value: z.null(), error: z.string().min(1) }).strict(),
  z
    .object({
      link: z.object({ record_id: uuid, label: z.string() }).strict(),
    })
    .strict(),
  z.object({ unlinked: z.string() }).strict(),
  z
    .object({
      state: z.enum([
        "no_access",
        "deleted",
        "removed",
        "unavailable",
        "field_removed",
        "column_removed",
        "multiple_matches",
      ]),
      // How many source rows matched (multiple_matches, D7.3a).
      count: z.number().int().min(2).optional(),
    })
    .strict(),
]);

export type WorksheetCell = z.output<typeof cellSchema>;
export type WorksheetCellState = Extract<
  WorksheetCell,
  { state: unknown }
>["state"];

const rowSchema = z
  .object({
    id: uuid,
    revision: z.number().int().min(0),
    etag: z.string().min(1),
    position: z.number().int(),
    cells: z.record(z.string(), cellSchema),
  })
  .strict();

export type WorksheetRow = z.output<typeof rowSchema>;

const totalSchema = z
  .object({
    fn: totalFunction,
    value: z.union([z.number(), z.string(), z.null()]),
    hidden_count: z.number().int().min(0),
  })
  .strict();

export type WorksheetTotal = z.output<typeof totalSchema>;

const rowPageSchema = z
  .object({
    items: z.array(rowSchema),
    pagination: z
      .object({
        limit: z.number().int().min(1).max(200),
        offset: z.number().int().min(0),
        count: z.number().int().min(0),
        total: z.number().int().min(0),
        has_more: z.boolean(),
      })
      .strict(),
    totals: z.record(z.string(), totalSchema),
  })
  .strict()
  .transform(({ items, pagination, totals }) => ({
    rows: items,
    total: pagination.total,
    totals,
  }));

export type WorksheetRowPage = z.output<typeof rowPageSchema>;

/** The grid reads rows in pages of this size (route 9). */
export const WORKSHEET_ROW_PAGE = 200;

export type WorksheetRowSort = { key: string; order: "asc" | "desc" };

/**
 * A page of the sheet's rows (route 9) in one column's order and matching
 * the search, with the totals of every row (F7). Neither is saved.
 */
export function queryWorksheetRows(
  id: string,
  query: {
    sort: WorksheetRowSort | null;
    search: string;
    offset: number;
    signal?: AbortSignal;
  },
): Promise<WorksheetRowPage> {
  const search = query.search.trim();
  return apiFetch(
    `/worksheets/${encodeURIComponent(id)}/rows/query`,
    rowPageSchema,
    {
      method: "POST",
      cache: "no-store",
      signal: query.signal,
      body: JSON.stringify({
        limit: WORKSHEET_ROW_PAGE,
        offset: query.offset,
        ...(query.sort ? { sort: query.sort } : {}),
        ...(search ? { search } : {}),
      }),
    },
  );
}

// ------------------------------------------------------------------ writes

/** One cell's new value and the cell as the person saw it (F4). */
export type WorksheetCellChange = { value: unknown; expected: WorksheetCell };

/**
 * Saves changed cells of one row (route 12). A cell someone else changed
 * since the person saw it answers 412 `cell_changed` with the newer row
 * (`cellConflict` reads it); other cells of the row save normally.
 */
export function updateWorksheetCells(
  sheetId: string,
  rowId: string,
  cells: Record<string, WorksheetCellChange>,
): Promise<WorksheetRow> {
  return apiFetch(
    `/worksheets/${encodeURIComponent(sheetId)}/rows/${encodeURIComponent(rowId)}`,
    rowSchema,
    { method: "PATCH", body: JSON.stringify({ cells }) },
  );
}

/** A blank row at the end of the sheet (route 10). */
export function createWorksheetRow(sheetId: string): Promise<WorksheetRow> {
  return apiFetch(
    `/worksheets/${encodeURIComponent(sheetId)}/rows`,
    rowSchema,
    { method: "POST", body: JSON.stringify({}) },
  );
}

/** Deletes a row at the version the person saw (route 13). */
export function deleteWorksheetRow(
  sheetId: string,
  row: { id: string; etag: string },
): Promise<null> {
  return apiFetch(
    `/worksheets/${encodeURIComponent(sheetId)}/rows/${encodeURIComponent(row.id)}`,
    z.null(),
    { method: "DELETE", headers: { "If-Match": row.etag } },
  );
}

/** A column as route 6 takes it: the stored column, never a masked one. */
export type WorksheetColumnInput = Exclude<
  WorksheetStructure["columns"][number],
  { state: "no_access" }
>;

/**
 * Saves the whole column list, groups and totals at the sheet's version
 * (route 6, `If-Match`). A new column's key comes from `nextColumnSeq`.
 */
export function saveWorksheetStructure(
  sheetId: string,
  etag: string,
  structure: {
    columns: WorksheetColumnInput[];
    groups: WorksheetStructure["groups"];
    totals: WorksheetStructure["totals"];
  },
): Promise<WorksheetDetail> {
  return apiFetch(
    `/worksheets/${encodeURIComponent(sheetId)}/structure`,
    detailSchema,
    {
      method: "PUT",
      headers: { "If-Match": etag },
      body: JSON.stringify(structure),
    },
  );
}

// ------------------------------------------------- sheet actions (F5)

const titleSchema = z.string().trim().min(1).max(200);

function sheetPath(id: string) {
  return `/worksheets/${encodeURIComponent(id)}`;
}

/** The owner renames a sheet that is not open (route 5, `If-Match`). */
export function renameWorksheet(
  id: string,
  etag: string,
  title: string,
): Promise<WorksheetDetail> {
  return apiFetch(sheetPath(id), detailSchema, {
    method: "PATCH",
    headers: { "If-Match": etag },
    body: JSON.stringify({ title: titleSchema.parse(title) }),
  });
}

/** The owner deletes a sheet that is not open (route 7, `If-Match`). */
export function deleteWorksheet(id: string, etag: string): Promise<null> {
  return apiFetch(sheetPath(id), z.null(), {
    method: "DELETE",
    headers: { "If-Match": etag },
  });
}

const personRefSchema = z
  .object({ id: uuid, display_name: z.string() })
  .strict()
  .transform((wire) => ({ id: wire.id, displayName: wire.display_name }));
const groupRefSchema = z.object({ id: uuid, name: z.string() }).strict();

const listPagination = z
  .object({
    limit: z.number().int().min(1).max(100),
    offset: z.number().int().min(0),
    count: z.number().int().min(0),
    total: z.number().int().min(0),
    has_more: z.boolean(),
    total_is_capped: z.boolean().optional(),
  })
  .strict();

const revisionSchema = z
  .object({
    id: uuid,
    row_id: uuid,
    revision: z.number().int(),
    action: z.enum(["create", "update", "delete", "restore"]),
    changed_keys: z.array(z.string()),
    cells: z.record(z.string(), cellSchema),
    author: personRefSchema.nullable(),
    created_at: timestamp,
  })
  .strict()
  .transform((wire) => ({
    id: wire.id,
    rowId: wire.row_id,
    revision: wire.revision,
    action: wire.action,
    changedKeys: wire.changed_keys,
    cells: wire.cells,
    author: wire.author,
    createdAt: wire.created_at,
  }));

export type WorksheetRevision = z.output<typeof revisionSchema>;

/** History reads this many changes at a time. */
export const WORKSHEET_HISTORY_PAGE = 50;

/** A page of a sheet's row changes, newest first (route 15, H3). */
export function listWorksheetHistory(
  id: string,
  options: { offset: number; signal?: AbortSignal },
): Promise<{ items: WorksheetRevision[]; hasMore: boolean }> {
  const query = new URLSearchParams({
    limit: String(WORKSHEET_HISTORY_PAGE),
    offset: String(options.offset),
    sort_order: "desc",
  });
  return apiFetch(
    `${sheetPath(id)}/history?${query}`,
    z
      .object({ items: z.array(revisionSchema), pagination: listPagination })
      .strict()
      .transform((page) => ({
        items: page.items,
        hasMore: page.pagination.has_more,
      })),
    { cache: "no-store", signal: options.signal },
  );
}

const shareSchema = z
  .object({
    id: uuid,
    subject: z.enum(["user", "group"]),
    user: personRefSchema.nullable(),
    group: groupRefSchema.nullable(),
    level: z.enum(["view", "edit"]),
    created_at: timestamp,
  })
  .strict()
  .transform((wire, context) => {
    if (wire.subject === "user")
      return {
        id: wire.id,
        level: wire.level,
        subject: "user" as const,
        person: wire.user,
      };
    if (!wire.group) {
      context.addIssue({
        code: "custom",
        message: "group share without a group",
      });
      return z.NEVER;
    }
    return {
      id: wire.id,
      level: wire.level,
      subject: "group" as const,
      group: wire.group,
    };
  });

export type WorksheetShare = z.output<typeof shareSchema>;

const SHARE_PAGE = 100;
const SHARE_MAX_PAGES = 20;

/** Every live share of the owner's sheet (route 16). */
export async function listWorksheetShares(
  id: string,
  signal?: AbortSignal,
): Promise<WorksheetShare[]> {
  const shares: WorksheetShare[] = [];
  for (let page = 0; page < SHARE_MAX_PAGES; page += 1) {
    const query = new URLSearchParams({
      limit: String(SHARE_PAGE),
      offset: String(shares.length),
    });
    const result = await apiFetch(
      `${sheetPath(id)}/shares?${query}`,
      z
        .object({ items: z.array(shareSchema), pagination: listPagination })
        .strict(),
      { cache: "no-store", signal },
    );
    shares.push(...result.items);
    if (!result.pagination.has_more || result.items.length === 0) break;
  }
  return shares;
}

export type WorksheetShareTarget =
  { subject: "user"; id: string } | { subject: "group"; id: string };

/** A View or Edit share to one person or one group (route 17). */
export function shareWorksheet(
  id: string,
  target: WorksheetShareTarget,
  level: "view" | "edit",
): Promise<WorksheetShare> {
  const targetId = uuid.parse(target.id);
  return apiFetch(`${sheetPath(id)}/shares`, shareSchema, {
    method: "POST",
    body: JSON.stringify(
      target.subject === "user"
        ? { subject: "user", user_id: targetId, level }
        : { subject: "group", group_id: targetId, level },
    ),
  });
}

/** A share's new level (route 18). */
export function changeWorksheetShare(
  id: string,
  shareId: string,
  level: "view" | "edit",
): Promise<WorksheetShare> {
  return apiFetch(
    `${sheetPath(id)}/shares/${encodeURIComponent(shareId)}`,
    shareSchema,
    { method: "PATCH", body: JSON.stringify({ level }) },
  );
}

/** Removes a share (route 19). */
export function removeWorksheetShare(
  id: string,
  shareId: string,
): Promise<null> {
  return apiFetch(
    `${sheetPath(id)}/shares/${encodeURIComponent(shareId)}`,
    z.null(),
    { method: "DELETE" },
  );
}

function searchText(query: string) {
  return new URLSearchParams({ q: query.trim().slice(0, 100) });
}

const candidatesSchema = z
  .object({
    people: z.array(personRefSchema),
    groups: z.array(groupRefSchema),
  })
  .strict();

export type WorksheetShareCandidates = z.output<typeof candidatesSchema>;

/** People the owner can see and the owner's groups (route 25). */
export function searchWorksheetShareCandidates(
  id: string,
  query: string,
  signal?: AbortSignal,
): Promise<WorksheetShareCandidates> {
  return apiFetch(
    `${sheetPath(id)}/share-candidates?${searchText(query)}`,
    candidatesSchema,
    { cache: "no-store", signal },
  );
}

/** Up to 20 people an editor may put in a person cell (people route). */
export function searchWorksheetPeople(
  id: string,
  query: string,
  signal?: AbortSignal,
): Promise<{ id: string; displayName: string }[]> {
  return apiFetch(
    `${sheetPath(id)}/people?${searchText(query)}`,
    z
      .object({ people: z.array(personRefSchema) })
      .strict()
      .transform((wire) => wire.people),
    { cache: "no-store", signal },
  );
}

export type WorksheetExportFormat = "csv" | "xlsx" | "template";

const EXPORT_FILES: Record<
  WorksheetExportFormat,
  { type: RegExp; extension: string }
> = {
  csv: { type: /^text\/csv(?:;\s*charset=utf-8)?$/, extension: ".csv" },
  xlsx: {
    type: /^application\/vnd\.openxmlformats-officedocument\.spreadsheetml\.sheet$/,
    extension: ".xlsx",
  },
  template: {
    type: /^application\/json(?:;\s*charset=utf-8)?$/,
    extension: ".json",
  },
};

// The record export's file cap (D9.1).
const EXPORT_MAX_BYTES = 8 * 1024 * 1024;

const exportErrorSchema = z.object({
  detail: z.union([
    z.string(),
    z.object({ code: z.string(), message: z.string().optional() }),
  ]),
});

/**
 * The sheet as a file (route 20): CSV or Excel with every row, or the
 * template (columns only). The server writes one security event per file
 * (X3). A refusal keeps its status and code, never the server's words.
 */
export async function exportWorksheet(
  id: string,
  format: WorksheetExportFormat,
  signal?: AbortSignal,
): Promise<{ blob: Blob; filename: string }> {
  const response = await apiRequest(`${sheetPath(id)}/export`, {
    method: "POST",
    signal,
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ format }),
  });
  if (!response.ok) {
    const parsed = exportErrorSchema.safeParse(
      await response.json().catch(() => null),
    );
    const code =
      parsed.success && typeof parsed.data.detail !== "string"
        ? parsed.data.detail.code
        : undefined;
    // A session that now needs a second step or another network is checked
    // again, as the record export does.
    if (["mfa_required", "ip_not_allowed"].includes(code ?? ""))
      queueMicrotask(() => {
        if (!signal?.aborted) requestSessionRecheck();
      });
    throw keepRequestId(
      new ApiError(
        response.status,
        "Export could not be downloaded.",
        undefined,
        code,
      ),
      response,
    );
  }
  const expected = EXPORT_FILES[format];
  const type = response.headers.get("Content-Type")?.trim().toLowerCase();
  const filename = response.headers
    .get("Content-Disposition")
    ?.match(/^attachment; filename="([A-Za-z0-9][A-Za-z0-9_.-]{0,179})"$/)?.[1];
  if (
    response.status !== 200 ||
    !type ||
    !expected.type.test(type) ||
    !filename ||
    filename.includes("..") ||
    !filename.endsWith(expected.extension) ||
    !response.headers
      .get("Cache-Control")
      ?.toLowerCase()
      .split(",")
      .some((part) => part.trim() === "no-store") ||
    response.headers.get("X-Content-Type-Options")?.trim().toLowerCase() !==
      "nosniff"
  )
    throw apiContractError(response);
  const blob = await response.blob();
  if (blob.size > EXPORT_MAX_BYTES) throw apiContractError(response);
  return { blob, filename };
}
