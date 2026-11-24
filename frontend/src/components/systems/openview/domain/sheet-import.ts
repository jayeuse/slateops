import {
  datetimeValue,
  type GridColumn,
  type SheetColumnType,
} from "./sheet-grid";

// Data import into a sheet (docs/specs/sheets.md X8 to X11, D8, D9.3 and
// Screens 8): read the file, choose the header row, map file columns to sheet
// columns, match a key column to records, and cut the rows into batches. The
// server is the one number parser (O4): number text goes as typed, and only
// the checks here decide that a cell cannot be sent, so one bad cell never
// fails a batch of 100. Loaded on first use only.

export type ImportCell = string | number | boolean | null;

export const CSV_MAX_BYTES = 8 * 1024 * 1024;
export const XLSX_MAX_BYTES = 10 * 1024 * 1024;
export const SHEET_MAX_ROWS = 10_000;
export const BATCH_ROWS = 100;
/** A batch's JSON body stays under the request cap (D8: 1 MiB). */
export const BATCH_BYTES = 1_000_000;
/** A stored row holds at most 32 KiB (D8, `MAX_ROW_BYTES`). */
export const ROW_BYTES = 32 * 1024;
export const MATCH_KEYS = 2_000;
export const KEY_MAX = 200;
const TEXT_MAX = 4_000;
const NAME_MAX = 150;

/** The file kind, or an Error whose message the dialog shows. */
export function importFileKind(file: {
  name: string;
  size: number;
}): "csv" | "xlsx" {
  const name = file.name.toLowerCase();
  if (/\.(xlsm|xltm|xlam)$/.test(name))
    throw new Error(
      "Macro-enabled Excel files cannot be imported. Save the file as .xlsx and try again.",
    );
  if (name.endsWith(".xlsx")) {
    if (file.size > XLSX_MAX_BYTES)
      throw new Error(
        "This Excel file is too large to read. Save it as CSV and import that.",
      );
    return "xlsx";
  }
  if (name.endsWith(".csv")) {
    // Stored rows are larger than the CSV they come from, and a sheet holds
    // at most 8 MiB (D8), so a larger CSV cannot fit.
    if (file.size > CSV_MAX_BYTES)
      throw new Error(
        "A CSV file can be at most 8 MiB, the most a sheet holds.",
      );
    return "csv";
  }
  throw new Error("Choose a CSV file or an Excel (.xlsx) file.");
}

/** A header and 10,000 rows: a sheet holds no more (D8). */
export const CSV_MAX_ROWS = 10_011;
/** Far above a sheet's 100 columns, and low enough to stop a hostile row. */
export const CSV_MAX_COLUMNS = 1_000;
export const OVER_LIMIT =
  "This file has more than 10,000 rows (or too many columns) for one import.";
const QUOTES = "The CSV file could not be read. Check its quotes.";
// The read gives the page a turn after each part of this many characters.
const CSV_PART = 65_536;

const DELIMITERS = [";", ",", "\t", "|"] as const;

/**
 * The file's delimiter: the most frequent of ; , tab | outside quotes on its
 * first rows (up to 5), a semicolon winning a tie. A quote opens a quoted
 * field only at the start of a field, so a quote inside unquoted text (a
 * header like Height (5'11")) does not change the count.
 */
function delimiterOf(text: string): string {
  const counts = new Map<string, number>(DELIMITERS.map((mark) => [mark, 0]));
  let quoted = false;
  let fieldStart = true;
  let lines = 0;
  for (let index = 0; index < text.length && index < CSV_PART; index += 1) {
    const char = text[index];
    if (quoted) {
      if (char === '"') {
        if (text[index + 1] === '"') index += 1;
        else quoted = false;
      }
      continue;
    }
    if (char === '"' && fieldStart) {
      quoted = true;
      fieldStart = false;
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && text[index + 1] === "\n") index += 1;
      lines += 1;
      fieldStart = true;
      if (lines >= 5) break;
    } else if (counts.has(char)) {
      counts.set(char, (counts.get(char) ?? 0) + 1);
      fieldStart = true;
    } else fieldStart = false;
  }
  let best = ",";
  let most = 0;
  // In list order, so a tie keeps the semicolon.
  for (const mark of DELIMITERS) {
    const count = counts.get(mark) ?? 0;
    if (count > most) {
      best = mark;
      most = count;
    }
  }
  return best;
}

