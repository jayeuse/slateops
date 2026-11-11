import { expect, test } from "@playwright/test";

import { tryTriggerPlan } from "../../../src/components/systems/sandbox/domain/try-this-trigger";
import {
  condition,
  context,
  field,
  literal,
  ordersDesign,
  trigger,
} from "./test-section-design";

// "Try this trigger" (docs/specs/sandbox-ux-redesign.md TEST-9, UXD-11):
// that trigger alone, on its own event, with only its literal same-module
// conditions met by values valid for the field and its linked targets.

const added = { kind: "record-created", moduleId: "orders" } as const;

test(
  "Try this trigger sends only that trigger and meets its condition",
  { tag: "@UX-C33" },
  () => {
    const flag = trigger("flag", "Flag large orders", added, {
      priority: 1,
      conditions: [condition("c1", "amount", ">=", literal(100))],
      sets: [["status", "review"]],
    });
    const plan = tryTriggerPlan(ordersDesign(), flag, context);
    expect(plan.triggerIds).toEqual(["flag"]);
    expect(plan.event).toEqual({ kind: "record-created" });
    // Amount 1 becomes 100; Status keeps its example, Open.
    expect(plan.values).toMatchObject({ amount: 100, status: "open" });
    expect(plan.setFieldIds).toEqual(["amount"]);
    expect(plan.notes).toEqual([]);
  },
);

test(
  "a condition that compares two fields keeps the example values and says why",
  { tag: "@UX-C33" },
  () => {
    const design = ordersDesign([
      field("total", "Total", { kind: "number", defaultValue: 5 }),
    ]);
    const compare = trigger("compare", "Over total", added, {
      conditions: [
        condition("c1", "amount", ">", {
          kind: "field-reference",
          moduleId: "orders",
          fieldId: "total",
        }),
      ],
    });
    const plan = tryTriggerPlan(design, compare, context);
    expect(plan.values).toMatchObject({ amount: 1, total: 5 });
    expect(plan.setFieldIds).toEqual([]);
    expect(plan.notes).toEqual(["Amount is compared with Total; values kept."]);
  },
);

test("in an any group only the first condition that can be filled is filled", () => {
  const either = trigger("either", "Large or paid", added, {
    operator: "any",
    conditions: [
      condition("c1", "amount", ">=", literal(100)),
      condition("c2", "paid", "=", literal(true)),
    ],
  });
  const plan = tryTriggerPlan(ordersDesign(), either, context);
  expect(plan.values).toMatchObject({ amount: 100, paid: false });
  expect(plan.setFieldIds).toEqual(["amount"]);
});

test("a value outside the field's limits is not used", () => {
  const design = ordersDesign();
  design.modules[0].fields[0].config = {
    kind: "number",
    defaultValue: 1,
    max: 50,
  };
  const flag = trigger("flag", "Flag large orders", added, {
    conditions: [condition("c1", "amount", ">=", literal(100))],
  });
  const plan = tryTriggerPlan(design, flag, context);
  expect(plan.values.amount).toBe(1);
  expect(plan.notes).toEqual(["100 is outside Amount's limits; value kept."]);
});

test("a value outside a linked target field's limits is not used", () => {
  const design = ordersDesign();
  design.modules[1].fields = [
    field("limit", "Limit", { kind: "number", defaultValue: null, max: 60 }),
  ];
  design.relationships = [
    {
      id: "orders-customers",
      name: "Orders to Customers",
      sourceModuleId: "orders",
      targetModuleId: "customers",
      cardinality: "one-to-many",
      fieldMappings: [{ sourceFieldId: "amount", targetFieldId: "limit" }],
    },
  ];
  const flag = trigger("flag", "Flag large orders", added, {
    conditions: [condition("c1", "amount", ">=", literal(100))],
  });
  const plan = tryTriggerPlan(design, flag, context);
  expect(plan.values.amount).toBe(1);
  expect(plan.notes).toEqual(["100 is outside Amount's limits; value kept."]);
});

test("two conditions on one field that cannot both hold keep the example", () => {
  const both = trigger("both", "Impossible", added, {
    conditions: [
      condition("c1", "amount", ">=", literal(100)),
      condition("c2", "amount", "<=", literal(10)),
    ],
  });
  const plan = tryTriggerPlan(ordersDesign(), both, context);
  expect(plan.values.amount).toBe(1);
  expect(plan.notes).toEqual([
    "Amount has conditions that cannot both hold; value kept.",
  ]);
});

test("on a field change, the watched field takes the new value and the previous one differs", () => {
  const review = trigger(
    "review",
    "Status review",
    { kind: "field-changed", moduleId: "orders", fieldId: "status" },
    { conditions: [condition("c1", "status", "=", literal("review"))] },
  );
  const plan = tryTriggerPlan(ordersDesign(), review, context);
  expect(plan.values.status).toBe("review");
  expect(plan.event).toEqual({
    kind: "field-changed",
    fieldId: "status",
    previousValue: "open",
  });
});

test("a condition on the field a threshold event fixes keeps the event's value", () => {
  const large = trigger(
    "large",
    "Very large",
    {
      kind: "threshold-crossed",
      moduleId: "orders",
      fieldId: "amount",
      operator: ">=",
      value: literal(1000),
    },
    { conditions: [condition("c1", "amount", ">=", literal(5000))] },
  );
  const plan = tryTriggerPlan(ordersDesign(), large, context);
  expect(plan.values.amount).toBe(1000);
  expect(plan.notes).toEqual(["Amount is set by the event; value kept."]);
});
