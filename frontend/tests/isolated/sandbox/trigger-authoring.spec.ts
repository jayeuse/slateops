import { expect, test } from "@playwright/test";

import type {
  SandboxDocumentDesign,
  SandboxDocumentField,
  SandboxTrigger,
} from "../../../src/components/systems/sandbox/domain/document";
import {
  changeTriggerEvent,
  changeTriggerModule,
  fieldChoices,
  moduleChoiceGroups,
  operatorFits,
  operatorsForField,
  triggerDraftGaps,
} from "../../../src/components/systems/sandbox/domain/trigger-draft";
import {
  addTriggerAction,
  addTriggerCondition,
  defaultTrigger,
  newTriggerFromBuild,
  TRIGGER_LIMIT,
} from "../../../src/components/systems/sandbox/domain/trigger-rules";
import { triggerSentence } from "../../../src/components/systems/sandbox/components/trigger-sentence";
import { structureRegionModel } from "../../../src/components/systems/sandbox/components/trigger-structure-region";
import {
  documentSelectField,
  documentTextField,
} from "../../helpers/sandbox-fixtures";

// Writing triggers with the structure in view (docs/specs/sandbox-ux-redesign.md,
// TRIG-1 to TRIG-7): the structure region's content, pickers grouped and
// typed, operators by field type, no silent choice or reset, the
// whole-trigger sentence, and Then offering only actions that publish.

function field(
  id: string,
  name: string,
  config: SandboxDocumentField["config"],
  type: SandboxDocumentField["type"],
  required = false,
): SandboxDocumentField {
  return { id, name, type, required, closed: false, config };
}

const design: SandboxDocumentDesign = {
  departments: [
    { id: "sales", name: "Sales", closed: false },
    { id: "finance", name: "Finance", closed: false },
  ],
  modules: [
    {
      id: "orders",
      departmentId: "sales",
      name: "Orders",
      closed: false,
      titleFieldId: null,
      fields: [
        documentTextField({
          id: "number",
          name: "Order number",
          required: true,
        }),
        field(
          "amount",
          "Amount",
          { kind: "number", defaultValue: null },
          "Number",
        ),
        documentSelectField({
          id: "status",
          name: "Status",
          defaultValue: null,
          options: [
            { id: "status-open", label: "Open" },
            { id: "status-review", label: "Review" },
          ],
        }),
        field(
          "paid",
          "Paid",
          { kind: "checkbox", defaultValue: false },
          "Checkbox",
        ),
        field(
          "due",
          "Due",
          { kind: "datetime", defaultValue: null },
          "Date/Time",
        ),
      ],
    },
    {
      id: "customers",
      departmentId: "sales",
      name: "Customers",
      closed: false,
      titleFieldId: null,
      fields: [documentTextField({ id: "name", name: "Name" })],
    },
    {
      id: "invoices",
      departmentId: "finance",
      name: "Invoices",
      closed: false,
      titleFieldId: null,
      fields: [
        field(
          "total",
          "Total",
          { kind: "integer", defaultValue: null },
          "Integer",
        ),
        field("issued", "Issued", { kind: "date", defaultValue: null }, "Date"),
      ],
    },
  ],
  relationships: [
    {
      id: "orders-customers",
      name: "Customer",
      sourceModuleId: "orders",
      targetModuleId: "customers",
      cardinality: "one-to-many",
      fieldMappings: [],
    },
    {
      id: "invoices-orders",
      name: "Order",
      sourceModuleId: "invoices",
      targetModuleId: "orders",
      cardinality: "one-to-many",
      fieldMappings: [],
    },
  ],
  layout: {},
};

const fieldsOf = (moduleId: string) =>
  design.modules.find((item) => item.id === moduleId)!.fields;
const fieldOf = (moduleId: string, fieldId: string) =>
  fieldsOf(moduleId).find((item) => item.id === fieldId)!;

/** "When a record is added to Orders, if Amount is at least 100, set Status to Review." */
function largeOrders(): SandboxTrigger {
  return {
    id: "large-orders",
    name: "Flag large orders",
    enabled: true,
    priority: 1,
    trigger: { kind: "record-created", moduleId: "orders" },
    conditionGroup: {
      operator: "all",
      conditions: [
        {
          id: "condition-1",
          field: { moduleId: "orders", fieldId: "amount" },
          operator: ">=",
          value: { kind: "literal", value: 100 },
        },
      ],
    },
    actions: [
      {
        id: "action-1",
        kind: "set-field",
        target: { moduleId: "orders", fieldId: "status" },
        value: { kind: "literal", value: "status-review" },
      },
    ],
  };
}

