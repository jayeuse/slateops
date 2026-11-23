import {
  createWorksheet,
  getWorksheet,
  listModuleWorksheets,
  listMyWorksheets,
  listRecordWorksheets,
  queryWorksheetRows,
  restoreWorksheet,
} from "../../../src/components/systems/openview/adapters/worksheets-api";
import { describeContracts } from "./openapi-contract";

const worksheetId = "00000000-0000-4000-8000-0000000005a1";
const recordId = "00000000-0000-4000-8000-0000000005a2";
const moduleId = "00000000-0000-4000-8000-0000000005a3";

// My sheets (1), a record's sheets (2), a module's sheets (2a), create (3),
// one sheet (4), Restore (8) and a page of rows (9), spec D10.
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
    name: "restoreWorksheet",
    run: () => restoreWorksheet(worksheetId),
  },
]);
