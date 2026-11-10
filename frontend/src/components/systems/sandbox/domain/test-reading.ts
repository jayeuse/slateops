import type { SandboxTestEvent } from "../state/api";
import type {
  SandboxComparisonOperator,
  SandboxDocumentDesign,
  SandboxDocumentField,
  SandboxDocumentModule,
  SandboxFieldValue,
  SandboxTrigger,
  SandboxTriggerCondition,
  SandboxValueSource,
} from "./document";
import {
  differentValue,
  exampleValues,
  meetingValue,
  openFields,
  valueBeforeLimit,
  type ExampleContext,
  type UnfillableField,
} from "./example-values";
import { triggerPublicationBlockers } from "./trigger-rules";

// The Test reading (docs/specs/sandbox-ux-redesign.md TEST-1, TEST-2, E1):
// what the saved draft does when people use a module, built in the browser
// with no request. One block per event, the triggers that listen to it with
// their conditions in words and the fields they set, then the module's
// links in both directions. "Try it" (TEST-3, N9) turns a block into one
// run request with example values shaped only by the event (UXD-11).

/** The words after a field for each comparison. */
export const conditionWords: Record<SandboxComparisonOperator, string> = {
  "=": "is",
  "!=": "is not",
  ">": "is more than",
  ">=": "is at least",
  "<": "is less than",
  "<=": "is at most",
};

/** The words after "reaches" for a threshold; "at least" reads as plain. */
const reachesWords: Record<SandboxComparisonOperator, string> = {
  "=": "exactly ",
  "!=": "a value other than ",
  ">": "more than ",
  ">=": "",
  "<": "less than ",
  "<=": "at most ",
};

const weekdays = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

/** The event of a reading block, as the draft's trigger states it. */
export type ReadingEvent =
  | { kind: "record-created" }
  | { kind: "field-changed"; fieldId: string }
  | {
      kind: "threshold-crossed";
      fieldId: string;
      operator: SandboxComparisonOperator;
      value: SandboxValueSource;
    }
  | {
      kind: "schedule";
      frequency: "daily" | "weekly";
      time: string;
      weekday?: number;
    };

export type ReadingTrigger = {
  id: string;
  name: string;
  enabled: boolean;
  /** "if Amount is at least 100", or "always" with no condition. */
  conditions: string;
  /** Names of this module's fields that the trigger sets. */
  sets: string[];
  /** The existing attention reason, when the trigger needs attention. */
  attention: string | null;
};

export type ReadingBlock = {
  key: string;
  title: string;
  event: ReadingEvent;
  triggers: ReadingTrigger[];
};

export type ReadingLink = {
  key: string;
  direction: "out" | "in";
  moduleId: string;
  moduleName: string;
  departmentId: string;
  departmentName: string;
  /** This module's fields that the link's mappings carry. */
  carries: string[];
};

export type ModuleReading = {
  moduleId: string;
  name: string;
  departmentId: string;
  departmentName: string;
  /** "Sales · 6 fields · 4 triggers · 2 links"; zero counts left out. */
  facts: string;
  blocks: ReadingBlock[];
  links: ReadingLink[];
};

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function fieldOf(
  sandboxModule: SandboxDocumentModule | undefined,
  fieldId: string,
): SandboxDocumentField | undefined {
  return sandboxModule?.fields.find((field) => field.id === fieldId);
}

/** A field value in words: a choice by its label, a checkbox as Checked. */
export function valueWords(
  field: SandboxDocumentField | undefined,
  value: SandboxFieldValue | undefined,
): string {
  if (value === undefined || value === null || value === "") return "empty";
  if (value === true) return "Checked";
  if (value === false) return "Unchecked";
  if (typeof value === "number") return value.toLocaleString("en-US");
  if (field?.config.kind === "select")
    return (
      field.config.options.find((option) => option.id === value)?.label ?? value
    );
  return value;
}

function sourceWords(
  source: SandboxValueSource,
  sandboxModule: SandboxDocumentModule | undefined,
  field: SandboxDocumentField | undefined,
): string {
  if (source.kind === "field-reference")
    return `the value of ${fieldOf(sandboxModule, source.fieldId)?.name ?? "a field"}`;
  return valueWords(field, source.value);
}

