import { expect, test } from "@playwright/test";

import type {
  Design,
  Field,
  Module,
} from "../../../src/components/systems/sandbox/domain/model";
import {
  mergeTemplateDepartment,
  templateDepartmentGroups,
  templateDepartmentName,
  templateDepartmentRefusal,
  templateDepartmentSummary,
  type TemplateDepartment,
} from "../../../src/components/systems/sandbox/domain/template-merge";
import { classifyDesignChange } from "../../../src/components/systems/sandbox/state/save-queue";

// One department from an organization template, added to the draft
// (docs/specs/sandbox-ux-redesign.md, FAST-7, "Template department", A2).

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

function ordersModule(): Module {
  return {
    id: "orders",
    department: "sales",
    name: "Orders",
    closed: false,
    fields: [textField("number", "Order number")],
    x: 90,
    y: 104,
  };
}

/** A design that already has Sales, with a module, a link, and a trigger. */
function designWithSales(): Design {
  return {
    departments: [{ id: "sales", name: "Sales", closed: false }],
    modules: [
      ordersModule(),
      { ...ordersModule(), id: "customers", name: "Customers", x: 420 },
    ],
    relationships: [
      {
        id: "orders-customers",
        name: "Orders to Customers",
        source: "orders",
        target: "customers",
        cardinality: "One-to-many",
        fieldMappings: [],
      },
    ],
    rules: [
      {
        id: "orders-notice",
        name: "Orders notice",
        trigger: "Record created",
        condition: "Always",
        action: "Notify",
        enabled: true,
      },
    ],
    layout: {
      sales: { x: 48, y: 48, width: 680, height: 180 },
      orders: { x: 90, y: 104, width: 232, height: 60 },
      customers: { x: 420, y: 104, width: 232, height: 60 },
    },
  };
}

/** Ids `new-1`, `new-2`, … in the order the merge asks for them. */
function counterIds(): () => string {
  let next = 0;
  return () => `new-${(next += 1)}`;
}

function templateDepartment(templateName: string, name: string) {
  const department = templateDepartmentGroups()
    .find((group) => group.templateName === templateName)
    ?.departments.find((item) => item.name === name);
  if (!department) throw new Error(`No template department ${name}`);
  return department;
}

const sales = (): TemplateDepartment =>
  templateDepartment("Finance, accounting & sales", "Sales");

// FAST-7: the dialog lists the 23 departments of the six templates.
test("the catalog groups the 23 template departments under their six templates with module counts", () => {
  const groups = templateDepartmentGroups();
  expect(
    groups.map((group) => [
      group.templateName,
      group.departments.map((item) => [item.name, item.modules.length]),
    ]),
  ).toEqual([
    [
      "Inventory & procurement",
      [
        ["Procurement", 2],
        ["Inventory & warehousing", 5],
        ["Finance controls", 1],
      ],
    ],
    [
      "Finance, accounting & sales",
      [
        ["Sales", 3],
        ["Finance", 2],
        ["Accounting", 2],
        ["Management reporting", 1],
      ],
    ],
    [
      "Retail & commerce",
      [
        ["Merchandising", 1],
        ["Commerce", 4],
        ["Fulfillment", 1],
        ["Customer care", 1],
      ],
    ],
    [
      "Professional services",
      [
        ["Business development", 3],
        ["Client delivery", 2],
        ["Finance", 2],
        ["People operations", 1],
      ],
    ],
    [
      "Field service & maintenance",
      [
        ["Service desk", 2],
        ["Field operations", 3],
        ["Parts and logistics", 2],
        ["Service finance", 2],
      ],
    ],
    [
      "Light manufacturing",
      [
        ["Production planning", 3],
        ["Production", 3],
        ["Quality assurance", 1],
        ["Warehouse", 3],
      ],
    ],
  ]);
  // Two templates both have a "Finance": each choice keeps its own key.
  const keys = groups.flatMap((group) =>
    group.departments.map((item) => item.key),
  );
  expect(new Set(keys).size).toBe(23);
});

