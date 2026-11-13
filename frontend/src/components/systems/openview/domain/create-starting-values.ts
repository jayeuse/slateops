import type {
  OpenViewDataSourceField,
  OpenViewQueryDefinition,
} from "../adapters/views-api";
import { selectOptions, type RecordFormValues } from "./record-form";
import { isFilterApplied } from "./server-view-draft";

// Candidate 2 of docs/specs/subtle-interactions.md: New record starts with
// the values of the applied conditions. Only an applied condition "is <one
// value>" on a Choice list, Checkbox, or User field of the form gives its
// field a starting value; everything else keeps the field's default.

/**
 * The starting values that the applied conditions give (SI-2.1 to SI-2.3,
 * DR-SI-2.1 to DR-SI-2.3). Only fields with a starting value are in the
 * result; they go over `initialFormValues`, so the others keep their
 * defaults.
 *
 * - SI-0.1: with "Any condition", only a single applied condition counts.
 * - DR-SI-2.2: the field has exactly one applied condition, and it is "is".
 * - A Choice value must still be an option.
 * - DR-SI-2.3: a User value only when it is the signed-in person.
 */
export function createStartingValues(
  fields: readonly OpenViewDataSourceField[],
  definition: Pick<OpenViewQueryDefinition, "logic" | "filters">,
  identityId: string | null,
): RecordFormValues {
  const applied = definition.filters.filter(isFilterApplied);
  if (definition.logic === "or" && applied.length > 1) return {};
  const values: RecordFormValues = {};
  for (const field of fields) {
    const onField = applied.filter((filter) => filter.fieldId === field.id);
    if (onField.length !== 1) continue;
    const [condition] = onField;
    if (condition.operator !== "eq" || condition.expectedType !== field.type)
      continue;
    const value = condition.value;
    if (field.type === "boolean" && typeof value === "boolean")
      values[field.id] = value;
    else if (
      field.type === "select" &&
      typeof value === "string" &&
      selectOptions(field).some((option) => option.id === value)
    )
      values[field.id] = value;
    else if (
      field.type === "user" &&
      typeof value === "string" &&
      identityId !== null &&
      value === identityId
    )
      values[field.id] = value;
  }
  return values;
}
