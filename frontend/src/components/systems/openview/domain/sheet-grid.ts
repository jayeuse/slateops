import { z } from "zod";
import { ApiError } from "@/lib/api";
import { formatDateTimeLocal } from "@/lib/date-time";
import { Temporal } from "@js-temporal/polyfill";
import {
  WORKSHEET_ROW_PAGE,
  worksheetRowSchema,
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
  /** The link column a lookup reads through. */
  lookupLinkKey?: string;
  places?: number;
  /** A Number column with the currency option (K2). */
  currency?: boolean;
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
    if (column.type === "lookup") view.lookupLinkKey = column.lookup.linkKey;
    if (column.type === "decimal") {
      view.places = column.decimal.places;
      if (column.decimal.currency) view.currency = true;
    }
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

export type GridFormat = {
  locale: string;
  timezone: string;
  /** The organization's currency (ISO 4217), when its profile is read. */
  currency?: string;
};

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
  | { kind: "state"; state: WorksheetCellState; words: string }
  | { kind: "error"; words: string };

function numberText(
  value: unknown,
  format: GridFormat,
  places?: number,
  currency?: string,
): string | null {
  const number =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : NaN;
  if (!Number.isFinite(number)) return null;
  // A currency column shows the organization's currency in its locale
  // (K2, O3); its places are the column's. Editing and exports keep the
  // plain number (X4).
  if (currency)
    return new Intl.NumberFormat(format.locale, {
      style: "currency",
      currency,
      minimumFractionDigits: places ?? 2,
      maximumFractionDigits: places ?? 2,
    }).format(number);
  return new Intl.NumberFormat(format.locale, {
    minimumFractionDigits: places ?? 0,
    maximumFractionDigits: places ?? 2,
  }).format(number);
}

/** The currency a column's numbers show in, if any. */
const columnCurrency = (column: GridColumn, format: GridFormat) =>
  column.currency ? format.currency : undefined;

function valueText(
  column: GridColumn,
  value: unknown,
  format: GridFormat,
): string {
  if (column.type === "select" && typeof value === "string")
    return column.options?.[value] ?? value;
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (column.numeric) {
    const text = numberText(
      value,
      format,
      column.places,
      columnCurrency(column, format),
    );
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
    return {
      kind: "state",
      state: cell.state,
      words:
        cell.state === "multiple_matches" && cell.count
          ? // 101 stands for more than 100 matching rows.
            cell.count > 100
            ? "100+ matches"
            : `${cell.count} matches`
          : STATE_WORDS[cell.state],
    };
  // A computed cell that cannot be worked out (D7.2), shown with a warn mark.
  if ("error" in cell)
    return {
      kind: "error",
      words:
        cell.error === "division_by_zero"
          ? "Division by zero"
          : cell.error === "overflow"
            ? "Number too large"
            : "Cannot be calculated",
    };
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
  const scope =
    place.first && place.searching
      ? `${word} · all ${place.allRows} rows`
      : word;
  // Cells the viewer cannot read are skipped and counted (K6, D7.3).
  const label =
    total.hidden_count > 0 ? `${scope} · ${total.hidden_count} hidden` : scope;
  const text =
    total.value === null
      ? ""
      : (numberText(
          total.value,
          format,
          total.fn === "count" ? 0 : column.places,
          total.fn === "count" ? undefined : columnCurrency(column, format),
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
      : column.type === "boolean"
        ? order === "asc"
          ? "No first"
          : "Yes first"
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
  /** The totals cover every row, whatever the search: they outlive a key. */
  totals: Readonly<Record<string, WorksheetTotal>>;
  /** The request number of the answer that set `total` and `totals`. */
  answered: number;
  pages: Readonly<Record<number, readonly WorksheetRow[]>>;
  /** The request number of each stored page; an older answer is stale. */
  sequences: Readonly<Record<number, number>>;
};

export function emptyRowStore(
  queryKey: string,
  totals: RowStore["totals"] = {},
): RowStore {
  return {
    queryKey,
    total: null,
    totals,
    answered: -1,
    pages: {},
    sequences: {},
  };
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
  page: {
    rows: readonly WorksheetRow[];
    total: number;
    totals?: Record<string, WorksheetTotal>;
  },
  sequence = 0,
): RowStore {
  if (queryKey !== store.queryKey) return store;
  if (sequence < (store.sequences[offset] ?? -1)) return store;
  // The row count and totals come from the newest answer of any page: an
  // older answer for another page must not bring back older ones.
  const newest = sequence >= store.answered;
  return {
    ...store,
    total: newest ? page.total : store.total,
    totals: newest && page.totals ? page.totals : store.totals,
    answered: newest ? sequence : store.answered,
    pages: { ...store.pages, [offset]: page.rows },
    sequences: { ...store.sequences, [offset]: sequence },
  };
}

/** Where a row is in the loaded pages, by its id; -1 when not loaded. */
export function rowIndex(store: RowStore, rowId: string): number {
  for (const [offset, rows] of Object.entries(store.pages)) {
    const at = rows.findIndex((row) => row.id === rowId);
    if (at >= 0) return Number(offset) + at;
  }
  return -1;
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
  // A date and time is edited in the organization's time zone (O3).
  if (column.type === "datetime")
    return formatDateTimeLocal(value, format.timezone);
  return typeof value === "string" ? value : JSON.stringify(value);
}

/**
 * The instant a "date and time" edit names in the organization's time zone,
 * sent as an ISO value with its offset; a time that a clock change skips
 * moves forward, as the clock does. Empty clears the cell.
 */
export function datetimeValue(draft: string, timezone: string): string | null {
  if (!draft.trim()) return null;
  return Temporal.PlainDateTime.from(draft)
    .toZonedDateTime(timezone, { disambiguation: "compatible" })
    .toInstant()
    .toString();
}

const conflictSchema = z.object({
  code: z.literal("cell_changed"),
  keys: z.array(z.string()),
  // Who changed the cells, when the editor can see them (F4); else null.
  changed_by: z
    .object({ id: z.string(), display_name: z.string() })
    .nullable()
    .optional(),
  current: worksheetRowSchema,
});

/** A 412 `cell_changed`: the cells someone else changed, and the newer row. */
export function cellConflict(error: unknown): {
  keys: string[];
  current: WorksheetRow;
  changedBy: string | null;
} | null {
  if (!(error instanceof ApiError) || error.status !== 412) return null;
  const parsed = conflictSchema.safeParse(error.details);
  return parsed.success
    ? {
        keys: parsed.data.keys,
        current: parsed.data.current,
        changedBy: parsed.data.changed_by?.display_name ?? null,
      }
    : null;
}

/** The conflict line's first sentence (Screens 3; F4). */
export function conflictWords(changedBy: string | null): string {
  return `${changedBy ?? "Someone"} changed this row while you were editing it.`;
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
