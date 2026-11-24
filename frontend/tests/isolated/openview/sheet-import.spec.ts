import { expect, test } from "@playwright/test";

import {
  cellProblemWords,
  decodeCsv,
  dataTemplate,
  fromExport,
  needsMark,
  fileTable,
  importableColumn,
  importFileKind,
  importKey,
  importRows,
  importValue,
  keyChunks,
  localeNumber,
  matchCounts,
  parseCsv,
  rowBatches,
  rowResults,
  suggestColumnType,
  uniqueNames,
  type KeyResult,
} from "../../../src/components/systems/openview/domain/sheet-import";
import { gridColumns } from "../../../src/components/systems/openview/domain/sheet-grid";
import type { WorksheetStructure } from "../../../src/components/systems/openview/adapters/worksheets-api";

// docs/specs/sheets.md X8 to X11, D8, D9.3, O4, Decisions 13 and 14 (SH-35,
// SH-36 UI, SH-37): reading a data file, the header row, type suggestions,
// what each cell sends, key matching in chunks and the batches of 100.

const MiB = 1024 * 1024;

test("a file is a CSV of at most 8 MiB or an .xlsx of at most 10 MiB; macro files are refused", () => {
  expect(importFileKind({ name: "Roster.CSV", size: 8 * MiB })).toBe("csv");
  expect(importFileKind({ name: "roster.xlsx", size: 10 * MiB })).toBe("xlsx");
  expect(() =>
    importFileKind({ name: "roster.csv", size: 8 * MiB + 1 }),
  ).toThrow("A CSV file can be at most 8 MiB, the most a sheet holds.");
  expect(() =>
    importFileKind({ name: "roster.xlsx", size: 10 * MiB + 1 }),
  ).toThrow(
    "This Excel file is too large to read. Save it as CSV and import that.",
  );
  expect(() => importFileKind({ name: "roster.xlsm", size: 10 })).toThrow(
    "Macro-enabled Excel files cannot be imported. Save the file as .xlsx and try again.",
  );
  expect(() => importFileKind({ name: "roster.xls", size: 10 })).toThrow(
    "Choose a CSV file or an Excel (.xlsx) file.",
  );
});

test("a CSV keeps quoted commas and line breaks and drops trailing blank lines", async () => {
  expect(
    await parseCsv('Name,Notes\r\n"Cruz, Ana","line 1\nline 2"\r\n\r\n'),
  ).toEqual([
    ["Name", "Notes"],
    ["Cruz, Ana", "line 1\nline 2"],
  ]);
  expect(await parseCsv('A\n"say ""hi"""\n')).toEqual([["A"], ['say "hi"']]);
  // A file whose cells a semicolon parts, as comma-decimal locales write.
  expect(await parseCsv("Name;Grade\nAna;12,5\n")).toEqual([
    ["Name", "Grade"],
    ["Ana", "12,5"],
  ]);
  await expect(parseCsv("\r\n")).rejects.toThrow("The file has no rows.");
  await expect(parseCsv('Name\n"Ana')).rejects.toThrow(
    "The CSV file could not be read. Check its quotes.",
  );
});

const OVER_LIMIT =
  "This file has more than 10,000 rows (or too many columns) for one import.";

test("a file over 10,000 rows or 1,000 columns stops while it is read, before a table is built (F7-S1)", async () => {
  expect(await parseCsv(`Name\n${"a\n".repeat(10_010)}`)).toHaveLength(10_011);
  await expect(parseCsv(`Name\n${"a\n".repeat(10_011)}`)).rejects.toThrow(
    OVER_LIMIT,
  );
  expect((await parseCsv(`x${",".repeat(999)}\n`))[0]).toHaveLength(1_000);
  await expect(parseCsv(`x${",".repeat(1_000)}\n`)).rejects.toThrow(OVER_LIMIT);
  // The probes' hostile shapes stop at the limit too (one pass, no backtracking).
  await expect(parseCsv('"a""b"\n'.repeat(1_000_000))).rejects.toThrow(
    OVER_LIMIT,
  );
  await expect(parseCsv(`"a",`.repeat(80_000))).rejects.toThrow(OVER_LIMIT);
});