/**
 * A CSV file's bytes as text: UTF-8 only, without its byte order mark.
 * Other encodings are refused, never guessed.
 */
export function decodeCsv(bytes: ArrayBuffer): string {
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new Error(
      "The CSV file must use UTF-8 text. Save it as UTF-8 and try again.",
    );
  }
}

// One shared array for blank rows: blank rows take no room of their own.
const BLANK_ROW: string[] = [];

function aborted(signal: AbortSignal | undefined) {
  if (signal?.aborted)
    throw new DOMException("The file read was stopped.", "AbortError");
}

/**
 * A CSV file's rows, as text (F7-S1). One pass, with no backtracking, in
 * parts that give the page a turn, so a hostile file cannot freeze the tab;
 * it stops at once past 10,011 rows or 1,000 columns, before any table is
 * built, and when the signal aborts (the dialog closed, another file). A
 * trailing line break adds no row; trailing blank rows are dropped.
 */
export async function parseCsv(
  text: string,
  options: { signal?: AbortSignal } = {},
): Promise<string[][]> {
  aborted(options.signal);
  // The file's size bounds every row, blank ones included (D8).
  if (text.length > CSV_MAX_BYTES)
    throw new Error("A CSV file can be at most 8 MiB, the most a sheet holds.");
  const delimiter = delimiterOf(text);
  const rows: string[][] = [];
  let filled = 0;
  let row: string[] = [];
  let cell = "";
  let fieldStart = true;
  let quotedField = false;
  const endCell = () => {
    row.push(cell);
    if (row.length > CSV_MAX_COLUMNS) throw new Error(OVER_LIMIT);
    cell = "";
    fieldStart = true;
    quotedField = false;
  };
  // Only rows with a value count toward the limit (F7 review).
  const endRow = () => {
    if (row.every((value) => value === "")) rows.push(BLANK_ROW);
    else {
      rows.push(row);
      filled += 1;
      if (filled > CSV_MAX_ROWS) throw new Error(OVER_LIMIT);
    }
    row = [];
  };
  let index = 0;
  let turn = CSV_PART;
  while (index < text.length) {
    if (index >= turn) {
      turn = index + CSV_PART;
      await new Promise((resolve) => setTimeout(resolve, 0));
      aborted(options.signal);
    }
    const char = text[index];
    if (fieldStart && char === '"') {
      // A quoted cell: up to the closing quote, "" standing for one quote.
      index += 1;
      for (;;) {
        const quote = text.indexOf('"', index);
        if (quote < 0) throw new Error(QUOTES);
        cell += text.slice(index, quote);
        if (text[quote + 1] === '"') {
          cell += '"';
          index = quote + 2;
        } else {
          index = quote + 1;
          break;
        }
      }
      fieldStart = false;
      quotedField = true;
      continue;
    }
    if (char === delimiter) {
      endCell();
      index += 1;
      continue;
    }
    if (char === "\n" || char === "\r") {
      endCell();
      endRow();
      index += char === "\r" && text[index + 1] === "\n" ? 2 : 1;
      continue;
    }
    // After a closing quote only a delimiter or a line break may follow.
    if (quotedField) throw new Error(QUOTES);
    let end = index;
    while (
      end < text.length &&
      text[end] !== delimiter &&
      text[end] !== "\n" &&
      text[end] !== "\r"
    )
      end += 1;
    cell += text.slice(index, end);
    fieldStart = false;
    index = end;
  }
  if (!fieldStart || row.length) {
    endCell();
    endRow();
  }
  while (rows.length && rows.at(-1)?.every((value) => value.trim() === ""))
    rows.pop();
  if (!rows.length) throw new Error("The file has no rows.");
  return rows;
}

