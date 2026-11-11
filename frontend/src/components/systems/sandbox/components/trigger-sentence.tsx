// The whole-trigger sentence (docs/specs/sandbox-ux-redesign.md TRIG-6):
// one plain sentence under the trigger name that follows each edit and
// replaces the per-step summaries. A missing part reads as its kind ("a
// module", "a field", "a value", "no action yet"), never as a default.

import { cn } from "@/lib/utils";
import type {
  SandboxDocumentDesign,
  SandboxDocumentField,
  SandboxDocumentModule,
  SandboxFieldReference,
  SandboxTriggerAction,
  SandboxTriggerCondition,
  SandboxValueSource,
} from "../domain/document";
import {
  draftModuleId,
  resolveReference,
  thresholdFieldFits,
  type SandboxTriggerDraft,
} from "../domain/trigger-draft";
import { operatorWords, weekdayOptions } from "./trigger-flow";

export type SentencePart = {
  text: string;
  /** A name the trigger uses, plain glue words, or a missing part. */
  kind: "plain" | "name" | "missing";
};

const plain = (text: string): SentencePart => ({ text, kind: "plain" });
const name = (text: string): SentencePart => ({ text, kind: "name" });
const missing = (text: string): SentencePart => ({ text, kind: "missing" });

/** The words after "reaches" for each threshold operator. */
const thresholdWords = {
  "=": "exactly",
  "!=": "a value other than",
  ">": "more than",
  ">=": "at least",
  "<": "less than",
  "<=": "at most",
} as const;

function closedSuffix(item: { name: string; closed: boolean }): string {
  return `${item.name}${item.closed ? " (closed)" : ""}`;
}

function fieldPart(
  reference: SandboxFieldReference,
  sandboxModule: SandboxDocumentModule | undefined,
  design: SandboxDocumentDesign,
  fits: (field: SandboxDocumentField) => boolean = () => true,
): { part: SentencePart; field: SandboxDocumentField | undefined } {
  const resolved = resolveReference(reference, sandboxModule, design);
  return resolved.state === "ok" && fits(resolved.field)
    ? { part: name(closedSuffix(resolved.field)), field: resolved.field }
    : { part: missing("a field"), field: undefined };
}

function valuePart(
  value: SandboxValueSource,
  field: SandboxDocumentField | undefined,
  sandboxModule: SandboxDocumentModule | undefined,
  design: SandboxDocumentDesign,
): SentencePart {
  if (value.kind === "field-reference") {
    const resolved = resolveReference(value, sandboxModule, design);
    return resolved.state === "ok"
      ? name(`the value of ${closedSuffix(resolved.field)}`)
      : missing("a value");
  }
  const literal = value.value;
  const blank = literal === null || literal === "";
  if (blank && (!field || field.required)) return missing("a value");
  if (blank) return name("empty");
  if (literal === true) return name("Checked");
  if (literal === false) return name("Unchecked");
  if (typeof literal === "number") return name(literal.toLocaleString("en-US"));
  if (field?.config.kind === "select")
    return name(
      field.config.options.find((option) => option.id === literal)?.label ??
        literal,
    );
  return name(literal);
}

function conditionParts(
  condition: SandboxTriggerCondition,
  sandboxModule: SandboxDocumentModule | undefined,
  design: SandboxDocumentDesign,
): SentencePart[] {
  const { part, field } = fieldPart(condition.field, sandboxModule, design);
  // With no field of the trigger's module, the operator and value belong
  // to nothing: the part reads as a missing field only (QA-2).
  if (!field) return [part];
  return [
    part,
    plain(` ${operatorWords[condition.operator]} `),
    valuePart(condition.value, field, sandboxModule, design),
  ];
}