test("a read that is aborted stops", async () => {
  const controller = new AbortController();
  controller.abort();
  await expect(
    parseCsv("a\n".repeat(5_000), { signal: controller.signal }),
  ).rejects.toMatchObject({ name: "AbortError" });
});

test("the chosen header row names the columns; rows above it and blank rows are left out", () => {
  const table = fileTable(
    [
      ["Class 4D roster", null],
      ["Full name", ""],
      ["Ana Cruz", 18],
      ["", null],
      ["Ben Reyes", 12.5],
    ],
    1,
  );
  expect(table.headers).toEqual(["Full name", "Column 2"]);
  expect(table.body).toEqual([
    { fileRow: 3, cells: ["Ana Cruz", 18] },
    { fileRow: 5, cells: ["Ben Reyes", 12.5] },
  ]);
});

test("numbers read in the organization's locale, with grouping only in threes", () => {
  expect(localeNumber("1,234.5", "en-US")).toBe(1234.5);
  expect(localeNumber("-12", "en-US")).toBe(-12);
  expect(localeNumber("12,5", "de-DE")).toBe(12.5);
  expect(localeNumber("1.234,5", "de-DE")).toBe(1234.5);
  // The organization's own export writes the locale's mark, no grouping (B13).
  expect(localeNumber("1234,50", "de-DE")).toBe(1234.5);
  for (const [text, locale] of [
    ["12,5", "en-US"],
    ["1,23", "en-US"],
    ["12.5.1", "en-US"],
    ["1e5", "en-US"],
    ["", "en-US"],
    ["=1+1", "en-US"],
  ])
    expect(localeNumber(text, locale)).toBeNull();
});

test("a new sheet's columns get a suggested type from their values (Decision 14)", () => {
  expect(suggestColumnType(["18", "9", ""], "en-US")).toEqual({ type: "int" });
  expect(suggestColumnType(["12,5", "9,25"], "de-DE")).toEqual({
    type: "decimal",
    places: 2,
  });
  expect(suggestColumnType([12.5, 3], "en-US")).toEqual({
    type: "decimal",
    places: 1,
  });
  expect(suggestColumnType(["true", "false", true], "en-US")).toEqual({
    type: "boolean",
  });
  expect(suggestColumnType(["2026-11-24", "2026-01-05"], "en-US")).toEqual({
    type: "date",
  });
  expect(suggestColumnType(["2026-11-24T08:30:00+08:00"], "en-US")).toEqual({
    type: "datetime",
  });
  expect(suggestColumnType(["Ana", "18"], "en-US")).toEqual({ type: "text" });
  expect(suggestColumnType(["line 1\nline 2"], "en-US")).toEqual({
    type: "long_text",
  });
  expect(suggestColumnType(["", null], "en-US")).toEqual({ type: "text" });
});

const structure: WorksheetStructure = {
  structureVersion: 1,
  nextColumnSeq: 9,
  columns: [
    {
      key: "c1",
      name: "Student",
      type: "link",
      link: { moduleId: "00000000-0000-4000-8000-000000000aa1" },
    },
    {
      key: "c2",
      name: "Student no.",
      type: "lookup",
      lookup: {
        linkKey: "c1",
        fieldId: "00000000-0000-4000-8000-000000000aa2",
      },
    },
    { key: "c3", name: "Quiz", type: "int" },
    {
      key: "c4",
      name: "Grade",
      type: "decimal",
      decimal: { places: 2, currency: false },
    },
    { key: "c5", name: "Present", type: "boolean" },
    { key: "c6", name: "Due", type: "date" },
    {
      key: "c7",
      name: "Track",
      type: "select",
      select: { options: [{ id: "o1", label: "BSIT" }] },
    },
    { key: "c8", name: "Teacher", type: "user" },
  ],
  groups: [],
  totals: {},
};
const columns = gridColumns(structure);
const byName = (name: string) => {
  const found = columns.find((column) => column.name === name);
  if (!found) throw new Error(name);
  return found;
};

test("lookups and people are never import targets; the export writes names, not ids", () => {
  expect(columns.filter(importableColumn).map((column) => column.name)).toEqual(
    ["Student", "Quiz", "Grade", "Present", "Due", "Track"],
  );
});