// FAST-7: the preview shows the modules, their first fields, and the links.
test("the Sales preview lists its modules with their first fields and its own links", () => {
  const department = sales();
  expect(
    department.modules.map((item) => [
      item.name,
      item.fieldCount,
      item.firstFields.map((field) => [field.name, field.type]),
    ]),
  ).toEqual([
    [
      "Customers",
      7,
      [
        ["Customer ID", "Text"],
        ["Status", "Choice list"],
        ["Needs review", "Checkbox"],
      ],
    ],
    [
      "Opportunities",
      7,
      [
        ["Opportunity ID", "Text"],
        ["Status", "Choice list"],
        ["Needs review", "Checkbox"],
      ],
    ],
    [
      "Sales orders",
      7,
      [
        ["Sales order ID", "Text"],
        ["Status", "Choice list"],
        ["Needs review", "Checkbox"],
      ],
    ],
  ]);
  // The template's Finance and Accounting links stay out.
  expect(department.links.map((item) => item.name)).toEqual([
    "Customer opportunities",
    "Customer sales orders",
    "Opportunity sales orders",
  ]);
  expect(templateDepartmentSummary(department)).toBe(
    "Adds 3 modules and 3 links, without triggers.",
  );
  expect(
    templateDepartmentSummary(
      templateDepartment("Inventory & procurement", "Finance controls"),
    ),
  ).toBe("Adds 1 module, without triggers.");
});

// UX-C13 (FAST-7, A2)
test("adding Sales from a template keeps every existing element and adds a renamed department with new ids", () => {
  const before = designWithSales();
  const result = mergeTemplateDepartment(
    before,
    sales().key,
    "Sales 2",
    counterIds(),
  );
  if (!result.ok) throw new Error(result.reason);
  const next = result.design;

  // Every existing element is unchanged, the trigger list included.
  expect(next.departments.slice(0, 1)).toEqual(before.departments);
  expect(next.modules.slice(0, 2)).toEqual(before.modules);
  expect(next.relationships.slice(0, 1)).toEqual(before.relationships);
  expect(next.rules).toEqual(before.rules);
  for (const id of ["sales", "orders", "customers"])
    expect(next.layout?.[id]).toEqual(before.layout?.[id]);

  // The department: a new id, the chosen name, and no setup value, so it
  // starts from the default setup (FIT-4, N13).
  expect(next.departments.slice(1)).toEqual([
    { id: "new-1", name: "Sales 2", closed: false },
  ]);
  // Modules: new ids, in the new department, with their fields.
  const added = next.modules.slice(2);
  expect(added.map((item) => [item.id, item.department, item.name])).toEqual([
    ["new-2", "new-1", "Customers"],
    ["new-3", "new-1", "Opportunities"],
    ["new-4", "new-1", "Sales orders"],
  ]);
  expect(
    added[0]!.fields.map((field) => [field.name, field.type, field.required]),
  ).toEqual([
    ["Customer ID", "Text", true],
    ["Status", "Select", true],
    ["Needs review", "Checkbox", false],
    ["Legal name", "Text", true],
    ["Customer segment", "Select", true],
    ["Billing email", "Email", false],
    ["Credit limit", "Number", false],
  ]);
  // Only Sales' own links, between the new modules, with new ids.
  expect(
    next.relationships
      .slice(1)
      .map((item) => [item.id, item.name, item.source, item.target]),
  ).toEqual([
    ["new-5", "Customer opportunities", "new-2", "new-3"],
    ["new-6", "Customer sales orders", "new-2", "new-4"],
    ["new-7", "Opportunity sales orders", "new-3", "new-4"],
  ]);

  // One change that the save queue sends as one add.
  expect(classifyDesignChange(before, next)).toEqual({
    kind: "add",
    ids: ["new-1", "new-2", "new-3", "new-4", "new-5", "new-6", "new-7"],
  });
});

// A2: the frame takes the next free slot; each module sits inside it.
test("the added department takes the next free slot right of the existing frames", () => {
  const result = mergeTemplateDepartment(
    designWithSales(),
    sales().key,
    "Sales 2",
    counterIds(),
  );
  if (!result.ok) throw new Error(result.reason);
  const layout = result.design.layout ?? {};
  const frame = layout["new-1"]!;
  // Right of Sales (x 48, width 680), on the same top line.
  expect(frame.x).toBeGreaterThan(728);
  expect(frame.y).toBe(48);
  for (const item of result.design.modules.slice(2)) {
    const box = layout[item.id]!;
    // A parsed document takes the module position from its box.
    expect([item.x, item.y]).toEqual([box.x, box.y]);
    expect(box.x).toBeGreaterThanOrEqual(frame.x);
    expect(box.y).toBeGreaterThanOrEqual(frame.y);
    expect(box.x + box.width).toBeLessThanOrEqual(frame.x + frame.width);
    expect(box.y + box.height).toBeLessThanOrEqual(frame.y + frame.height);
  }
});

