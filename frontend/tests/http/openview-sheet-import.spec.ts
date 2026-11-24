import { expect, signedInAs, test, type Page } from "./helpers/test";
import { installListApi, listIds, recordId } from "./helpers/openview-list-api";
import {
  installSheetEditApi,
  installSheetImportApi,
  installSheetPageApi,
  installSheetsApi,
  sheetPeople,
  sheetPlace,
  wireSheetDetail,
  wireSheetRow,
  wireSheetSummary,
  type WireImportFile,
} from "./helpers/openview-sheets-api";
import { profilePreferences } from "./helpers/profile-api";
import { wireWorkspace } from "../helpers/wire";
import { openedSheet } from "./helpers/settled";

// docs/specs/sheets.md X6, X8 to X12, D9.2, D9.3, Decisions 13 to 15
// (SH-33, SH-35, SH-36 UI, SH-37) and Screens 2 and 8: a new sheet from a
// template or a data file, and rows added to a sheet from a file. Parsing,
// types, keys and batches are owned by tests/isolated/openview/
// sheet-import.spec.ts and sheet-template.spec.ts.

const contacts = `/openview?section=views&module=${listIds.module}`;
const anaCruz = recordId(0);

async function newSheetDialog(
  page: Page,
  options: { personalZone?: string } = {},
) {
  await installListApi(page, { viewer: "reader" });
  // The person's own zone, after the list fake so it wins over its catch-all.
  const zone = options.personalZone;
  if (zone)
    await page.route(`**/api/users/${listIds.user}/preferences`, (route) =>
      route.fulfill({
        json: profilePreferences(listIds.user, { timezone: zone }),
      }),
    );
  // The organization's settings (the list fake answers no workspace read):
  // a file's numbers and times are read in its locale and zone (D1).
  await page.route("**/api/workspace", (route) =>
    route.request().method() === "GET"
      ? route.fulfill({
          json: wireWorkspace({
            id: "00000000-0000-4000-8000-000000000102",
            locale: "en-PH",
            timezone: "Asia/Manila",
            currency: "PHP",
            today: "2026-11-24",
            purge_enabled: false,
          }),
        })
      : route.fallback(),
  );
  const sheets = await installSheetsApi(page, { live: [] });
  await page.goto(`${contacts}&record=${anaCruz}`);
  const panel = await openedSheet(
    page.getByRole("dialog", { name: "Record details" }),
  );
  await panel.getByRole("tab").last().click();
  await panel
    .getByRole("region", { name: "On this record" })
    .getByRole("button", { name: "New sheet" })
    .click();
  return { sheets, dialog: page.getByRole("dialog", { name: "New sheet" }) };
}

const csv = [
  "Full name,Quiz,Notes",
  "Ana Cruz,18,'=SUM(A1)",
  "Ben Reyes,12,",
  "Nobody Here,9,",
  "Twin Name,7,",
].join("\r\n");