test("each cell sends what its column takes, as the organization's export writes it", () => {
  // Number text goes as written; the server reads it in the locale (O4).
  expect(importValue(byName("Grade"), "12,5", "de-DE")).toBe("12,5");
  expect(importValue(byName("Grade"), 12.5, "de-DE")).toBe(12.5);
  expect(importValue(byName("Quiz"), "18", "en-US")).toBe("18");
  expect(importValue(byName("Quiz"), "18.5", "en-US")).toBeUndefined();
  expect(importValue(byName("Quiz"), "eighteen", "en-US")).toBeUndefined();
  expect(importValue(byName("Present"), "true", "en-US")).toBe(true);
  expect(importValue(byName("Present"), false, "en-US")).toBe(false);
  expect(importValue(byName("Present"), "maybe", "en-US")).toBeUndefined();
  expect(importValue(byName("Due"), "2026-11-24", "en-US")).toBe("2026-11-24");
  expect(importValue(byName("Due"), "2026-11-24T00:00:00", "en-US")).toBe(
    "2026-11-24",
  );
  expect(importValue(byName("Due"), "11/24/2026", "en-US")).toBeUndefined();
  expect(importValue(byName("Track"), "bsit", "en-US")).toBe("BSIT");
  expect(importValue(byName("Track"), "BSCS", "en-US")).toBeUndefined();
  expect(importValue(byName("Quiz"), "  ", "en-US")).toBeNull();
});

test("text that starts like a formula is sent as text (X11)", () => {
  const notes = { key: "c9", name: "Notes", type: "text" as const };
  for (const text of ["=SUM(A1)", "+1", "-2", "@here"])
    expect(importValue(notes, text, "en-US")).toBe(text);
  expect(importValue(notes, 18, "en-US")).toBe("18");
  expect(importValue(notes, "x".repeat(4_001), "en-US")).toBeUndefined();
});

test("a problem line names the column and the count", () => {
  expect(cellProblemWords(byName("Quiz"), 2)).toBe(
    "2 cells in Quiz are not whole numbers. They may be added empty.",
  );
  expect(cellProblemWords(byName("Due"), 1)).toBe(
    "1 cell in Due is not dates (YYYY-MM-DD). It may be added empty.",
  );
  expect(cellProblemWords({ name: "Notes", type: "text" }, 3)).toBe(
    "3 cells in Notes are longer than 4,000 characters. They may be added empty.",
  );
});

test("keys are sent once each, in chunks of 2,000; blank and over-long keys are never sent", () => {
  expect(importKey("  Ana Cruz ")).toBe("Ana Cruz");
  expect(importKey(2025031)).toBe("2025031");
  expect(importKey("")).toBeNull();
  expect(importKey("x".repeat(201))).toBeNull();
  // 4,100 distinct keys, each twice; K7 is blank both times.
  const keys = Array.from({ length: 8_200 }, (_, index) =>
    index % 4_100 === 7 ? null : `K${index % 4_100}`,
  );
  const chunks = keyChunks(keys);
  expect(chunks.map((chunk) => chunk.length)).toEqual([2_000, 2_000, 99]);
  expect(chunks[0][0]).toBe("K0");
  expect(chunks[0]).not.toContain(null);
  expect(chunks.flat()).toHaveLength(4_099);
});

test("the counts are of rows: a repeated key counts once per row", () => {
  const found = new Map<string, KeyResult>([
    ["Ana", { state: "matched", recordId: "r1", label: "Ana Cruz" }],
    ["Ben", { state: "ambiguous" }],
    ["Cid", { state: "unmatched" }],
  ]);
  const results = rowResults(["Ana", "Ana", "Ben", null, "Cid", "Dee"], found);
  expect(results.map((result) => result.state)).toEqual([
    "matched",
    "matched",
    "ambiguous",
    "unmatched",
    "unmatched",
    "unmatched",
  ]);
  expect(matchCounts(results)).toEqual({
    matched: 2,
    unmatched: 3,
    ambiguous: 1,
  });
});