/** One condition in words: "Amount is at least 100". */
export function conditionText(
  condition: SandboxTriggerCondition,
  sandboxModule: SandboxDocumentModule | undefined,
): string {
  const field = fieldOf(sandboxModule, condition.field.fieldId);
  return `${field?.name ?? "A field"} ${conditionWords[condition.operator]} ${sourceWords(condition.value, sandboxModule, field)}`;
}

function conditionsText(
  recordTrigger: SandboxTrigger,
  sandboxModule: SandboxDocumentModule | undefined,
): string {
  const { conditions, operator } = recordTrigger.conditionGroup;
  if (!conditions.length) return "always";
  return `if ${conditions
    .map((condition) => conditionText(condition, sandboxModule))
    .join(operator === "any" ? " or " : " and ")}`;
}

function readingTrigger(
  recordTrigger: SandboxTrigger,
  sandboxModule: SandboxDocumentModule | undefined,
  design: SandboxDocumentDesign,
): ReadingTrigger {
  const sets = recordTrigger.actions.flatMap((action) =>
    action.kind === "set-field" && action.target.moduleId === sandboxModule?.id
      ? [fieldOf(sandboxModule, action.target.fieldId)?.name ?? "a field"]
      : [],
  );
  const blockers = triggerPublicationBlockers([recordTrigger], design);
  return {
    id: recordTrigger.id,
    name: recordTrigger.name,
    enabled: recordTrigger.enabled,
    conditions: conditionsText(recordTrigger, sandboxModule),
    sets: [...new Set(sets)],
    attention: blockers[0]?.message ?? null,
  };
}

/** The block a trigger listens to, as a stable key. */
export function eventKey(event: ReadingEvent | SandboxTestEvent): string {
  switch (event.kind) {
    case "record-created":
      return "added";
    case "field-changed":
      return `changed:${event.fieldId}`;
    case "threshold-crossed":
      return "operator" in event
        ? `reaches:${event.fieldId}:${event.operator}:${JSON.stringify(event.value)}`
        : `reaches:${event.fieldId}`;
    case "schedule":
      return `schedule:${event.frequency}:${event.time}:${event.frequency === "weekly" ? (event.weekday ?? "") : ""}`;
  }
}

function blockTitle(
  event: ReadingEvent,
  sandboxModule: SandboxDocumentModule | undefined,
): string {
  switch (event.kind) {
    case "record-created":
      return "When an item is added";
    case "field-changed":
      return `When ${fieldOf(sandboxModule, event.fieldId)?.name ?? "a field"} changes`;
    case "threshold-crossed": {
      const field = fieldOf(sandboxModule, event.fieldId);
      return `When ${field?.name ?? "a field"} reaches ${reachesWords[event.operator]}${sourceWords(event.value, sandboxModule, field)}`;
    }
    case "schedule":
      return event.frequency === "daily"
        ? `Every day at ${event.time}`
        : `Every ${weekdays[(event.weekday ?? 1) - 1] ?? "week"} at ${event.time}`;
  }
}

/** The event a trigger listens to, as a reading event. */
export function readingEventOf(recordTrigger: SandboxTrigger): ReadingEvent {
  const trigger = recordTrigger.trigger;
  switch (trigger.kind) {
    case "record-created":
      return { kind: trigger.kind };
    case "field-changed":
      return { kind: trigger.kind, fieldId: trigger.fieldId };
    case "threshold-crossed":
      return {
        kind: trigger.kind,
        fieldId: trigger.fieldId,
        operator: trigger.operator,
        value: trigger.value,
      };
    case "schedule":
      return {
        kind: trigger.kind,
        frequency: trigger.frequency,
        time: trigger.time,
        ...(trigger.frequency === "weekly" ? { weekday: trigger.weekday } : {}),
      };
  }
}

/** The triggers of a module: those whose event is on it. */
export function moduleTriggers(
  triggers: readonly SandboxTrigger[],
  moduleId: string,
): SandboxTrigger[] {
  return triggers.filter((item) => item.trigger.moduleId === moduleId);
}