test("a new sheet from a CSV file shows the matching first, then is made with the rows that matched", async ({
  page,
}) => {
  const { sheets, dialog } = await newSheetDialog(page);
  const imports = await installSheetImportApi(page, {
    matches: {
      "Ana Cruz": { record_id: recordId(0), label: "Ana Cruz" },
      "Ben Reyes": { record_id: recordId(1), label: "Ben Reyes" },
      "Twin Name": "ambiguous",
    },
  });
  await dialog.getByRole("textbox", { name: "Name" }).fill("Class 4D");
  await expect(
    dialog.getByRole("radiogroup", { name: "Start with" }).getByRole("radio"),
  ).toHaveCount(3);
  await dialog.getByRole("radio", { name: /Data file/ }).check();
  await dialog.getByLabel("Choose a file").setInputFiles({
    name: "class-4d.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv),
  });
  await expect(dialog).toContainText("class-4d.csv");
  await dialog.getByRole("button", { name: "Check the rows" }).click();

  const preview = page.getByRole("dialog", {
    name: "New sheet Class 4D from a file",
  });
  await expect(preview).toContainText("On Ana Cruz · Contacts");
  await expect(preview).toContainText("4 rows under the header row");
  // Types are suggested from the values (Decision 14).
  await expect(preview.getByRole("combobox", { name: "Quiz" })).toHaveValue(
    "int",
  );
  await expect(preview.getByRole("combobox", { name: "Notes" })).toHaveValue(
    "text",
  );
  await preview
    .getByRole("combobox", { name: "Full name" })
    .selectOption("link");
  await preview
    .getByRole("combobox", { name: "Full name links to" })
    .selectOption({ label: "Contacts · Sales" });

  await expect(
    preview.getByRole("heading", { name: "Match the Full name column" }),
  ).toBeVisible();
  await expect(preview).toContainText(
    "Only records you can read count as matches.",
  );
  await expect(preview).toContainText("Find each row's record in Contacts by");
  await expect(
    preview.getByRole("group", { name: "Rows by result" }).getByRole("button"),
  ).toHaveText([
    "All 4",
    "Matched 2",
    "Not matched 1",
    "Matched more than once 1",
  ]);
  expect(imports.matches).toEqual([
    {
      module_id: listIds.module,
      field_id: listIds.name,
      keys: ["Ana Cruz", "Ben Reyes", "Nobody Here", "Twin Name"],
    },
  ]);
  const rows = preview.getByRole("table", { name: "Rows to add" });
  await expect(rows.getByRole("row").nth(1)).toContainText(
    "Matched · Ana Cruz",
  );
  await expect(rows.getByRole("row").nth(4)).toContainText(
    "Matched more than once · kept as text",
  );
  await expect(preview).toContainText("Nothing is added until you confirm.");
  await expect(
    preview.getByRole("button", { name: "Create Class 4D with 4 rows" }),
  ).toBeVisible();
  // Nothing is written before the person confirms (SH-35).
  expect(sheets.creates).toEqual([]);
  expect(imports.batches).toEqual([]);

  await preview
    .getByRole("radiogroup", { name: "The 2 rows without one match" })
    .getByRole("radio", { name: "Skip them" })
    .check();
  await preview
    .getByRole("button", { name: "Create Class 4D with 2 rows" })
    .click();

  await expect(
    page.getByRole("heading", { level: 1, name: "Class 4D" }),
  ).toBeVisible();
  expect(sheets.creates).toEqual([
    {
      record_id: anaCruz,
      title: "Class 4D",
      source: {
        kind: "template",
        template: {
          kind: "slateops-worksheet-template",
          schemaVersion: 1,
          title: "Class 4D",
          columns: [
            {
              key: "c1",
              name: "Full name",
              type: "link",
              link: { moduleName: "Contacts", departmentName: "Sales" },
            },
            { key: "c2", name: "Quiz", type: "int" },
            { key: "c3", name: "Notes", type: "text" },
          ],
          groups: [],
          totals: {},
        },
        module_mapping: { c1: listIds.module },
      },
    },
  ]);
  // The apostrophe the export adds goes; the text stays text (X11, X12).
  expect(imports.batches).toEqual([
    {
      sheetId: sheets.createdId,
      body: {
        structure_revision: 1,
        creates: [
          {
            cells: {
              c1: { record_id: recordId(0) },
              c2: "18",
              c3: "=SUM(A1)",
            },
          },
          { cells: { c1: { record_id: recordId(1) }, c2: "12", c3: null } },
        ],
        invalid_cells: "empty",
      },
    },
  ]);
});

const template = {
  kind: "slateops-worksheet-template",
  schemaVersion: 1,
  title: "Class sheet",
  columns: [
    {
      key: "c1",
      name: "Student",
      type: "link",
      link: { moduleName: "Contacts", departmentName: "Sales" },
    },
    {
      key: "c2",
      name: "Section",
      type: "link",
      link: { moduleName: "Section", departmentName: "Registrar" },
    },
    { key: "c3", name: "Quiz 1", type: "int" },
    {
      key: "c4",
      name: "Total",
      type: "computed",
      computed: { expression: "{c3} * 2", places: 0 },
    },
  ],
  groups: [{ name: "Prelim", keys: ["c3", "c4"] }],
  totals: { c4: "average" },
};