function cellText(cell: ImportCell): string {
  return cell === null ? "" : String(cell).trim();
}

// Python's `str.lstrip` whitespace, character by character (not `\s`).
const SPACES =
  "\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const LEADING = `[${SPACES}]`;
/**
 * The export marks text with one apostrophe when this matches at its start
 * (`safe_text`, records/export.py, as the backend states it for every first
 * character of the Basic Multilingual Plane): apostrophes, then a tab, CR
 * or LF, or = + - @ after leading whitespace.
 */
const MARKED = new RegExp(`^'*(?:[\\t\\r\\n]|${LEADING}*[=+\\-@])`);
/** The import drops the first character when this matches (X12). */
const MARK = new RegExp(`^'(?='*(?:[\\t\\r\\n]|${LEADING}*[=+\\-@]))`);

/** Whether the export puts its apostrophe before this text. */
export function needsMark(text: string): boolean {
  return MARKED.test(text);
}

/**
 * Text as the organization's own export wrote it: the one apostrophe the
 * export added is taken away; any other stays. The text is still stored as
 * text and never evaluated (X11).
 */
export function fromExport(text: string): string {
  return MARK.test(text) ? text.slice(1) : text;
}

export type FileTable = {
  headers: string[];
  /** Data rows under the header row; `fileRow` counts from 1. */
  body: { fileRow: number; cells: ImportCell[] }[];
};

/** The rows under the chosen header row (0-based), with no blank rows. */
export function fileTable(rows: ImportCell[][], headerRow: number): FileTable {
  // A loop, not a spread: a spread of 10,000 rows can pass the engine's
  // argument limit.
  let width = 0;
  for (const row of rows) if (row.length > width) width = row.length;
  const head = rows[headerRow] ?? [];
  const headers = Array.from({ length: width }, (_, index) => {
    const text = cellText(head[index] ?? null);
    return text ? text.slice(0, NAME_MAX) : `Column ${index + 1}`;
  });
  const body = rows
    .map((cells, index) => ({ fileRow: index + 1, cells }))
    .slice(headerRow + 1)
    .filter((row) => row.cells.some((cell) => cellText(cell) !== ""));
  return { headers, body };
}

// ------------------------------------------------------------------ numbers

type NumberRule = {
  decimal: string;
  group: string;
  /** Digits and one decimal mark, with no grouping. */
  plain: RegExp;
  /** Digits with the locale's group mark in the whole part. */
  grouped: RegExp;
};

// One rule per locale: building a number format and a pattern per cell made
// a 10,000-row file take seconds.
const numberRules = new Map<string, NumberRule>();

function numberRule(locale: string): NumberRule {
  const known = numberRules.get(locale);
  if (known) return known;
  const parts = new Intl.NumberFormat(locale).formatToParts(12345.6);
  const decimal = parts.find((part) => part.type === "decimal")?.value ?? ".";
  const group = parts.find((part) => part.type === "group")?.value ?? ",";
  const fraction = `(?:${escaped(decimal)}(\\d+))?`;
  const rule = {
    decimal,
    group,
    plain: new RegExp(`^(-?)(\\d+)${fraction}$`),
    grouped: new RegExp(`^(-?)(\\d(?:\\d|${escaped(group)})*\\d)${fraction}$`),
  };
  numberRules.set(locale, rule);
  return rule;
}

// One format per locale and fraction length, to read grouped text back.
const formats = new Map<string, Intl.NumberFormat>();

function formatOf(locale: string, places: number): Intl.NumberFormat {
  const key = `${locale}|${places}`;
  let format = formats.get(key);
  if (!format) {
    format = new Intl.NumberFormat(locale, {
      minimumFractionDigits: places,
      maximumFractionDigits: places,
    });
    formats.set(key, format);
  }
  return format;
}

