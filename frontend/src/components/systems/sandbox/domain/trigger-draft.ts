// Trigger drafts (docs/specs/sandbox-ux-redesign.md B1, TRIG-2 to TRIG-5).
//
// While a trigger is edited it may have empty parts: no module yet, no
// watched field, a condition or action with no field, or no action at all.
// A draft keeps the `SandboxTrigger` shape, and the only empty markers are
// an empty id ("") and an empty action list, so a complete draft serializes
// exactly as its trigger and the equality checks against the saved triggers
// keep their meaning. Why a part is empty is never stored: it is derived
// from the draft and the current design whenever it is shown.
//
// A draft never enters the document, its parser, or a request. Save turns
// drafts into triggers only through `checkTriggerDrafts`, after every
// changed draft is complete; kept edits use their own format-2 parser.

import { fieldTypeLabel } from "./model";
import type {
  SandboxComparisonOperator,
  SandboxDocumentDesign,
  SandboxDocumentField,
  SandboxDocumentModule,
  SandboxFieldReference,
  SandboxTrigger,
  SandboxTriggerEvent,
  SandboxValueSource,
} from "./document";
import { defaultLiteral } from "./trigger-rules";

/** A trigger while it is edited; `""` ids and `[]` actions are empty parts. */
export type SandboxTriggerDraft = SandboxTrigger;

/** Every comparison, in the order the pickers list them. */
export const triggerOperators: readonly SandboxComparisonOperator[] = [
  "=",
  "!=",
  ">",
  ">=",
  "<",
  "<=",
];
const equalityOperators: readonly SandboxComparisonOperator[] = ["=", "!="];

/** Field kinds that are ordered, so "more" and "less" mean something. */
function ordered(field: SandboxDocumentField): boolean {
  const kind = field.config.kind;
  return (
    kind === "number" ||
    kind === "integer" ||
    kind === "date" ||
    kind === "datetime"
  );
}

/**
 * The operators a field offers (TRIG-3): Number, Whole number, Date, and
 * Date and time get all six; every other type gets "is" and "is not". With
 * no field chosen yet, nothing is ruled out.
 */
export function operatorsForField(
  field: SandboxDocumentField | undefined,
): readonly SandboxComparisonOperator[] {
  return !field || ordered(field) ? triggerOperators : equalityOperators;
}

/** False for a saved operator that its field type does not offer (TRIG-4). */
export function operatorFits(
  operator: SandboxComparisonOperator,
  field: SandboxDocumentField | undefined,
): boolean {
  return operatorsForField(field).includes(operator);
}

/** A threshold watches an ordered field: a number or a date. */
export function thresholdFieldFits(field: SandboxDocumentField): boolean {
  return ordered(field);
}

/** The module a trigger's steps belong to; "" while none is chosen. */
export function draftModuleId(draft: SandboxTriggerDraft): string {
  return draft.trigger.moduleId ?? "";
}

function moduleById(
  design: SandboxDocumentDesign,
  moduleId: string,
): SandboxDocumentModule | undefined {
  return moduleId
    ? design.modules.find((item) => item.id === moduleId)
    : undefined;
}

export type ResolvedReference =
  | { state: "empty" }
  | { state: "gone" }
  | { state: "elsewhere" }
  | { state: "ok"; field: SandboxDocumentField };

/**
 * Where a field reference points, seen from the trigger's module: nowhere
 * yet, at something no longer in the design, at a field of another module
 * (after a module change), or at a field of the trigger's module.
 */
export function resolveReference(
  reference: SandboxFieldReference,
  sandboxModule: SandboxDocumentModule | undefined,
  design: SandboxDocumentDesign,
): ResolvedReference {
  if (!reference.fieldId) return { state: "empty" };
  if (
    sandboxModule &&
    reference.moduleId === sandboxModule.id &&
    reference.relationshipId === undefined
  ) {
    const found = sandboxModule.fields.find(
      (item) => item.id === reference.fieldId,
    );
    return found ? { state: "ok", field: found } : { state: "gone" };
  }
  const exists = design.modules
    .find((item) => item.id === reference.moduleId)
    ?.fields.some((item) => item.id === reference.fieldId);
  return exists ? { state: "elsewhere" } : { state: "gone" };
}

export type TriggerDraftGap = {
  /** The flow step, keyed as `triggerStepErrors` keys it, or "actions". */
  step: string;
  part: "module" | "field" | "value" | "actions";
  reason: string;
};