test("a template file maps its link columns by name; an unknown version creates nothing", async ({
  page,
}) => {
  const { sheets, dialog } = await newSheetDialog(page);
  await dialog.getByRole("textbox", { name: "Name" }).fill("Class 4E");
  await dialog.getByRole("radio", { name: /Template file/ }).check();

  const choose = dialog.getByLabel("Choose a file");
  await choose.setInputFiles({
    name: "class-sheet-template.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify({ ...template, schemaVersion: 2 })),
  });
  await expect(dialog).toContainText(
    "This template has a version that this installation cannot read. Nothing was created.",
  );
  const create = dialog.getByRole("button", { name: "Create sheet" });
  await expect(create).toHaveAttribute("aria-disabled", "true");
  expect(sheets.creates).toEqual([]);

  await choose.setInputFiles({
    name: "class-sheet-template.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(template)),
  });
  await expect(dialog).toContainText(
    "4 columns · 1 column group · 1 computed column · totals",
  );
  const links = dialog.getByRole("group", { name: "Link columns" });
  await expect(
    links.getByRole("combobox", { name: "Student links to" }),
  ).toHaveValue(listIds.module);
  await expect(links).toContainText(
    "Suggested: same module name as in the template.",
  );
  await expect(
    links.getByRole("combobox", { name: "Section links to" }),
  ).toHaveValue("");
  await expect(links).toContainText(
    "No module named Section. It becomes a text column.",
  );
  await create.click();

  await expect(
    page.getByRole("heading", { level: 1, name: "Class 4E" }),
  ).toBeVisible();
  expect(sheets.creates).toEqual([
    {
      record_id: anaCruz,
      title: "Class 4E",
      source: {
        kind: "template",
        template,
        module_mapping: { c1: listIds.module, c2: null },
      },
    },
  ]);
});

// ------------------------------------------------- rows into an open sheet

const sheetId = "00000000-0000-4000-8000-000000000ba1";
const recordOfSheet = "00000000-0000-4000-8000-000000000ba2";
const titleField = "00000000-0000-4000-8000-000000000ba3";
const studentId = (index: number) =>
  `00000000-0000-4000-8000-${String(990000 + index).padStart(12, "0")}`;

const owner = {
  id: sheetPeople.viewer.id,
  role: "member",
  access: [
    { department_id: sheetPlace.department, module_id: null, level: "write" },
  ],
} as const;

function classRoster() {
  const summary = wireSheetSummary(sheetId, "Class roster", {
    recordId: recordOfSheet,
    recordTitle: "Ana Cruz",
    moduleName: "Contacts",
    rows: 2,
  });
  return {
    detail: {
      ...wireSheetDetail(summary),
      structure: {
        structureVersion: 1,
        nextColumnSeq: 5,
        columns: [
          {
            key: "c1",
            name: "Student",
            type: "link",
            link: { moduleId: sheetPlace.module },
          },
          {
            key: "c2",
            name: "Student number",
            type: "lookup",
            lookup: { linkKey: "c1", fieldId: titleField },
          },
          { key: "c3", name: "Quiz 1", type: "int" },
          { key: "c4", name: "Teacher", type: "user" },
        ],
        groups: [],
        totals: {},
      },
    },
    rows: [
      wireSheetRow(0, { c3: { value: 10 } }),
      wireSheetRow(1, { c3: { value: 11 } }),
    ],
    totals: {},
  };
}

const roster: WireImportFile = {
  tabs: [
    { index: 0, name: "Roster" },
    { index: 1, name: "Notes" },
  ],
  tab_index: 0,
  rows: [
    ["Class roster, second term", null, null],
    ["Student", "Quiz 1", "Teacher"],
    ...Array.from({ length: 250 }, (_, index) => [
      `Student ${index + 1}`,
      index % 20,
      "Rosa Lim",
    ]),
  ],
  formula_without_value_count: 1,
  row_count: 252,
  column_count: 3,
};

