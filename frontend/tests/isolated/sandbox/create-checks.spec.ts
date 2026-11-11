import { expect, test } from "@playwright/test";

import {
  addElement,
  createEntryKey,
  createLimitReason,
  createRefusalPlace,
  emptyCreateDraft,
  typePickFocus,
  type CreateDraft,
} from "../../../src/components/systems/sandbox/domain/create-checks";
import type {
  Design,
  Field,
  Module,
} from "../../../src/components/systems/sandbox/domain/model";
import { classifyDesignChange } from "../../../src/components/systems/sandbox/state/save-queue";

// The add-next entry's checks and adds (docs/specs/sandbox-ux-redesign.md,
// "The entry", N2 and N3).

function textField(id: string, name: string): Field {
  return {
    id,
    name,
    type: "Text",
    required: false,
    value: "",
    options: "",
    closed: false,
  };
}

function salesDesign(): Design {
  return {
    departments: [{ id: "sales", name: "Sales", closed: false }],
    modules: [
      {
        id: "orders",
        department: "sales",
        name: "Orders",
        closed: false,
        fields: [textField("number", "Order number")],
        x: 72,
        y: 104,
      },
    ],
    relationships: [],
    rules: [],
    layout: {
      sales: { x: 48, y: 48, width: 680, height: 180 },
      orders: { x: 90, y: 104, width: 232, height: 60 },
    },
  };
}

function draft(name: string, patch: Partial<CreateDraft> = {}): CreateDraft {
  return { ...emptyCreateDraft, name, ...patch };
}

function added(result: ReturnType<typeof addElement>): Design {
  if (!result.ok) throw new Error(`refused: ${result.reason}`);
  return result.design;
}

// UX-C6 (FAST-1)
test("two modules added one after another land under the same department in separate slots", () => {
  const first = added(
    addElement(salesDesign(), "module", "invoices", "sales", draft("Invoices")),
  );
  const second = added(
    addElement(first, "module", "payments", "sales", draft("Payments")),
  );

  const names = second.modules.map((item) => [item.name, item.department]);
  expect(names).toEqual([
    ["Orders", "sales"],
    ["Invoices", "sales"],
    ["Payments", "sales"],
  ]);
  // The next slots of the frame: right of Orders, then the next row.
  expect(second.layout?.invoices).toEqual({
    x: 402,
    y: 118,
    width: 232,
    height: 60,
  });
  expect(second.layout?.payments).toEqual({
    x: 90,
    y: 196,
    width: 232,
    height: 60,
  });
  // The stored module position follows its box, as a parsed document does.
  const payments = second.modules.find((item) => item.id === "payments");
  expect([payments?.x, payments?.y]).toEqual([90, 196]);
});

// UX-C6 (FAST-1)
test("Enter on a blank name and Escape end the entry instead of adding", () => {
  const rows: Array<
    [string, CreateDraft, "Enter" | "Escape", "add" | "close"]
  > = [
    ["Enter with a name", draft("Invoices"), "Enter", "add"],
    ["Enter on an empty name", draft(""), "Enter", "close"],
    ["Enter on spaces only", draft("   "), "Enter", "close"],
    ["Escape with a typed name", draft("Invoices"), "Escape", "close"],
  ];
  for (const [label, entry, key, expected] of rows)
    expect(createEntryKey(entry, key), label).toBe(expected);
});

// UX-C8 (FAST-2)
test("a field takes its chosen type and Required when it is added", () => {
  const next = added(
    addElement(
      salesDesign(),
      "field",
      "amount",
      "orders",
      draft(" Amount due ", { type: "Number", required: true }),
    ),
  );
  const amount = next.modules[0]?.fields.find((item) => item.id === "amount");
  expect(amount).toMatchObject({
    name: "Amount due",
    type: "Number",
    required: true,
    config: { kind: "number", defaultValue: null },
  });

  const status = added(
    addElement(
      salesDesign(),
      "field",
      "status",
      "orders",
      draft("Status", { type: "Select", choices: "Open, Paid ,, Closed" }),
    ),
  ).modules[0]?.fields.find((item) => item.id === "status");
  expect(status?.type).toBe("Select");
  expect(
    status?.config?.kind === "select"
      ? status.config.options.map((option) => option.label)
      : null,
  ).toEqual(["Open", "Paid", "Closed"]);
});

// UX-C8 (FAST-2): one click on a type; Choice list then needs its choices.
test("picking a type returns to the name, and Choice list moves on to Choices", () => {
  expect(typePickFocus("Number")).toBe("name");
  expect(typePickFocus("Date/Time")).toBe("name");
  expect(typePickFocus("Select")).toBe("choices");
});

