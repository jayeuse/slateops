import {
  getWorksheet,
  listMyWorksheets,
  restoreWorksheet,
} from "../../../src/components/systems/openview/adapters/worksheets-api";
import { describeContracts } from "./openapi-contract";

const worksheetId = "00000000-0000-4000-8000-0000000005a1";

// My sheets (route 1), one sheet (route 4) and Restore (route 8), spec D10.
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
    name: "getWorksheet",
    run: () => getWorksheet(worksheetId),
  },
  {
    name: "restoreWorksheet",
    run: () => restoreWorksheet(worksheetId),
  },
]);