function referenceGap(
  resolved: ResolvedReference,
  sandboxModule: SandboxDocumentModule,
  emptyReason: string,
): string | null {
  if (resolved.state === "empty") return emptyReason;
  if (resolved.state === "gone") return "No longer in the design.";
  if (resolved.state === "elsewhere")
    return `Not in ${sandboxModule.name}; choose a field.`;
  return null;
}

function valueGap(
  value: SandboxValueSource,
  sandboxModule: SandboxDocumentModule,
  design: SandboxDocumentDesign,
): string | null {
  if (value.kind !== "field-reference") return null;
  return resolveReference(value, sandboxModule, design).state === "ok"
    ? null
    : "Choose a value.";
}

/**
 * The empty parts of a draft, in reading order (When, If, Then), each with
 * the reason the editor shows for it. A complete draft has none. A saved
 * operator that does not fit its field is not an empty part (OQ-2).
 */
export function triggerDraftGaps(
  draft: SandboxTriggerDraft,
  design: SandboxDocumentDesign,
): TriggerDraftGap[] {
  const gaps: TriggerDraftGap[] = [];
  const moduleId = draftModuleId(draft);
  const sandboxModule = moduleById(design, moduleId);
  const noActions: TriggerDraftGap = {
    step: "actions",
    part: "actions",
    reason: "Add an action.",
  };
  if (!sandboxModule) {
    gaps.push({
      step: "trigger",
      part: "module",
      reason: moduleId ? "No longer in the design." : "Choose a module.",
    });
    if (!draft.actions.length) gaps.push(noActions);
    return gaps;
  }
  const trigger = draft.trigger;
  if (
    trigger.kind === "field-changed" ||
    trigger.kind === "threshold-crossed"
  ) {
    const resolved = resolveReference(
      { moduleId: trigger.moduleId, fieldId: trigger.fieldId },
      sandboxModule,
      design,
    );
    const threshold = trigger.kind === "threshold-crossed";
    const reason =
      threshold &&
      resolved.state === "ok" &&
      !thresholdFieldFits(resolved.field)
        ? "Choose a number or date field."
        : referenceGap(
            resolved,
            sandboxModule,
            threshold
              ? "Choose a number or date field."
              : "Choose the field to watch.",
          );
    if (reason) gaps.push({ step: "trigger", part: "field", reason });
    else if (threshold) {
      const value = valueGap(trigger.value, sandboxModule, design);
      if (value) gaps.push({ step: "trigger", part: "value", reason: value });
    }
  }
  for (const condition of draft.conditionGroup.conditions) {
    const step = `condition:${condition.id}`;
    const reason = referenceGap(
      resolveReference(condition.field, sandboxModule, design),
      sandboxModule,
      "Choose a field.",
    );
    if (reason) gaps.push({ step, part: "field", reason });
    else {
      const value = valueGap(condition.value, sandboxModule, design);
      if (value) gaps.push({ step, part: "value", reason: value });
    }
  }
  if (!draft.actions.length) gaps.push(noActions);
  for (const action of draft.actions) {
    if (action.kind !== "set-field") continue;
    const step = `action:${action.id}`;
    const reason = referenceGap(
      resolveReference(action.target, sandboxModule, design),
      sandboxModule,
      "Choose a field.",
    );
    if (reason) gaps.push({ step, part: "field", reason });
    else {
      const value = valueGap(action.value, sandboxModule, design);
      if (value) gaps.push({ step, part: "value", reason: value });
    }
  }
  return gaps;
}

export type IncompleteTriggers = {
  /** Changed triggers with at least one empty part. */
  count: number;
  /** The first of them, and its first empty part. */
  triggerId: string;
  step: string;
  part: TriggerDraftGap["part"];
  /** What the save bar says: "1 trigger is incomplete; choose a module." */
  message: string;
};

function lowerFirst(text: string): string {
  return text.charAt(0).toLowerCase() + text.slice(1);
}

/** The changed drafts that have an empty part, by id. */
export function incompleteTriggerIds(
  drafts: readonly SandboxTriggerDraft[],
  design: SandboxDocumentDesign,
  changed: ReadonlySet<string>,
): Set<string> {
  return new Set(
    drafts
      .filter(
        (draft) =>
          changed.has(draft.id) && triggerDraftGaps(draft, design).length,
      )
      .map((draft) => draft.id),
  );
}

/**
 * Save's check before any request (B1 rule c). Only changed drafts are
 * checked; saved triggers that were not edited go out as they are. When
 * every changed draft is complete, the drafts are the triggers to save.
 */
