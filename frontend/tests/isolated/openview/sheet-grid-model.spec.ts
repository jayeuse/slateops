import { expect, test } from "@playwright/test";
import {
  cellView,
  emptyRowStore,
  gridBands,
  gridColumns,
  pagesForRange,
  rowAt,
  rowQueryKey,
  sortLabel,
  storeRowPage,
  totalView,
} from "../../../src/components/systems/openview/domain/sheet-grid";
import type {
  WorksheetRow,
  WorksheetStructure,
} from "../../../src/components/systems/openview/adapters/worksheets-api";

// The read-only sheet grid (docs/specs/sheets.md P3, F7, N4, N6 to N8 and
// Screens 3): columns, bands, cell words, totals, sort words and the pages
// of 200 rows that the grid loads as it scrolls.

const moduleId = "00000000-0000-4000-8000-000000000aa1";
const fieldId = "00000000-0000-4000-8000-000000000aa2";
const recordId = "00000000-0000-4000-8000-000000000aa3";

const structure: WorksheetStructure = {
  structureVersion: 1,
  nextColumnSeq: 9,
  columns: [
    { key: "c1", name: "Student", type: "link", link: { moduleId } },
    {
      key: "c2",
      name: "Student number",
      type: "lookup",
      lookup: { linkKey: "c1", fieldId },
    },
    { key: "c3", name: "Quiz 1", type: "int" },
    {
      key: "c4",
      name: "Prelim exam",
      type: "decimal",
      decimal: { places: 2, currency: false },
    },
    {
      key: "c5",
      name: "Final grade",
      type: "computed",
      computed: { expression: "{Quiz 1} * 2", places: 2 },
    },
    {
      key: "c6",
      name: "Remarks",
      type: "select",
      select: {
        options: [
          { id: "o1", label: "Passed" },
          { id: "o2", label: "Failed" },
        ],
      },
    },
    { key: "c7", name: "Present", type: "boolean" },
    {
      key: "c8",
      name: "From roster",
      type: "sheet_lookup",
      state: "no_access",
    },
  ],
  groups: [{ name: "Prelim", keys: ["c3", "c4"] }],
  totals: { c1: "count", c4: "average" },
};
const column = (key: string) => {
  const found = gridColumns(structure).find((item) => item.key === key);
  if (!found) throw new Error(`no column ${key}`);
  return found;
};
const format = { locale: "en-US", timezone: "UTC" };

test("columns keep their order and mark the ones nobody edits", () => {
  expect(
    gridColumns(structure).map(({ key, readOnly, numeric }) => [
      key,
      readOnly,
      numeric,
    ]),
  ).toEqual([
    ["c1", false, false],
    ["c2", true, false],
    ["c3", false, true],
    ["c4", false, true],
    ["c5", true, true],
    ["c6", false, false],
    ["c7", false, false],
    ["c8", true, false],
  ]);
  expect(column("c1").linkModuleId).toBe(moduleId);
});

test("column groups become bands over their columns, in order", () => {
  expect(gridBands(gridColumns(structure))).toEqual([
    { label: null, span: 2 },
    { label: "Prelim", span: 2 },
    { label: null, span: 4 },
  ]);
});