test("rows without one match are kept as unlinked text or skipped (Decision 13)", () => {
  const body = [
    { fileRow: 2, cells: ["Ana", "18", "x"] },
    { fileRow: 3, cells: ["Ben", "oops", "y"] },
    { fileRow: 4, cells: ["", "9", "z"] },
  ];
  const results: KeyResult[] = [
    { state: "matched", recordId: "r1", label: "Ana Cruz" },
    { state: "ambiguous" },
    { state: "unmatched" },
  ];
  const plan = [{ fileIndex: 1, target: byName("Quiz") }];
  const kept = importRows({
    body,
    plan,
    link: { key: "c1", fileIndex: 0, results, unmatched: "keep" },
    locale: "en-US",
  });
  expect(kept.rows).toEqual([
    { c1: { record_id: "r1" }, c3: "18" },
    // A doubted cell goes as it is; the server decides (R5).
    { c1: { unlinked: "Ben" }, c3: "oops" },
    { c1: null, c3: "9" },
  ]);
  expect([...kept.problems]).toEqual([["c3", 1]]);
  expect(kept.skipped).toBe(0);
  const skipped = importRows({
    body,
    plan,
    link: { key: "c1", fileIndex: 0, results, unmatched: "skip" },
    locale: "en-US",
  });
  expect(skipped.rows).toEqual([{ c1: { record_id: "r1" }, c3: "18" }]);
  expect(skipped.skipped).toBe(2);
});

test("rows go in batches of at most 100", () => {
  const rows = Array.from({ length: 250 }, (_, index) => ({ c1: index }));
  const batches = rowBatches(rows, 1);
  expect(batches.map((batch) => batch.length)).toEqual([100, 100, 50]);
  expect(batches[2][0]).toEqual({ c1: 200 });
  expect(rowBatches([], 1)).toEqual([]);
});

test("a batch also ends before its body passes 1,000,000 bytes (D8)", () => {
  // Each create is {"cells":{"c1":"…"}}: 10,009 bytes. The body with 99
  // rows is 991,026 bytes; with 100 it would be 1,001,036.
  const rows = Array.from({ length: 100 }, () => ({ c1: "x".repeat(9_990) }));
  expect(rowBatches(rows, 1).map((batch) => batch.length)).toEqual([99, 1]);
  // UTF-8 counts bytes, not characters: "é" is two.
  const wide = Array.from({ length: 100 }, () => ({ c1: "é".repeat(4_995) }));
  expect(rowBatches(wide, 1).map((batch) => batch.length)).toEqual([99, 1]);
});

test("a new sheet's column names are unique and at most 150 characters", () => {
  expect(uniqueNames(["Quiz", "quiz", "Quiz", " ", ""])).toEqual([
    "Quiz",
    "quiz 2",
    "Quiz 3",
    "Column",
    "Column 2",
  ]);
  expect(uniqueNames(["x".repeat(200)])[0]).toHaveLength(150);
});

test("the import takes away exactly the apostrophe the export adds (X11, X12)", () => {
  for (const [file, text] of [
    ["'=SUM(A1)", "=SUM(A1)"],
    ["'+63 917", "+63 917"],
    ["'-2", "-2"],
    ["'@here", "@here"],
    // A typed '=A1 is exported as ''=A1 and comes back as '=A1.
    ["''=A1", "'=A1"],
    ["'=A1", "=A1"],
    ["'\nline", "\nline"],
    ["'\tcode", "\tcode"],
    ["' =x", " =x"],
    ["'' =x", "' =x"],
    [" =x", " =x"],
    ["'\u3000@x", "\u3000@x"],
    ["'hello", "'hello"],
    ["''hello", "''hello"],
  ])
    expect(fromExport(file), file).toBe(text);
  // Each text the export marks comes back exactly (the backend's examples).
  for (const text of ["'=A1", " =x", "' =x", "\nline", "'hello"])
    expect(fromExport(needsMark(text) ? `'${text}` : text), text).toBe(text);
  expect(needsMark("'hello")).toBe(false);
  const notes = { key: "c9", name: "Notes", type: "text" as const };
  expect(importValue(notes, "''=A1", "en-US")).toBe("'=A1");
  expect(importValue(notes, "' =x", "en-US")).toBe(" =x");
  expect(importKey("'=Cruz")).toBe("=Cruz");
});

