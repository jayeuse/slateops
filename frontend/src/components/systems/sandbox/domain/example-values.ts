import { dateTimeInstant, dateValueInRange } from "./date-values";
import type {
  SandboxComparisonOperator,
  SandboxDocumentDesign,
  SandboxDocumentField,
  SandboxDocumentModule,
  SandboxFieldValue,
} from "./document";

// Example values for Test (docs/specs/sandbox-ux-redesign.md TEST-3, N7,
// UXD-11). Every value is valid for its field and for each field that a
// relationship mapping carries it to, so the evaluator raises no
// `value_required`, `value_invalid`, or `relationship_invalid` for a field
// that can have a value. The checks mirror the backend evaluator
// (`backend/app/systems/sandbox/test_runs/evaluator.py` `_value_is_valid`,
// `value_validation.py`, `relationships.py`, `trigger_values.py` `compare`).

/** What the examples depend on outside the draft. */
export type ExampleContext = {
  /** "Today" for Date fields and "now, to the hour" for Date and time. */
  now: Date;
  /** The signed-in administrator, the example for a User field. */
  administratorId: string | null;
};

/* Exact decimals: a step check in binary floating point (0.1 + 0.2) would
   refuse values the backend's Decimal check accepts. */

type Decimal = { digits: bigint; scale: number };

// BigInt() calls, not `0n` literals: the TypeScript target is below ES2020.
const ZERO = BigInt(0);
const TEN = BigInt(10);

function toDecimal(value: number): Decimal {
  const [mantissa, exponentText] = value.toString().toLowerCase().split("e");
  const negative = mantissa.startsWith("-");
  const [whole, fraction = ""] = (
    negative ? mantissa.slice(1) : mantissa
  ).split(".");
  let digits = BigInt(`${whole}${fraction}`);
  let scale = fraction.length - Number(exponentText ?? 0);
  if (scale < 0) {
    digits *= TEN ** BigInt(-scale);
    scale = 0;
  }
  return { digits: negative ? -digits : digits, scale };
}

function scaled(value: Decimal, scale: number): bigint {
  return value.digits * TEN ** BigInt(scale - value.scale);
}

function fromDigits(digits: bigint, scale: number): number {
  const negative = digits < ZERO;
  const text = (negative ? -digits : digits)
    .toString()
    .padStart(scale + 1, "0");
  const whole = text.slice(0, text.length - scale);
  const fraction = scale ? `.${text.slice(text.length - scale)}` : "";
  return Number(`${negative ? "-" : ""}${whole}${fraction}`);
}

/** Whether `value` sits on the step that starts at `origin`, exactly. */
export function onStep(value: number, origin: number, step: number): boolean {
  if (!(step > 0)) return false;
  const parts = [toDecimal(value), toDecimal(origin), toDecimal(step)];
  const scale = Math.max(...parts.map((part) => part.scale));
  const [v, o, s] = parts.map((part) => scaled(part, scale));
  return (v - o) % s === ZERO;
}

/** `origin + count × step`, computed exactly. */
export function stepFrom(origin: number, step: number, count: number): number {
  const parts = [toDecimal(origin), toDecimal(step)];
  const scale = Math.max(...parts.map((part) => part.scale));
  const [o, s] = parts.map((part) => scaled(part, scale));
  return fromDigits(o + BigInt(count) * s, scale);
}

type NumberConfig = Extract<
  SandboxDocumentField["config"],
  { kind: "number" | "integer" }
>;

