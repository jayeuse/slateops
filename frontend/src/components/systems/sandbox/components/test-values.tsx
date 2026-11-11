"use client";

import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import type { WorkspaceRegion } from "@/lib/date-time-display";
import type {
  SandboxDocumentField,
  SandboxFieldValue,
} from "../domain/document";
import { fieldValueText } from "../domain/test-run-summary";
import { TestValueRow } from "./test-setup-rows";

// "Values used" in a Test result (docs/specs/sandbox-ux-redesign.md TEST-4,
// TEST-5, E2, E3, E10): the example values a run used, read as words; in
// "Change values" each row becomes a slim input with an "Edited" mark, and
// a "Triggers" row chooses the listening triggers that run.

export type ValuesTriggerChoice = { id: string; name: string };

type Props = {
  fields: readonly SandboxDocumentField[];
  values: Readonly<Record<string, SandboxFieldValue>>;
  /** The values the run started from, for the "Edited" marks. */
  startValues: Readonly<Record<string, SandboxFieldValue>>;
  /** Fields a "Try this trigger" set to meet its conditions. */
  setFieldIds: readonly string[];
  /** The event's previous value, shown and sent as "<field> before". */
  before: { label: string; text: string } | null;
  administrator: { id: string; name: string } | null;
  /** The workspace region, for dates in read mode. */
  region: WorkspaceRegion | undefined;
  editing: boolean;
  idPrefix: string;
  /** Fields whose settings allow no value: named until they get one (E4). */
  needed: ReadonlySet<string>;
  /** The Triggers row, only for an event run. */
  triggerChoices: readonly ValuesTriggerChoice[] | null;
  checkedTriggerIds: readonly string[];
  onValue: (fieldId: string, value: SandboxFieldValue) => void;
  onCheckTrigger: (triggerId: string, checked: boolean) => void;
};

export function TestValues({
  fields,
  values,
  startValues,
  setFieldIds,
  before,
  administrator,
  region,
  editing,
  idPrefix,
  needed,
  triggerChoices,
  checkedTriggerIds,
  onValue,
  onCheckTrigger,
}: Props) {
  if (!editing)
    return (
      <dl className="grid grid-cols-[minmax(6rem,auto)_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
        {fields.map((field) => (
          <div key={field.id} className="contents">
            <dt className="text-muted-foreground [overflow-wrap:anywhere]">
              {field.name}
            </dt>
            <dd className="flex min-w-0 flex-wrap items-center gap-2 [overflow-wrap:anywhere]">
              {fieldValueText(field, values[field.id], administrator, region)}
              {setFieldIds.includes(field.id) ? (
                <Badge variant="secondary">Set for this trigger</Badge>
              ) : null}
            </dd>
          </div>
        ))}
        {before ? (
          <div className="contents">
            <dt className="text-muted-foreground">{before.label}</dt>
            <dd>{before.text}</dd>
          </div>
        ) : null}
      </dl>
    );
  return (
    <div className="@container/setup grid gap-3">
      {fields.map((field) => (
        <TestValueRow
          key={field.id}
          idPrefix={idPrefix}
          field={field}
          value={values[field.id] ?? null}
          edited={!Object.is(values[field.id], startValues[field.id])}
          error={
            needed.has(field.id)
              ? "Its settings allow no value. Enter one to run."
              : undefined
          }
          onChange={(value) => onValue(field.id, value)}
        />
      ))}
      {triggerChoices ? (
        <fieldset className="grid gap-1 @min-[22rem]/setup:grid-cols-[7rem_minmax(0,1fr)] @min-[22rem]/setup:gap-x-3">
          <legend className="text-muted-foreground float-left text-sm @min-[22rem]/setup:min-h-8">
            Triggers
          </legend>
          <div className="grid gap-0.5">
            {triggerChoices.map((choice) => (
              <label
                key={choice.id}
                htmlFor={`${idPrefix}-trigger-${choice.id}`}
                className="flex min-h-11 items-center gap-2 text-sm xl:min-h-8"
              >
                <Checkbox
                  id={`${idPrefix}-trigger-${choice.id}`}
                  checked={checkedTriggerIds.includes(choice.id)}
                  onCheckedChange={(checked) =>
                    onCheckTrigger(choice.id, checked)
                  }
                />
                {choice.name}
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}
    </div>
  );
}