async function openRoster(
  page: Page,
  options: Parameters<typeof installSheetImportApi>[1] = {},
  role: "member" | "guest" = "member",
) {
  await signedInAs(page, { ...owner, role });
  const data = classRoster();
  const api = await installSheetPageApi(page, data);
  await installSheetEditApi(page, api, {
    moduleFields: {
      [sheetPlace.module]: [{ id: titleField, name: "Name", type: "text" }],
    },
  });
  const imports = await installSheetImportApi(page, {
    sheetRows: api.rows,
    types: { c3: "int" },
    ...options,
  });
  await page.goto(`/openview?sheet=${sheetId}`);
  await expect(page.getByRole("grid", { name: "Class roster" })).toBeVisible();
  return { api, imports };
}

const xlsx = (name = "class-roster.xlsx") => ({
  name,
  mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  buffer: Buffer.from("PK\u0003\u0004 fake workbook"),
});

test("rows from an Excel tab are added after the sheet's rows in batches; a refused batch stops and says how many were added", async ({
  page,
}) => {
  const matches = Object.fromEntries(
    Array.from({ length: 250 }, (_, index) => [
      `Student ${index + 1}`,
      { record_id: studentId(index), label: `Student ${index + 1}` },
    ]),
  );
  const { api, imports } = await openRoster(page, {
    file: (tab) =>
      tab === 0 ? roster : { ...roster, tab_index: 1, rows: [["Note"]] },
    matches,
    refuseBatch: {
      at: 2,
      status: 409,
      detail: { code: "structure_changed", message: "The columns changed" },
    },
  });
  const header = page.locator("header").filter({
    has: page.getByRole("heading", { level: 1 }),
  });

  // Cancel writes nothing.
  await header.getByRole("button", { name: "Import" }).click();
  let preview = page.getByRole("dialog", {
    name: "Add rows to Class roster from a file",
  });
  await preview.getByLabel("Choose a file").setInputFiles(xlsx());
  await expect(preview).toContainText("class-roster.xlsx");
  await preview.getByRole("button", { name: "Cancel" }).click();
  await expect(preview).toBeHidden();
  expect(imports.batches).toEqual([]);

  await header.getByRole("button", { name: "Import" }).click();
  preview = page.getByRole("dialog", {
    name: "Add rows to Class roster from a file",
  });
  await preview.getByLabel("Choose a file").setInputFiles(xlsx());
  // The bytes go to the server's reader, one tab at a time.
  await expect(preview.getByRole("combobox", { name: "Tab" })).toHaveValue("0");
  expect(imports.files.at(-1)).toMatchObject({
    tab: 0,
    type: "application/octet-stream",
  });
  await preview
    .getByRole("combobox", { name: "Header row" })
    .selectOption({ label: "Row 2" });
  await expect(preview).toContainText("250 rows under the header row");
  await expect(preview).toContainText(
    "1 cell has a formula with no saved result. It is added empty.",
  );
  // Decision 15: rows are added; the preview says how many exist.
  await expect(preview).toContainText(
    "Class roster has 2 rows. These rows are added after them.",
  );
  // Columns map by name; a person column is never a target (X12).
  await expect(preview.getByRole("combobox", { name: "Student" })).toHaveValue(
    "c1",
  );
  await expect(preview.getByRole("combobox", { name: "Quiz 1" })).toHaveValue(
    "c3",
  );
  const teacher = preview.getByRole("combobox", { name: "Teacher" });
  await expect(teacher).toHaveValue("");
  await expect(teacher.getByRole("option")).not.toContainText(["Teacher"]);
  await expect(preview).toContainText(
    "Teacher is a person column. Files cannot fill it.",
  );
  // Two file columns into one sheet column wait for a choice (N2).
  await teacher.selectOption("c3");
  await expect(preview).toContainText(
    "Two file columns go into Quiz 1: Quiz 1 and Teacher. Choose one.",
  );
  await expect(
    preview.getByRole("button", { name: /^Add \d+ rows to Class roster$/ }),
  ).toHaveAttribute("aria-disabled", "true");
  await teacher.selectOption("");

  await expect(
    preview.getByRole("group", { name: "Rows by result" }).getByRole("button"),
  ).toHaveText([
    "All 250",
    "Matched 250",
    "Not matched 0",
    "Matched more than once 0",
  ]);
  // Someone changes a column's type while the rows are added.
  api.detail = {
    ...api.detail!,
    revision: 2,
    etag: `"${sheetId}:2"`,
    structure: {
      ...(api.detail!.structure as { columns: { key: string }[] }),
      columns: (
        api.detail!.structure as { columns: Record<string, unknown>[] }
      ).columns.map((column) =>
        column.key === "c3"
          ? { key: "c3", name: "Quiz 1", type: "text" }
          : column,
      ),
    },
  };
  await preview
    .getByRole("button", { name: "Add 250 rows to Class roster" })
    .click();

  await expect(preview.getByRole("alert")).toContainText(
    "100 of 250 rows were added. The columns of Class roster changed meanwhile, so the rest were not added.",
  );
  // A refused batch is never sent again from here.
  await expect(
    preview.getByRole("button", { name: /Add .* rows/ }),
  ).toHaveCount(0);
  expect(imports.batches.map((batch) => batch.body.creates.length)).toEqual([
    100, 100,
  ]);
  expect(imports.batches[0].body.structure_revision).toBe(1);
  expect(imports.batches[0].body.creates[0]).toEqual({
    cells: { c1: { record_id: studentId(0) }, c3: 0 },
  });
  const reads = api.queries.length;
  await preview.getByRole("button", { name: "Close", exact: true }).click();
  await expect.poll(() => api.queries.length).toBeGreaterThan(reads);
});

