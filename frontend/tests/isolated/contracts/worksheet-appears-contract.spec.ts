import { listRecordAppearances } from "../../../src/components/systems/openview/adapters/worksheet-appears-api";
import { describeContracts } from "./openapi-contract";

// Appears in (route 23, docs/specs/sheets.md N5, D10).
describeContracts("OpenView sheet appearances", [
  {
    name: "listRecordAppearances",
    run: () =>
      listRecordAppearances("00000000-0000-4000-8000-0000000005a2", 25),
  },
]);