/** The sentence as text, with each missing part in brackets. */
function sentenceText(recordTrigger: SandboxTrigger): string {
  return triggerSentence(recordTrigger, design)
    .map((part) => (part.kind === "missing" ? `[${part.text}]` : part.text))
    .join("");
}

test(
  "the structure region shows the trigger module's department, typed fields and links both ways",
  { tag: "@UX-C14" },
  () => {
    expect(structureRegionModel(design, "orders")).toEqual({
      kind: "module",
      moduleName: "Orders",
      departmentName: "Sales",
      departmentIndex: 0,
      fields: [
        { id: "number", name: "Order number", type: "Text", required: true },
        { id: "amount", name: "Amount", type: "Number", required: false },
        { id: "status", name: "Status", type: "Choice list", required: false },
        { id: "paid", name: "Paid", type: "Checkbox", required: false },
        { id: "due", name: "Due", type: "Date and time", required: false },
      ],
      links: [
        {
          id: "orders-customers",
          direction: "out",
          moduleName: "Customers",
          departmentName: "Sales",
          departmentIndex: 0,
        },
        {
          id: "invoices-orders",
          direction: "in",
          moduleName: "Invoices",
          departmentName: "Finance",
          departmentIndex: 1,
        },
      ],
    });
    // With no module chosen, the region lists the whole structure (T2).
    expect(structureRegionModel(design, "")).toEqual({
      kind: "design",
      departments: [
        {
          id: "sales",
          name: "Sales",
          index: 0,
          modules: [
            { id: "orders", name: "Orders" },
            { id: "customers", name: "Customers" },
          ],
        },
        {
          id: "finance",
          name: "Finance",
          index: 1,
          modules: [{ id: "invoices", name: "Invoices" }],
        },
      ],
    });
  },
);

test(
  "module pickers group modules by department and field pickers show each type",
  { tag: "@UX-C15" },
  () => {
    expect(moduleChoiceGroups(design)).toEqual([
      {
        label: "Sales",
        departmentIndex: 0,
        choices: [
          { value: "orders", label: "Orders", meta: "5 fields" },
          { value: "customers", label: "Customers", meta: "1 field" },
        ],
      },
      {
        label: "Finance",
        departmentIndex: 1,
        choices: [{ value: "invoices", label: "Invoices", meta: "2 fields" }],
      },
    ]);
    expect(fieldChoices(fieldsOf("invoices"))).toEqual([
      { value: "total", label: "Total", meta: "Whole number" },
      { value: "issued", label: "Issued", meta: "Date" },
    ]);
  },
);

test(
  "only operators that fit the field type are offered",
  { tag: "@UX-C16" },
  () => {
    const two = ["=", "!="];
    const six = ["=", "!=", ">", ">=", "<", "<="];
    const rows: Array<[string, SandboxDocumentField, string[]]> = [
      ["Checkbox", fieldOf("orders", "paid"), two],
      ["Text", fieldOf("orders", "number"), two],
      ["Choice list", fieldOf("orders", "status"), two],
      ["Number", fieldOf("orders", "amount"), six],
      ["Whole number", fieldOf("invoices", "total"), six],
      ["Date", fieldOf("invoices", "issued"), six],
      ["Date and time", fieldOf("orders", "due"), six],
    ];
    for (const [type, item, operators] of rows)
      expect(operatorsForField(item), type).toEqual(operators);
  },
);

test(
  "a saved operator that does not fit its field stays and is flagged",
  { tag: "@UX-C17" },
  () => {
    const text = fieldOf("orders", "number");
    expect(operatorFits(">", text)).toBe(false);
    expect(operatorFits("!=", text)).toBe(true);
    expect(operatorFits(">", fieldOf("orders", "amount"))).toBe(true);
    // A misfit is not an empty part: Save does not refuse it (OQ-2 a).
    const saved = largeOrders();
    saved.conditionGroup.conditions[0] = {
      ...saved.conditionGroup.conditions[0]!,
      field: { moduleId: "orders", fieldId: "number" },
      operator: ">",
      value: { kind: "literal", value: "M" },
    };
    expect(triggerDraftGaps(saved, design)).toEqual([]);
  },
);

