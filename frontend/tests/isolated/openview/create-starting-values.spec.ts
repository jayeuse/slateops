import { expect, test } from "@playwright/test";

import type {
  OpenViewDataSourceField,
  OpenViewQueryDefinition,
} from "../../../src/components/systems/openview/adapters/views-api";
import { createStartingValues } from "../../../src/components/systems/openview/domain/create-starting-values";

// Candidate 2 of docs/specs/subtle-interactions.md: which applied conditions
// give New record its starting values. The page journey is owned by
// tests/http/openview-create-flow.spec.ts.

const moduleId = "00000000-0000-4000-8000-000000000b01";
const nameId = "00000000-0000-4000-8000-000000000b11";
const statusId = "00000000-0000-4000-8000-000000000b12";
const paidId = "00000000-0000-4000-8000-000000000b13";
const ownerId = "00000000-0000-4000-8000-000000000b14";
const notInFormId = "00000000-0000-4000-8000-000000000b15";
const meId = "00000000-0000-4000-8000-000000000b21";
const otherPersonId = "00000000-0000-4000-8000-000000000b22";

function field(
  id: string,
  name: string,
  type: OpenViewDataSourceField["type"],
  config: Record<string, unknown> = {},
): OpenViewDataSourceField {
  return {
    id,
    moduleId,
    name,
    type,
    required: false,
    position: 0,
    config,
  };
}

const fields = [
  field(nameId, "Name", "text"),
  field(statusId, "Status", "select", {
    options: [
      { id: "active", label: "Active" },
      { id: "former", label: "Former" },
    ],
  }),
  field(paidId, "Paid", "boolean", { defaultValue: true }),
  field(ownerId, "Owner", "user"),
];

type Filter = OpenViewQueryDefinition["filters"][number];
const is = (
  fieldId: string,
  expectedType: Filter["expectedType"],
  value: Filter["value"],
): Filter => ({ fieldId, expectedType, operator: "eq", value });
const statusIs = (value: string) => is(statusId, "select", value);

const starting = (
  filters: Filter[],
  logic: "and" | "or" = "and",
  identityId: string | null = meId,
) => createStartingValues(fields, { logic, filters }, identityId);

test("SI-C2.1: each applied 'is' condition on a Choice list or Checkbox field starts that field; the other fields keep their defaults", () => {
  expect(
    starting([
      statusIs("former"),
      // A Checkbox "is off" starts the field off over its default of on.
      is(paidId, "boolean", false),
      // A text condition gives no value: only Choice, Checkbox, and User.
      is(nameId, "text", "Ana"),
    ]),
  ).toEqual({ [statusId]: "former", [paidId]: false });
  expect(starting([])).toEqual({});
});

test("SI-C2.2: a User field starts with the signed-in person only", () => {
  expect(starting([is(ownerId, "user", meId)])).toEqual({ [ownerId]: meId });
  // Another person: the field starts empty, so no assignment goes out unseen.
  expect(starting([is(ownerId, "user", otherPersonId)])).toEqual({});
  // The signed-in person is not known yet.
  expect(starting([is(ownerId, "user", meId)], "and", null)).toEqual({});
});

test("SI-C2.3: Any condition, an incomplete or other condition, a field outside the form, and a removed option give no starting value", () => {
  const cases: { label: string; filters: Filter[]; logic?: "or" }[] = [
    {
      label: "Any condition with two conditions",
      filters: [statusIs("former"), is(paidId, "boolean", true)],
      logic: "or",
    },
    { label: "an incomplete condition", filters: [statusIs("")] },
    {
      label: "two conditions on the field",
      filters: [statusIs("former"), statusIs("active")],
    },
    {
      label: "another operator",
      filters: [{ ...statusIs("former"), operator: "neq" }],
    },
    {
      label: "a field that is not in the form",
      filters: [is(notInFormId, "select", "former")],
    },
    { label: "an option that was removed", filters: [statusIs("prospect")] },
  ];
  for (const { label, filters, logic } of cases)
    expect(starting(filters, logic), label).toEqual({});
  // SI-0.1: with exactly one condition, "Any condition" still reads it.
  expect(starting([statusIs("former")], "or")).toEqual({
    [statusId]: "former",
  });
});
