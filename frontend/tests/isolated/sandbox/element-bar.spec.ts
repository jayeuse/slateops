import { expect, test } from "@playwright/test";

import {
  BAR_LINGER_MS,
  BAR_REST_MS,
  elementBarOwner,
  elementBarOwners,
  idlePointerRest,
  itemMenuEntries,
  reducePointerRest,
  savingMarkIds,
  type PointerRest,
  type PointerRestEvent,
} from "../../../src/components/systems/sandbox/helpers/element-bar";
import type { Design } from "../../../src/components/systems/sandbox/domain/model";

// The element bar and the canvas item menu (docs/specs/sandbox-ux-redesign.md,
// "Build: find and create"): when a bar shows, which element owns it, which
// rows carry the saving mark, and what the item menu holds.

function run(events: PointerRestEvent[]): PointerRest {
  return events.reduce(reducePointerRest, idlePointerRest);
}

// UX-C1 (FIND-1): the pointed element's bar shows on rest, not on a pass.
test("a pointed element's bar shows after a 120 ms rest and not before", () => {
  expect(BAR_REST_MS).toBe(120);
  const entered: PointerRestEvent = { type: "enter", id: "sales", at: 1000 };
  expect(run([entered, { type: "tick", at: 1119 }]).shown).toBeNull();
  expect(run([entered, { type: "tick", at: 1120 }]).shown).toBe("sales");
  // A pointer that passes through leaves no bar behind.
  expect(
    run([
      entered,
      { type: "leave", id: "sales", at: 1050 },
      { type: "tick", at: 1200 },
    ]).shown,
  ).toBeNull();
});

// UX-C1 (FIND-1): the bar stays long enough for the pointer to reach it.
test("a shown bar stays 300 ms after the pointer leaves, and reaching it keeps it", () => {
  expect(BAR_LINGER_MS).toBe(300);
  const shown: PointerRestEvent[] = [
    { type: "enter", id: "sales", at: 0 },
    { type: "tick", at: 120 },
    { type: "leave", id: "sales", at: 500 },
  ];
  expect(run([...shown, { type: "tick", at: 799 }]).shown).toBe("sales");
  expect(run([...shown, { type: "tick", at: 800 }]).shown).toBeNull();
  expect(
    run([...shown, { type: "barEnter" }, { type: "tick", at: 2000 }]).shown,
  ).toBe("sales");
  expect(
    run([
      ...shown,
      { type: "barEnter" },
      { type: "barLeave", at: 2000 },
      { type: "tick", at: 2300 },
    ]).shown,
  ).toBeNull();
});

// FIND-1: a pan, zoom, or drag hides the pointed bar at once.
test("a canvas gesture drops the pointed bar and any pending rest", () => {
  expect(
    run([
      { type: "enter", id: "sales", at: 0 },
      { type: "tick", at: 120 },
      { type: "cancel" },
    ]).shown,
  ).toBeNull();
  expect(
    run([
      { type: "enter", id: "sales", at: 0 },
      { type: "cancel" },
      { type: "tick", at: 500 },
    ]).shown,
  ).toBeNull();
});

// FIND-1 table: a field shows the bar of its module; a link has none.
test("a selected field owns its module's bar and a relationship owns none", () => {
  const state = {
    departments: [{ id: "sales" }],
    modules: [{ id: "orders" }],
    fields: [{ id: "field-1", moduleId: "orders" }],
  };
  expect(
    ["sales", "orders", "field-1", "link-1", ""].map((id) =>
      elementBarOwner(state, id),
    ),
  ).toEqual(["sales", "orders", "orders", null, null]);
});

// UXD-2: only the selected element shows its bar without pointer action; a
// held bar (focus inside, or an open entry) survives a gesture.
test("the shown bars are the held, selected, focused-row and pointed owners, once each", () => {
  expect(
    elementBarOwners({
      held: "sales",
      selected: "orders",
      focused: "orders",
      pointed: "customers",
      busy: false,
    }),
  ).toEqual(["sales", "orders", "customers"]);
  expect(
    elementBarOwners({
      held: null,
      selected: null,
      focused: null,
      pointed: null,
      busy: false,
    }),
  ).toEqual([]);
  expect(
    elementBarOwners({
      held: "sales",
      selected: "orders",
      focused: null,
      pointed: "customers",
      busy: true,
    }),
  ).toEqual(["sales"]);
});

function design(): Design {
  const field = (id: string, name: string) => ({
    id,
    name,
    type: "Text",
    required: false,
    value: "",
    options: "",
    closed: false,
  });
  return {
    departments: [{ id: "sales", name: "Sales", closed: false }],
    modules: [
      {
        id: "orders",
        department: "sales",
        name: "Orders",
        closed: false,
        fields: [field("number", "Number")],
        x: 0,
        y: 0,
      },
    ],
    relationships: [],
    rules: [],
  };
}

// FAST-6: the mark follows the queue, but only for elements the design still
// has; an undone add can stay queued and must not mark anything.
test("saving marks name only elements the design has, fields by their canvas id", () => {
  expect([
    ...savingMarkIds(design(), ["sales", "orders", "number", "undone"]),
  ]).toEqual(["sales", "orders", "sandbox-field:orders:number"]);
  expect(savingMarkIds(design(), []).size).toBe(0);
});

// FIND-6, TRIG-8: the canvas and the tree show the same item menu; a module
// adds Connect… and, once Triggers can take it, New trigger.
test("the item menu holds the tree items, and a module adds Connect and New trigger", () => {
  const labels = (entries: ReturnType<typeof itemMenuEntries>) =>
    entries.map((entry) => entry.label);
  const base = {
    closed: false,
    canPurge: false,
    lifecycle: true,
    duplicate: true,
    connect: true,
    newTrigger: true,
  };
  expect(labels(itemMenuEntries("department", base))).toEqual([
    "Rename department",
    "Close department",
    "Duplicate department",
    "Delete department",
  ]);
  expect(labels(itemMenuEntries("module", base))).toEqual([
    "Rename module",
    "Close module",
    "Duplicate module",
    "Connect…",
    "New trigger",
    "Delete module",
  ]);
  // T8-C1: a closed module takes no new trigger; Triggers offers only open
  // modules, so the item is hidden.
  expect(
    labels(
      itemMenuEntries("module", {
        ...base,
        closed: true,
        canPurge: true,
      }),
    ),
  ).toEqual([
    "Rename module",
    "Reopen module",
    "Delete module forever",
    "Duplicate module",
    "Connect…",
    "Delete module",
  ]);
  expect(labels(itemMenuEntries("field", base))).toEqual([
    "Rename field",
    "Close field",
    "Duplicate field",
    "Delete field",
  ]);
});
