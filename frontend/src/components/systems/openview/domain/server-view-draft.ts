import type {
  OpenViewDataSourceField,
  OpenViewQueryDefinition,
  OpenViewQueryFieldType,
  OpenViewSavedView,
} from "../adapters/views-api";

const SEARCHABLE_TYPES = new Set<OpenViewQueryFieldType>([
  "text",
  "long_text",
  "email",
  "url",
  "select",
]);
export const EMPTY_OPERATORS = new Set([
  "empty",
  "not_empty",
  "blank",
  "not_blank",
]);
export const OPERATOR_LABELS: Record<OpenViewFilterOperator, string> = {
  eq: "is",
  neq: "is not",
  lt: "is before / less than",
  lte: "is on or before / at most",
  gt: "is after / greater than",
  gte: "is on or after / at least",
  contains: "contains",
  prefix: "starts with",
  suffix: "ends with",
  in: "is one of",
  // DR-9.3: one "no value" pair. `blank` and `not_blank` back it; a saved
  // `empty` or `not_empty` reads apart where its result differs.
  empty: "is empty",
  not_empty: "is not empty",
  blank: "is empty",
  not_blank: "is not empty",
};

export type SavedDraft = {
  name: string;
  definition: OpenViewQueryDefinition;
  presentation: OpenViewSavedView["presentation"];
};
export type OpenViewFilterOperator =
  OpenViewQueryDefinition["filters"][number]["operator"];
export function emptyDefinition(
  fields: readonly OpenViewDataSourceField[],
): OpenViewQueryDefinition {
  const columns = fields.slice(0, 100).map(({ id, type }) => ({
    fieldId: id,
    expectedType: type,
  }));
  return {
    version: 1,
    logic: "and",
    columns,
    filters: [],
    sort: [],
    deleted: "exclude",
    search: null,
    searchFields: fields
      .filter((field) => SEARCHABLE_TYPES.has(field.type))
      .slice(0, 100)
      .map(({ id, type }) => ({ fieldId: id, expectedType: type })),
  };
}

export function emptyPresentation(
  fields: readonly OpenViewDataSourceField[],
): OpenViewSavedView["presentation"] {
  const columns = fields.slice(0, 8).map((field) => field.id);
  return {
    version: 1,
    layout: "table",
    columnFieldIds: columns,
    pinnedFieldIds: columns.slice(0, 1),
    density: "comfortable",
    wrap: false,
    cardSize: "comfortable",
    primaryFieldId: columns[0] ?? null,
    secondaryFieldId: columns[1] ?? null,
    groupByFieldId: null,
  };
}

export function draftForView(view: OpenViewSavedView): SavedDraft {
  return {
    name: view.name,
    definition: view.definition,
    presentation: view.presentation,
  };
}

export function upsertSavedView(
  views: OpenViewSavedView[],
  view: OpenViewSavedView,
): OpenViewSavedView[] {
  return [...views.filter((item) => item.id !== view.id), view];
}

export function duplicateViewName(
  name: string,
  views: readonly OpenViewSavedView[],
): string {
  const nameCharacters = Array.from(name.trim() || "View");
  const existingNames = new Set(views.map((view) => view.name.toLowerCase()));
  for (let copyNumber = 1; ; copyNumber += 1) {
    const suffix = copyNumber === 1 ? " (copy)" : ` (copy ${copyNumber})`;
    let base = "";
    for (const character of nameCharacters) {
      if (base.length + character.length > 200 - suffix.length) break;
      base += character;
    }
    const candidate = `${base}${suffix}`;
    if (!existingNames.has(candidate.toLowerCase())) return candidate;
  }
}

export function changedSavedViewFields(
  base: OpenViewSavedView,
  latest: OpenViewSavedView,
): string[] {
  const changed: string[] = [];
  if (base.name !== latest.name) changed.push("Name");
  if (base.isDefault !== latest.isDefault) changed.push("Default view");
  if (JSON.stringify(base.definition) !== JSON.stringify(latest.definition))
    changed.push("Query, filters, or sort");
  if (
    base.presentation.layout !== latest.presentation.layout ||
    JSON.stringify(base.presentation.columnFieldIds) !==
      JSON.stringify(latest.presentation.columnFieldIds)
  )
    changed.push("Layout or columns");
  if (
    JSON.stringify(base.presentation) !== JSON.stringify(latest.presentation) &&
    !changed.includes("Layout or columns")
  )
    changed.push("Other presentation settings");
  return changed.length
    ? changed
    : ["Revision changed without visible field changes"];
}

/**
 * DR-9.3: a condition's label. A saved `empty` or `not_empty` on a text-like
 * field reads "(exact)": it matches no value but keeps a value of only
 * spaces, where the offered pair counts that as empty. Elsewhere the result is
 * the same, so the label is too.
 */
