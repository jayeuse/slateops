import { z } from "zod";
import { ApiError } from "@/lib/api";
import {
  WORKSHEET_ROW_PAGE,
  type WorksheetCell,
  type WorksheetCellState,
  type WorksheetRow,
  type WorksheetRowSort,
  type WorksheetStructure,
  type WorksheetTotal,
} from "../adapters/worksheets-api";

// The read-only sheet grid (docs/specs/sheets.md P3, F7, N4, N6 to N8 and
// Screens 3): which columns show and how, what each cell and total says, and
// the pages of rows the grid loads as it scrolls. Users read "sheet" (P7).

type StructureColumn = WorksheetStructure["columns"][number];
export type SheetColumnType = StructureColumn["type"];

export type GridColumn = {
  key: string;
  name: string;
  type: SheetColumnType;
  /** Lookup, computed and From another sheet cells accept no edit. */
  readOnly: boolean;
  /** Sorted and totalled as numbers. */
  numeric: boolean;
  /** The column group's name, for the band over the headers. */
  group: string | null;
  /** The module a link column points to; its records events refresh lookups. */
  linkModuleId?: string;
  places?: number;
  options?: Record<string, string>;
};

const NUMERIC: ReadonlySet<SheetColumnType> = new Set([
  "int",
  "number",
  "decimal",
  "computed",
]);
const READ_ONLY: ReadonlySet<SheetColumnType> = new Set([
  "lookup",
  "computed",
  "sheet_lookup",
]);

export function gridColumns(structure: WorksheetStructure): GridColumn[] {
  const groups = new Map<string, string>();
  for (const group of structure.groups)
    for (const key of group.keys) groups.set(key, group.name);
  return structure.columns.map((column) => {
    const view: GridColumn = {
      key: column.key,
      name: column.name,
      type: column.type,
      readOnly: READ_ONLY.has(column.type),
      numeric: NUMERIC.has(column.type),
      group: groups.get(column.key) ?? null,
    };
    if (column.type === "link") view.linkModuleId = column.link.moduleId;
    if (column.type === "decimal") view.places = column.decimal.places;
    if (
      column.type === "computed" &&
      typeof column.computed.places === "number"
    )
      view.places = column.computed.places;
    if (column.type === "select")
      view.options = Object.fromEntries(
        column.select.options.map((option) => [option.id, option.label]),
      );
    return view;
  });
}

export type GridBand = { label: string | null; span: number };

/** One band per run of columns in the same group, ungrouped runs included. */
export function gridBands(columns: readonly GridColumn[]): GridBand[] {
  const bands: GridBand[] = [];
  for (const column of columns) {
    const last = bands.at(-1);
    if (last && last.label === column.group) last.span += 1;
    else bands.push({ label: column.group, span: 1 });
  }
  return bands;
}

export type GridFormat = { locale: string; timezone: string };

const STATE_WORDS: Record<WorksheetCellState, string> = {
  no_access: "No access",
  deleted: "Deleted record",
  removed: "Removed record",
  unavailable: "Unavailable",
  field_removed: "Field removed",
  column_removed: "Column removed",
  multiple_matches: "Several matches",
};

export type CellView =
  | { kind: "blank" }
  | { kind: "value"; text: string }
  | { kind: "link"; label: string; recordId: string }
  | { kind: "unlinked"; text: string }
  | { kind: "state"; state: WorksheetCellState; words: string };

function numberText(
  value: unknown,
  format: GridFormat,
  places?: number,
): string | null {
  const number =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : NaN;
  if (!Number.isFinite(number)) return null;
  return new Intl.NumberFormat(format.locale, {
    minimumFractionDigits: places ?? 0,
    maximumFractionDigits: places ?? 2,
  }).format(number);
}