const blockOrder = {
  "record-created": 0,
  "field-changed": 1,
  "threshold-crossed": 2,
  schedule: 3,
} as const;

/** The reading of one module (TEST-1, TEST-2); null for a missing module. */
export function moduleReading(
  design: SandboxDocumentDesign,
  triggers: readonly SandboxTrigger[],
  moduleId: string,
): ModuleReading | null {
  const sandboxModule = design.modules.find((item) => item.id === moduleId);
  if (!sandboxModule) return null;
  const department = design.departments.find(
    (item) => item.id === sandboxModule.departmentId,
  );
  const fields = openFields(sandboxModule);
  const own = moduleTriggers(triggers, moduleId);

  // "When an item is added" always shows; other events show when a trigger
  // listens to them.
  const blocks = new Map<string, ReadingBlock>();
  const added: ReadingEvent = { kind: "record-created" };
  blocks.set(eventKey(added), {
    key: eventKey(added),
    title: blockTitle(added, sandboxModule),
    event: added,
    triggers: [],
  });
  for (const recordTrigger of own) {
    const event = readingEventOf(recordTrigger);
    const key = eventKey(event);
    const block = blocks.get(key) ?? {
      key,
      title: blockTitle(event, sandboxModule),
      event,
      triggers: [],
    };
    block.triggers.push(readingTrigger(recordTrigger, sandboxModule, design));
    blocks.set(key, block);
  }
  const fieldOrder = (event: ReadingEvent) =>
    "fieldId" in event
      ? fields.findIndex((field) => field.id === event.fieldId)
      : 0;
  const ordered = [...blocks.values()].sort(
    (a, b) =>
      blockOrder[a.event.kind] - blockOrder[b.event.kind] ||
      fieldOrder(a.event) - fieldOrder(b.event),
  );

  const departmentName = (id: string) =>
    design.departments.find((item) => item.id === id)?.name ?? "Department";
  const links: ReadingLink[] = design.relationships.flatMap((relationship) => {
    const out = relationship.sourceModuleId === moduleId;
    const into = relationship.targetModuleId === moduleId;
    if (!out && !into) return [];
    const otherId = out
      ? relationship.targetModuleId
      : relationship.sourceModuleId;
    const other = design.modules.find((item) => item.id === otherId);
    const carries = relationship.fieldMappings.map(
      (mapping) =>
        fieldOf(
          sandboxModule,
          out ? mapping.sourceFieldId : mapping.targetFieldId,
        )?.name ?? "a field",
    );
    const link = (direction: "out" | "in"): ReadingLink => ({
      key: `${relationship.id}:${direction}`,
      direction,
      moduleId: otherId,
      moduleName: other?.name ?? "Unavailable module",
      departmentId: other?.departmentId ?? "",
      departmentName: other ? departmentName(other.departmentId) : "",
      carries,
    });
    // A link from a module to itself reads both ways.
    return out && into ? [link("out"), link("in")] : [link(out ? "out" : "in")];
  });

  const facts = [
    department?.name ?? "Department",
    ...(fields.length ? [plural(fields.length, "field")] : []),
    ...(own.length ? [plural(own.length, "trigger")] : []),
    ...(links.length ? [plural(links.length, "link")] : []),
  ].join(" · ");
  return {
    moduleId,
    name: sandboxModule.name,
    departmentId: sandboxModule.departmentId,
    departmentName: department?.name ?? "Department",
    facts,
    blocks: ordered,
    links,
  };
}

/** The block of a stored run's event, for a result opened from the list. */
export function blockKeyOfRun(
  reading: ModuleReading,
  event: SandboxTestEvent,
): string | undefined {
  if (event.kind !== "threshold-crossed") {
    const key = eventKey(event);
    return reading.blocks.some((block) => block.key === key) ? key : undefined;
  }
  return reading.blocks.find(
    (block) =>
      block.event.kind === "threshold-crossed" &&
      block.event.fieldId === event.fieldId,
  )?.key;
}

/** A module row of the Modules list. */
export type TestModuleRow = { id: string; name: string; triggerCount: number };

export type TestModuleGroup = {
  departmentId: string;
  departmentName: string;
  /** No live department yet: the New chip (E6). */
  isNew: boolean;
  modules: TestModuleRow[];
};