/** DR-9.3: the text fields, where a value of only spaces counts as empty. */
const TEXT_FIELD_TYPES = new Set<OpenViewQueryFieldType>([
  "text",
  "long_text",
  "email",
  "url",
]);

export function readsExact(
  operator: OpenViewFilterOperator,
  type: OpenViewQueryFieldType,
): boolean {
  return (
    (operator === "empty" || operator === "not_empty") &&
    TEXT_FIELD_TYPES.has(type)
  );
}

export function operatorLabel(
  operator: OpenViewFilterOperator,
  type: OpenViewQueryFieldType,
): string {
  return readsExact(operator, type)
    ? `${OPERATOR_LABELS[operator]} (exact)`
    : OPERATOR_LABELS[operator];
}

/**
 * The conditions a field offers. The "no value" pair is `blank` and
 * `not_blank` (DR-9.3); a saved `empty` or `not_empty` (`current`) stays
 * listed so the condition keeps its stored operator.
 */
export function operatorChoices(
  type: OpenViewQueryFieldType,
  current?: OpenViewFilterOperator,
): OpenViewFilterOperator[] {
  const kept: OpenViewFilterOperator[] =
    current === "empty" || current === "not_empty" ? [current] : [];
  const common: OpenViewFilterOperator[] = [
    "eq",
    "neq",
    "blank",
    "not_blank",
    ...kept,
  ];
  if (SEARCHABLE_TYPES.has(type)) {
    return type === "select"
      ? [...common, "contains", "in"]
      : [...common, "contains", "prefix", "suffix"];
  }
  if (type === "user") return common;
  if (["number", "decimal", "int", "date", "datetime"].includes(type))
    return [...common, "lt", "lte", "gt", "gte"];
  return common;
}

export function isFilterOperator(
  value: string,
  type: OpenViewQueryFieldType,
): value is OpenViewFilterOperator {
  return operatorChoices(type).some((operator) => operator === value);
}

export function filterValueForType(
  type: OpenViewQueryFieldType,
  value: string,
): string | number | boolean | null {
  if (type === "boolean") return value === "true";
  if (type === "decimal") return value;
  if (type === "int") {
    if (value === "") return value;
    const raw = value.trim();
    if (!/^[+-]?\d+$/.test(raw)) return value;
    const significantDigits = raw.replace(/^[+-]?0*/, "");
    if (significantDigits.length > 16) return value;
    const integerValue = Number(raw);
    return Number.isSafeInteger(integerValue) ? integerValue : value;
  }
  if (type === "number") {
    if (value === "") return value;
    const numberValue = Number(value);
    return Number.isFinite(numberValue) ? numberValue : value;
  }
  return value;
}

export function membershipFilterValues(
  value: OpenViewQueryDefinition["filters"][number]["value"],
): string[] {
  if (Array.isArray(value))
    return value.filter((item): item is string => typeof item === "string");
  if (typeof value !== "string") return [];
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function normalizeFilterValues(
  definition: OpenViewQueryDefinition,
): OpenViewQueryDefinition {
  return {
    ...definition,
    filters: definition.filters.map((filter) =>
      filter.operator === "in"
        ? { ...filter, value: membershipFilterValues(filter.value) }
        : filter,
    ),
  };
}

export function filterInputValue(
  filter: OpenViewQueryDefinition["filters"][number],
): string {
  if (filter.operator === "in" && Array.isArray(filter.value))
    return membershipFilterValues(filter.value).join(", ");
  return String(filter.value ?? "");
}

export function hasUnsafeIntegerFilter(
  filter: OpenViewQueryDefinition["filters"][number],
): boolean {
  if (filter.expectedType !== "int") return false;
  const value = filter.value;
  if (value === null || value === undefined || value === "") return false;
  return typeof value !== "number" || !Number.isSafeInteger(value);
}

export function isFilterReady(
  filter: OpenViewQueryDefinition["filters"][number],
): boolean {
  if (EMPTY_OPERATORS.has(filter.operator)) return true;
  if (filter.operator === "in")
    return membershipFilterValues(filter.value).length > 0;
  if (Array.isArray(filter.value)) return false;
  return (
    filter.value !== null && filter.value !== undefined && filter.value !== ""
  );
}

/**
 * A condition is applied when it is complete and holds no unsafe integer.
 * Only applied conditions reach a records read, a count, or an export; the
 * others stay in the draft until they are finished (DR-3.1).
 */
export function isFilterApplied(
  filter: OpenViewQueryDefinition["filters"][number],
): boolean {
  return isFilterReady(filter) && !hasUnsafeIntegerFilter(filter);
}

/** The definition with only its applied conditions (DR-3.1). */
export function appliedDefinition(
  definition: OpenViewQueryDefinition,
): OpenViewQueryDefinition {
  return {
    ...definition,
    filters: definition.filters.filter(isFilterApplied),
  };
}
