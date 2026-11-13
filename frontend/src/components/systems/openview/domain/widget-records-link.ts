import type {
  OpenViewDataSourceField,
  OpenViewQueryDefinition,
  OpenViewQueryFieldReference,
} from "../adapters/views-api";
import { selectOptions } from "./record-form";
import { isFilterApplied } from "./server-view-draft";
import { encodeTemporaryDefinition } from "./temporary-view";

// Candidate 6 of docs/specs/subtle-interactions.md: a dashboard figure or
// table group row links to exactly the records it counts (SI-6.4). The link
// carries the widget's conditions, its group's condition and its date window
// as temporary changes of the module page. When any part cannot be carried
// exactly, there is no link: a link never opens a list whose count differs
// from its figure (DR-SI-6.6).

type Filter = OpenViewQueryDefinition["filters"][number];

export type WidgetLinkWindow = {
  dateField: OpenViewQueryFieldReference;
  fromDate: string;
  toDate: string;
};

export type WidgetLinkInput = {
  definition: OpenViewQueryDefinition;
  window: WidgetLinkWindow | null;
  /** The module's fields this person can read. */
  fields: readonly OpenViewDataSourceField[];
  /** The workspace timezone (not the person's display zone); null until read. */
  timezone: string | null;
};

export type WidgetLinkGroup = {
  dimension: OpenViewQueryFieldReference;
  /** The server's group key; null is the group of records with no value. */
  key: string | null;
};

/** The server's `date.max`: a window with this end has no upper bound. */
const OPEN_ENDED = "9999-12-31";
/** The module page keeps at most this many conditions (`queryDefinitionSchema`). */
const MAX_CONDITIONS = 10;
/** The longest condition value the module page keeps (`scalarSchema`). */
const MAX_VALUE_LENGTH = 4000;
/** Table widgets group only by these types (`chart-query.ts`, DR-SI-6.2). */
const GROUP_TYPES = new Set([
  "text",
  "long_text",
  "email",
  "url",
  "select",
  "user",
  "boolean",
]);
const DAY = /^(\d{4})-(\d{2})-(\d{2})$/;
const HOUR_MS = 3_600_000;

function readable(
  reference: OpenViewQueryFieldReference,
  fields: readonly OpenViewDataSourceField[],
): boolean {
  return fields.some(
    (field) =>
      field.id === reference.fieldId && field.type === reference.expectedType,
  );
}

function dayStart(day: string): number | null {
  const match = DAY.exec(day);
  if (!match) return null;
  const value = Date.UTC(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3]),
  );
  return new Date(value).toISOString().slice(0, 10) === day ? value : null;
}

function nextDay(day: string): string | null {
  const start = dayStart(day);
  return start === null
    ? null
    : new Date(start + 24 * HOUR_MS).toISOString().slice(0, 10);
}

/** The zone's offset from UTC at an instant, in whole seconds. */
function offsetSeconds(format: Intl.DateTimeFormat, instant: number): number {
  const parts = Object.fromEntries(
    format
      .formatToParts(new Date(instant))
      .map((part) => [part.type, part.value]),
  );
  const wall = Date.UTC(
    Number(parts.year),
    Number(parts.month) - 1,
    Number(parts.day),
    Number(parts.hour) % 24,
    Number(parts.minute),
    Number(parts.second),
  );
  return Math.round((wall - Math.floor(instant / 1000) * 1000) / 1000);
}

/**
 * Local midnight at the start of `day` in `timezone`, as ISO text with its
 * offset. It matches the server's `datetime.combine(day, time.min,
 * tzinfo=ZoneInfo(zone))` (fold=0): where a clock change skips or repeats
 * midnight, the offset before the change applies.
 */