function escaped(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

type Digits = { negative: boolean; whole: string; fraction: string };

/**
 * Number text in the locale as its digits, or null. An estimate only: the
 * server's parse decides (R5). It is stricter than the server where they
 * may differ: grouped text counts only when the locale writes the number
 * exactly so, and a first group never starts with 0.
 */
function textDigits(text: string, locale: string): Digits | null {
  const trimmed = text.trim();
  const rule = numberRule(locale);
  const plain = rule.plain.exec(trimmed);
  if (plain)
    return {
      negative: plain[1] === "-",
      whole: plain[2],
      fraction: plain[3] ?? "",
    };
  const grouped = rule.grouped.exec(trimmed);
  if (!grouped || grouped[2].startsWith("0")) return null;
  const whole = grouped[2].split(rule.group).join("");
  const fraction = grouped[3] ?? "";
  if (fraction.length > 20) return null;
  const value = Number(`${grouped[1]}${whole}.${fraction || "0"}`);
  if (formatOf(locale, fraction.length).format(value) !== trimmed) return null;
  return { negative: grouped[1] === "-", whole, fraction };
}

/**
 * An Excel number as its digits, read from the text it reads back with
 * (`String`), exponents included (1e-21, 1e21), or null when not finite.
 */
function numberDigits(value: number): Digits | null {
  if (!Number.isFinite(value)) return null;
  const match = /^(-?)(\d+)(?:\.(\d+))?(?:e([+-]\d+))?$/.exec(String(value));
  if (!match) return null;
  const digits = `${match[2]}${match[3] ?? ""}`;
  const point = match[2].length + Number(match[4] ?? 0);
  if (point <= 0)
    return {
      negative: match[1] === "-",
      whole: "0",
      fraction: `${"0".repeat(-point)}${digits}`,
    };
  if (point >= digits.length)
    return {
      negative: match[1] === "-",
      whole: `${digits}${"0".repeat(point - digits.length)}`,
      fraction: "",
    };
  return {
    negative: match[1] === "-",
    whole: digits.slice(0, point),
    fraction: digits.slice(point),
  };
}

/**
 * A number written in the organization's locale (O4): its decimal mark, and
 * its group mark only between groups of three digits. Used to suggest types
 * and to flag cells before a write; the server parses the text itself.
 */
export function localeNumber(text: string, locale: string): number | null {
  const digits = textDigits(text, locale);
  if (!digits) return null;
  const value = Number(
    `${digits.negative ? "-" : ""}${digits.whole}.${digits.fraction || "0"}`,
  );
  return Number.isFinite(value) ? value : null;
}

const LARGEST_EXACT_INTEGER = Number.MAX_SAFE_INTEGER;

/**
 * Whether the server stores these digits in a column of this type
 * (worksheets/cells.py `_number`, `_json_number`; sandbox/fields
 * validation.py `_canonical_decimal`): at most 38 whole digits and an
 * exponent within 37 either way; whole numbers within 2^53 - 1; other
 * numbers with at most 15 significant digits; decimals with at most 18
 * fraction digits.
 */
function storable(type: "int" | "number" | "decimal", digits: Digits): boolean {
  const whole = digits.whole.replace(/^0+/, "");
  const fraction = digits.fraction.replace(/0+$/, "");
  if (whole.length > 38) return false;
  if (!whole && fraction) {
    const leading = fraction.length - fraction.replace(/^0+/, "").length;
    if (leading >= 37) return false;
  }
  const isWhole = fraction === "";
  if (type === "int" && !isWhole) return false;
  if (type === "decimal") return digits.fraction.length <= 18;
  if (isWhole)
    return whole.length <= 16 && Number(whole || "0") <= LARGEST_EXACT_INTEGER;
  return (whole + fraction).replace(/^0+/, "").length <= 15;
}

// ------------------------------------------------------------- column types

/** The types a new sheet's column can take from a file (Decision 14). */
export type NewColumnType =
  "text" | "long_text" | "int" | "decimal" | "boolean" | "date" | "datetime";

const YES = new Set(["true", "yes", "y"]);
const NO = new Set(["false", "no", "n"]);
const DATE = /^\d{4}-\d{2}-\d{2}$/;
// The server's patterns (sandbox/designs/date_values.py).
const DATETIME =
  /^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,6})?)?(Z|[+-](\d{2}):(\d{2}))?$/;