// UX-C12 (FAST-6, N3): one change holds the element and its layout box, so
// the save queue takes it as one add and Undo removes it in one step.
test("each add is one queued add of the element with its own layout box", () => {
  const before = salesDesign();
  const rows: Array<[string, Design, string]> = [
    [
      "department",
      added(
        addElement(before, "department", "finance", null, draft("Finance")),
      ),
      "finance",
    ],
    [
      "module",
      added(
        addElement(before, "module", "invoices", "sales", draft("Invoices")),
      ),
      "invoices",
    ],
    [
      "field",
      added(addElement(before, "field", "due", "orders", draft("Due on"))),
      "due",
    ],
  ];
  for (const [label, next, id] of rows)
    expect(classifyDesignChange(before, next), label).toEqual({
      kind: "add",
      ids: [id],
    });

  const [department, moduleLayout, field] = rows.map(([, next]) => next.layout);
  // A department goes to the next free slot right of the existing frames.
  expect(department?.finance).toEqual({
    x: 808,
    y: 48,
    width: 336,
    height: 144,
  });
  expect(moduleLayout?.invoices).toEqual({
    x: 402,
    y: 118,
    width: 232,
    height: 60,
  });
  // Fields have no layout box; the card grows a row on the canvas.
  expect(field).toEqual(before.layout);
});

// N2: refused in place, before the draft changes.
test("an add that the save would refuse is refused with its reason", () => {
  const before = salesDesign();
  const farRight: Design = {
    ...before,
    layout: {
      ...before.layout,
      // The next slot starts at 99,500 + 680 + 80, past 100,000.
      sales: { x: 99_500, y: 48, width: 680, height: 180 },
    },
  };
  const rows: Array<
    [
      string,
      Design,
      Parameters<typeof addElement>[1],
      string,
      CreateDraft,
      string,
    ]
  > = [
    [
      "a Choice list with no choices",
      before,
      "field",
      "orders",
      draft("Status", { type: "Select", choices: " , " }),
      "Add at least one choice.",
    ],
    [
      "a Choice list that repeats a choice",
      before,
      "field",
      "orders",
      draft("Status", { type: "Select", choices: "Open, Open" }),
      "Choices must be unique.",
    ],
    [
      "a name over 80 characters",
      before,
      "module",
      "sales",
      draft("x".repeat(81)),
      "Use 80 characters or fewer.",
    ],
    [
      "a department past the canvas edge",
      farRight,
      "department",
      "",
      draft("Finance"),
      "The canvas has no room for another department.",
    ],
    [
      "a module whose department was deleted",
      before,
      "module",
      "gone",
      draft("Invoices"),
      "This department was deleted. Refresh the designer and try again.",
    ],
  ];
  for (const [label, design, kind, parent, entry, reason] of rows)
    expect(
      addElement(design, kind, "new", parent || null, entry),
      label,
    ).toEqual({ ok: false, reason });

  // A name of exactly 80 characters is accepted.
  expect(
    addElement(before, "module", "new", "sales", draft("x".repeat(80))).ok,
  ).toBe(true);
});

function withCounts(departments: number, modules: number, fields: number) {
  const design: Design = {
    departments: Array.from({ length: departments }, (_, index) => ({
      id: `d${index}`,
      name: `D${index}`,
      closed: false,
    })),
    modules: [],
    relationships: [],
    rules: [],
    layout: {},
  };
  const perModule = Math.ceil(fields / Math.max(modules, 1));
  let left = fields;
  design.modules = Array.from({ length: modules }, (_, index): Module => {
    const count = Math.min(perModule, left);
    left -= count;
    return {
      id: `m${index}`,
      department: "d0",
      name: `M${index}`,
      closed: index % 2 === 0,
      fields: Array.from({ length: count }, (_, at) =>
        textField(`m${index}f${at}`, `F${at}`),
      ),
      x: 0,
      y: 0,
    };
  });
  return design;
}