/**
 * The Modules list: open modules grouped by open department, in draft
 * order. A department is new when the bindings are known and none binds
 * it; while they load, nothing reads as new.
 */
export function testModuleGroups(
  design: SandboxDocumentDesign,
  triggers: readonly SandboxTrigger[],
  bindings: ReadonlyArray<{ kind: string; sandbox_id: string }> | null,
): TestModuleGroup[] {
  return design.departments
    .filter((department) => !department.closed)
    .map((department) => ({
      departmentId: department.id,
      departmentName: department.name,
      isNew:
        bindings !== null &&
        !bindings.some(
          (binding) =>
            binding.kind === "department" &&
            binding.sandbox_id === department.id,
        ),
      modules: design.modules
        .filter((item) => item.departmentId === department.id && !item.closed)
        .map((item) => ({
          id: item.id,
          name: item.name,
          triggerCount: moduleTriggers(triggers, item.id).length,
        })),
    }))
    .filter((group) => group.modules.length > 0);
}

/** A run request that Test can send, with what the browser changed. */
export type TryPlan = {
  moduleId: string;
  values: Record<string, SandboxFieldValue>;
  event: SandboxTestEvent;
  /** Null runs every enabled trigger. */
  triggerIds: string[] | null;
  /** Fields with no valid value: no request until they have one (E4). */
  unfillable: UnfillableField[];
  /** Fields set to meet a trigger's conditions ("Set for this trigger"). */
  setFieldIds: string[];
  /** Why a condition or a limit kept its example value. */
  notes: string[];
};

/**
 * The "Try it" request of a block (TEST-3, N9): example values shaped only
 * by the event, with every enabled trigger. A field change gets a previous
 * value that differs; a threshold gets a previous value that does not meet
 * the limit and the smallest valid new value that does. When no valid value
 * meets the limit, the examples stay and a note says why.
 */
export function tryEventPlan(
  design: SandboxDocumentDesign,
  moduleId: string,
  event: ReadingEvent,
  context: ExampleContext,
): TryPlan {
  const examples = exampleValues(design, moduleId, context);
  const values = { ...examples.values };
  const sandboxModule = design.modules.find((item) => item.id === moduleId);
  const notes: string[] = [];
  const plan = (testEvent: SandboxTestEvent): TryPlan => ({
    moduleId,
    values,
    event: testEvent,
    triggerIds: null,
    unfillable: examples.unfillable,
    setFieldIds: [],
    notes,
  });
  switch (event.kind) {
    case "record-created":
      return plan({ kind: "record-created" });
    case "schedule":
      return plan({
        kind: "schedule",
        frequency: event.frequency,
        time: event.time,
        ...(event.frequency === "weekly"
          ? { weekday: event.weekday ?? 1 }
          : {}),
      });
    case "field-changed": {
      const field = fieldOf(sandboxModule, event.fieldId);
      const current = values[event.fieldId] ?? null;
      return plan({
        kind: "field-changed",
        fieldId: event.fieldId,
        previousValue: field ? differentValue(field, current) : null,
      });
    }
    case "threshold-crossed": {
      const field = fieldOf(sandboxModule, event.fieldId);
      const limit =
        event.value.kind === "literal"
          ? event.value.value
          : (values[event.value.fieldId] ?? null);
      const current = values[event.fieldId] ?? null;
      const reached =
        field && limit !== null
          ? meetingValue(
              design,
              moduleId,
              field,
              event.operator,
              limit,
              current,
            )
          : undefined;
      if (
        !field ||
        limit === null ||
        reached === undefined ||
        reached === null
      ) {
        if (field && limit !== null)
          notes.push(
            `${valueWords(field, limit)} is outside ${field.name}'s limits; values kept.`,
          );
        return plan({
          kind: "threshold-crossed",
          fieldId: event.fieldId,
          // The example on both sides: the limit is not crossed.
          previousValue: current ?? 0,
        });
      }
      values[event.fieldId] = reached;
      return plan({
        kind: "threshold-crossed",
        fieldId: event.fieldId,
        previousValue: valueBeforeLimit(field, event.operator, limit),
      });
    }
  }
}