// FAST-7: the name never equals an existing department name.
test("the name is prefilled with the template name, or the next free number when it is taken", () => {
  const withNames = (...names: string[]): Design => ({
    ...designWithSales(),
    departments: names.map((name, index) => ({
      id: `department-${index}`,
      name,
      closed: false,
    })),
  });
  const cases: Array<[string, Design, { name: string; taken: string | null }]> =
    [
      ["free", withNames("Finance"), { name: "Sales", taken: null }],
      [
        "taken",
        withNames("Sales"),
        { name: "Sales 2", taken: "Sales is taken in this design." },
      ],
      [
        "taken in any letter case, with 2 taken too",
        withNames("sales", "SALES 2"),
        { name: "Sales 3", taken: "Sales is taken in this design." },
      ],
    ];
  for (const [label, design, expected] of cases)
    expect(templateDepartmentName(design, "Sales"), label).toEqual(expected);
});

// FAST-7, N2: Add department says why it cannot add.
test("a taken, blank, or long name refuses the add with the entry's reasons", () => {
  const design = designWithSales();
  const cases: Array<[string, string | null]> = [
    ["sales", "A department named Sales already exists."],
    ["  ", "Enter a name."],
    ["S".repeat(81), "Use 80 characters or fewer."],
    [" Sales 2 ", null],
  ];
  for (const [name, reason] of cases)
    expect(templateDepartmentRefusal(design, sales(), name), name).toBe(reason);
  const refused = mergeTemplateDepartment(design, sales().key, "SALES");
  expect(refused).toEqual({
    ok: false,
    reason: "A department named Sales already exists.",
  });
});

// N2: the merge never passes a document limit.
test("a merge that would pass a document limit is refused with the room left", () => {
  const base = designWithSales();
  const manyModules: Design = {
    ...base,
    modules: Array.from({ length: 498 }, (_, index) => ({
      ...ordersModule(),
      id: `module-${index}`,
      fields: [],
    })),
  };
  const manyFields: Design = {
    ...base,
    modules: [
      {
        ...ordersModule(),
        fields: Array.from({ length: 4_990 }, (_, index) =>
          textField(`field-${index}`, `Field ${index}`),
        ),
      },
    ],
  };
  const manyLinks: Design = {
    ...base,
    relationships: Array.from({ length: 999 }, (_, index) => ({
      ...base.relationships[0]!,
      id: `link-${index}`,
    })),
  };
  const manyDepartments: Design = {
    ...base,
    departments: Array.from({ length: 100 }, (_, index) => ({
      id: `department-${index}`,
      name: `Department ${index}`,
      closed: false,
    })),
  };
  const manyLayoutEntries: Design = {
    ...base,
    layout: Object.fromEntries(
      Array.from({ length: 598 }, (_, index) => [
        `box-${index}`,
        { x: 0, y: 0, width: 10, height: 10 },
      ]),
    ),
  };
  const cases: Array<[string, Design, string]> = [
    ["modules", manyModules, "Adds 3 modules; this design has room for 2."],
    ["fields", manyFields, "Adds 21 fields; this design has room for 10."],
    ["links", manyLinks, "Adds 3 links; this design has room for 1."],
    [
      "departments",
      manyDepartments,
      "This design has 100 departments, the limit.",
    ],
    [
      "layout entries",
      manyLayoutEntries,
      "Adds 4 departments and modules; this design has room for 2.",
    ],
  ];
  for (const [label, design, reason] of cases) {
    expect(templateDepartmentRefusal(design, sales(), "Sales 2"), label).toBe(
      reason,
    );
    expect(
      mergeTemplateDepartment(design, sales().key, "Sales 2"),
      label,
    ).toEqual({ ok: false, reason });
  }
});