// N2: at a document limit the add control says why it cannot add.
test("at a document limit the add is disabled with the limit as its reason", () => {
  const rows: Array<
    [string, Design, Parameters<typeof createLimitReason>[1], string | null]
  > = [
    ["below every limit", withCounts(99, 499, 4_999), "module", null],
    [
      "100 departments",
      withCounts(100, 1, 1),
      "department",
      "This design has 100 departments, the limit.",
    ],
    [
      "500 modules, closed ones counted",
      withCounts(1, 500, 1),
      "module",
      "This design has 500 modules, the limit.",
    ],
    [
      "5,000 fields",
      withCounts(1, 10, 5_000),
      "field",
      "This design has 5,000 fields, the limit.",
    ],
    [
      "600 departments and modules on the canvas",
      {
        ...withCounts(1, 1, 1),
        layout: Object.fromEntries(
          Array.from({ length: 600 }, (_, index) => [
            `box${index}`,
            { x: 0, y: 0, width: 10, height: 10 },
          ]),
        ),
      },
      "module",
      "This design has 600 departments and modules, the limit.",
    ],
  ];
  for (const [label, design, kind, reason] of rows)
    expect(createLimitReason(design, kind), label).toBe(reason);

  // The add itself refuses past the limit too, with the same reason.
  expect(
    addElement(withCounts(1, 500, 1), "module", "new", "d0", draft("More")),
  ).toEqual({ ok: false, reason: "This design has 500 modules, the limit." });
});

// N2 (TASK-0049 QA D-2): a name that publish would refuse as a duplicate is
// refused in place, compared without case (stricter than publish), in the
// scope publish uses: open departments across the design, open modules of
// the same department, and a module's open fields with its outgoing
// relationships to open modules.
test("a name already in use in its scope is refused, comparing without case", () => {
  const before = salesDesign();
  const design: Design = {
    ...before,
    departments: [
      ...before.departments,
      { id: "finance", name: "Finance", closed: false },
      { id: "archive", name: "Archive", closed: true },
    ],
    modules: [
      ...before.modules,
      {
        id: "customers",
        department: "sales",
        name: "Customers",
        closed: false,
        fields: [],
        x: 0,
        y: 0,
      },
      {
        id: "old",
        department: "sales",
        name: "Old orders",
        closed: true,
        fields: [],
        x: 0,
        y: 0,
      },
    ],
    relationships: [
      {
        id: "orders-customers",
        name: "Buyer",
        source: "orders",
        target: "customers",
        cardinality: "One-to-many",
        fieldMappings: [],
      },
    ],
  };
  const refused: Array<
    [string, Parameters<typeof addElement>[1], string | null, string, string]
  > = [
    [
      "a department",
      "department",
      null,
      " sales ",
      "A department named Sales already exists.",
    ],
    [
      "a module in its department",
      "module",
      "sales",
      "ORDERS",
      "Sales already has a module named Orders.",
    ],
    [
      "a field in its module",
      "field",
      "orders",
      "order NUMBER",
      "Orders already has a field named Order number.",
    ],
    [
      "a field named as an outgoing relationship",
      "field",
      "orders",
      "buyer",
      "Orders already has a relationship named Buyer.",
    ],
  ];
  for (const [name, kind, parentId, value, reason] of refused)
    expect(
      addElement(design, kind, "new", parentId, draft(value)),
      name,
    ).toEqual({ ok: false, reason });
  // Outside the scope, or held by a closed element: accepted.
  const accepted: Array<
    [string, Parameters<typeof addElement>[1], string | null, string]
  > = [
    ["a closed department's name", "department", null, "Archive"],
    ["a module name used in another department", "module", "finance", "Orders"],
    ["a closed module's name", "module", "sales", "Old orders"],
    [
      "a field name used in another module",
      "field",
      "customers",
      "Order number",
    ],
  ];
  for (const [name, kind, parentId, value] of accepted)
    expect(
      addElement(design, kind, "new", parentId, draft(value)).ok,
      name,
    ).toBe(true);
});

// B5d (Product Designer review): a choice problem shows under Choices; any
// other refusal shows under the name.
test("a refused Choice list shows a choice problem under Choices and the rest under the name", () => {
  const choiceList = (choices: string) =>
    draft("Status", { type: "Select", choices });
  const rows: Array<[string, CreateDraft, string, "name" | "choices"]> = [
    ["no choices", choiceList(" , "), "Add at least one choice.", "choices"],
    [
      "a repeated choice",
      choiceList("Open, Open"),
      "Choices must be unique.",
      "choices",
    ],
    ["an empty name", draft("", { type: "Select" }), "Enter a name.", "name"],
    [
      "a duplicate name",
      choiceList("Open"),
      "Orders already has a field named Status.",
      "name",
    ],
    ["a Text field", draft("Status"), "Enter a name.", "name"],
  ];
  for (const [label, entry, reason, place] of rows)
    expect(createRefusalPlace(entry, reason), label).toBe(place);
});