// The server's URL regex, with Python's whitespace for `\s`.
const URL_TEXT = new RegExp(`^https?://[^${SPACES}/$.?#][^${SPACES}]*$`);

const SPACE = new RegExp(`[${SPACES}]`);

/**
 * The server's email rule in one pass (F7-S1; the same answers as
 * `[^\s@]+@[^\s@]+\.[^\s@]+` with no backtracking): no whitespace, one @
 * with text before it, and a dot after it with text on both sides.
 */
function validEmail(value: string): boolean {
  if (SPACE.test(value)) return false;
  const at = value.indexOf("@");
  if (at <= 0 || value.indexOf("@", at + 1) !== -1) return false;
  return value.slice(at + 2, -1).includes(".");
}

/** A real calendar date in ISO form (`date.fromisoformat`). */
function realDate(text: string): boolean {
  if (!DATE.test(text)) return false;
  const [year, month, day] = text.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return (
    year >= 1 &&
    date.getUTCFullYear() === year &&
    date.getUTCMonth() === month - 1 &&
    date.getUTCDate() === day
  );
}

/** A date and time the server reads (`parse_datetime`); null when not. */
function realDatetime(text: string) {
  const match = DATETIME.exec(text);
  if (!match || !realDate(match[1])) return null;
  const [hours, minutes, seconds] = [match[2], match[3], match[4] ?? "0"].map(
    Number,
  );
  if (hours > 23 || minutes > 59 || seconds > 59) return null;
  // An offset is within plus or minus 23:59.
  if (match[6] && (Number(match[6]) > 23 || Number(match[7]) > 59)) return null;
  return { offset: match[5] ?? null };
}

/** Text length as the server counts it: code points, not UTF-16 units. */
function textLength(text: string): number {
  return Array.from(text).length;
}

function fractionDigits(cell: ImportCell, locale: string): number {
  if (typeof cell === "number") {
    const [, fraction = ""] = String(cell).split(".");
    return fraction.length;
  }
  const { decimal } = numberRule(locale);
  const [, fraction = ""] = cellText(cell).split(decimal);
  return fraction.length;
}

/** The type suggested for a file column of a new sheet; the person may change it. */
export function suggestColumnType(
  values: readonly ImportCell[],
  locale: string,
): { type: NewColumnType; places?: number } {
  const filled = values.filter((cell) => cellText(cell) !== "");
  if (!filled.length) return { type: "text" };
  const every = (test: (cell: ImportCell) => boolean) => filled.every(test);
  const asNumber = (cell: ImportCell) =>
    typeof cell === "number"
      ? cell
      : typeof cell === "string"
        ? localeNumber(cell, locale)
        : null;
  if (
    every(
      (cell) =>
        typeof cell === "boolean" ||
        YES.has(cellText(cell).toLowerCase()) ||
        NO.has(cellText(cell).toLowerCase()),
    ) &&
    every((cell) => typeof cell === "boolean" || !/^\d+$/.test(cellText(cell)))
  )
    return { type: "boolean" };
  if (every((cell) => asNumber(cell) !== null)) {
    if (every((cell) => Number.isInteger(asNumber(cell))))
      return { type: "int" };
    let places = 0;
    for (const cell of filled)
      places = Math.max(places, fractionDigits(cell, locale));
    return { type: "decimal", places: Math.min(places, 6) };
  }
  if (every((cell) => DATE.test(cellText(cell)))) return { type: "date" };
  if (every((cell) => realDatetime(cellText(cell)) !== null))
    return { type: "datetime" };
  if (
    every((cell) => !/\n/.test(cellText(cell)) && cellText(cell).length <= 255)
  )
    return { type: "text" };
  return { type: "long_text" };
}