test("a file that cannot be read says why, in the browser or from the server", async ({
  page,
}) => {
  const { imports } = await openRoster(page, {
    file: () => ({
      status: 422,
      detail: {
        code: "import_file_invalid",
        reason: "archive_bounds",
        message: "The archive is too large",
      },
    }),
  });
  await page.getByRole("button", { name: "Import" }).click();
  const preview = page.getByRole("dialog", {
    name: "Add rows to Class roster from a file",
  });
  const choose = preview.getByLabel("Choose a file");
  await choose.setInputFiles(xlsx("macros.xlsm"));
  await expect(preview.getByRole("alert")).toHaveText(
    "Macro-enabled Excel files cannot be imported. Save the file as .xlsx and try again.",
  );
  expect(imports.files).toEqual([]);

  await choose.setInputFiles(xlsx());
  await expect(preview.getByRole("alert")).toHaveText(
    "This file holds more than an import may unpack. Save it again as .xlsx, or as CSV.",
  );
  await expect(
    preview.getByRole("button", { name: /Add .* rows/ }),
  ).toHaveAttribute("aria-disabled", "true");
});

test("nothing can be confirmed until the rows are matched; a failed field read offers Retry", async ({
  page,
}) => {
  const { sheets, dialog } = await newSheetDialog(page);
  const imports = await installSheetImportApi(page, {});
  let refuseFields = true;
  await page.route(
    (url) =>
      url.pathname === `/api/views/data-sources/${listIds.module}/fields`,
    (route) =>
      refuseFields
        ? route.fulfill({ status: 503, json: { detail: "Unavailable" } })
        : route.fallback(),
  );
  await dialog.getByRole("textbox", { name: "Name" }).fill("Class 4D");
  await dialog.getByRole("radio", { name: /Data file/ }).check();
  await dialog.getByLabel("Choose a file").setInputFiles({
    name: "class-4d.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(csv),
  });
  await dialog.getByRole("button", { name: "Check the rows" }).click();
  const preview = page.getByRole("dialog", {
    name: "New sheet Class 4D from a file",
  });
  await preview
    .getByRole("combobox", { name: "Full name" })
    .selectOption("link");
  await preview
    .getByRole("combobox", { name: "Full name links to" })
    .selectOption({ label: "Contacts · Sales" });

  const failure = preview
    .getByRole("alert")
    .filter({ hasText: "The fields of Contacts could not be read." });
  await expect(failure).toBeVisible();
  const confirm = preview.getByRole("button", { name: /^Create Class 4D/ });
  await expect(confirm).toHaveAttribute("aria-disabled", "true");
  expect(imports.matches).toEqual([]);
  expect(sheets.creates).toEqual([]);

  refuseFields = false;
  await failure.getByRole("button", { name: "Retry" }).click();
  await expect(
    preview.getByRole("group", { name: "Rows by result" }).getByRole("button"),
  ).toHaveText([
    "All 4",
    "Matched 0",
    "Not matched 4",
    "Matched more than once 0",
  ]);
  await expect(confirm).not.toHaveAttribute("aria-disabled", "true");
});