test("cells are checked by the server's own rules; one that fails is added empty and counted (F7-B1)", () => {
  const column = (type: string, extra: object = {}) =>
    ({ key: "c9", name: "C", type, ...extra }) as Parameters<
      typeof importValue
    >[0];
  const email = column("email");
  expect(importValue(email, "ana@example.com", "en-US")).toBe(
    "ana@example.com",
  );
  for (const bad of ["ana@example", "ana example@x.com", "@x.com"])
    expect(importValue(email, bad, "en-US"), bad).toBeUndefined();
  const url = column("url");
  expect(importValue(url, "https://example.com/a", "en-US")).toBe(
    "https://example.com/a",
  );
  for (const bad of [
    "example.com",
    "ftp://example.com",
    "https:///x",
    "https://a b",
  ])
    expect(importValue(url, bad, "en-US"), bad).toBeUndefined();
  const date = column("date");
  for (const bad of ["2026-02-30", "2026-13-01", "26-01-05"])
    expect(importValue(date, bad, "en-US"), bad).toBeUndefined();
  expect(importValue(date, "2024-02-29", "en-US")).toBe("2024-02-29");
  const datetime = column("datetime");
  expect(
    importValue(datetime, "2026-11-24T08:30:00.123456+08:00", "en-US"),
  ).toBe("2026-11-24T08:30:00.123456+08:00");
  expect(
    importValue(datetime, "2026-11-24T08:30:00.1234567Z", "en-US"),
  ).toBeUndefined();
  expect(importValue(datetime, "2026-11-31T08:30Z", "en-US")).toBeUndefined();
  const whole = column("int");
  expect(importValue(whole, 9_007_199_254_740_991, "en-US")).toBe(
    9_007_199_254_740_991,
  );
  expect(importValue(whole, 9_007_199_254_740_992, "en-US")).toBeUndefined();
  expect(importValue(whole, "9007199254740992", "en-US")).toBeUndefined();
  const number = column("number");
  expect(importValue(number, "1.23456789012345", "en-US")).toBe(
    "1.23456789012345",
  );
  expect(importValue(number, "1.234567890123456", "en-US")).toBeUndefined();
  const decimal = column("decimal", { places: 2 });
  expect(importValue(decimal, `${"9".repeat(38)}.5`, "en-US")).toBe(
    `${"9".repeat(38)}.5`,
  );
  expect(importValue(decimal, `${"9".repeat(39)}`, "en-US")).toBeUndefined();
  expect(importValue(decimal, `0.${"1".repeat(19)}`, "en-US")).toBeUndefined();
  // fr-FR groups with U+202F only; a plain or no-break space is refused.
  expect(importValue(number, "1\u202f234,5", "fr-FR")).toBe("1\u202f234,5");
  expect(importValue(number, "1 234,5", "fr-FR")).toBeUndefined();
  expect(importValue(number, "1\u00a0234,5", "fr-FR")).toBeUndefined();
});

test("dates and times without an offset are read in the organization's time zone (D1)", () => {
  const datetime = { key: "c9", name: "Due", type: "datetime" as const };
  expect(
    importValue(datetime, "2026-11-24T08:30", "en-US", "Asia/Manila"),
  ).toBe("2026-11-24T00:30:00Z");
  expect(
    importValue(datetime, "2026-11-24T08:30:15", "en-US", "Asia/Manila"),
  ).toBe("2026-11-24T00:30:15Z");
  // A date alone is midnight there.
  expect(importValue(datetime, "2026-11-24", "en-US", "Asia/Manila")).toBe(
    "2026-11-23T16:00:00Z",
  );
  expect(
    importValue(datetime, "2026-11-24T08:30Z", "en-US", "Asia/Manila"),
  ).toBe("2026-11-24T08:30Z");
});

test("a row over 32 KiB is left out and counted (D8)", () => {
  const notes = { key: "c1", name: "Notes", type: "text" as const };
  const plan = Array.from({ length: 9 }, (_, index) => ({
    fileIndex: index,
    target: { ...notes, key: `c${index + 1}` },
  }));
  const big = Array.from({ length: 9 }, () => "x".repeat(4_000));
  const built = importRows({
    body: [
      { fileRow: 2, cells: big },
      { fileRow: 3, cells: ["small"] },
    ],
    plan,
    link: null,
    locale: "en-US",
  });
  expect(built.rows).toHaveLength(1);
  expect(built.oversized).toBe(1);
});