/** Sheet columns a file column cannot go into (shown as "Not added"). */
export function importableColumn(column: GridColumn): boolean {
  return !column.readOnly && column.type !== "user";
}

/** A sheet column as the import writes into it. */
export type ImportTarget = Pick<GridColumn, "key" | "name" | "type"> & {
  options?: Record<string, string>;
};

/**
 * The value a file cell sends into a column, `null` for an empty cell, or
 * `undefined` when the server would refuse it, so the cell is added empty
 * and counted (F7-B1: the server's own cell rules). Text that starts like a
 * formula stays text (X11), less the export's mark (X12). Number text goes
 * as written (the server reads it in the locale, O4); an Excel number goes
 * as a number. A date and time with no offset, or a date alone, is read in
 * the organization's time zone and sent as an instant (D1).
 */
export function importValue(
  target: Pick<ImportTarget, "type" | "options">,
  cell: ImportCell,
  locale: string,
  /** The organization's zone (D1); no zone, no naive time is read. */
  timezone?: string,
  source: ImportSource = "csv",
): unknown {
  const text = cellText(cell);
  if (text === "") return null;
  const type: SheetColumnType = target.type;
  if (type === "int" || type === "number" || type === "decimal") {
    const digits =
      typeof cell === "number" ? numberDigits(cell) : textDigits(text, locale);
    if (!digits || !storable(type, digits)) return undefined;
    return typeof cell === "number" ? cell : text;
  }
  if (type === "boolean") {
    if (typeof cell === "boolean") return cell;
    const word = text.toLowerCase();
    if (YES.has(word)) return true;
    if (NO.has(word)) return false;
    return undefined;
  }
  if (type === "date") {
    if (realDate(text)) return text;
    return realDatetime(text) ? text.slice(0, 10) : undefined;
  }
  if (type === "datetime") {
    const read = realDate(text) ? { offset: null } : realDatetime(text);
    if (!read) return undefined;
    if (read.offset) return text;
    if (!timezone) return undefined;
    return datetimeValue(realDate(text) ? `${text}T00:00` : text, timezone);
  }
  // The export's mark goes before anything is read, CSV only (X12).
  const unmarked = unmark(cell, source);
  if (type === "select") {
    const label = unmarked.trim();
    const options = Object.entries(target.options ?? {});
    const found =
      options.find(([, option]) => option === label) ??
      options.find(
        ([, option]) => option.toLowerCase() === label.toLowerCase(),
      );
    return found ? found[1] : undefined;
  }
  if (type === "email" || type === "url") {
    const value = unmarked.trim();
    if (textLength(value) > TEXT_MAX) return undefined;
    return (type === "email" ? validEmail(value) : URL_TEXT.test(value))
      ? value
      : undefined;
  }
  if (type === "text" || type === "long_text")
    // Text keeps its spaces: the export's mark may stand before them.
    return textLength(unmarked) > TEXT_MAX ? undefined : unmarked;
  return undefined;
}

/** Where cells come from: only the CSV export marks formula-like text. */
export type ImportSource = "csv" | "xlsx";

/** A cell as text, less the CSV export's mark. */
function unmark(cell: ImportCell, source: ImportSource): string {
  if (typeof cell !== "string") return cellText(cell);
  return source === "csv" ? fromExport(cell) : cell;
}

/**
 * What goes to the server for a cell the estimate doubts: the cell as the
 * file has it, so the server's own rule decides (R5; `invalid_cells:
 * "empty"` stores it empty and counts it when it fails).
 */
function asSent(cell: ImportCell, source: ImportSource): unknown {
  if (cellText(cell) === "") return null;
  return typeof cell === "string" ? unmark(cell, source) : cell;
}

const PROBLEM_WORDS: Partial<Record<SheetColumnType, string>> = {
  int: "whole numbers",
  number: "numbers",
  decimal: "numbers",
  boolean: "yes or no",
  date: "dates (YYYY-MM-DD)",
  datetime: "dates and times",
  email: "email addresses",
  url: "web links (http or https)",
  select: `one of the column's choices`,
};

