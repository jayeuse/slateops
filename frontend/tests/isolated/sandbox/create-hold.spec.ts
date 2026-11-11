import { expect, test } from "@playwright/test";

import { refusedSaveClosesCreate } from "../../../src/components/systems/sandbox/helpers/create-hold";

// N1 rules 3 and 6 (docs/specs/sandbox-ux-redesign.md): a refused save
// closes an open entry or Connect; any other hold keeps them open, with
// their controls disabled and the reason.

const HOLD = "Wait for the current Sandbox action to finish.";

// N1 rule 3 (B5c)
test("a refused save closes the entry, and every other hold keeps it open", () => {
  const rows: Array<[string, boolean, boolean, boolean, boolean]> = [
    // name, saving before, hold after, saving after, closes
    ["a queued save is refused (409 or failure)", true, true, false, true],
    ["an edit's own save is refused", true, true, false, true],
    ["a queued save confirms", true, false, false, false],
    ["an edit's own save starts", false, true, true, false],
    ["a publish or a lifecycle action starts", false, true, false, false],
    ["nothing changes while saving", true, false, true, false],
  ];
  for (const [name, savingBefore, held, savingAfter, closes] of rows)
    expect(
      refusedSaveClosesCreate(
        { hold: null, saving: savingBefore },
        { hold: held ? HOLD : null, saving: savingAfter },
      ),
      name,
    ).toBe(closes);
  // An edit's save that was holding already is refused: still a refusal.
  expect(
    refusedSaveClosesCreate(
      { hold: HOLD, saving: true },
      { hold: HOLD, saving: false },
    ),
  ).toBe(true);
});