test("a new sheet from a file gets one template column per added file column, never a person column", () => {
  const built = dataTemplate("Class 4D", [
    {
      name: "Full name",
      type: "link",
      link: { moduleName: "Students", departmentName: "Registrar" },
    },
    { name: "Prelim", type: "decimal", places: 2 },
    { name: "Teacher", type: "text" },
    { name: "prelim", type: "int" },
  ]);
  expect(built).toEqual({
    kind: "slateops-worksheet-template",
    schemaVersion: 1,
    title: "Class 4D",
    columns: [
      {
        key: "c1",
        name: "Full name",
        type: "link",
        link: { moduleName: "Students", departmentName: "Registrar" },
      },
      {
        key: "c2",
        name: "Prelim",
        type: "decimal",
        decimal: { places: 2, currency: false },
      },
      { key: "c3", name: "Teacher", type: "text" },
      { key: "c4", name: "prelim 2", type: "int" },
    ],
    groups: [],
    totals: {},
  });
  expect(built.columns.map((column) => column.type)).not.toContain("user");
});

test("the preview's estimate refuses what it cannot be sure the server takes", () => {
  const number = { key: "c9", name: "N", type: "number" as const };
  const whole = { key: "c9", name: "W", type: "int" as const };
  // A first group that starts with 0, and grouping the locale does not write.
  expect(importValue(number, "01,234", "en-US")).toBeUndefined();
  expect(importValue(number, "1,234", "en-US")).toBe("1,234");
  expect(importValue(number, "12,34,567", "en-IN")).toBe("12,34,567");
  expect(importValue(number, "1,234,567", "en-IN")).toBeUndefined();
  // An Excel number's significant digits are those it reads back with.
  expect(importValue(number, 1.234567890123456e-7, "en-US")).toBeUndefined();
  expect(importValue(number, 1.5e-7, "en-US")).toBe(1.5e-7);
  expect(importValue(number, 1e-21, "en-US")).toBe(1e-21);
  expect(importValue(whole, 1e21, "en-US")).toBeUndefined();
  // Email and web links refuse Python's whitespace, not only JavaScript's.
  const email = { key: "c9", name: "E", type: "email" as const };
  expect(importValue(email, "ana\u2028x@example.com", "en-US")).toBeUndefined();
  expect(importValue(email, "ana\u001cx@example.com", "en-US")).toBeUndefined();
  // An offset is within plus or minus 23:59.
  const due = { key: "c9", name: "D", type: "datetime" as const };
  expect(
    importValue(due, "2026-11-24T08:30+24:00", "en-US", "UTC"),
  ).toBeUndefined();
  expect(
    importValue(due, "2026-11-24T08:30+05:60", "en-US", "UTC"),
  ).toBeUndefined();
  expect(importValue(due, "2026-11-24T08:30-23:59", "en-US", "UTC")).toBe(
    "2026-11-24T08:30-23:59",
  );
});

test("a time with no offset is never read without the organization's time zone (D1)", () => {
  const due = { key: "c9", name: "D", type: "datetime" as const };
  expect(importValue(due, "2026-11-24T08:30", "en-US")).toBeUndefined();
  expect(importValue(due, "2026-11-24", "en-US")).toBeUndefined();
  expect(importValue(due, "2026-11-24T08:30Z", "en-US")).toBe(
    "2026-11-24T08:30Z",
  );
});

test("the export's mark is removed from CSV cells only, before choices, emails and links are read (X12)", () => {
  const choice = {
    key: "c9",
    name: "Track",
    type: "select" as const,
    options: { o1: "-", o2: "@Office" },
  };
  expect(importValue(choice, "'-", "en-US")).toBe("-");
  expect(importValue(choice, "'@Office", "en-US")).toBe("@Office");
  const email = { key: "c9", name: "E", type: "email" as const };
  expect(importValue(email, "'+ana@example.com", "en-US")).toBe(
    "+ana@example.com",
  );
  const notes = { key: "c9", name: "Notes", type: "text" as const };
  // An Excel cell keeps a leading apostrophe: the Excel export never adds one.
  expect(importValue(notes, "'=A1", "en-US", undefined, "xlsx")).toBe("'=A1");
  expect(importValue(notes, "'=A1", "en-US", undefined, "csv")).toBe("=A1");
  expect(importKey("'=Cruz", "xlsx")).toBe("'=Cruz");
  expect(importKey("'=Cruz", "csv")).toBe("=Cruz");
});