export function zonedMidnight(day: string, timezone: string): string | null {
  const wall = dayStart(day);
  if (wall === null) return null;
  let format: Intl.DateTimeFormat;
  try {
    format = new Intl.DateTimeFormat("en-US", {
      timeZone: timezone,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return null;
  }
  // Clock changes are months apart, so the offsets a day either side are the
  // ones before and after any change at this midnight.
  const before = offsetSeconds(format, wall - 30 * HOUR_MS);
  const after = offsetSeconds(format, wall + 30 * HOUR_MS);
  const holds = (offset: number) =>
    offsetSeconds(format, wall - offset * 1000) === offset;
  // A skipped midnight (neither holds) and a repeated one (both hold) take
  // the earlier offset, as fold=0 does.
  const offset = !holds(before) && holds(after) ? after : before;
  if (offset % 60 !== 0) return null;
  const minutes = Math.abs(offset) / 60;
  const sign = offset < 0 ? "-" : "+";
  const hours = String(Math.floor(minutes / 60)).padStart(2, "0");
  return `${day}T00:00:00${sign}${hours}:${String(minutes % 60).padStart(2, "0")}`;
}

/**
 * The window as conditions on its field, exactly as the server applies it
 * (`aggregation.py`, `_date_window_predicates`): a Date field from <from>
 * through <to>; a Date and time field from local midnight at <from> to the
 * local midnight after <to>, in the workspace timezone.
 */
export function windowConditions(
  window: WidgetLinkWindow,
  fields: readonly OpenViewDataSourceField[],
  timezone: string | null,
): Filter[] | null {
  const { dateField, fromDate, toDate } = window;
  if (!readable(dateField, fields)) return null;
  if (dayStart(fromDate) === null || dayStart(toDate) === null) return null;
  const openEnded = toDate === OPEN_ENDED;
  if (dateField.expectedType === "date")
    return [
      { ...dateField, operator: "gte", value: fromDate },
      ...(openEnded
        ? []
        : [{ ...dateField, operator: "lte" as const, value: toDate }]),
    ];
  if (dateField.expectedType !== "datetime" || !timezone) return null;
  const from = zonedMidnight(fromDate, timezone);
  if (!from) return null;
  if (openEnded) return [{ ...dateField, operator: "gte", value: from }];
  const after = nextDay(toDate);
  const until = after ? zonedMidnight(after, timezone) : null;
  if (!until) return null;
  return [
    { ...dateField, operator: "gte", value: from },
    { ...dateField, operator: "lt", value: until },
  ];
}

/**
 * The condition of one table group: "is <key>", or the stored `empty` for
 * the group with no value (SQL NULL only; `blank` would also count blank
 * text). Null when the key cannot be stated as a condition that the module
 * page keeps.
 */
export function groupCondition(
  group: WidgetLinkGroup,
  fields: readonly OpenViewDataSourceField[],
): Filter | null {
  const { dimension, key } = group;
  const field = fields.find(
    (item) =>
      item.id === dimension.fieldId && item.type === dimension.expectedType,
  );
  if (!field || !GROUP_TYPES.has(field.type)) return null;
  if (key === null) return { ...dimension, operator: "empty", value: null };
  if (field.type === "boolean")
    return key === "true" || key === "false"
      ? { ...dimension, operator: "eq", value: key === "true" }
      : null;
  if (
    field.type === "select" &&
    !selectOptions(field).some((option) => option.id === key)
  )
    return null;
  // An empty value is not an applied condition on the module page.
  if (key === "" || key.length > MAX_VALUE_LENGTH) return null;
  return { ...dimension, operator: "eq", value: key };
}

/**
 * The temporary definition changes that open exactly the counted records,
 * or null. They replace the module's default view's conditions and carry the
 * widget's deleted and search settings, which the count also used. Under
 * SI-0.1 a link that adds a condition needs "All conditions" or at most one
 * condition, and then uses "All conditions" (DR-SI-6.3).
 */
export function widgetLinkDefinition(
  input: WidgetLinkInput,
  group?: WidgetLinkGroup,
): Partial<OpenViewQueryDefinition> | null {
  const { definition, fields } = input;
  if (!definition.filters.every(isFilterApplied)) return null;
  if (!definition.filters.every((filter) => readable(filter, fields)))
    return null;
  const added: Filter[] = [];
  if (input.window) {
    const window = windowConditions(input.window, fields, input.timezone);
    if (!window) return null;
    added.push(...window);
  }
  if (group) {
    const condition = groupCondition(group, fields);
    if (!condition) return null;
    added.push(condition);
  }
  if (
    added.length &&
    definition.logic === "or" &&
    definition.filters.length > 1
  )
    return null;
  const filters = [...definition.filters, ...added];
  if (filters.length > MAX_CONDITIONS) return null;
  return {
    logic: added.length ? "and" : definition.logic,
    filters,
    deleted: definition.deleted,
    search: definition.search,
    ...(definition.search ? { searchFields: definition.searchFields } : {}),
  };
}

/** The module page's `changes` value for the link, or null for no link. */
export function widgetLinkChanges(
  input: WidgetLinkInput,
  group?: WidgetLinkGroup,
): string | null {
  const changes = widgetLinkDefinition(input, group);
  return changes ? encodeTemporaryDefinition(changes) : null;
}
