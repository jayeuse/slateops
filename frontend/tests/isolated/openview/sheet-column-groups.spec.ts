import { expect, test } from "@playwright/test";
import { ApiError } from "../../../src/lib/api";
import {
  columnRefusal,
  placeColumn,
  removeGroup,
  renameGroup,
  withoutColumn,
} from "../../../src/components/systems/openview/domain/sheet-columns";
import type { WorksheetStructure } from "../../../src/components/systems/openview/adapters/worksheets-api";

// docs/specs/sheets.md K8 and D1.7 (SH-25): a column group is a named band
// over adjacent columns, kept in column order, never overlapping. Route 6
// refuses anything else, so the editor places a column where its group is.

function structure(): WorksheetStructure {
  return {
    structureVersion: 1,
    nextColumnSeq: 8,
    columns: ["Student", "Quiz 1", "Quiz 2", "Exam", "Quiz 3", "Notes"].map(
      (name, index) => ({ key: `c${index + 1}`, name, type: "int" as const }),
    ),
    groups: [
      { name: "Prelim", keys: ["c2", "c3", "c4"] },
      { name: "Midterm", keys: ["c5"] },
    ],
    totals: { c2: "average", c6: "count" },
  };
}

const order = (columns: { key: string }[]) => columns.map((item) => item.key);

test("a column that joins a group moves after the group's last column", () => {
  const placed = placeColumn(structure(), "c6", { group: 1 });
  expect(order(placed.columns)).toEqual(["c1", "c2", "c3", "c4", "c5", "c6"]);
  expect(placed.groups).toEqual([
    { name: "Prelim", keys: ["c2", "c3", "c4"] },
    { name: "Midterm", keys: ["c5", "c6"] },
  ]);

  const first = placeColumn(structure(), "c1", { group: 0 });
  expect(order(first.columns)).toEqual(["c2", "c3", "c4", "c1", "c5", "c6"]);
  expect(first.groups[0]).toEqual({
    name: "Prelim",
    keys: ["c2", "c3", "c4", "c1"],
  });
});

test("a column that leaves a group from its middle moves out after it, so the group stays adjacent", () => {
  const placed = placeColumn(structure(), "c3", { group: null });
  expect(order(placed.columns)).toEqual(["c1", "c2", "c4", "c3", "c5", "c6"]);
  expect(placed.groups).toEqual([
    { name: "Prelim", keys: ["c2", "c4"] },
    { name: "Midterm", keys: ["c5"] },
  ]);
  // A column that stays where it is keeps its place.
  expect(
    order(placeColumn(structure(), "c6", { group: null }).columns),
  ).toEqual(["c1", "c2", "c3", "c4", "c5", "c6"]);
  const stays = placeColumn(structure(), "c3", { group: 0 });
  expect(order(stays.columns)).toEqual(["c1", "c2", "c3", "c4", "c5", "c6"]);
  expect(stays.groups[0].keys).toEqual(["c2", "c3", "c4"]);
});

test("a new column goes into its group or to the end, and a new group starts with one column", () => {
  const added = { key: "c8", name: "Quiz 4", type: "int" as const };
  const grouped = placeColumn(structure(), added, { group: 0 });
  expect(order(grouped.columns)).toEqual([
    "c1",
    "c2",
    "c3",
    "c4",
    "c8",
    "c5",
    "c6",
  ]);
  expect(grouped.groups[0].keys).toEqual(["c2", "c3", "c4", "c8"]);

  const alone = placeColumn(structure(), added, { newGroup: "Finals" });
  expect(order(alone.columns).at(-1)).toBe("c8");
  expect(alone.groups.at(-1)).toEqual({ name: "Finals", keys: ["c8"] });

  // Leaving Prelim's middle for a new group: out after Prelim first.
  const moved = placeColumn(structure(), "c3", { newGroup: "Extra" });
  expect(order(moved.columns)).toEqual(["c1", "c2", "c4", "c3", "c5", "c6"]);
  expect(moved.groups).toContainEqual({ name: "Extra", keys: ["c3"] });
  expect(moved.groups).toContainEqual({ name: "Prelim", keys: ["c2", "c4"] });
});

test("groups are renamed and removed by their place, and their columns stay", () => {
  expect(renameGroup(structure().groups, 0, "Period 1")[0]).toEqual({
    name: "Period 1",
    keys: ["c2", "c3", "c4"],
  });
  expect(removeGroup(structure().groups, 0)).toEqual([
    { name: "Midterm", keys: ["c5"] },
  ]);
});

test("a deleted column leaves its group and its total; an emptied group goes", () => {
  const removed = withoutColumn(structure(), "c5");
  expect(order(removed.columns)).toEqual(["c1", "c2", "c3", "c4", "c6"]);
  expect(removed.groups).toEqual([
    { name: "Prelim", keys: ["c2", "c3", "c4"] },
  ]);
  expect(withoutColumn(structure(), "c2").totals).toEqual({ c6: "count" });
});

test("a refused save reads in plain words and names another column when it is the cause", () => {
  const refused = (status: number, detail: Record<string, unknown>) =>
    new ApiError(status, String(detail.message), detail);
  const names = { c5: "Final grade", c9: "Total" };
  // The column being edited: its name is not repeated.
  expect(
    columnRefusal(
      refused(422, {
        code: "expression_invalid",
        message: "Total: the columns Total, Bonus use each other",
        key: "c9",
        reason: "loop",
      }),
      { editedKey: "c9", names },
    ),
  ).toBe("The columns Total, Bonus use each other.");
  // Deleting a column another computed column reads.
  expect(
    columnRefusal(
      refused(422, {
        code: "expression_invalid",
        message: "Final grade: the sheet has no column {c2}",
        key: "c5",
        reason: "unknown_column",
      }),
      { editedKey: "c2", names, removedName: "Quiz 1" },
    ),
  ).toBe("Final grade uses Quiz 1. Change Final grade first.");
  expect(
    columnRefusal(
      refused(422, {
        code: "column_not_visible",
        message:
          "Linked grade: only the owner can remove a column whose source you cannot see",
        key: "c7",
      }),
      { editedKey: "c7", names: { c7: "Linked grade" } },
    ),
  ).toBe("Only the owner can remove a column whose source you cannot see.");
  expect(
    columnRefusal(
      refused(412, { code: "worksheet_changed", message: "changed" }),
      { editedKey: "c1", names },
    ),
  ).toBe("Someone changed this sheet's columns. Close this and try again.");
  expect(columnRefusal(new Error("offline"), { editedKey: "c1", names })).toBe(
    "The column could not be saved. Try again.",
  );
});
