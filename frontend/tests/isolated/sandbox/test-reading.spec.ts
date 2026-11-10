import { expect, test } from "@playwright/test";

import {
  moduleReading,
  testModuleGroups,
  tryEventPlan,
} from "../../../src/components/systems/sandbox/domain/test-reading";
import {
  condition,
  context,
  field,
  literal,
  ordersDesign,
  trigger,
} from "./test-section-design";

// The Test reading (docs/specs/sandbox-ux-redesign.md TEST-1, TEST-2, E1,
// E6, E7) and the "Try it" request of each event block (TEST-3, N9).

const triggers = [
  trigger(
    "flag",
    "Flag large orders",
    { kind: "record-created", moduleId: "orders" },
    {
      conditions: [condition("c1", "amount", ">=", literal(100))],
      sets: [["status", "review"]],
    },
  ),
  trigger(
    "hold",
    "Hold unpaid orders",
    { kind: "record-created", moduleId: "orders" },
    { enabled: false, sets: [["status", "open"]] },
  ),
  trigger(
    "confirm",
    "Confirm paid orders",
    { kind: "field-changed", moduleId: "orders", fieldId: "paid" },
    {
      conditions: [condition("c2", "paid", "=", literal(true))],
      sets: [["status", "review"]],
    },
  ),
  trigger(
    "large",
    "Review very large orders",
    {
      kind: "threshold-crossed",
      moduleId: "orders",
      fieldId: "amount",
      operator: ">=",
      value: literal(1000),
    },
    { sets: [["status", "review"]] },
  ),
  trigger(
    "daily",
    "Daily check",
    {
      kind: "schedule",
      moduleId: "orders",
      frequency: "weekly",
      time: "09:00",
      weekday: 1,
    },
    { conditions: [condition("c3", "status", "=", literal("open"))] },
  ),
  trigger("elsewhere", "Invoice added", {
    kind: "record-created",
    moduleId: "invoices",
  }),
];

function linkedOrders() {
  const design = ordersDesign([
    field("customer", "Customer", { kind: "text", defaultValue: "" }),
  ]);
  design.relationships = [
    {
      id: "orders-customers",
      name: "Orders to Customers",
      sourceModuleId: "orders",
      targetModuleId: "customers",
      cardinality: "one-to-many",
      fieldMappings: [{ sourceFieldId: "customer", targetFieldId: "name" }],
    },
    {
      id: "invoices-orders",
      name: "Invoices to Orders",
      sourceModuleId: "invoices",
      targetModuleId: "orders",
      cardinality: "one-to-many",
      fieldMappings: [],
    },
  ];
  design.modules[1].fields = [
    field("name", "Name", { kind: "text", defaultValue: "" }),
  ];
  return design;
}

test(
  "the reading lists each event with the triggers that listen and the fields they set",
  { tag: "@UX-C22" },
  () => {
    const reading = moduleReading(linkedOrders(), triggers, "orders");

    expect(reading?.facts).toBe("Sales · 5 fields · 5 triggers · 2 links");
    expect(
      reading?.blocks.map((block) => ({
        title: block.title,
        triggers: block.triggers.map((item) => [
          item.name,
          item.enabled ? "on" : "Off",
          item.conditions,
          item.sets.join(", "),
        ]),
      })),
    ).toEqual([
      {
        title: "When an item is added",
        triggers: [
          ["Flag large orders", "on", "if Amount is at least 100", "Status"],
          ["Hold unpaid orders", "Off", "always", "Status"],
        ],
      },
      {
        title: "When Paid changes",
        triggers: [
          ["Confirm paid orders", "on", "if Paid is Checked", "Status"],
        ],
      },
      {
        title: "When Amount reaches 1,000",
        triggers: [["Review very large orders", "on", "always", "Status"]],
      },
      {
        title: "Every Monday at 09:00",
        triggers: [["Daily check", "on", "if Status is Open", ""]],
      },
    ]);
  },
);