export function checkTriggerDrafts(
  drafts: readonly SandboxTriggerDraft[],
  design: SandboxDocumentDesign,
  changed: ReadonlySet<string>,
):
  | { ok: true; triggers: SandboxTrigger[] }
  | { ok: false; incomplete: IncompleteTriggers } {
  const incomplete = drafts
    .filter((draft) => changed.has(draft.id))
    .map((draft) => ({ draft, gaps: triggerDraftGaps(draft, design) }))
    .filter(({ gaps }) => gaps.length);
  const first = incomplete[0];
  if (!first) return { ok: true, triggers: [...drafts] };
  const gap = first.gaps[0]!;
  const count = incomplete.length;
  return {
    ok: false,
    incomplete: {
      count,
      triggerId: first.draft.id,
      step: gap.step,
      part: gap.part,
      message: `${count} ${count === 1 ? "trigger is" : "triggers are"} incomplete; ${lowerFirst(gap.reason)}`,
    },
  };
}

/**
 * A new event for the trigger (TRIG-5): the module stays, a watched field
 * carries over when the new event watches one too, and nothing is picked
 * on the person's behalf. A field the new event cannot use shows empty
 * with its reason (see `triggerDraftGaps`).
 */
export function changeTriggerEvent(
  draft: SandboxTriggerDraft,
  kind: SandboxTriggerEvent["kind"],
  design: SandboxDocumentDesign,
): SandboxTriggerDraft {
  const before = draft.trigger;
  if (before.kind === kind) return draft;
  const moduleId = draftModuleId(draft);
  const fieldId =
    before.kind === "field-changed" || before.kind === "threshold-crossed"
      ? before.fieldId
      : "";
  let next: SandboxTriggerEvent;
  if (kind === "record-created") next = { kind, moduleId };
  else if (kind === "field-changed") next = { kind, moduleId, fieldId };
  else if (kind === "threshold-crossed") {
    const resolved = resolveReference(
      { moduleId, fieldId },
      moduleById(design, moduleId),
      design,
    );
    next = {
      kind,
      moduleId,
      fieldId,
      operator: ">=",
      value:
        resolved.state === "ok" && thresholdFieldFits(resolved.field)
          ? defaultLiteral(resolved.field)
          : { kind: "literal", value: null },
    };
  } else
    next = { kind: "schedule", moduleId, frequency: "daily", time: "09:00" };
  return { ...draft, trigger: next };
}

/**
 * A new module for the trigger (TRIG-5): only the module changes. Steps
 * that point at fields of the old module read empty with "Not in …" until
 * the person chooses, and come back whole if the old module is chosen again.
 */
export function changeTriggerModule(
  draft: SandboxTriggerDraft,
  moduleId: string,
): SandboxTriggerDraft {
  return { ...draft, trigger: { ...draft.trigger, moduleId } };
}

export type TriggerChoice = { value: string; label: string; meta: string };
export type TriggerChoiceGroup = {
  label: string;
  /** The department's position in the design, for its color mark. */
  departmentIndex: number;
  choices: TriggerChoice[];
};

function fieldCount(sandboxModule: SandboxDocumentModule): string {
  const count = sandboxModule.fields.filter((item) => !item.closed).length;
  return `${count} ${count === 1 ? "field" : "fields"}`;
}

/**
 * The module picker's choices (TRIG-2): open modules under their
 * department, in design order, each with its field count.
 */
export function moduleChoiceGroups(
  design: SandboxDocumentDesign,
): TriggerChoiceGroup[] {
  const groups = design.departments.map((department, index) => ({
    label: department.name,
    departmentIndex: index,
    choices: design.modules
      .filter((item) => item.departmentId === department.id && !item.closed)
      .map((item) => ({
        value: item.id,
        label: item.name,
        meta: fieldCount(item),
      })),
  }));
  const departmentIds = new Set(design.departments.map((item) => item.id));
  const loose = design.modules.filter(
    (item) => !departmentIds.has(item.departmentId) && !item.closed,
  );
  if (loose.length)
    groups.push({
      label: "Other modules",
      departmentIndex: groups.length,
      choices: loose.map((item) => ({
        value: item.id,
        label: item.name,
        meta: fieldCount(item),
      })),
    });
  return groups.filter((group) => group.choices.length);
}