test(
  "changing the event keeps the module and empties the watched field",
  { tag: "@UX-C18" },
  () => {
    const onInvoices: SandboxTrigger = {
      ...largeOrders(),
      trigger: { kind: "record-created", moduleId: "invoices" },
      conditionGroup: { operator: "all", conditions: [] },
      actions: [
        {
          id: "action-1",
          kind: "set-field",
          target: { moduleId: "invoices", fieldId: "total" },
          value: { kind: "literal", value: 1 },
        },
      ],
    };
    const changed = changeTriggerEvent(onInvoices, "field-changed", design);
    expect(changed.trigger).toEqual({
      kind: "field-changed",
      moduleId: "invoices",
      fieldId: "",
    });
    expect(triggerDraftGaps(changed, design)).toEqual([
      { step: "trigger", part: "field", reason: "Choose the field to watch." },
    ]);
    // A threshold needs a number or date field; a text field reads empty.
    const threshold = changeTriggerEvent(
      {
        ...largeOrders(),
        trigger: {
          kind: "field-changed",
          moduleId: "orders",
          fieldId: "number",
        },
      },
      "threshold-crossed",
      design,
    );
    expect(threshold.trigger).toMatchObject({
      kind: "threshold-crossed",
      moduleId: "orders",
      fieldId: "number",
    });
    expect(triggerDraftGaps(threshold, design)).toEqual([
      {
        step: "trigger",
        part: "field",
        reason: "Choose a number or date field.",
      },
    ]);
  },
);

test(
  "changing the module replaces no field; each affected step reads empty with a reason",
  { tag: "@UX-C19" },
  () => {
    const moved = changeTriggerModule(largeOrders(), "customers");
    expect(moved.trigger).toEqual({
      kind: "record-created",
      moduleId: "customers",
    });
    // The rows keep their old references; nothing takes "the first field".
    expect(moved.conditionGroup.conditions[0]!.field).toEqual({
      moduleId: "orders",
      fieldId: "amount",
    });
    expect(triggerDraftGaps(moved, design)).toEqual([
      {
        step: "condition:condition-1",
        part: "field",
        reason: "Not in Customers; choose a field.",
      },
      {
        step: "action:action-1",
        part: "field",
        reason: "Not in Customers; choose a field.",
      },
    ]);
    // Back on Orders, the same rows are whole again.
    expect(
      triggerDraftGaps(changeTriggerModule(moved, "orders"), design),
    ).toEqual([]);
  },
);

test(
  "a new trigger, condition, or action starts empty instead of taking the first module or field",
  { tag: "@UX-C19" },
  () => {
    const created = defaultTrigger(design);
    expect(created.trigger).toEqual({ kind: "record-created", moduleId: "" });
    expect(created.actions).toEqual([]);
    expect(triggerDraftGaps(created, design)).toEqual([
      { step: "trigger", part: "module", reason: "Choose a module." },
      { step: "actions", part: "actions", reason: "Add an action." },
    ]);
    // From a module (TRIG-8 context), only the module is preset.
    const onOrders = defaultTrigger(design, "orders");
    const expanded = addTriggerAction(
      addTriggerCondition(onOrders, design),
      design,
    );
    expect(expanded.conditionGroup.conditions[0]).toMatchObject({
      field: { moduleId: "orders", fieldId: "" },
      value: { kind: "literal", value: null },
    });
    expect(expanded.actions[0]).toMatchObject({
      kind: "set-field",
      target: { moduleId: "orders", fieldId: "" },
      value: { kind: "literal", value: null },
    });
    expect(triggerDraftGaps(expanded, design).map((gap) => gap.reason)).toEqual(
      ["Choose a field.", "Choose a field."],
    );
  },
);

