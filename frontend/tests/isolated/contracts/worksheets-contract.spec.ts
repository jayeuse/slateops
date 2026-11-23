import {
  createWorksheet,
  getWorksheet,
  listModuleWorksheets,
  listMyWorksheets,
  listRecordWorksheets,
  createWorksheetRow,
  deleteWorksheetRow,
  queryWorksheetRows,
  restoreWorksheet,
  saveWorksheetStructure,
  updateWorksheetCells,
  renameWorksheet,
  deleteWorksheet,
  listWorksheetHistory,
  listWorksheetShares,
  shareWorksheet,
  changeWorksheetShare,
  removeWorksheetShare,
  searchWorksheetShareCandidates,
  searchWorksheetPeople,
  exportWorksheet,
} from "../../../src/components/systems/openview/adapters/worksheets-api";
import { describeContracts } from "./openapi-contract";

const worksheetId = "00000000-0000-4000-8000-0000000005a1";
const recordId = "00000000-0000-4000-8000-0000000005a2";
const moduleId = "00000000-0000-4000-8000-0000000005a3";
const rowId = "00000000-0000-4000-8000-0000000005a4";
const shareId = "00000000-0000-4000-8000-0000000005a5";
const personId = "00000000-0000-4000-8000-0000000005a6";

// My sheets (1), a record's sheets (2), a module's sheets (2a), create (3),
// one sheet (4), Restore (8), a page of rows (9), and the sheet actions:
// rename (5), delete (7), history (15), shares (16 to 19), export (20),
// share candidates (25) and the people list, spec D10.
describeContracts("OpenView sheets", [
  {
    name: "listMyWorksheets",
    run: () => listMyWorksheets({ deleted: "exclude" }),
  },
  {
    name: "listMyWorksheets deleted",
    run: () => listMyWorksheets({ deleted: "only" }),
  },
  {
    name: "listRecordWorksheets",
    run: () => listRecordWorksheets(recordId),
  },
  {
    name: "listModuleWorksheets",
    run: () => listModuleWorksheets(moduleId),
  },
  {
    name: "createWorksheet on a record",
    run: () => createWorksheet({ recordId, title: "Class 4D" }),
  },
  {
    name: "createWorksheet on a module",
    run: () => createWorksheet({ moduleId, title: "Visit plan" }),
  },
  {
    name: "getWorksheet",
    run: () => getWorksheet(worksheetId),
  },
  {
    name: "queryWorksheetRows",
    run: () =>
      queryWorksheetRows(worksheetId, {
        sort: { key: "c1", order: "asc" },
        search: "an",
        offset: 0,
      }),
  },
  {
    name: "updateWorksheetCells",
    run: () =>
      updateWorksheetCells(worksheetId, rowId, {
        c1: { value: "18", expected: { value: 10 } },
      }),
  },
  {
    name: "createWorksheetRow",
    run: () => createWorksheetRow(worksheetId),
  },
  {
    name: "deleteWorksheetRow",
    run: () => deleteWorksheetRow(worksheetId, { id: rowId, etag: '"r:1"' }),
  },
  {
    name: "saveWorksheetStructure",
    run: () =>
      saveWorksheetStructure(worksheetId, '"s:1"', {
        columns: [{ key: "c1", name: "Quiz", type: "int" }],
        groups: [],
        totals: { c1: "average" },
      }),
  },
  {
    name: "restoreWorksheet",
    run: () => restoreWorksheet(worksheetId),
  },
  {
    name: "renameWorksheet",
    run: () => renameWorksheet(worksheetId, '"s:1"', "Class 1B"),
  },
  {
    name: "deleteWorksheet",
    run: () => deleteWorksheet(worksheetId, '"s:1"'),
  },
  {
    name: "listWorksheetHistory",
    run: () => listWorksheetHistory(worksheetId, { offset: 0 }),
  },
  {
    name: "listWorksheetShares",
    run: () => listWorksheetShares(worksheetId),
  },
  {
    name: "shareWorksheet with a person",
    run: () =>
      shareWorksheet(worksheetId, { subject: "user", id: personId }, "edit"),
  },
  {
    name: "shareWorksheet with a group",
    run: () =>
      shareWorksheet(worksheetId, { subject: "group", id: personId }, "view"),
  },
  {
    name: "changeWorksheetShare",
    run: () => changeWorksheetShare(worksheetId, shareId, "view"),
  },
  {
    name: "removeWorksheetShare",
    run: () => removeWorksheetShare(worksheetId, shareId),
  },
  {
    name: "searchWorksheetShareCandidates",
    run: () => searchWorksheetShareCandidates(worksheetId, "ber"),
  },
  {
    name: "searchWorksheetPeople",
    run: () => searchWorksheetPeople(worksheetId, "ber"),
  },
  {
    name: "exportWorksheet",
    run: () => exportWorksheet(worksheetId, "xlsx"),
    requestOnly: "The response is the file bytes, not JSON",
  },
]);
