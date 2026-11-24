import { expect, test } from "@playwright/test";

import { cappedListWords } from "../../../src/components/systems/openview/components/sheet-display";

// docs/specs/sheets.md P4 and the parent's decision on a list past one
// read's bound: My sheets shows the newest 5,000 and says so. The bound
// itself is owned by worksheets-api.spec.ts.

test("a list longer than one read says how many of how many it shows", () => {
  expect(cappedListWords(5_000, 5_100)).toBe("Showing 5,000 of 5,100 sheets.");
  expect(cappedListWords(12, 12)).toBeNull();
});