function valueText(
  column: GridColumn,
  value: unknown,
  format: GridFormat,
): string {
  if (column.type === "select" && typeof value === "string")
    return column.options?.[value] ?? value;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (column.numeric) {
    const text = numberText(value, format, column.places);
    if (text !== null) return text;
  }
  if (typeof value === "number")
    return numberText(value, format) ?? String(value);
  if (column.type === "date" && typeof value === "string") {
    const date = new Date(`${value}T00:00:00Z`);
    if (!Number.isNaN(date.valueOf()))
      return new Intl.DateTimeFormat(format.locale, {
        dateStyle: "medium",
        timeZone: "UTC",
      }).format(date);
  }
  if (column.type === "datetime" && typeof value === "string") {
    const date = new Date(value);
    if (!Number.isNaN(date.valueOf()))
      return new Intl.DateTimeFormat(format.locale, {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: format.timezone,
      }).format(date);
  }
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

export function cellView(
  column: GridColumn,
  cell: WorksheetCell | undefined,
  format: GridFormat,
): CellView {
  if (!cell) return { kind: "blank" };
  if ("link" in cell)
    return {
      kind: "link",
      label: cell.link.label,
      recordId: cell.link.record_id,
    };
  if ("unlinked" in cell) return { kind: "unlinked", text: cell.unlinked };
  if ("state" in cell)
    return { kind: "state", state: cell.state, words: STATE_WORDS[cell.state] };
  const value = cell.value;
  if (value === null || value === undefined || value === "")
    return { kind: "blank" };
  return { kind: "value", text: valueText(column, value, format) };
}

const TOTAL_WORDS: Record<WorksheetTotal["fn"], string> = {
  count: "Count",
  sum: "Sum",
  average: "Average",
  min: "Min",
  max: "Max",
};

/**
 * A total and its label. Totals cover every row; during a search the first
 * total says so ("Count · all 15 rows").
 */
export function totalView(
  column: GridColumn,
  total: WorksheetTotal,
  place: { first: boolean; searching: boolean; allRows: number },
  format: GridFormat,
): { label: string; text: string } {
  const word = TOTAL_WORDS[total.fn];
  const label =
    place.first && place.searching
      ? `${word} · all ${place.allRows} rows`
      : word;
  const text =
    total.value === null
      ? ""
      : (numberText(
          total.value,
          format,
          total.fn === "count" ? 0 : column.places,
        ) ?? String(total.value));
  return { label, text };
}

export function sortLabel(
  column: GridColumn,
  order: WorksheetRowSort["order"],
): string {
  const words = column.numeric
    ? order === "asc"
      ? "low to high"
      : "high to low"
    : column.type === "date" || column.type === "datetime"
      ? order === "asc"
        ? "oldest first"
        : "newest first"
      : order === "asc"
        ? "A to Z"
        : "Z to A";
  return `${column.name}, ${words}`;
}

/** The offsets of the pages of 200 rows that rows start to end fall in. */
export function pagesForRange(
  start: number,
  end: number,
  total: number,
): number[] {
  if (total <= 0) return [];
  const last = Math.min(Math.max(end, start), total - 1);
  const pages: number[] = [];
  for (
    let offset =
      Math.floor(Math.max(start, 0) / WORKSHEET_ROW_PAGE) * WORKSHEET_ROW_PAGE;
    offset <= last;
    offset += WORKSHEET_ROW_PAGE
  )
    pages.push(offset);
  return pages;
}

/** One key per search and sort; pages of another key are stale. */
export function rowQueryKey(query: {
  sort: WorksheetRowSort | null;
  search: string;
}): string {
  return JSON.stringify([
    query.sort?.key ?? null,
    query.sort?.order ?? null,
    query.search.trim(),
  ]);
}

export type RowStore = {
  queryKey: string;
  total: number | null;
  pages: Readonly<Record<number, readonly WorksheetRow[]>>;
  /** The request number of each stored page; an older answer is stale. */
  sequences: Readonly<Record<number, number>>;
};

export function emptyRowStore(queryKey: string): RowStore {
  return { queryKey, total: null, pages: {}, sequences: {} };
}

/**
 * Adds a page answered for `queryKey`. An answer for another search or sort
 * is dropped, and so is one whose request started before the stored page's
 * (`sequence` grows with each request).
 */
export function storeRowPage(
  store: RowStore,
  queryKey: string,
  offset: number,
  page: { rows: readonly WorksheetRow[]; total: number },
  sequence = 0,
): RowStore {
  if (queryKey !== store.queryKey) return store;
  if (sequence < (store.sequences[offset] ?? -1)) return store;
  return {
    queryKey,
    total: page.total,
    pages: { ...store.pages, [offset]: page.rows },
    sequences: { ...store.sequences, [offset]: sequence },
  };
}

export function rowAt(
  store: RowStore,
  index: number,
): WorksheetRow | undefined {
  const offset = Math.floor(index / WORKSHEET_ROW_PAGE) * WORKSHEET_ROW_PAGE;
  return store.pages[offset]?.[index - offset];
}

// ---------------------------------------------------------------- editing

/** A pasted block: one array per line, cells split at tabs (F4, X11). */
export function parsePastedGrid(text: string): string[][] {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  if (lines.length > 1 && lines.at(-1) === "") lines.pop();
  return lines.map((line) => line.split("\t"));
}

const YES = new Set(["true", "yes", "1", "checked"]);
const NO = new Set(["false", "no", "0", ""]);

/**
 * What a typed or pasted text sends for a column. Numbers go as text in the
 * organization's locale, so the server is their one parser (O4). Text that
 * starts like a formula stays text: nothing is evaluated (X11).
 */
export function inputValue(column: GridColumn, text: string): unknown {
  const trimmed = text.trim();
  if (column.type === "boolean") {
    const word = trimmed.toLowerCase();
    if (YES.has(word)) return true;
    if (NO.has(word)) return false;
    return trimmed;
  }
  if (trimmed === "") return null;
  if (column.numeric) return trimmed;
  return column.type === "long_text" ? text : trimmed;
}

/** The edit box's first text: the value as the organization writes it. */
export function editInput(
  column: GridColumn,
  cell: WorksheetCell | undefined,
  format: GridFormat,
): string {
  if (!cell || !("value" in cell) || cell.value === null) return "";
  const value = cell.value;
  if (column.numeric) {
    const number = typeof value === "number" ? value : Number(value);
    if (Number.isFinite(number))
      return new Intl.NumberFormat(format.locale, {
        useGrouping: false,
        minimumFractionDigits: column.places ?? 0,
        maximumFractionDigits: column.places ?? 20,
      }).format(number);
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return typeof value === "string" ? value : JSON.stringify(value);
}

const conflictSchema = z.object({
  keys: z.array(z.string()),
  current: z.object({
    id: z.string(),
    revision: z.number(),
    etag: z.string(),
    position: z.number(),
    cells: z.record(z.string(), z.unknown()),
  }),
});

/** A 412 `cell_changed`: the cells someone else changed, and the newer row. */
export function cellConflict(
  error: unknown,
): { keys: string[]; current: WorksheetRow } | null {
  if (!(error instanceof ApiError) || error.status !== 412) return null;
  const parsed = conflictSchema.safeParse(error.details);
  return parsed.success
    ? {
        keys: parsed.data.keys,
        current: parsed.data.current as WorksheetRow,
      }
    : null;
}

/**
 * A saved or refreshed row replaces its copy where the store holds it. Its
 * page takes the newer request number, so an older refresh cannot undo it.
 */
export function storeRow(
  store: RowStore,
  row: WorksheetRow,
  sequence: number,
): RowStore {
  for (const [key, rows] of Object.entries(store.pages)) {
    const index = rows.findIndex((item) => item.id === row.id);
    if (index < 0) continue;
    const offset = Number(key);
    const next = [...rows];
    next[index] = row;
    return {
      ...store,
      pages: { ...store.pages, [offset]: next },
      sequences: {
        ...store.sequences,
        [offset]: Math.max(sequence, store.sequences[offset] ?? -1),
      },
    };
  }
  return store;
}