test("an email is read in one pass, with the server's answers on the same table (F7-S1)", () => {
  const email = { key: "c9", name: "E", type: "email" as const };
  for (const [text, valid] of [
    ["ana@example.com", true],
    ["a@b.c", true],
    ["a@.b.c", true],
    ["a@b..c", true],
    ["a@b.", false],
    ["a@.b", false],
    ["a@bc", false],
    ["@b.c", false],
    ["a@b@c.d", false],
    ["a b@c.d", false],
    ["a\u2028b@c.d", false],
    ["a\u001cb@c.d", false],
    // The probes' hostile 4,000-character shapes.
    [`a@${".".repeat(3_996)}@`, false],
    [`a@${"b".repeat(3_997)}.`, false],
    [`a@${".".repeat(3_997)}b`, true],
    [`${"a".repeat(1_998)}@${"b".repeat(1_998)}.c`, true],
  ] as const)
    expect(importValue(email, text, "en-US") !== undefined, text).toBe(valid);
});

test("blank rows do not count toward the row limit (F7 review 1)", async () => {
  const rows = `Name\n${"a\n\n,,\n".repeat(10_010)}`;
  const parsed = await parseCsv(rows);
  expect(parsed.filter((row) => row.some((cell) => cell !== ""))).toHaveLength(
    10_011,
  );
  await expect(parseCsv(`${rows}b\n`)).rejects.toThrow(OVER_LIMIT);
});

test("the delimiter is read from the first rows, a semicolon winning a tie (F7 review 2)", async () => {
  // A comma inside quotes, on the first line, does not count.
  expect(await parseCsv('"Cruz, Ana";Grade\nBen;12,5\n')).toEqual([
    ["Cruz, Ana", "Grade"],
    ["Ben", "12,5"],
  ]);
  // A tie on the first rows: the semicolon.
  expect(await parseCsv("a;b,c\n1;2,3\n")).toEqual([
    ["a", "b,c"],
    ["1", "2,3"],
  ]);
  // A quote inside an unquoted header does not start a quoted field.
  expect(await parseCsv("Height (5'11\"),Name\n180,Ana\n")).toEqual([
    ["Height (5'11\")", "Name"],
    ["180", "Ana"],
  ]);
  expect(await parseCsv("a\tb\n1\t2\n")).toEqual([
    ["a", "b"],
    ["1", "2"],
  ]);
  expect(await parseCsv("a|b\n1|2\n")).toEqual([
    ["a", "b"],
    ["1", "2"],
  ]);
});

test("the reader takes CR line ends and quotes inside unquoted text, and refuses text after a closing quote (F7 review 8)", async () => {
  expect(await parseCsv("a,b\r1,2\r")).toEqual([
    ["a", "b"],
    ["1", "2"],
  ]);
  expect(await parseCsv('a,b\nab"c,d\n')).toEqual([
    ["a", "b"],
    ['ab"c', "d"],
  ]);
  await expect(parseCsv('a\n"x"y\n')).rejects.toThrow(
    "The CSV file could not be read. Check its quotes.",
  );
});

test("a read aborted while it runs stops at its next part (F7 review 8)", async () => {
  const controller = new AbortController();
  // 3,000 long rows: past one part, within the row limit.
  const read = parseCsv(`${"a".repeat(100)}\n`.repeat(3_000), {
    signal: controller.signal,
  });
  controller.abort();
  await expect(read).rejects.toMatchObject({ name: "AbortError" });
});

test("a CSV file is read as UTF-8 without its byte order mark, and other text is refused (F7 review 8)", () => {
  const bom = new Uint8Array([0xef, 0xbb, 0xbf, 0x41, 0x2c, 0xc3, 0xa9]);
  expect(decodeCsv(bom.buffer)).toBe("A,é");
  expect(() => decodeCsv(new Uint8Array([0x41, 0xff, 0x42]).buffer)).toThrow(
    "The CSV file must use UTF-8 text. Save it as UTF-8 and try again.",
  );
});