test("a cell reads as the viewer may see it", () => {
  expect(
    cellView(
      column("c1"),
      { link: { record_id: recordId, label: "Ana Cruz" } },
      format,
    ),
  ).toEqual({ kind: "link", label: "Ana Cruz", recordId });
  expect(cellView(column("c1"), { unlinked: "A. Cruz" }, format)).toEqual({
    kind: "unlinked",
    text: "A. Cruz",
  });
  for (const [state, words] of [
    ["no_access", "No access"],
    ["deleted", "Deleted record"],
    ["removed", "Removed record"],
    ["unavailable", "Unavailable"],
    ["field_removed", "Field removed"],
    ["column_removed", "Column removed"],
    ["multiple_matches", "Several matches"],
  ] as const)
    expect(cellView(column("c2"), { state }, format)).toEqual({
      kind: "state",
      state,
      words,
    });
  expect(
    cellView(column("c3"), { value: null, error: "division_by_zero" }, format),
  ).toEqual({ kind: "error", words: "Division by zero" });
  expect(
    cellView(column("c3"), { value: null, error: "overflow" }, format),
  ).toEqual({ kind: "error", words: "Number too large" });
  expect(
    cellView(column("c3"), { value: null, error: "unknown_code" }, format),
  ).toEqual({ kind: "error", words: "Cannot be calculated" });
  expect(
    cellView(column("c2"), { state: "multiple_matches", count: 3 }, format),
  ).toEqual({ kind: "state", state: "multiple_matches", words: "3 matches" });
  // 101 stands for more than 100 matching rows.
  expect(
    cellView(column("c2"), { state: "multiple_matches", count: 101 }, format),
  ).toEqual({
    kind: "state",
    state: "multiple_matches",
    words: "100+ matches",
  });
  expect(cellView(column("c3"), { value: 1234 }, format)).toEqual({
    kind: "value",
    text: "1,234",
  });
  expect(cellView(column("c4"), { value: "85.5" }, format)).toEqual({
    kind: "value",
    text: "85.50",
  });
  expect(cellView(column("c6"), { value: "o2" }, format)).toEqual({
    kind: "value",
    text: "Failed",
  });
  expect(cellView(column("c7"), { value: true }, format)).toEqual({
    kind: "value",
    text: "Yes",
  });
  expect(cellView(column("c3"), { value: null }, format)).toEqual({
    kind: "blank",
  });
  expect(cellView(column("c3"), undefined, format)).toEqual({ kind: "blank" });
});

test("totals carry their label; during a search the first names all rows", () => {
  expect(
    totalView(
      column("c1"),
      { fn: "count", value: 15, hidden_count: 0 },
      { first: true, searching: false, allRows: 15 },
      format,
    ),
  ).toEqual({ label: "Count", text: "15" });
  expect(
    totalView(
      column("c1"),
      { fn: "count", value: 15, hidden_count: 0 },
      { first: true, searching: true, allRows: 15 },
      format,
    ),
  ).toEqual({ label: "Count · all 15 rows", text: "15" });
  expect(
    totalView(
      column("c4"),
      { fn: "average", value: "78.333333", hidden_count: 0 },
      { first: false, searching: true, allRows: 15 },
      format,
    ),
  ).toEqual({ label: "Average", text: "78.33" });
  expect(
    totalView(
      column("c4"),
      { fn: "max", value: null, hidden_count: 0 },
      { first: false, searching: false, allRows: 0 },
      format,
    ),
  ).toEqual({ label: "Max", text: "" });
  // Cells the viewer cannot read are skipped and counted (K6, SH-58).
  expect(
    totalView(
      column("c4"),
      { fn: "average", value: "80", hidden_count: 1 },
      { first: false, searching: false, allRows: 15 },
      format,
    ),
  ).toEqual({ label: "Average · 1 hidden", text: "80.00" });
  expect(
    totalView(
      column("c1"),
      { fn: "count", value: 12, hidden_count: 3 },
      { first: true, searching: true, allRows: 15 },
      format,
    ),
  ).toEqual({ label: "Count · all 15 rows · 3 hidden", text: "12" });
});

test("a sort reads as the column and its direction", () => {
  expect(sortLabel(column("c5"), "desc")).toBe("Final grade, high to low");
  expect(sortLabel(column("c3"), "asc")).toBe("Quiz 1, low to high");
  expect(sortLabel(column("c1"), "asc")).toBe("Student, A to Z");
  expect(sortLabel(column("c6"), "desc")).toBe("Remarks, Z to A");
  expect(
    sortLabel({ ...column("c6"), type: "boolean", numeric: false }, "asc"),
  ).toBe("Remarks, No first");
  expect(
    sortLabel({ ...column("c6"), type: "boolean", numeric: false }, "desc"),
  ).toBe("Remarks, Yes first");
});

test("the grid asks only for the pages of 200 rows that it shows", () => {
  expect(pagesForRange(0, 30, 450)).toEqual([0]);
  expect(pagesForRange(190, 230, 450)).toEqual([0, 200]);
  expect(pagesForRange(430, 460, 450)).toEqual([400]);
  expect(pagesForRange(0, 10, 0)).toEqual([]);
});