function actionParts(
  action: SandboxTriggerAction,
  sandboxModule: SandboxDocumentModule | undefined,
  design: SandboxDocumentDesign,
): SentencePart[] {
  if (action.kind !== "set-field")
    return [plain(`${action.kind.replaceAll("-", " ")} (can't publish yet)`)];
  const { part, field } = fieldPart(action.target, sandboxModule, design);
  if (!field) return [plain("set "), part];
  return [
    plain("set "),
    part,
    plain(" to "),
    valuePart(action.value, field, sandboxModule, design),
  ];
}

function eventParts(
  draft: SandboxTriggerDraft,
  sandboxModule: SandboxDocumentModule | undefined,
  design: SandboxDocumentDesign,
): SentencePart[] {
  const moduleName = sandboxModule
    ? name(closedSuffix(sandboxModule))
    : missing("a module");
  const trigger = draft.trigger;
  switch (trigger.kind) {
    case "record-created":
      return [plain("When an item is added to "), moduleName];
    case "field-changed":
      return [
        plain("When "),
        fieldPart(trigger, sandboxModule, design).part,
        plain(" changes in "),
        moduleName,
      ];
    case "threshold-crossed": {
      const { part, field } = fieldPart(
        trigger,
        sandboxModule,
        design,
        thresholdFieldFits,
      );
      if (!field)
        return [
          plain("When "),
          part,
          plain(" reaches "),
          missing("a value"),
          plain(" in "),
          moduleName,
        ];
      return [
        plain("When "),
        part,
        plain(` reaches ${thresholdWords[trigger.operator]} `),
        valuePart(trigger.value, field, sandboxModule, design),
        plain(" in "),
        moduleName,
      ];
    }
    case "schedule": {
      const weekday = weekdayOptions.find(
        (option) => option.value === String(trigger.weekday),
      );
      return [
        plain(
          trigger.frequency === "daily"
            ? "Every day"
            : `Every ${weekday?.label ?? ""}`,
        ),
        plain(` at ${trigger.time} in `),
        moduleName,
      ];
    }
  }
}

function joined(groups: SentencePart[][], word: string): SentencePart[] {
  return groups.flatMap((group, index) =>
    index ? [plain(word), ...group] : group,
  );
}

/** The trigger as one sentence, in parts, for the editor head (TRIG-6). */
export function triggerSentence(
  draft: SandboxTriggerDraft,
  design: SandboxDocumentDesign,
): SentencePart[] {
  const moduleId = draftModuleId(draft);
  const sandboxModule = design.modules.find((item) => item.id === moduleId);
  const { conditions, operator } = draft.conditionGroup;
  return [
    ...eventParts(draft, sandboxModule, design),
    ...(conditions.length
      ? [
          plain(", if "),
          ...joined(
            conditions.map((condition) =>
              conditionParts(condition, sandboxModule, design),
            ),
            operator === "any" ? " or " : " and ",
          ),
        ]
      : []),
    plain(", "),
    ...(draft.actions.length
      ? joined(
          draft.actions.map((action) =>
            actionParts(action, sandboxModule, design),
          ),
          " and ",
        )
      : [missing("no action yet")]),
    plain("."),
  ];
}

/**
 * The sentence under the trigger name. It is the editor's description
 * (`aria-describedby`), not a live region: it follows each edit quietly.
 */
export function TriggerSentence({
  id,
  draft,
  design,
  className,
}: {
  id: string;
  draft: SandboxTriggerDraft;
  design: SandboxDocumentDesign;
  className?: string;
}) {
  return (
    <p
      id={id}
      className={cn("text-muted-foreground text-sm leading-relaxed", className)}
    >
      {triggerSentence(draft, design).map((part, index) => (
        <span
          // Parts have no identity of their own; their order is the sentence.
          key={index}
          className={
            part.kind === "name"
              ? "text-foreground font-semibold"
              : part.kind === "missing"
                ? "text-warn-text underline decoration-dashed underline-offset-4"
                : undefined
          }
        >
          {part.text}
        </span>
      ))}
    </p>
  );
}
