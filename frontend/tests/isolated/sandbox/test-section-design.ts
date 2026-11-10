import type {
  SandboxComparisonOperator,
  SandboxDocumentDesign,
  SandboxDocumentField,
  SandboxTrigger,
  SandboxTriggerCondition,
  SandboxTriggerEvent,
} from "../../../src/components/systems/sandbox/domain/document";
import type {
  FieldConfig,
  FieldTypeName,
} from "../../../src/components/systems/sandbox/domain/model";

// Builders for the Test section specs (reading, example values, Try this
// trigger): fields from their settings, triggers from their parts, and the
// Orders design that the UX spec's criteria name.

const typeNames: Record<FieldConfig["kind"], FieldTypeName> = {
  text: "Text",
  "long-text": "Long text",
  email: "Email",
  url: "URL",
  number: "Number",
  integer: "Integer",
  date: "Date",
  datetime: "Date/Time",
  checkbox: "Checkbox",
  select: "Select",
  user: "User",
};

export function field(
  id: string,
  name: string,
  config: FieldConfig,
  required = false,
): SandboxDocumentField {
  return {
    id,
    name,
    type: typeNames[config.kind],
    required,
    closed: false,
    config,
  };
}

export function condition(
  id: string,
  fieldId: string,
  operator: SandboxComparisonOperator,
  value: SandboxTriggerCondition["value"],
  moduleId = "orders",
): SandboxTriggerCondition {
  return { id, field: { moduleId, fieldId }, operator, value };
}

export function trigger(
  id: string,
  name: string,
  event: SandboxTriggerEvent,
  {
    enabled = true,
    priority = 1,
    operator = "all",
    conditions = [],
    sets = [],
  }: {
    enabled?: boolean;
    priority?: number;
    operator?: "all" | "any";
    conditions?: SandboxTriggerCondition[];
    /** Field ids of the trigger's module that it sets to a literal. */
    sets?: Array<[string, string | number | boolean | null]>;
  } = {},
): SandboxTrigger {
  const moduleId = event.moduleId ?? "orders";
  return {
    id,
    name,
    enabled,
    priority,
    trigger: event,
    conditionGroup: { operator, conditions },
    actions: sets.map(([fieldId, value], index) => ({
      id: `${id}-action-${index}`,
      kind: "set-field" as const,
      target: { moduleId, fieldId },
      value: { kind: "literal" as const, value },
    })),
  };
}

export const literal = (value: string | number | boolean | null) => ({
  kind: "literal" as const,
  value,
});

/** Orders (Sales) with Amount 1 and Status Open as their examples. */
export function ordersDesign(
  extraFields: SandboxDocumentField[] = [],
): SandboxDocumentDesign {
  return {
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
        titleFieldId: "amount",
        fields: [
          field("amount", "Amount", { kind: "number", defaultValue: 1 }, true),
          field(
            "status",
            "Status",
            {
              kind: "select",
              defaultValue: "open",
              options: [
                { id: "open", label: "Open" },
                { id: "review", label: "Review" },
              ],
            },
            true,
          ),
          field("paid", "Paid", { kind: "checkbox", defaultValue: false }),
          field("owner", "Owner", { kind: "user" }),
          ...extraFields,
        ],
      },
      {
        id: "customers",
        departmentId: "sales",
        name: "Customers",
        closed: false,
        titleFieldId: null,
        fields: [],
      },
      {
        id: "invoices",
        departmentId: "finance",
        name: "Invoices",
        closed: false,
        titleFieldId: null,
        fields: [],
      },
    ],
    relationships: [],
    layout: {},
  };
}

export const ADMINISTRATOR_ID = "0b6a1f6e-3c1d-4d55-9a1e-2f1b7c9d8e01";
export const context = {
  now: new Date(2026, 10, 10, 14, 37),
  administratorId: ADMINISTRATOR_ID,
};
