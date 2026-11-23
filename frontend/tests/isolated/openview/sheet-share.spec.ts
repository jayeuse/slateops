import { expect, test } from "@playwright/test";

import type { WorksheetShare } from "../../../src/components/systems/openview/adapters/worksheets-api";
import {
  openLine,
  sharedWithWords,
  shareLines,
  sheetActions,
  sheetRole,
} from "../../../src/components/systems/openview/domain/sheet-share";

// docs/specs/sheets.md V5, V8, L7, L10 and Screens 3 to 5: who may do what
// on a sheet's page, and the words for sharing and the open state. The http
// specs openview-sheet-share and openview-sheet-open keep one journey each.

const owner = {
  id: "00000000-0000-4000-8000-000000000a01",
  displayName: "Andrea Villamor",
};
const onRecord = {
  recordId: "00000000-0000-4000-8000-000000000a02",
  anchorTitle: "Andrea Villamor",
  moduleName: "Faculty Members",
  owner,
};
const onModule = {
  recordId: null,
  anchorTitle: "Faculty Members",
  moduleName: "Faculty Members",
  owner,
};

test("an open sheet is read-only for everyone, its owner included", () => {
  expect(
    (["owner", "edit", "view"] as const).map((myLevel) =>
      sheetRole({ state: "open", myLevel }),
    ),
  ).toEqual(["open", "open", "open"]);
  expect(
    (["owner", "edit", "view"] as const).map((myLevel) =>
      sheetRole({ state: "private", myLevel }),
    ),
  ).toEqual(["owner", "edit", "view"]);
});

test("only the owner of a sheet that is not open shares, renames or deletes it", () => {
  const none = { share: false, rename: false, remove: false };
  expect(sheetActions("owner")).toEqual({
    share: true,
    rename: true,
    remove: true,
    history: true,
    export: true,
  });
  for (const role of ["edit", "view", "open"] as const)
    expect(sheetActions(role), role).toEqual({
      ...none,
      history: true,
      export: true,
    });
});

test("the owner's chip counts people and groups apart", () => {
  const person = (id: string): WorksheetShare => ({
    id,
    level: "view",
    subject: "user",
    person: { id, displayName: id },
  });
  const group = (id: string): WorksheetShare => ({
    id,
    level: "view",
    subject: "group",
    group: { id, name: id },
  });
  expect(
    [
      [],
      [person("a")],
      [person("a"), person("b")],
      [group("g")],
      [person("a"), person("b"), group("g")],
      [person("a"), group("g"), group("h")],
    ].map(sharedWithWords),
  ).toEqual([
    "Only you",
    "Shared with 1 person",
    "Shared with 2 people",
    "Shared with 1 group",
    "Shared with 2 people and 1 group",
    "Shared with 1 person and 2 groups",
  ]);
});

test("the share lines and the open line name the record, or the module of a module sheet", () => {
  expect(shareLines(onRecord, "Larkspur College")).toEqual([
    "People see this sheet only while they can read Andrea Villamor's record.",
    "If you leave Larkspur College, this sheet opens read-only to everyone who can read Andrea Villamor's record.",
  ]);
  expect(shareLines(onModule, "Larkspur College")).toEqual([
    "People see this sheet only while they can read Faculty Members.",
    "If you leave Larkspur College, this sheet opens read-only to everyone who can read Faculty Members.",
  ]);
  expect(openLine(onRecord, "Larkspur College")).toBe(
    "Andrea Villamor no longer has access to Larkspur College. Everyone who can read Andrea Villamor's record can read this sheet. Nobody can change it.",
  );
  expect(openLine(onModule, "Larkspur College")).toBe(
    "Andrea Villamor no longer has access to Larkspur College. Everyone who can read Faculty Members can read this sheet. Nobody can change it.",
  );
});
