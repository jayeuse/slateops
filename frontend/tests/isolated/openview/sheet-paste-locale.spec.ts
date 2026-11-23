import { expect, test } from "@playwright/test";
import {
  cellConflict,
  editInput,
  gridColumns,
  inputValue,
  parsePastedGrid,
  storeRow,
  emptyRowStore,
  rowAt,
  rowQueryKey,
  storeRowPage,
} from "../../../src/components/systems/openview/domain/sheet-grid";
import { ApiError } from "../../../src/lib/api";
import type {
  WorksheetRow,
  WorksheetStructure,
} from "../../../src/components/systems/openview/adapters/worksheets-api";

// docs/specs/sheets.md O4 and X11 (SH-38), F4: what a typed or pasted value
// sends, and how a refused save reads. The server is the one number parser:
// typed and pasted numbers go as text in the organization's locale.

const structure: WorksheetStructure = {
  structureVersion: 1,
  nextColumnSeq: 5,
  columns: [
    { key: "c1", name: "Remarks", type: "text" },
    { key: "c2", name: "Quiz", type: "int" },
    {
      key: "c3",
      name: "Grade",
      type: "decimal",
      decimal: { places: 2, currency: false },
    },
    { key: "c4", name: "Present", type: "boolean" },
  ],
  groups: [],
  totals: {},
};
const [remarks, quiz, grade, present] = gridColumns(structure);

test("a pasted block splits into rows and cells, dropping the last line break", () => {
  expect(parsePastedGrid("Ana\t12,5\r\nBen\t9\n")).toEqual([
    ["Ana", "12,5"],
    ["Ben", "9"],
  ]);
  expect(parsePastedGrid("only one")).toEqual([["only one"]]);
});

test("numbers go to the server as typed, in the organization's locale", () => {
  expect(inputValue(grade, " 12,5 ")).toBe("12,5");
  expect(inputValue(quiz, "1.234")).toBe("1.234");
  expect(inputValue(quiz, "  ")).toBeNull();
});

test("text that starts like a formula stays text", () => {
  for (const text of ["=SUM(A1)", "+1", "-2", "@here"])
    expect(inputValue(remarks, text)).toBe(text);
  expect(inputValue(remarks, "")).toBeNull();
});

test("a checkbox reads yes and no words too", () => {
  expect(inputValue(present, "TRUE")).toBe(true);
  expect(inputValue(present, "no")).toBe(false);
});

test("the edit box starts from the value as the organization writes it", () => {
  expect(
    editInput(grade, { value: "12.5" }, { locale: "de-DE", timezone: "UTC" }),
  ).toBe("12,50");
  expect(
    editInput(quiz, { value: 1234 }, { locale: "en-US", timezone: "UTC" }),
  ).toBe("1234");
  expect(
    editInput(remarks, undefined, { locale: "en-US", timezone: "UTC" }),
  ).toBe("");
});

function row(id: number, quizValue: number, revision = 1): WorksheetRow {
  return {
    id: `00000000-0000-4000-8000-${String(id).padStart(12, "0")}`,
    revision,
    etag: `"r${id}:${revision}"`,
    position: id,
    cells: { c2: { value: quizValue } },
  };
}

test("a refused save reads the changed columns and the newer row", () => {
  const current = row(1, 18, 2);
  expect(
    cellConflict(
      new ApiError(412, "Someone changed these cells", {
        code: "cell_changed",
        message: "Someone changed these cells",
        keys: ["c2"],
        current,
      }),
    ),
  ).toEqual({ keys: ["c2"], current });
  expect(cellConflict(new ApiError(422, "Enter a number"))).toBeNull();
});

test("a saved row replaces its stale copy, and an older refresh cannot undo it", () => {
  const key = rowQueryKey({ sort: null, search: "" });
  const loaded = storeRowPage(
    emptyRowStore(key),
    key,
    0,
    { rows: [row(1, 10), row(2, 11)], total: 2 },
    1,
  );
  const saved = storeRow(loaded, row(2, 15, 2), 3);
  expect(rowAt(saved, 1)?.cells.c2).toEqual({ value: 15 });
  expect(
    storeRowPage(
      saved,
      key,
      0,
      { rows: [row(1, 10), row(2, 11)], total: 2 },
      2,
    ),
  ).toBe(saved);
});
