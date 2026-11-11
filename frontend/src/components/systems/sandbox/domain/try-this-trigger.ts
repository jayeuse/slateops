import type {
  SandboxDocumentDesign,
  SandboxDocumentField,
  SandboxFieldValue,
  SandboxTrigger,
  SandboxTriggerCondition,
} from "./document";
import {
  compareTestValues,
  differentValue,
  meetingValue,
  type ExampleContext,
} from "./example-values";
import {
  readingEventOf,
  tryEventPlan,
  valueWords,
  type TryPlan,
} from "./test-reading";

// "Try this trigger" (docs/specs/sandbox-ux-redesign.md TEST-9, UXD-11):
// one run of one trigger on its own event, with the example values changed
// only where this trigger's literal same-module conditions need it. No
// order, priority, or chain of other triggers is copied into the browser.

type Fillable = {
  condition: SandboxTriggerCondition;
  field: SandboxDocumentField;
  literal: SandboxFieldValue;
};

function ordered(field: SandboxDocumentField): boolean {
  const kind = field.config.kind;
  return (
    kind === "number" ||
    kind === "integer" ||
    kind === "date" ||
    kind === "datetime"
  );
}

/** Why a condition's value cannot be used: "100 is outside Amount's limits". */
function invalidFillNote(
  field: SandboxDocumentField,
  literal: SandboxFieldValue,
) {
  const value = valueWords(field, literal);
  return ordered(field)
    ? `${value} is outside ${field.name}'s limits; value kept.`
    : `${value} is not a valid value for ${field.name}; value kept.`;
}

/**
 * The run request of "Try this trigger": the trigger's own event, the
 * example values, `triggerIds` with only this trigger, and each literal
 * condition on the trigger's module met with a value valid for its field and
 * its linked target fields. A condition that compares two fields, one on the
 * field a Threshold crossed event fixes, two conditions on one field that
 * cannot both hold, and a value that would be invalid keep the example value,
 * with a note. In an "any" group only the first condition that can be filled
 * is filled.
 */
export function tryTriggerPlan(
  design: SandboxDocumentDesign,
  recordTrigger: SandboxTrigger,
  context: ExampleContext,
): TryPlan {
  const moduleId = recordTrigger.trigger.moduleId ?? "";
  const event = readingEventOf(recordTrigger);
  const base = tryEventPlan(design, moduleId, event, context);
  const sandboxModule = design.modules.find((item) => item.id === moduleId);
  const fieldOf = (id: string) =>
    sandboxModule?.fields.find((field) => field.id === id);
  const values = { ...base.values };
  const notes = [...base.notes];

  const fillable: Fillable[] = [];
  for (const condition of recordTrigger.conditionGroup.conditions) {
    const field = fieldOf(condition.field.fieldId);
    // A condition on another module needs attention in the result itself.
    if (
      !field ||
      condition.field.moduleId !== moduleId ||
      condition.field.relationshipId !== undefined
    )
      continue;
    if (condition.value.kind === "field-reference") {
      const other = fieldOf(condition.value.fieldId)?.name ?? "another field";
      notes.push(`${field.name} is compared with ${other}; values kept.`);
      continue;
    }
    if (event.kind === "threshold-crossed" && event.fieldId === field.id) {
      notes.push(`${field.name} is set by the event; value kept.`);
      continue;
    }
    fillable.push({ condition, field, literal: condition.value.value });
  }

  const meet = (item: Fillable) =>
    meetingValue(
      design,
      moduleId,
      item.field,
      item.condition.operator,
      item.literal,
      values[item.field.id] ?? null,
    );

  if (recordTrigger.conditionGroup.operator === "any") {
    // Only the first condition that can be filled is filled.
    const skipped: string[] = [];
    let filled = false;
    for (const item of fillable) {
      const value = meet(item);
      if (value === undefined) {
        skipped.push(invalidFillNote(item.field, item.literal));
        continue;
      }
      values[item.field.id] = value;
      filled = true;
      break;
    }
    if (!filled) notes.push(...skipped);
  } else {
    const byField = new Map<string, Fillable[]>();
    for (const item of fillable)
      byField.set(item.field.id, [...(byField.get(item.field.id) ?? []), item]);
    for (const [fieldId, items] of byField) {
      const field = items[0].field;
      const invalid = items.find((item) => meet(item) === undefined);
      if (invalid) {
        notes.push(invalidFillNote(field, invalid.literal));
        continue;
      }
      const candidates = items.map(meet);
      const together = candidates.find((value) =>
        items.every((item) =>
          compareTestValues(
            value,
            item.condition.operator,
            item.literal,
            field.config.kind,
          ),
        ),
      );
      if (together === undefined) {
        notes.push(
          `${field.name} has conditions that cannot both hold; value kept.`,
        );
        continue;
      }
      values[fieldId] = together;
    }
  }

  const setFieldIds = Object.keys(values).filter(
    (id) => !Object.is(values[id], base.values[id]),
  );
  // A field change keeps a previous value that differs from the new one.
  let testEvent = base.event;
  if (
    testEvent.kind === "field-changed" &&
    setFieldIds.includes(testEvent.fieldId)
  ) {
    const field = fieldOf(testEvent.fieldId);
    testEvent = {
      ...testEvent,
      previousValue: field
        ? differentValue(field, values[testEvent.fieldId] ?? null)
        : null,
    };
  }
  return {
    ...base,
    values,
    event: testEvent,
    triggerIds: [recordTrigger.id],
    setFieldIds,
    notes,
  };
}