function numberFits(value: number, config: NumberConfig): boolean {
  if (config.min !== undefined && value < config.min) return false;
  if (config.max !== undefined && value > config.max) return false;
  if (config.step !== undefined)
    return onStep(value, config.min ?? 0, config.step);
  return true;
}

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const URL_PATTERN = /^([a-z][a-z0-9+.-]*):\/\/([^/?#]*)/i;

function withinLength(value: string, maxLength: number | undefined): boolean {
  // Python counts code points, not UTF-16 units.
  return maxLength === undefined || [...value].length <= maxLength;
}

/**
 * Whether the evaluator accepts `value` for `field`: the same rules as its
 * `_value_is_valid`, including "no value" only for a field that is not
 * required.
 */
export function testValueValid(
  field: SandboxDocumentField,
  value: SandboxFieldValue,
): boolean {
  if (value === null) return !field.required;
  if (typeof value === "string" && field.required && !value.trim())
    return false;
  const config = field.config;
  switch (config.kind) {
    case "text":
    case "long-text":
      return typeof value === "string" && withinLength(value, config.maxLength);
    case "email":
      return (
        typeof value === "string" &&
        withinLength(value, config.maxLength) &&
        (value === "" || EMAIL_PATTERN.test(value))
      );
    case "url": {
      if (typeof value !== "string" || !withinLength(value, config.maxLength))
        return false;
      if (value === "") return true;
      const match = URL_PATTERN.exec(value);
      return (
        match !== null &&
        ["http", "https"].includes(match[1].toLowerCase()) &&
        match[2] !== ""
      );
    }
    case "checkbox":
      return typeof value === "boolean";
    case "integer":
      return (
        typeof value === "number" &&
        Number.isInteger(value) &&
        numberFits(value, config)
      );
    case "number":
      return (
        typeof value === "number" &&
        Number.isFinite(value) &&
        numberFits(value, config)
      );
    case "select":
      return (
        typeof value === "string" &&
        config.options.some((option) => option.id === value)
      );
    case "user":
      return typeof value === "string" && UUID_PATTERN.test(value);
    case "date":
    case "datetime":
      return (
        typeof value === "string" &&
        dateValueInRange(config.kind, value, config.earliest, config.latest)
      );
  }
}

/** A field that a relationship mapping carries this field's value to. */
export type LinkedTarget = {
  source: SandboxDocumentField;
  target: SandboxDocumentField;
};

/** The fields a relationship from this module carries `field` to. */
export function linkedTargets(
  design: SandboxDocumentDesign,
  moduleId: string,
  field: SandboxDocumentField,
): LinkedTarget[] {
  return design.relationships.flatMap((relationship) => {
    if (relationship.sourceModuleId !== moduleId) return [];
    const targetModule = design.modules.find(
      (item) => item.id === relationship.targetModuleId,
    );
    return relationship.fieldMappings.flatMap((mapping) => {
      if (mapping.sourceFieldId !== field.id) return [];
      const target = targetModule?.fields.find(
        (item) => item.id === mapping.targetFieldId,
      );
      return target ? [{ source: field, target }] : [];
    });
  });
}

/** The value as it arrives in the target: a choice maps by its label. */
function projected(
  link: LinkedTarget,
  value: SandboxFieldValue,
): SandboxFieldValue {
  if (
    typeof value !== "string" ||
    link.source.config.kind !== "select" ||
    link.target.config.kind !== "select"
  )
    return value;
  const label = link.source.config.options.find(
    (option) => option.id === value,
  )?.label;
  return (
    link.target.config.options.find((option) => option.label === label)?.id ??
    value
  );
}

/** Valid for the field and for every field a mapping carries it to. */
export function valueFits(
  design: SandboxDocumentDesign,
  moduleId: string,
  field: SandboxDocumentField,
  value: SandboxFieldValue,
): boolean {
  return (
    testValueValid(field, value) &&
    linkedTargets(design, moduleId, field).every((link) =>
      testValueValid(link.target, projected(link, value)),
    )
  );
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

function localDate(now: Date): string {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function localHour(now: Date): string {
  return `${localDate(now)}T${pad(now.getHours())}:00`;
}

const DAY = 24 * 60 * 60 * 1000;
const HOUR = 60 * 60 * 1000;

/** A date or date-and-time moved by `count` days (or hours). */
function shiftDate(
  kind: "date" | "datetime",
  value: string,
  count: number,
): string | null {
  if (kind === "date") {
    const time = Date.parse(`${value}T00:00:00Z`);
    if (Number.isNaN(time)) return null;
    return new Date(time + count * DAY).toISOString().slice(0, 10);
  }
  const instant = dateTimeInstant(value);
  if (instant === undefined) return null;
  return `${new Date(instant + count * HOUR).toISOString().slice(0, 16)}Z`;
}

function earlier(
  kind: "date" | "datetime",
  left: string,
  right: string,
): boolean {
  if (kind === "date") return left < right;
  return (dateTimeInstant(left) ?? 0) < (dateTimeInstant(right) ?? 0);
}

function textExample(field: SandboxDocumentField, limit: number | undefined) {
  const text = [...`Example ${field.name.toLocaleLowerCase()}`];
  return (limit === undefined ? text : text.slice(0, limit)).join("");
}

/** The smallest length limit across the field and its linked targets. */
function smallestLimit(fields: readonly SandboxDocumentField[]) {
  const limits = fields.flatMap((field) =>
    "maxLength" in field.config && field.config.maxLength !== undefined
      ? [field.config.maxLength]
      : [],
  );
  return limits.length ? Math.min(...limits) : undefined;
}

/** Values on a number field's step near `around`, in order of distance. */
function numberGrid(config: NumberConfig, around: number): number[] {
  const origin = config.min ?? 0;
  const values: number[] = [];
  if (config.step !== undefined && config.step > 0) {
    const center = Math.round((around - origin) / config.step);
    for (let offset = 0; offset <= 200; offset += 1) {
      values.push(stepFrom(origin, config.step, center + offset));
      if (offset) values.push(stepFrom(origin, config.step, center - offset));
    }
  } else {
    values.push(around, Math.ceil(around), Math.floor(around));
    for (let offset = 1; offset <= 2; offset += 1)
      values.push(Math.floor(around) + offset, Math.ceil(around) - offset);
  }
  if (config.min !== undefined) values.push(config.min);
  if (config.max !== undefined) values.push(config.max);
  return values.filter((value) => Number.isFinite(value));
}

/** The candidates an example tries, in order; the first that fits wins. */
function exampleCandidates(
  design: SandboxDocumentDesign,
  moduleId: string,
  field: SandboxDocumentField,
  context: ExampleContext,
): SandboxFieldValue[] {
  const config = field.config;
  const fields = [
    field,
    ...linkedTargets(design, moduleId, field).map((link) => link.target),
  ];
  const optional: SandboxFieldValue[] = field.required ? [] : [null];
  switch (config.kind) {
    case "text":
    case "long-text":
      return [
        ...(config.defaultValue ? [config.defaultValue] : []),
        textExample(field, smallestLimit(fields)),
        ...optional,
      ];
    case "email":
      return [
        ...(config.defaultValue ? [config.defaultValue] : []),
        "a@example.com",
        "a@b.c",
        ...optional,
      ];
    case "url":
      return [
        ...(config.defaultValue ? [config.defaultValue] : []),
        "https://example.com",
        "http://a.io",
        "http://a",
        ...optional,
      ];
    case "number":
    case "integer": {
      // The first value on the step from the minimum (else 0) inside the
      // limits: upward from the start, else downward when the start is
      // above the maximum.
      const origin = config.min ?? 0;
      const start =
        config.max !== undefined && origin > config.max ? config.max : origin;
      const grid = numberGrid(config, start).sort((a, b) =>
        start === origin ? a - b : b - a,
      );
      const ordered = grid.filter((value) =>
        start === origin ? value >= origin : value <= start,
      );
      // A linked target with its own limits: values on this field's step
      // from the target's minimum (or down from its maximum).
      const linked = linkedTargets(design, moduleId, field).flatMap((link) => {
        const target = link.target.config;
        if (target.kind !== "number" && target.kind !== "integer") return [];
        const from = target.min ?? target.max;
        if (from === undefined) return [];
        return numberGrid(config, from)
          .filter((value) =>
            target.min !== undefined ? value >= from : value <= from,
          )
          .sort((a, b) => (target.min !== undefined ? a - b : b - a));
      });
      return [
        ...(config.defaultValue !== null ? [config.defaultValue] : []),
        ...ordered,
        ...linked,
        ...optional,
      ];
    }
    case "date":
    case "datetime": {
      const kind = config.kind;
      let value =
        kind === "date" ? localDate(context.now) : localHour(context.now);
      // Move today inside the earliest and latest limits of every field
      // the value reaches.
      for (const item of fields) {
        if (item.config.kind !== kind) continue;
        if (item.config.earliest && earlier(kind, value, item.config.earliest))
          value = item.config.earliest;
      }
      for (const item of fields) {
        if (item.config.kind !== kind) continue;
        if (item.config.latest && earlier(kind, item.config.latest, value))
          value = item.config.latest;
      }
      return [
        ...(config.defaultValue ? [config.defaultValue] : []),
        value,
        ...optional,
      ];
    }
    case "checkbox":
      return [config.defaultValue, !config.defaultValue];
    case "select":
      return [
        ...(config.defaultValue ? [config.defaultValue] : []),
        ...config.options.map((option) => option.id),
        ...optional,
      ];
    case "user":
      return [
        ...(context.administratorId ? [context.administratorId] : []),
        ...optional,
      ];
  }
}

/** One field's example, or `undefined` when no valid value exists (E4). */
export function exampleFieldValue(
  design: SandboxDocumentDesign,
  moduleId: string,
  field: SandboxDocumentField,
  context: ExampleContext,
): SandboxFieldValue | undefined {
  return exampleCandidates(design, moduleId, field, context).find((value) =>
    valueFits(design, moduleId, field, value),
  );
}

/** A field whose settings allow no valid value (E4). */
export type UnfillableField = { fieldId: string; name: string };

export type ExampleValues = {
  values: Record<string, SandboxFieldValue>;
  /** Fields with no valid value; Try it sends nothing until they get one. */
  unfillable: UnfillableField[];
};

/** The open fields of a module, in their order. */
export function openFields(
  sandboxModule: SandboxDocumentModule | undefined,
): SandboxDocumentField[] {
  return sandboxModule?.fields.filter((field) => !field.closed) ?? [];
}

/** The example value of every open field of the module (TEST-3). */
export function exampleValues(
  design: SandboxDocumentDesign,
  moduleId: string,
  context: ExampleContext,
): ExampleValues {
  const values: Record<string, SandboxFieldValue> = {};
  const unfillable: UnfillableField[] = [];
  const sandboxModule = design.modules.find((item) => item.id === moduleId);
  for (const field of openFields(sandboxModule)) {
    const value = exampleFieldValue(design, moduleId, field, context);
    if (value === undefined) {
      unfillable.push({ fieldId: field.id, name: field.name });
      values[field.id] = null;
    } else values[field.id] = value;
  }
  return { values, unfillable };
}

/** The evaluator's `compare`: equality for any value, order for numbers,
 *  text, and date-and-time instants; nothing compares with no value. */
export function compareTestValues(
  left: SandboxFieldValue | undefined,
  operator: SandboxComparisonOperator,
  right: SandboxFieldValue | undefined,
  kind?: SandboxDocumentField["config"]["kind"],
): boolean {
  if (left === undefined || right === undefined) return false;
  let a: SandboxFieldValue = left;
  let b: SandboxFieldValue = right;
  if (kind === "datetime") {
    if (typeof a !== "string" || typeof b !== "string") return false;
    const instantA = dateTimeInstant(a);
    const instantB = dateTimeInstant(b);
    if (instantA === undefined || instantB === undefined) return false;
    a = instantA;
    b = instantB;
  }
  if (operator === "=") return a === b;
  if (operator === "!=") return a !== b;
  if (
    typeof a === "boolean" ||
    typeof b === "boolean" ||
    a === null ||
    b === null
  )
    return false;
  if (typeof a !== typeof b) return false;
  switch (operator) {
    case ">":
      return a > b;
    case ">=":
      return a >= b;
    case "<":
      return a < b;
    case "<=":
      return a <= b;
  }
}

/** A value that differs from `value`: the next choice, step, or day. */
export function differentValue(
  field: SandboxDocumentField,
  value: SandboxFieldValue,
): SandboxFieldValue {
  const config = field.config;
  switch (config.kind) {
    case "select": {
      const index = config.options.findIndex((option) => option.id === value);
      const next = config.options[(index + 1) % config.options.length];
      return next && next.id !== value ? next.id : null;
    }
    case "checkbox":
      return value !== true;
    case "number":
    case "integer":
      return typeof value === "number"
        ? stepFrom(value, config.step ?? 1, 1)
        : (config.min ?? 0);
    case "date":
    case "datetime":
      return typeof value === "string"
        ? shiftDate(config.kind, value, config.kind === "date" ? 1 : 24)
        : null;
    case "text":
    case "long-text":
      return `Example ${field.name.toLocaleLowerCase()} (before)`;
    default:
      return value === null ? "" : null;
  }
}

/**
 * Candidates near `limit` for an ordered or equality comparison: the limit
 * itself, its neighbors on the field's step (or a day or an hour away), and
 * the field's own limits.
 */
function candidatesNear(
  field: SandboxDocumentField,
  limit: SandboxFieldValue,
): SandboxFieldValue[] {
  const config = field.config;
  if (
    (config.kind === "number" || config.kind === "integer") &&
    typeof limit === "number"
  )
    return [limit, ...numberGrid(config, limit)];
  if (
    (config.kind === "date" || config.kind === "datetime") &&
    typeof limit === "string"
  ) {
    // A day away for a Date, an hour away for a Date and time.
    return [
      limit,
      shiftDate(config.kind, limit, 1),
      shiftDate(config.kind, limit, -1),
      config.earliest ?? null,
      config.latest ?? null,
    ].filter((value): value is string => typeof value === "string");
  }
  return [limit];
}

function orderOf(
  field: SandboxDocumentField,
  value: SandboxFieldValue,
): number {
  if (typeof value === "number") return value;
  if (typeof value === "string")
    return field.config.kind === "datetime"
      ? (dateTimeInstant(value) ?? 0)
      : Date.parse(`${value}T00:00:00Z`);
  return 0;
}

/**
 * The value that meets `field operator limit` and fits the field and its
 * linked targets: the smallest for "more than" and "at least", the largest
 * for "less than" and "at most", the limit for "is", and for "is not" the
 * example itself when it already differs. `undefined` when none fits.
 */
export function meetingValue(
  design: SandboxDocumentDesign,
  moduleId: string,
  field: SandboxDocumentField,
  operator: SandboxComparisonOperator,
  limit: SandboxFieldValue,
  example: SandboxFieldValue,
): SandboxFieldValue | undefined {
  const kind = field.config.kind;
  const fits = (value: SandboxFieldValue) =>
    compareTestValues(value, operator, limit, kind) &&
    valueFits(design, moduleId, field, value);
  if (operator === "!=") {
    const options =
      field.config.kind === "select"
        ? field.config.options.map((option) => option.id)
        : [];
    return [
      example,
      differentValue(field, limit),
      ...options,
      ...candidatesNear(field, limit),
    ].find(fits);
  }
  const candidates = candidatesNear(field, limit).filter(fits);
  if (operator === "=" || !candidates.length) return candidates[0];
  const sorted = [...candidates].sort(
    (a, b) => orderOf(field, a) - orderOf(field, b),
  );
  return operator === ">" || operator === ">="
    ? sorted[0]
    : sorted[sorted.length - 1];
}

/** A value that does not meet `operator limit`: the previous value of a
 *  Threshold crossed event. */
export function valueBeforeLimit(
  field: SandboxDocumentField,
  operator: SandboxComparisonOperator,
  limit: Exclude<SandboxFieldValue, null>,
): Exclude<SandboxFieldValue, null> {
  const kind = field.config.kind;
  const step =
    (kind === "number" || kind === "integer") && "step" in field.config
      ? (field.config.step ?? 1)
      : 1;
  const below = (count: number): Exclude<SandboxFieldValue, null> => {
    if (typeof limit === "number") return stepFrom(limit, step, count);
    if (typeof limit === "string" && (kind === "date" || kind === "datetime"))
      return shiftDate(kind, limit, count) ?? limit;
    return limit;
  };
  switch (operator) {
    case ">=":
      return below(-1);
    case "<=":
    case "=":
      return below(1);
    default:
      return limit;
  }
}