test("a column list saved meanwhile with the same columns does not stop the import", async ({
  page,
}) => {
  const matches = Object.fromEntries(
    Array.from({ length: 250 }, (_, index) => [
      `Student ${index + 1}`,
      { record_id: studentId(index), label: `Student ${index + 1}` },
    ]),
  );
  const { api, imports } = await openRoster(page, {
    file: () => roster,
    matches,
    refuseBatch: {
      at: 2,
      status: 409,
      detail: { code: "structure_changed", message: "The columns changed" },
    },
  });
  await page.getByRole("button", { name: "Import" }).click();
  const preview = page.getByRole("dialog", {
    name: "Add rows to Class roster from a file",
  });
  await preview.getByLabel("Choose a file").setInputFiles(xlsx());
  await preview
    .getByRole("combobox", { name: "Header row" })
    .selectOption({ label: "Row 2" });
  await expect(
    preview.getByRole("group", { name: "Rows by result" }).getByRole("button"),
  ).toHaveText([
    "All 250",
    "Matched 250",
    "Not matched 0",
    "Matched more than once 0",
  ]);
  // A group was renamed: a new version, the same column keys and types.
  // The refused batch goes again at the new version; nothing is lost.
  api.detail = { ...api.detail!, revision: 2, etag: `"${sheetId}:2"` };
  await preview
    .getByRole("button", { name: "Add 250 rows to Class roster" })
    .click();
  await expect(preview).toBeHidden();
  expect(
    imports.batches.map((batch) => [
      batch.body.structure_revision,
      batch.body.creates.length,
    ]),
  ).toEqual([
    [1, 100],
    [1, 100],
    [2, 100],
    [2, 50],
  ]);
});

test("a lost answer to the create says the sheet may exist and offers no retry", async ({
  page,
}) => {
  const { sheets, dialog } = await newSheetDialog(page);
  await installSheetImportApi(page, {});
  await page.route(
    (url) => url.pathname === "/api/worksheets",
    (route) =>
      route.request().method() === "POST" ? route.abort() : route.fallback(),
  );
  await dialog.getByRole("textbox", { name: "Name" }).fill("Class 4D");
  await dialog.getByRole("radio", { name: /Data file/ }).check();
  await dialog.getByLabel("Choose a file").setInputFiles({
    name: "class-4d.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("Quiz\r\n18\r\n"),
  });
  await dialog.getByRole("button", { name: "Check the rows" }).click();
  const preview = page.getByRole("dialog", {
    name: "New sheet Class 4D from a file",
  });
  await preview
    .getByRole("button", { name: "Create Class 4D with 1 row" })
    .click();
  await expect(preview.getByRole("alert")).toHaveText(
    "The sheet may have been created. Check My sheets before you try again.",
  );
  await expect(
    preview.getByRole("button", { name: /^Create Class 4D/ }),
  ).toHaveCount(0);
  expect(sheets.creates).toEqual([]);
});

