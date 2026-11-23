import { z } from "zod";
import { apiFetch } from "@/lib/api";
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