test(
  "the reading shows links out and in, with the other module and its department",
  { tag: "@UX-C23" },
  () => {
    const reading = moduleReading(linkedOrders(), triggers, "orders");
    expect(
      reading?.links.map((link) => [
        link.direction,
        link.moduleName,
        link.departmentName,
        link.carries,
      ]),
    ).toEqual([
      ["out", "Customers", "Sales", ["Customer"]],
      ["in", "Invoices", "Finance", []],
    ]);
  },
);

test("a module with no trigger reads one event block with no listener", () => {
  const reading = moduleReading(ordersDesign(), triggers, "customers");
  expect(reading?.facts).toBe("Sales");
  expect(
    reading?.blocks.map((block) => [block.title, block.triggers.length]),
  ).toEqual([["When an item is added", 0]]);
});

test(
  "the Modules list groups open modules by department and marks a department with no live binding as new",
  { tag: "@UX-C28" },
  () => {
    const design = ordersDesign();
    design.modules[1].closed = true;
    const groups = testModuleGroups(design, triggers, [
      {
        kind: "department",
        sandbox_id: "sales",
      },
      // A module binding never makes its department live.
      { kind: "module", sandbox_id: "invoices" },
    ]);
    expect(
      groups.map((group) => [
        group.departmentName,
        group.isNew,
        group.modules.map((item) => [item.name, item.triggerCount]),
      ]),
    ).toEqual([
      ["Sales", false, [["Orders", 5]]],
      ["Finance", true, [["Invoices", 1]]],
    ]);
    // While the bindings load, no department reads as new.
    expect(
      testModuleGroups(design, triggers, null).map((group) => group.isNew),
    ).toEqual([false, false]);
  },
);

test("Try it on a field change sends a previous value that differs", () => {
  const plan = tryEventPlan(
    ordersDesign(),
    "orders",
    { kind: "field-changed", fieldId: "status" },
    context,
  );
  expect(plan.event).toEqual({
    kind: "field-changed",
    fieldId: "status",
    previousValue: "review",
  });
  expect(plan.values.status).toBe("open");
  expect(plan.triggerIds).toBeNull();
});

test("Try it on a threshold crosses it with the smallest valid value", () => {
  const design = ordersDesign();
  design.modules[0].fields[0].config = {
    kind: "number",
    defaultValue: 1,
    step: 50,
  };
  const plan = tryEventPlan(
    design,
    "orders",
    {
      kind: "threshold-crossed",
      fieldId: "amount",
      operator: ">=",
      value: literal(1020),
    },
    context,
  );
  // 1,050 is the first step value at or above 1,020; 1,000 is below it.
  expect(plan.values.amount).toBe(1050);
  expect(plan.event).toEqual({
    kind: "threshold-crossed",
    fieldId: "amount",
    previousValue: 970,
  });
  expect(plan.notes).toEqual([]);
});

test("Try it on a threshold above the field's maximum keeps the examples and says why", () => {
  const design = ordersDesign();
  design.modules[0].fields[0].config = {
    kind: "number",
    defaultValue: 1,
    max: 500,
  };
  const plan = tryEventPlan(
    design,
    "orders",
    {
      kind: "threshold-crossed",
      fieldId: "amount",
      operator: ">=",
      value: literal(1000),
    },
    context,
  );
  expect(plan.values.amount).toBe(1);
  expect(plan.event).toEqual({
    kind: "threshold-crossed",
    fieldId: "amount",
    previousValue: 1,
  });
  expect(plan.notes).toEqual([
    "1,000 is outside Amount's limits; values kept.",
  ]);
});

test("Try it on a weekly schedule sends the schedule and no previous value", () => {
  const plan = tryEventPlan(
    ordersDesign(),
    "orders",
    { kind: "schedule", frequency: "weekly", time: "09:00", weekday: 1 },
    context,
  );
  expect(plan.event).toEqual({
    kind: "schedule",
    frequency: "weekly",
    time: "09:00",
    weekday: 1,
  });
});