/** "2 cells in Quiz 1 are not numbers. They are added empty." */
export function cellProblemWords(
  target: Pick<ImportTarget, "name" | "type">,
  count: number,
): string {
  const cells = `${count} ${count === 1 ? "cell" : "cells"} in ${target.name}`;
  const verb = count === 1 ? "is" : "are";
  const what = PROBLEM_WORDS[target.type];
  // An estimate: the server decides (R5).
  const may = count === 1 ? "It may be" : "They may be";
  return what
    ? `${cells} ${verb} not ${what}. ${may} added empty.`
    : `${cells} ${verb} longer than 4,000 characters. ${may} added empty.`;
}

// ------------------------------------------------------------- key matching

export type KeyResult =
  | { state: "matched"; recordId: string; label: string }
  | { state: "unmatched" }
  | { state: "ambiguous" };

/** The key a cell gives; blank or over 200 characters is never sent (no match). */
export function importKey(
  cell: ImportCell,
  source: ImportSource = "csv",
): string | null {
  const text = unmark(cell, source).trim();
  return text && text.length <= KEY_MAX ? text : null;
}

/** Each key once, in file order, in chunks of at most `size` keys (route 22). */
export function keyChunks(
  keys: readonly (string | null)[],
  size = MATCH_KEYS,
): string[][] {
  const unique = [
    ...new Set(keys.filter((key): key is string => key !== null)),
  ];
  const chunks: string[][] = [];
  for (let start = 0; start < unique.length; start += size)
    chunks.push(unique.slice(start, start + size));
  return chunks;
}

/** Each row's result: a key matched more than once is ambiguous wherever it appears. */
export function rowResults(
  keys: readonly (string | null)[],
  found: ReadonlyMap<string, KeyResult>,
): KeyResult[] {
  return keys.map((key) =>
    key === null
      ? { state: "unmatched" }
      : (found.get(key) ?? { state: "unmatched" }),
  );
}

export type MatchCounts = {
  matched: number;
  unmatched: number;
  ambiguous: number;
};

/** The three counts, of rows (not of keys). */
export function matchCounts(results: readonly KeyResult[]): MatchCounts {
  const counts = { matched: 0, unmatched: 0, ambiguous: 0 };
  for (const result of results) counts[result.state] += 1;
  return counts;
}

// ------------------------------------------------------------------- writes

export type ColumnPlan = { fileIndex: number; target: ImportTarget };

export type ImportLink = {
  key: string;
  fileIndex: number;
  results: readonly KeyResult[];
  /** Rows without one match: kept as unlinked text, or skipped (X8, Decision 13). */
  unmatched: "keep" | "skip";
};

export type ImportRows = {
  rows: Record<string, unknown>[];
  /** Per column key: cells that cannot go into the column, added empty. */
  problems: Map<string, number>;
  skipped: number;
  /** Rows over 32 KiB, which the server refuses: left out (D8). */
  oversized: number;
  /** Per row sent: cells the import itself sent empty (unread times). */
  cleared: number[];
};

const encoder = new TextEncoder();

/** Bytes of compact UTF-8 JSON, as the server measures rows and bodies. */
function jsonBytes(value: unknown): number {
  return encoder.encode(JSON.stringify(value)).length;
}