test("times with no offset are read in the organization's time zone, not the person's own (D1)", async ({
  page,
}) => {
  // The organization is in Asia/Manila; this person views in New York.
  const { sheets, dialog } = await newSheetDialog(page, {
    personalZone: "America/New_York",
  });
  const imports = await installSheetImportApi(page, {});
  await dialog.getByRole("textbox", { name: "Name" }).fill("Visits");
  await dialog.getByRole("radio", { name: /Data file/ }).check();
  await dialog.getByLabel("Choose a file").setInputFiles({
    name: "visits.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("Visitor,Due\r\nAna Cruz,2026-11-24T08:30\r\n"),
  });
  await dialog.getByRole("button", { name: "Check the rows" }).click();
  const preview = page.getByRole("dialog", {
    name: "New sheet Visits from a file",
  });
  await expect(preview.getByRole("combobox", { name: "Due" })).toHaveValue(
    "datetime",
  );
  await preview
    .getByRole("button", { name: "Create Visits with 1 row" })
    .click();
  await expect(
    page.getByRole("heading", { level: 1, name: "Visits" }),
  ).toBeVisible();
  expect(sheets.creates).toHaveLength(1);
  expect(imports.batches[0].body.creates).toEqual([
    { cells: { c1: "Ana Cruz", c2: "2026-11-24T00:30:00Z" } },
  ]);
});

test("the server decides doubtful cells, and the result says how many it added empty", async ({
  page,
}) => {
  const { imports } = await openRoster(page, {
    matches: {
      "Student 1": { record_id: studentId(0), label: "Student 1" },
      "Student 2": { record_id: studentId(1), label: "Student 2" },
    },
  });
  await page.getByRole("button", { name: "Import" }).click();
  const preview = page.getByRole("dialog", {
    name: "Add rows to Class roster from a file",
  });
  await preview.getByLabel("Choose a file").setInputFiles({
    name: "quiz.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("Student,Quiz 1\r\nStudent 1,18\r\nStudent 2,oops\r\n"),
  });
  // The preview's estimate.
  await expect(preview).toContainText(
    "1 cell in Quiz 1 is not whole numbers. It may be added empty.",
  );
  await preview
    .getByRole("button", { name: "Add 2 rows to Class roster" })
    .click();
  // The server's count.
  await expect(
    preview.getByRole("status").filter({ hasText: "rows were added" }),
  ).toHaveText(
    "2 rows were added. 1 cell did not fit its column and was added empty.",
  );
  expect(imports.batches[0].body).toEqual({
    structure_revision: 1,
    creates: [
      { cells: { c1: { record_id: studentId(0) }, c3: "18" } },
      // The doubted cell goes as the file has it; the server decides.
      { cells: { c1: { record_id: studentId(1) }, c3: "oops" } },
    ],
    invalid_cells: "empty",
  });
});

test("a guest never imports, even into a sheet they still own (F7-S4)", async ({
  page,
}) => {
  await openRoster(page, {}, "guest");
  const header = page.locator("header").filter({
    has: page.getByRole("heading", { level: 1 }),
  });
  await expect(header.getByRole("button", { name: "Export" })).toBeVisible();
  await expect(header.getByRole("button", { name: "Import" })).toHaveCount(0);
});

test("the result counts the date and time cells the import left empty, with the server's count (F7 review 3)", async ({
  page,
}) => {
  const { sheets, dialog } = await newSheetDialog(page);
  await installSheetImportApi(page, {});
  await dialog.getByRole("textbox", { name: "Name" }).fill("Visits");
  await dialog.getByRole("radio", { name: /Data file/ }).check();
  await dialog.getByLabel("Choose a file").setInputFiles({
    name: "visits.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "Visitor,Due\r\nAna Cruz,2026-11-24T08:30\r\nBen Reyes,2026-11-24T08:30\r\nCid Tan,2026-02-30T08:00\r\n",
    ),
  });
  await dialog.getByRole("button", { name: "Check the rows" }).click();
  const preview = page.getByRole("dialog", {
    name: "New sheet Visits from a file",
  });
  // One cell is not a real date, so the person chooses the type.
  await preview.getByRole("combobox", { name: "Due" }).selectOption("datetime");
  await preview
    .getByRole("button", { name: "Create Visits with 3 rows" })
    .click();
  await expect(
    preview.getByRole("status").filter({ hasText: "rows were added" }),
  ).toHaveText(
    "3 rows were added. 1 cell did not fit its column and was added empty.",
  );
  expect(sheets.creates).toHaveLength(1);
});