test(
  "UF-C9.1 the whole trigger reads as one sentence that follows each edit",
  { tag: "@UX-C20" },
  () => {
    const recordTrigger = largeOrders();
    expect(sentenceText(recordTrigger)).toBe(
      "When a record is added to Orders, if Amount is at least 100, set Status to Review.",
    );
    recordTrigger.conditionGroup.conditions[0]!.value = {
      kind: "literal",
      value: 2500,
    };
    expect(sentenceText(recordTrigger)).toBe(
      "When a record is added to Orders, if Amount is at least 2,500, set Status to Review.",
    );
    // A removed action reads as missing, never as a default.
    expect(sentenceText({ ...recordTrigger, actions: [] })).toBe(
      "When a record is added to Orders, if Amount is at least 2,500, [no action yet].",
    );
    expect(sentenceText(defaultTrigger(design))).toBe(
      "When a record is added to [a module], [no action yet].",
    );
    expect(
      sentenceText({
        ...recordTrigger,
        trigger: {
          kind: "threshold-crossed",
          moduleId: "orders",
          fieldId: "amount",
          operator: ">=",
          value: { kind: "literal", value: 1000 },
        },
        conditionGroup: {
          operator: "any",
          conditions: [
            {
              id: "a",
              field: { moduleId: "orders", fieldId: "paid" },
              operator: "=",
              value: { kind: "literal", value: true },
            },
            {
              id: "b",
              field: { moduleId: "orders", fieldId: "" },
              operator: "!=",
              value: { kind: "literal", value: null },
            },
          ],
        },
      }),
    ).toBe(
      "When Amount reaches at least 1,000 in Orders, if Paid is Checked or [a field], set Status to Review.",
    );
    expect(
      sentenceText({
        ...recordTrigger,
        trigger: {
          kind: "schedule",
          moduleId: "invoices",
          frequency: "weekly",
          weekday: 1,
          time: "09:00",
        },
        conditionGroup: { operator: "all", conditions: [] },
        actions: [
          {
            id: "x",
            kind: "set-field",
            target: { moduleId: "invoices", fieldId: "total" },
            value: { kind: "literal", value: 0 },
          },
          {
            id: "y",
            kind: "set-field",
            target: { moduleId: "invoices", fieldId: "issued" },
            value: {
              kind: "field-reference",
              moduleId: "invoices",
              fieldId: "issued",
            },
          },
        ],
      }),
    ).toBe(
      "Every Monday at 09:00 in Invoices, set Total to 0 and set Issued to the value of Issued.",
    );
  },
);

test(
  "a step whose field is empty or in another module reads as a missing field, with no stale operator, value or id",
  { tag: ["@UX-C20", "@UX-C19"] },
  () => {
    // Trigger A moved from Orders to Customers: its condition and action
    // still point at Orders' Amount and Status (a Choice list).
    expect(sentenceText(changeTriggerModule(largeOrders(), "customers"))).toBe(
      "When a record is added to Customers, if [a field], set [a field].",
    );
    // A new condition and a new action have no field yet.
    const fresh = addTriggerAction(
      addTriggerCondition(defaultTrigger(design, "orders"), design),
      design,
    );
    expect(sentenceText(fresh)).toBe(
      "When a record is added to Orders, if [a field], set [a field].",
    );
    // A threshold with no fitting field shows no stale limit either.
    expect(
      sentenceText(
        changeTriggerEvent(
          {
            ...largeOrders(),
            trigger: {
              kind: "field-changed",
              moduleId: "orders",
              fieldId: "number",
            },
          },
          "threshold-crossed",
          design,
        ),
      ),
    ).toBe(
      "When [a field] reaches [a value] in Orders, if Amount is at least 100, set Status to Review.",
    );
  },
);

test(
  "before a field is chosen, a condition offers no operator",
  { tag: "@UX-C16" },
  () => {
    expect(operatorsForField(undefined)).toEqual([]);
  },
);

test(
  "Then offers only Set a field on the trigger's own module",
  { tag: "@UX-C21" },
  () => {
    const expanded = addTriggerAction(largeOrders(), design);
    expect(expanded.actions.map((action) => action.kind)).toEqual([
      "set-field",
      "set-field",
    ]);
    expect(expanded.actions[1]).toMatchObject({
      target: { moduleId: "orders", fieldId: "" },
    });
    // With no module chosen, no action can be added yet.
    expect(addTriggerAction(defaultTrigger(design), design).actions).toEqual(
      [],
    );
  },
);

// TRIG-8 (T8-C1): "New trigger" from Build adds nothing while kept edits wait
// for Restore or Discard, while a save is pending, or at the trigger limit,
// as the list's New trigger is then unavailable.
test("New trigger from Build adds a trigger on its module only when the list could", () => {
  const ask = {
    moduleId: "orders" as string | undefined,
    keptWaiting: false,
    pending: false,
    count: 3,
  };
  const rows: Array<[string, Partial<typeof ask>, string | null]> = [
    ["a request with room", {}, "orders"],
    ["no request", { moduleId: undefined }, null],
    ["kept edits wait for Restore or Discard", { keptWaiting: true }, null],
    ["a save is pending", { pending: true }, null],
    ["one below the limit", { count: TRIGGER_LIMIT - 1 }, "orders"],
    ["at the limit", { count: TRIGGER_LIMIT }, null],
  ];
  expect(TRIGGER_LIMIT).toBe(500);
  for (const [name, patch, result] of rows)
    expect(newTriggerFromBuild({ ...ask, ...patch }), name).toBe(result);
});