/** The rows to create, and what the preview must say about them. */
export function importRows(options: {
  body: FileTable["body"];
  plan: readonly ColumnPlan[];
  link: ImportLink | null;
  locale: string;
  timezone?: string;
  source?: ImportSource;
}): ImportRows {
  const source = options.source ?? "csv";
  const problems = new Map<string, number>();
  const rows: Record<string, unknown>[] = [];
  let skipped = 0;
  let oversized = 0;
  const cleared: number[] = [];
  options.body.forEach((row, index) => {
    const cells: Record<string, unknown> = {};
    let emptiedHere = 0;
    const link = options.link;
    if (link) {
      const result = link.results[index] ?? { state: "unmatched" };
      if (result.state === "matched")
        cells[link.key] = { record_id: result.recordId };
      else if (link.unmatched === "skip") {
        skipped += 1;
        return;
      } else {
        const text = unmark(row.cells[link.fileIndex] ?? null, source)
          .trim()
          .slice(0, TEXT_MAX);
        cells[link.key] = text ? { unlinked: text } : null;
      }
    }
    for (const { fileIndex, target } of options.plan) {
      const cell = row.cells[fileIndex] ?? null;
      const value = importValue(
        target,
        cell,
        options.locale,
        options.timezone,
        source,
      );
      // The preview counts a doubted cell; the server decides it (R5).
      if (value === undefined) {
        problems.set(target.key, (problems.get(target.key) ?? 0) + 1);
        // A time it cannot read goes empty: the server would read a time
        // with no offset as UTC, not in the organization's zone (D1).
        if (target.type === "datetime") {
          cells[target.key] = null;
          emptiedHere += 1;
        } else cells[target.key] = asSent(cell, source);
      } else cells[target.key] = value;
    }
    if (jsonBytes(cells) > ROW_BYTES) {
      oversized += 1;
      return;
    }
    rows.push(cells);
    cleared.push(emptiedHere);
  });
  return { rows, problems, skipped, oversized, cleared };
}

/**
 * Rows in the batches of route 14: at most 100 each, and each body under
 * 1,000,000 bytes of JSON (D8), counted as `writeWorksheetRows` sends it.
 */
export function rowBatches<T>(
  rows: readonly T[],
  structureRevision: number,
): T[][] {
  const empty = jsonBytes({
    structure_revision: structureRevision,
    creates: [],
    invalid_cells: "empty",
  });
  const batches: T[][] = [];
  let batch: T[] = [];
  let bytes = empty;
  for (const row of rows) {
    const size = jsonBytes({ cells: row });
    // A comma joins each create after the first.
    if (
      batch.length &&
      (batch.length >= BATCH_ROWS || bytes + 1 + size > BATCH_BYTES)
    ) {
      batches.push(batch);
      batch = [];
      bytes = empty;
    }
    bytes += (batch.length ? 1 : 0) + size;
    batch.push(row);
  }
  if (batch.length) batches.push(batch);
  return batches;
}

/** Column names of a new sheet: each one once, at most 150 characters. */
export function uniqueNames(names: readonly string[]): string[] {
  const seen = new Set<string>();
  return names.map((name) => {
    const base = name.trim().slice(0, NAME_MAX - 4) || "Column";
    let candidate = name.trim().slice(0, NAME_MAX) || "Column";
    for (let count = 2; seen.has(candidate.toLowerCase()); count += 1)
      candidate = `${base} ${count}`;
    seen.add(candidate.toLowerCase());
    return candidate;
  });
}

/** A new sheet's column from a file column (Decision 14); never a person. */
export type NewColumn =
  | { name: string; type: Exclude<NewColumnType, "decimal"> }
  | { name: string; type: "decimal"; places: number }
  | {
      name: string;
      type: "link";
      link: { moduleName: string; departmentName: string };
    };

/**
 * The template route 3 makes a new sheet from a data file with: one column
 * per added file column, keys c1 to cn in order, names made unique. Its
 * link column is mapped to its module by id in the create request.
 */
export function dataTemplate(title: string, columns: readonly NewColumn[]) {
  const names = uniqueNames(columns.map((column) => column.name));
  return {
    kind: "slateops-worksheet-template" as const,
    schemaVersion: 1 as const,
    title,
    columns: columns.map((column, index) => {
      const base = { key: `c${index + 1}`, name: names[index] };
      if (column.type === "link")
        return { ...base, type: "link" as const, link: column.link };
      if (column.type === "decimal")
        return {
          ...base,
          type: "decimal" as const,
          decimal: { places: column.places, currency: false },
        };
      return { ...base, type: column.type };
    }),
    groups: [] as { name: string; keys: string[] }[],
    totals: {} as Record<string, string>,
  };
}
