import { expect, test } from "@playwright/test";

import {
  mappingLine,
  readTemplate,
  suggestModule,
} from "../../../src/components/systems/openview/domain/sheet-template";

// docs/specs/sheets.md X5, X6, D9.2 (SH-33): a template file in New sheet,
// its summary, and the module suggested for each link column by name.

const template = {
  kind: "slateops-worksheet-template",
  schemaVersion: 1,
  title: "Class sheet",
  columns: [
    {
      key: "c1",
      name: "Student",
      type: "link",
      link: { moduleName: "Student List", departmentName: "Registrar" },
    },
    {
      key: "c2",
      name: "Student no.",
      type: "lookup",
      lookup: { linkKey: "c1", fieldName: "Student number" },
    },
    {
      key: "c3",
      name: "Quiz 1",
      type: "decimal",
      decimal: { places: 2, currency: false },
    },
    {
      key: "c4",
      name: "Section",
      type: "link",
      link: { moduleName: "Section", departmentName: "Registrar" },
    },
    {
      key: "c5",
      name: "Total",
      type: "computed",
      computed: { expression: "{c3} + 1", places: 2 },
    },
  ],
  groups: [{ name: "Period 1", keys: ["c3", "c5"] }],
  totals: { c5: "average" },
};

test("a template reads as its summary and its link columns", () => {
  const read = readTemplate(JSON.stringify(template));
  if (!read.ok) throw new Error(read.problem);
  expect(read.summary).toBe(
    "5 columns · 1 column group · 1 computed column · totals",
  );
  expect(read.title).toBe("Class sheet");
  expect(read.links).toEqual([
    {
      key: "c1",
      name: "Student",
      moduleName: "Student List",
      departmentName: "Registrar",
    },
    {
      key: "c4",
      name: "Section",
      moduleName: "Section",
      departmentName: "Registrar",
    },
  ]);
  const bare = readTemplate(
    JSON.stringify({
      ...template,
      columns: [template.columns[2]],
      groups: [],
      totals: {},
    }),
  );
  expect(bare.ok && bare.summary).toBe("1 column");
});

test("an unknown version, a From another sheet column, or another file is refused before any request", () => {
  expect(
    readTemplate(JSON.stringify({ ...template, schemaVersion: 2 })),
  ).toEqual({
    ok: false,
    problem:
      "This template has a version that this installation cannot read. Nothing was created.",
  });
  expect(
    readTemplate(
      JSON.stringify({
        ...template,
        columns: [
          ...template.columns,
          { key: "c9", name: "Elsewhere", type: "sheet_lookup" },
        ],
      }),
    ),
  ).toEqual({
    ok: false,
    problem:
      "This template has a From another sheet column, which a template cannot carry. Nothing was created.",
  });
  const invalid =
    "This file is not a sheet template. Choose a .json file that Download template made.";
  for (const text of [
    "{",
    "[]",
    JSON.stringify({ kind: "other", schemaVersion: 1 }),
  ])
    expect(readTemplate(text)).toEqual({ ok: false, problem: invalid });
});

const modules = [
  { id: "m1", name: "Student List", departmentName: "Admissions" },
  { id: "m2", name: "student list", departmentName: "Registrar" },
  { id: "m3", name: "Faculty Members", departmentName: "Registrar" },
];

test("a link column is suggested a readable module of the same name, the same department first", () => {
  expect(
    suggestModule(
      { moduleName: "Student List", departmentName: "Registrar" },
      modules,
    ),
  ).toBe("m2");
  expect(
    suggestModule(
      { moduleName: "Student List", departmentName: "Finance" },
      modules,
    ),
  ).toBe("m1");
  expect(
    suggestModule(
      { moduleName: "Section", departmentName: "Registrar" },
      modules,
    ),
  ).toBeNull();
});

test("the line under a mapping says why", () => {
  expect(mappingLine({ moduleName: "Section" }, null, null)).toBe(
    "No module named Section. It becomes a text column.",
  );
  expect(mappingLine({ moduleName: "Student List" }, "m2", "m2")).toBe(
    "Suggested: same module name as in the template.",
  );
  expect(mappingLine({ moduleName: "Student List" }, null, "m2")).toBe(
    "It becomes a text column.",
  );
  expect(mappingLine({ moduleName: "Student List" }, "m1", "m2")).toBe("");
});

test("a template with more than 100 columns or a key a sheet cannot hold is refused (F7-S2)", () => {
  const invalid =
    "This file is not a sheet template. Choose a .json file that Download template made.";
  const columns = Array.from({ length: 101 }, (_, index) => ({
    key: `c${index + 1}`,
    name: `Q${index + 1}`,
    type: "int",
  }));
  expect(readTemplate(JSON.stringify({ ...template, columns }))).toEqual({
    ok: false,
    problem: invalid,
  });
  for (const key of ["__proto__", "constructor", "C1", "c1234567890"])
    expect(
      readTemplate(
        JSON.stringify({
          ...template,
          columns: [{ ...template.columns[0], key }],
        }),
      ),
      key,
    ).toEqual({ ok: false, problem: invalid });
  expect(
    readTemplate(
      JSON.stringify({ ...template, columns: columns.slice(0, 100) }),
    ).ok,
  ).toBe(true);
});
