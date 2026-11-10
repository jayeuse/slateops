import { expect, test } from "@playwright/test";

import {
  exampleValues,
  testValueValid,
} from "../../../src/components/systems/sandbox/domain/example-values";
import type {
  SandboxDocumentDesign,
  SandboxDocumentField,
} from "../../../src/components/systems/sandbox/domain/document";
import { ADMINISTRATOR_ID, context, field } from "./test-section-design";

// Example values (docs/specs/sandbox-ux-redesign.md TEST-3, N7, E4): valid
// for each field and each linked target field, built from the field's
// settings, never asked for unless no valid value exists.

function design(
  fields: SandboxDocumentField[],
  extra: Partial<SandboxDocumentDesign> = {},
): SandboxDocumentDesign {
  return {
    departments: [{ id: "sales", name: "Sales", closed: false }],
    modules: [
      {
        id: "orders",
        departmentId: "sales",
        name: "Orders",
        closed: false,
        titleFieldId: null,
        fields,
      },
      ...(extra.modules ?? []),
    ],
    relationships: extra.relationships ?? [],
    layout: {},
  };
}

test(
  "required Number, Whole number, Date, Select, and Checkbox fields with no default get valid examples",
  { tag: "@UX-C24" },
  () => {
    const fields = [
      field(
        "quantity",
        "Quantity",
        {
          kind: "number",
          defaultValue: null,
          max: -3,
          step: 2,
        },
        true,
      ),
      field(
        "units",
        "Units",
        {
          kind: "integer",
          defaultValue: null,
          min: 2.5,
        },
        true,
      ),
      field(
        "due",
        "Due",
        {
          kind: "date",
          defaultValue: null,
          earliest: "2030-01-01",
        },
        true,
      ),
      field("visit", "Visit", { kind: "datetime", defaultValue: null }, true),
      field(
        "stage",
        "Stage",
        {
          kind: "select",
          defaultValue: null,
          options: [
            { id: "stage-new", label: "New" },
            { id: "stage-done", label: "Done" },
          ],
        },
        true,
      ),
      field(
        "urgent",
        "Urgent",
        { kind: "checkbox", defaultValue: false },
        true,
      ),
    ];
    const examples = exampleValues(design(fields), "orders", context);

    expect(examples).toEqual({
      values: {
        // Down the step from 0 to the first value at or under the maximum.
        quantity: -4,
        // The first whole number at or above the minimum.
        units: 3,
        // Today, moved inside the earliest limit.
        due: "2030-01-01",
        // Now, to the hour.
        visit: "2026-11-10T14:00",
        // The first choice's id, not its label.
        stage: "stage-new",
        urgent: false,
      },
      unfillable: [],
    });
    for (const item of fields)
      expect(testValueValid(item, examples.values[item.id] ?? null)).toBe(true);
  },
);

test("a step is checked in exact decimals, as the evaluator does", () => {
  const amount = field(
    "amount",
    "Amount",
    {
      kind: "number",
      defaultValue: null,
      min: 0.1,
      max: 1,
      step: 0.1,
    },
    true,
  );
  // 0.1 × 3 is 0.30000000000000004 in binary floating point.
  expect(testValueValid(amount, 0.3)).toBe(true);
  expect(testValueValid(amount, 0.35)).toBe(false);
  expect(exampleValues(design([amount]), "orders", context).values).toEqual({
    amount: 0.1,
  });
});