function row(id: number): WorksheetRow {
  return {
    id: `00000000-0000-4000-8000-${String(id).padStart(12, "0")}`,
    revision: 1,
    etag: `"r${id}:1"`,
    position: id,
    cells: {},
  };
}

test("a page lands only in the store of the search and sort that asked for it", () => {
  const sorted = rowQueryKey({
    sort: { key: "c3", order: "desc" },
    search: "",
  });
  const searched = rowQueryKey({ sort: null, search: "an" });
  expect(sorted).not.toBe(searched);

  const store = storeRowPage(emptyRowStore(sorted), sorted, 200, {
    rows: [row(201), row(202)],
    total: 450,
  });
  expect(rowAt(store, 201)?.id).toBe(row(202).id);
  expect(store.total).toBe(450);
  // An answer for the earlier search arrives late: it changes nothing.
  expect(storeRowPage(store, searched, 0, { rows: [row(1)], total: 9 })).toBe(
    store,
  );
  expect(rowAt(store, 0)).toBeUndefined();
});

test("an older answer for the same page never replaces a newer one", () => {
  const key = rowQueryKey({ sort: null, search: "" });
  const newer = storeRowPage(
    emptyRowStore(key),
    key,
    0,
    { rows: [row(2)], total: 1 },
    2,
  );
  // A refresh that started earlier answers last: it changes nothing.
  const late = storeRowPage(newer, key, 0, { rows: [row(1)], total: 1 }, 1);
  expect(late).toBe(newer);
  expect(rowAt(late, 0)?.id).toBe(row(2).id);
});

test("an older answer for another page leaves the newer row count and totals", () => {
  const key = rowQueryKey({ sort: null, search: "" });
  const newer = storeRowPage(
    emptyRowStore(key),
    key,
    0,
    {
      rows: [row(1)],
      total: 450,
      totals: { c3: { fn: "average", value: "12.5", hidden_count: 0 } },
    },
    5,
  );
  const late = storeRowPage(
    newer,
    key,
    200,
    {
      rows: [row(201)],
      total: 300,
      totals: { c3: { fn: "average", value: "1.5", hidden_count: 0 } },
    },
    3,
  );
  expect(late.total).toBe(450);
  expect(late.totals).toEqual({
    c3: { fn: "average", value: "12.5", hidden_count: 0 },
  });
  // Its page itself is still the only copy of rows 200 on.
  expect(rowAt(late, 200)?.id).toBe(row(201).id);
});

test("a Number column with the currency option shows the organization's currency, in its locale", () => {
  const [fee, plain] = gridColumns({
    structureVersion: 1,
    nextColumnSeq: 3,
    columns: [
      {
        key: "c1",
        name: "Fee",
        type: "decimal",
        decimal: { places: 2, currency: true },
      },
      {
        key: "c2",
        name: "Weight",
        type: "decimal",
        decimal: { places: 2, currency: false },
      },
    ],
    groups: [],
    totals: {},
  } as unknown as WorksheetStructure);
  const ph = { locale: "en-PH", timezone: "Asia/Manila", currency: "PHP" };
  const de = { locale: "de-DE", timezone: "Europe/Berlin", currency: "EUR" };
  // SH-20, K2, O3: the symbol and the places in the organization's locale.
  expect(cellView(fee, { value: 7 }, ph)).toEqual({
    kind: "value",
    text: "₱7.00",
  });
  expect(cellView(fee, { value: "1234.5" }, de)).toEqual({
    kind: "value",
    text: "1.234,50 €",
  });
  // Without the option, or before the organization's currency is known,
  // the number stays plain.
  expect(cellView(plain, { value: 7 }, ph)).toEqual({
    kind: "value",
    text: "7.00",
  });
  expect(
    cellView(fee, { value: 7 }, { locale: "en-PH", timezone: "UTC" }),
  ).toEqual({
    kind: "value",
    text: "7.00",
  });
  // Sum, average, min and max carry the currency; a count does not.
  const place = { first: false, searching: false, allRows: 3 };
  expect(
    totalView(fee, { fn: "sum", value: "21", hidden_count: 0 }, place, ph).text,
  ).toBe("₱21.00");
  expect(
    totalView(fee, { fn: "count", value: 3, hidden_count: 0 }, place, ph).text,
  ).toBe("3");
});