/** A field picker's choices (TRIG-2): each field with its type word (C8). */
export function fieldChoices(
  fields: readonly SandboxDocumentField[],
): TriggerChoice[] {
  return fields.map((item) => ({
    value: item.id,
    label: item.name,
    meta: fieldTypeLabel(item.type),
  }));
}

// Kept edits, format 2 (B1 rule b).

export type KeptTriggerDrafts = {
  /** The saved triggers' JSON when the edits began; only for the warning. */
  base: string;
  triggers: SandboxTriggerDraft[];
};

export function encodeKeptTriggerDrafts(record: KeptTriggerDrafts): string {
  return JSON.stringify({
    version: 2,
    base: record.base,
    triggers: record.triggers,
  });
}

type Shape = Record<string, unknown>;

function isShape(value: unknown): value is Shape {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
const isText = (value: unknown): value is string => typeof value === "string";
const isId = (value: unknown): value is string =>
  typeof value === "string" && value.length > 0;
const isOperator = (value: unknown) =>
  (triggerOperators as readonly unknown[]).includes(value);

function isReference(value: unknown): boolean {
  return (
    isShape(value) &&
    isText(value.moduleId) &&
    isText(value.fieldId) &&
    (value.relationshipId === undefined || isText(value.relationshipId))
  );
}

function isValueSource(value: unknown): boolean {
  if (!isShape(value)) return false;
  if (value.kind === "literal")
    return (
      value.value === null ||
      ["string", "number", "boolean"].includes(typeof value.value)
    );
  return value.kind === "field-reference" && isReference(value);
}

function isEvent(value: unknown): boolean {
  if (!isShape(value)) return false;
  switch (value.kind) {
    case "record-created":
      return isText(value.moduleId);
    case "field-changed":
      return isText(value.moduleId) && isText(value.fieldId);
    case "threshold-crossed":
      return (
        isText(value.moduleId) &&
        isText(value.fieldId) &&
        isOperator(value.operator) &&
        isValueSource(value.value)
      );
    case "schedule":
      return (
        (value.moduleId === undefined || isText(value.moduleId)) &&
        (value.frequency === "daily" || value.frequency === "weekly") &&
        isText(value.time) &&
        (value.weekday === undefined || Number.isInteger(value.weekday))
      );
    default:
      return false;
  }
}

function isCondition(value: unknown): boolean {
  return (
    isShape(value) &&
    isId(value.id) &&
    isReference(value.field) &&
    isOperator(value.operator) &&
    isValueSource(value.value)
  );
}

function isAction(value: unknown): boolean {
  if (!isShape(value) || !isId(value.id)) return false;
  switch (value.kind) {
    case "set-field":
      return isReference(value.target) && isValueSource(value.value);
    case "notification":
      return isText(value.message);
    case "channel-message":
      return isText(value.channel);
    case "assign-task":
      return isText(value.assignee);
    case "create-record":
      return (
        isText(value.moduleId) &&
        Array.isArray(value.values) &&
        value.values.every(
          (item) =>
            isShape(item) && isText(item.fieldId) && isValueSource(item.value),
        )
      );
    default:
      return false;
  }
}

function isTriggerDraft(value: unknown): boolean {
  if (!isShape(value)) return false;
  const group = value.conditionGroup;
  return (
    isId(value.id) &&
    isText(value.name) &&
    typeof value.enabled === "boolean" &&
    typeof value.priority === "number" &&
    Number.isFinite(value.priority) &&
    isEvent(value.trigger) &&
    isShape(group) &&
    (group.operator === "all" || group.operator === "any") &&
    Array.isArray(group.conditions) &&
    group.conditions.every(isCondition) &&
    Array.isArray(value.actions) &&
    value.actions.every(isAction)
  );
}

/**
 * Reads a format-2 record. It checks the shape and the ids and accepts
 * empty parts; it never drops a record because a trigger is incomplete.
 * A part that points at a module or field no longer in the design reads
 * as empty, with "No longer in the design." (`triggerDraftGaps`). Returns
 * null only for a damaged record.
 */
export function parseKeptTriggerDrafts(
  value: unknown,
): KeptTriggerDrafts | null {
  if (
    !isShape(value) ||
    value.version !== 2 ||
    !isText(value.base) ||
    !Array.isArray(value.triggers) ||
    !value.triggers.every(isTriggerDraft)
  )
    return null;
  const triggers = value.triggers as SandboxTriggerDraft[];
  if (new Set(triggers.map((item) => item.id)).size !== triggers.length)
    return null;
  return { base: value.base, triggers };
}