for (const row of [
  {
    name: "Text is cut to its length limit",
    config: { kind: "text", defaultValue: "", maxLength: 4 } as const,
    value: "Exam",
  },
  {
    name: "a Text default of an empty string counts as no default",
    config: { kind: "text", defaultValue: "" } as const,
    value: "Example customer",
  },
  {
    name: "Email under 13 characters is the shortest accepted address",
    config: { kind: "email", defaultValue: "", maxLength: 12 } as const,
    value: "a@b.c",
  },
  {
    name: "Web link under 19 characters",
    config: { kind: "url", defaultValue: "", maxLength: 18 } as const,
    value: "http://a.io",
  },
  {
    name: "Web link under 11 characters",
    config: { kind: "url", defaultValue: "", maxLength: 10 } as const,
    value: "http://a",
  },
  {
    name: "a default wins",
    config: { kind: "email", defaultValue: "ops@harbor.test" } as const,
    value: "ops@harbor.test",
  },
]) {
  test(`text example: ${row.name}`, { tag: "@UX-C24" }, () => {
    const customer = field("customer", "Customer", row.config, true);
    expect(
      exampleValues(design([customer]), "orders", context).values.customer,
    ).toBe(row.value);
  });
}

test(
  "a User field with no default takes the signed-in administrator",
  { tag: "@UX-C25" },
  () => {
    const owner = field("owner", "Owner", { kind: "user" }, true);
    expect(exampleValues(design([owner]), "orders", context)).toEqual({
      values: { owner: ADMINISTRATOR_ID },
      unfillable: [],
    });
  },
);

test("a required field whose settings allow no value is named, and only it", () => {
  const fields = [
    field(
      "stage",
      "Stage",
      {
        kind: "select",
        defaultValue: null,
        options: [],
      },
      true,
    ),
    field(
      "score",
      "Score",
      {
        kind: "number",
        defaultValue: null,
        min: 5,
        max: 3,
      },
      true,
    ),
    field(
      "contact",
      "Contact",
      {
        kind: "email",
        defaultValue: "",
        maxLength: 4,
      },
      true,
    ),
    // Not required: no value is a valid value.
    field("note", "Note", { kind: "select", defaultValue: null, options: [] }),
    field("title", "Title", { kind: "text", defaultValue: "" }, true),
  ];
  expect(exampleValues(design(fields), "orders", context)).toEqual({
    values: {
      stage: null,
      score: null,
      contact: null,
      note: null,
      title: "Example title",
    },
    unfillable: [
      { fieldId: "stage", name: "Stage" },
      { fieldId: "score", name: "Score" },
      { fieldId: "contact", name: "Contact" },
    ],
  });
});

test("a value a relationship carries fits the target field too", () => {
  const source = [
    field("name", "Customer name", { kind: "text", defaultValue: "" }, true),
    field(
      "status",
      "Status",
      {
        kind: "select",
        defaultValue: null,
        options: [
          { id: "open", label: "Open" },
          { id: "review", label: "Review" },
        ],
      },
      true,
    ),
    field("amount", "Amount", { kind: "number", defaultValue: null }, true),
  ];
  const target = [
    field("short-name", "Name", {
      kind: "text",
      defaultValue: "",
      maxLength: 6,
    }),
    field("state", "State", {
      kind: "select",
      defaultValue: null,
      options: [{ id: "state-review", label: "Review" }],
    }),
    field("total", "Total", { kind: "number", defaultValue: null, min: 10 }),
  ];
  const linked = design(source, {
    modules: [
      {
        id: "customers",
        departmentId: "sales",
        name: "Customers",
        closed: false,
        titleFieldId: null,
        fields: target,
      },
    ],
    relationships: [
      {
        id: "orders-customers",
        name: "Orders to Customers",
        sourceModuleId: "orders",
        targetModuleId: "customers",
        cardinality: "one-to-many",
        fieldMappings: [
          { sourceFieldId: "name", targetFieldId: "short-name" },
          { sourceFieldId: "status", targetFieldId: "state" },
          { sourceFieldId: "amount", targetFieldId: "total" },
        ],
      },
    ],
  });
  expect(exampleValues(linked, "orders", context)).toEqual({
    values: {
      name: "Exampl",
      // "Open" has no matching label in State; "Review" does.
      status: "review",
      amount: 10,
    },
    unfillable: [],
  });
});
