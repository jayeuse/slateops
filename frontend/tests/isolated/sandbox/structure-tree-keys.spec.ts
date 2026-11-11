import { expect, test } from "@playwright/test";

import { treeTypeAheadLetter } from "../../../src/components/sandbox/sandbox-inspector-outline";

// The Tree Keys Rule (FIND-4) with the add-next entry (TASK-0050 D-1): a
// letter typed on a tree item jumps to the next item with that letter, but
// never while an entry or popover the tree opened is open or opening, and
// never for a key that does not come from a tree item.
test("tree type-ahead takes a plain letter on a tree item only while no entry is open", () => {
  const press = {
    key: "S",
    altKey: false,
    ctrlKey: false,
    metaKey: false,
    onTreeItem: true,
    createOpen: false,
  };
  const rows: Array<[string, Partial<typeof press>, string | null]> = [
    ["a letter on a tree item", {}, "s"],
    ["an entry is open or opening", { createOpen: true }, null],
    ["the key does not come from a tree item", { onTreeItem: false }, null],
    ["a modifier", { ctrlKey: true }, null],
    ["a named key", { key: "Enter" }, null],
  ];
  for (const [name, patch, letter] of rows)
    expect(treeTypeAheadLetter({ ...press, ...patch }), name).toBe(letter);
});
