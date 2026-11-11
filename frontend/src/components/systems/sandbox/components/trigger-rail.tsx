"use client";

import { useId, type ReactNode } from "react";
import { ListFilter, Plus, SquarePen, X } from "lucide-react";
import { DepartmentMark } from "@/components/sandbox/department-mark";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Combobox,
  ComboboxCollection,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxGroup,
  ComboboxGroupLabel,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxTrigger,
} from "@/components/ui/combobox";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type {
  SandboxComparisonOperator,
  SandboxDocumentDesign,
  SandboxDocumentField,
  SandboxDocumentModule,
  SandboxFieldReference,
  SandboxTriggerAction,
  SandboxTriggerCondition,
  SandboxValueSource,
} from "../domain/document";
import { fieldTypeLabel } from "../domain/model";
import {
  addTriggerAction,
  addTriggerCondition,
  compatibleReferenceOptions,
  defaultLiteral,
  displayLiteral,
  fieldReferenceOptionValue,
  parseLiteral,
  replaceAt,
  scheduleFrequencyChange,
} from "../domain/trigger-rules";
import {
  changeTriggerEvent,
  changeTriggerModule,
  draftModuleId,
  fieldChoices,
  moduleChoiceGroups,
  operatorsForField,
  resolveReference,
  thresholdFieldFits,
  triggerDraftGaps,
  type SandboxTriggerDraft,
  type TriggerChoice,
  type TriggerChoiceGroup,
  type TriggerDraftGap,
} from "../domain/trigger-draft";
import {
  TriggerEventIcon,
  operatorWords,
  triggerStatusWord,
  weekdayOptions,
} from "./trigger-flow";

// The detail of one trigger (docs/specs/sandbox-relayout.md S5, S6, and
// docs/specs/sandbox-ux-redesign.md TRIG-2 to TRIG-7): Name and Status as
// label-left rows, then When, If, and Then on one rail. The step heads keep
// only their names; the whole-trigger sentence above the rail says what the
// trigger does. The rail renders the draft that `useTriggerDraft` owns: a
// step may be empty, and then it shows why in warn ink.

type Change = (recordTrigger: SandboxTriggerDraft) => void;

/**
 * A label-left row: a muted label column and the control on the right from
 * a 384px detail (the editor at 1280px, beside the list and the structure
 * region); narrower, the label sits above. The visible label can be shorter
 * than the control's name ("Module" names "Event module").
 *
 * A picker row (`picker`) is not a Base UI field: inside one, the Combobox
 * trigger takes the field label as its name (`aria-labelledby`), so
 * "Event module" would read "Module". Its label points at it with `htmlFor`.
 */
const settingRowClass =
  "min-w-0 gap-1.5 @min-[24rem]/detail:grid @min-[24rem]/detail:min-h-10 @min-[24rem]/detail:grid-cols-[7rem_minmax(0,1fr)] @min-[24rem]/detail:items-center @min-[24rem]/detail:gap-x-4";
const settingLabelClass = "text-muted-foreground font-normal xl:text-sm";

function SettingRow({
  id,
  label,
  picker = false,
  children,
}: {
  id: string;
  label: string;
  picker?: boolean;
  children: ReactNode;
}) {
  return picker ? (
    <div className={cn("flex flex-col", settingRowClass)}>
      <label
        htmlFor={id}
        className={cn("text-sm font-medium", settingLabelClass)}
      >
        {label}
      </label>
      {children}
    </div>
  ) : (
    <Field className={settingRowClass}>
      <FieldLabel htmlFor={id} className={settingLabelClass}>
        {label}
      </FieldLabel>
      {children}
    </Field>
  );
}

function RailStep({
  name,
  icon,
  last = false,
  children,
}: {
  name: string;
  icon: ReactNode;
  last?: boolean;
  children: ReactNode;
}) {
  const headingId = useId();
  return (
    <li className="grid grid-cols-[2rem_minmax(0,1fr)] gap-x-3.5">
      <span aria-hidden="true" className="relative flex justify-center">
        <span className="text-muted-foreground z-[1] grid size-7 place-items-center rounded-full bg-[var(--surface-sunken)] [&_svg]:size-4">
          {icon}
        </span>
        {last ? null : (
          <span className="absolute top-[1.875rem] -bottom-1.5 w-px bg-[var(--rule-strong)]" />
        )}
      </span>
      <section
        aria-labelledby={headingId}
        className={cn("grid min-w-0 gap-2", !last && "pb-6")}
      >
        <h3
          id={headingId}
          className="flex min-h-7 items-center text-sm font-semibold"
        >
          {name}
        </h3>
        {children}
      </section>
    </li>
  );
}

/**
 * The notes of a step, under the settings they belong to, in warn ink: why
 * a part is empty, what Save will refuse, and an operator that does not fit.
 */
function StepNote({
  id,
  notes,
}: {
  id: string;
  notes: ReadonlyArray<string | null | undefined>;
}) {
  const shown = notes.filter((note): note is string => Boolean(note));
  return shown.length ? (
    <p id={id} className="text-warn-text text-xs">
      {shown.join(" ")}
    </p>
  ) : null;
}

/** The warn edge of a control whose part is empty or does not fit. */
const warnEdge = "border-b-[var(--warn)]!";
const warnSelectEdge = "[&_select]:border-b-[var(--warn)]!";

/**
 * A module or field picker (TRIG-2): a search, then the choices, grouped by
 * department for modules, each with its field count or its type on the
 * right. The closed picker shows the department or the type too. An empty
 * picker carries `data-empty-part`, so Save can bring focus to it.
 */
function TriggerPicker({
  id,
  label,
  value,
  groups,
  placeholder,
  searchPlaceholder,
  missing,
  describedBy,
  onChange,
}: {
  id?: string;
  label: string;
  value: string;
  groups: readonly TriggerChoiceGroup[];
  placeholder: string;
  searchPlaceholder: string;
  missing: boolean;
  describedBy?: string;
  onChange: (value: string) => void;
}) {
  const searchLabelId = useId();
  const grouped = groups.some((group) => group.label);
  const choices = new Map<
    string,
    { choice: TriggerChoice; group: TriggerChoiceGroup }
  >(
    groups.flatMap((group) =>
      group.choices.map((choice) => [choice.value, { choice, group }] as const),
    ),
  );
  const selected = choices.get(value);
  const item = (choiceValue: string) => {
    const entry = choices.get(choiceValue);
    if (!entry) return null;
    return (
      <ComboboxItem
        key={choiceValue}
        value={choiceValue}
        // One name for the row: "Status, Choice list" or "Orders, 6 fields".
        aria-label={`${entry.choice.label}, ${entry.choice.meta}`}
      >
        <span className="flex min-w-0 items-baseline gap-2">
          <span className="min-w-0 flex-1 break-words">
            {entry.choice.label}
          </span>
          <span
            className={cn(
              "text-muted-foreground shrink-0 text-xs",
              !grouped && "font-mono",
            )}
          >
            {entry.choice.meta}
          </span>
        </span>
      </ComboboxItem>
    );
  };
  return (
    <Combobox
      items={
        grouped
          ? groups.map((group) => ({
              value: group.label,
              items: group.choices.map((choice) => choice.value),
            }))
          : [...choices.keys()]
      }
      value={selected ? value : null}
      itemToStringLabel={(choiceValue) =>
        typeof choiceValue === "string"
          ? (choices.get(choiceValue)?.choice.label ?? "")
          : ""
      }
      onValueChange={(next) => {
        if (typeof next === "string") onChange(next);
      }}
    >
      <ComboboxTrigger
        id={id}
        aria-label={label}
        aria-describedby={describedBy}
        data-empty-part={missing || undefined}
        className={cn("h-8 min-w-0 px-2.5", missing && warnEdge)}
      >
        {selected ? (
          <span className="flex min-w-0 flex-1 items-baseline gap-2">
            {grouped ? (
              <DepartmentMark
                departmentIndex={selected.group.departmentIndex}
                className="self-center"
              />
            ) : null}
            <span className="min-w-0 truncate">{selected.choice.label}</span>
            {grouped ? (
              <span className="text-muted-foreground shrink-0 truncate">
                · {selected.group.label}
              </span>
            ) : (
              <span className="text-muted-foreground ml-auto shrink-0 font-mono text-xs">
                {selected.choice.meta}
              </span>
            )}
          </span>
        ) : (
          <span className="text-muted-foreground truncate">{placeholder}</span>
        )}
      </ComboboxTrigger>
      <ComboboxContent positionerClassName="z-[60]">
        <span id={searchLabelId} className="sr-only">
          {`Search ${label.toLowerCase()}`}
        </span>
        <ComboboxInput
          aria-labelledby={searchLabelId}
          placeholder={searchPlaceholder}
        />
        <ComboboxList>
          {grouped
            ? (group: { value: string; items: string[] }) => {
                const department = groups.find(
                  (entry) => entry.label === group.value,
                );
                return (
                  <ComboboxGroup key={group.value} items={group.items}>
                    <ComboboxGroupLabel className="flex items-center gap-2">
                      <DepartmentMark
                        departmentIndex={department?.departmentIndex ?? 0}
                      />
                      {group.value}
                    </ComboboxGroupLabel>
                    <ComboboxCollection>
                      {(choiceValue: string) => item(choiceValue)}
                    </ComboboxCollection>
                  </ComboboxGroup>
                );
              }
            : (choiceValue: string) => item(choiceValue)}
        </ComboboxList>
        <ComboboxEmpty className="text-muted-foreground p-3 text-sm empty:p-0">
          No matches. Try another search.
        </ComboboxEmpty>
      </ComboboxContent>
    </Combobox>
  );
}

/** A field picker for the trigger's module, with each field's type. */
function FieldPicker({
  fields,
  ...props
}: Omit<
  Parameters<typeof TriggerPicker>[0],
  "groups" | "placeholder" | "searchPlaceholder"
> & { fields: readonly SandboxDocumentField[] }) {
  return (
    <TriggerPicker
      {...props}
      groups={[
        { label: "", departmentIndex: 0, choices: fieldChoices(fields) },
      ]}
      placeholder="Choose a field"
      searchPlaceholder="Find a field"
    />
  );
}

/**
 * The operator choice (TRIG-3, TRIG-4): only the operators that fit the
 * field. A saved operator that does not fit stays selected, listed last as
 * "saved · does not fit", until the person picks another.
 */
function OperatorSelect({
  id,
  label,
  value,
  field,
  className,
  describedBy,
  onChange,
}: {
  id?: string;
  label: string;
  value: SandboxComparisonOperator;
  field: SandboxDocumentField | undefined;
  className?: string;
  describedBy?: string;
  onChange: (operator: SandboxComparisonOperator) => void;
}) {
  const offered = operatorsForField(field);
  const fits = offered.includes(value);
  // No field yet (or not one of this module): nothing to choose (QA-2).
  if (!field)
    return (
      <NativeSelect
        id={id}
        aria-label={label}
        aria-describedby={describedBy}
        className={cn("w-full", className)}
        value=""
        disabled
        onChange={() => undefined}
      >
        <NativeSelectOption value="">No field yet</NativeSelectOption>
      </NativeSelect>
    );
  return (
    <NativeSelect
      id={id}
      aria-label={label}
      aria-describedby={describedBy}
      className={cn("w-full", !fits && warnSelectEdge, className)}
      value={value}
      onChange={(event) =>
        onChange(event.target.value as SandboxComparisonOperator)
      }
    >
      {offered.map((operator) => (
        <NativeSelectOption key={operator} value={operator}>
          {operatorWords[operator]}
        </NativeSelectOption>
      ))}
      {fits ? null : (
        <NativeSelectOption value={value} className="text-muted-foreground">
          {`${operatorWords[value]} · saved · does not fit`}
        </NativeSelectOption>
      )}
    </NativeSelect>
  );
}

/** "Does not fit Text; choose is or is not." for a saved misfit operator. */
function operatorNote(
  operator: SandboxComparisonOperator,
  field: SandboxDocumentField | undefined,
): string | null {
  const offered = operatorsForField(field);
  if (!field || offered.includes(operator)) return null;
  return `Does not fit ${fieldTypeLabel(field.type)}; choose ${offered.map((item) => operatorWords[item]).join(" or ")}.`;
}

function ValueEditor({
  design,
  trigger: recordTrigger,
  target,
  value,
  onChange,
  layout,
}: {
  design: SandboxDocumentDesign;
  trigger: SandboxTriggerDraft;
  target?: SandboxDocumentField | undefined;
  value: SandboxValueSource;
  onChange: (value: SandboxValueSource) => void;
  /** A label-left row (the When threshold), or a cell of an inline row. */
  layout: "row" | "inline";
}) {
  const id = useId();
  const references = compatibleReferenceOptions(design, recordTrigger, target);
  const label = value.kind === "literal" ? "Value" : "Another field";
  const named = layout === "inline" ? { "aria-label": label } : {};
  // Another field as the value is rare: one quiet toggle beside the value,
  // shown only when a compatible field exists.
  const sourceToggle = references[0] ? (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="text-muted-foreground shrink-0 px-2 font-normal max-xl:min-h-11"
      onClick={() =>
        onChange(
          value.kind === "literal"
            ? { kind: "field-reference", ...references[0]!.reference }
            : defaultLiteral(target),
        )
      }
    >
      {value.kind === "literal" ? "Use a field" : "Use fixed value"}
    </Button>
  ) : null;
  const control = !target ? (
    // No field yet: nothing to type a value for.
    <Input
      id={id}
      {...named}
      className="min-w-0 flex-1"
      disabled
      placeholder="Choose a field first"
      value=""
      readOnly
    />
  ) : value.kind === "field-reference" ? (
    <NativeSelect
      id={id}
      {...named}
      className="min-w-0 flex-1"
      value={fieldReferenceOptionValue(value)}
      onChange={(event) => {
        const option = references.find(
          (item) => item.value === event.target.value,
        );
        if (option) onChange({ kind: "field-reference", ...option.reference });
      }}
    >
      {references.some(
        (option) => option.value === fieldReferenceOptionValue(value),
      ) ? null : (
        <NativeSelectOption value={fieldReferenceOptionValue(value)}>
          Choose a field
        </NativeSelectOption>
      )}
      {references.map((option) => (
        <NativeSelectOption key={option.value} value={option.value}>
          {option.label}
        </NativeSelectOption>
      ))}
    </NativeSelect>
  ) : target.config.kind === "select" ? (
    <NativeSelect
      id={id}
      {...named}
      className="min-w-0 flex-1"
      value={typeof value.value === "string" ? value.value : ""}
      onChange={(event) =>
        onChange({ kind: "literal", value: event.target.value || null })
      }
    >
      <NativeSelectOption value="">Empty</NativeSelectOption>
      {target.config.options.map((option) => (
        <NativeSelectOption key={option.id} value={option.id}>
          {option.label}
        </NativeSelectOption>
      ))}
    </NativeSelect>
  ) : target.config.kind === "checkbox" ? (
    <NativeSelect
      id={id}
      {...named}
      className="min-w-0 flex-1"
      value={String(value.value)}
      onChange={(event) =>
        onChange({ kind: "literal", value: event.target.value === "true" })
      }
    >
      <NativeSelectOption value="true">Checked</NativeSelectOption>
      <NativeSelectOption value="false">Unchecked</NativeSelectOption>
    </NativeSelect>
  ) : target.config.kind === "long-text" ? (
    <Textarea
      id={id}
      {...named}
      className="min-w-0 flex-1"
      value={displayLiteral(value.value)}
      required={target.required}
      maxLength={target.config.maxLength}
      onChange={(event) =>
        onChange({
          kind: "literal",
          value: parseLiteral(event.target.value, target),
        })
      }
    />
  ) : (
    <Input
      id={id}
      {...named}
      className="min-w-0 flex-1"
      type={
        target.config.kind === "number" || target.config.kind === "integer"
          ? "number"
          : target.config.kind === "email"
            ? "email"
            : target.config.kind === "url"
              ? "url"
              : target.config.kind === "date"
                ? "date"
                : target.config.kind === "datetime"
                  ? "datetime-local"
                  : "text"
      }
      value={displayLiteral(value.value)}
      required={target.required}
      min={
        target.config.kind === "number" || target.config.kind === "integer"
          ? target.config.min
          : target.config.kind === "date" || target.config.kind === "datetime"
            ? target.config.earliest
            : undefined
      }
      max={
        target.config.kind === "number" || target.config.kind === "integer"
          ? target.config.max
          : target.config.kind === "date" || target.config.kind === "datetime"
            ? target.config.latest
            : undefined
      }
      step={
        target.config.kind === "number" || target.config.kind === "integer"
          ? target.config.step
          : undefined
      }
      maxLength={
        target.config.kind === "text" ||
        target.config.kind === "email" ||
        target.config.kind === "url"
          ? target.config.maxLength
          : undefined
      }
      onChange={(event) =>
        onChange({
          kind: "literal",
          value: parseLiteral(event.target.value, target),
        })
      }
    />
  );
  const cell = (
    <div className="flex min-w-0 items-center gap-1">
      {control}
      {target ? sourceToggle : null}
    </div>
  );
  return layout === "row" ? (
    <SettingRow id={id} label={label}>
      {cell}
    </SettingRow>
  ) : (
    cell
  );
}

/** The remove control of an inline row: a quiet ×, named for its row. */
function RemoveButton({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={label}
      className="text-muted-foreground hover:text-danger-text size-11"
      onClick={onClick}
    >
      <X aria-hidden="true" />
    </Button>
  );
}

/** Adds a condition or an action, under the rows of its step. */
function AddButton({
  children,
  disabled,
  missing = false,
  onClick,
}: {
  children: ReactNode;
  disabled: boolean;
  missing?: boolean;
  onClick: () => void;
}) {
  return (
    <Button
      variant="ghost"
      className="text-foreground -ml-2 min-h-11 justify-self-start"
      disabled={disabled}
      data-empty-part={missing || undefined}
      onClick={onClick}
    >
      <Plus aria-hidden="true" />
      {children}
    </Button>
  );
}

/** What the rail knows about a field reference of the trigger's module. */
function referenced(
  reference: SandboxFieldReference,
  sandboxModule: SandboxDocumentModule | undefined,
  design: SandboxDocumentDesign,
): SandboxDocumentField | undefined {
  const resolved = resolveReference(reference, sandboxModule, design);
  return resolved.state === "ok" ? resolved.field : undefined;
}

export function TriggerRail({
  design,
  trigger: recordTrigger,
  stepErrors,
  pending,
  locked,
  onChange,
}: {
  design: SandboxDocumentDesign;
  trigger: SandboxTriggerDraft;
  /**
   * Fixed values Save will refuse, by step (see `triggerStepErrors`), less
   * the new steps nobody has touched yet. Each step group carries its key
   * in `data-step-key`.
   */
  stepErrors: ReadonlyMap<string, string>;
  pending: boolean;
  /** Read-only while kept edits wait; the fieldset does not reach Switch. */
  locked: boolean;
  onChange: Change;
}) {
  const nameId = useId();
  const statusId = useId();
  const statusWordId = useId();
  const statusNoteId = useId();
  const gaps = triggerDraftGaps(recordTrigger, design);
  const moduleId = draftModuleId(recordTrigger);
  const sandboxModule = design.modules.find((item) => item.id === moduleId);
  const fields = sandboxModule?.fields.filter((field) => !field.closed) ?? [];
  return (
    <fieldset
      className="grid min-w-0 gap-5 border-0 p-0"
      disabled={pending}
      aria-busy={pending}
    >
      <div className="grid gap-3 @min-[24rem]/detail:gap-2">
        <SettingRow id={nameId} label="Name">
          <Input
            id={nameId}
            aria-label="Trigger name"
            value={recordTrigger.name}
            onChange={(event) =>
              onChange({ ...recordTrigger, name: event.target.value })
            }
          />
        </SettingRow>
        <SettingRow id={statusId} label="Status">
          {/* The word says the state the switch is in (S6); Off adds what
              that means for the published workspace. */}
          <div className="flex min-h-11 items-center gap-2.5 xl:min-h-8">
            <Switch
              id={statusId}
              aria-label="Trigger status"
              aria-describedby={
                recordTrigger.enabled
                  ? statusWordId
                  : `${statusWordId} ${statusNoteId}`
              }
              disabled={pending || locked}
              checked={recordTrigger.enabled}
              onCheckedChange={(checked) =>
                onChange({ ...recordTrigger, enabled: checked })
              }
            />
            {/* The word is the switch's label too, so the tap target runs
                past the small track on a phone (EXIT-9, S25). */}
            <label
              id={statusWordId}
              htmlFor={statusId}
              data-sandbox-touch-label
              className={cn(
                "flex cursor-pointer items-center text-sm font-medium xl:min-h-8",
                !recordTrigger.enabled && "text-muted-foreground",
                (pending || locked) && "cursor-not-allowed",
              )}
            >
              {triggerStatusWord(recordTrigger.enabled)}
            </label>
            {recordTrigger.enabled ? null : (
              <span id={statusNoteId} className="text-muted-foreground text-sm">
                · won&apos;t run after publish
              </span>
            )}
          </div>
        </SettingRow>
      </div>
      <ol aria-label="Flow" className="grid min-w-0">
        <RailStep
          name="When"
          icon={<TriggerEventIcon kind={recordTrigger.trigger.kind} />}
        >
          <WhenSettings
            design={design}
            trigger={recordTrigger}
            sandboxModule={sandboxModule}
            fields={fields}
            gap={gaps.find((gap) => gap.step === "trigger")}
            note={stepErrors.get("trigger")}
            onChange={onChange}
          />
        </RailStep>
        <RailStep name="If" icon={<ListFilter />}>
          <Conditions
            design={design}
            trigger={recordTrigger}
            sandboxModule={sandboxModule}
            fields={fields}
            gaps={gaps}
            stepErrors={stepErrors}
            onChange={onChange}
          />
        </RailStep>
        <RailStep name="Then" icon={<SquarePen />} last>
          <Actions
            design={design}
            trigger={recordTrigger}
            sandboxModule={sandboxModule}
            fields={fields}
            gaps={gaps}
            stepErrors={stepErrors}
            onChange={onChange}
          />
        </RailStep>
      </ol>
    </fieldset>
  );
}

function WhenSettings({
  design,
  trigger: recordTrigger,
  sandboxModule,
  fields,
  gap,
  note,
  onChange,
}: {
  design: SandboxDocumentDesign;
  trigger: SandboxTriggerDraft;
  sandboxModule: SandboxDocumentModule | undefined;
  fields: readonly SandboxDocumentField[];
  /** The step's first empty part, if any. */
  gap: TriggerDraftGap | undefined;
  note: string | undefined;
  onChange: Change;
}) {
  const eventId = useId();
  const moduleId = useId();
  const frequencyId = useId();
  const timeId = useId();
  const weekdayId = useId();
  const fieldId = useId();
  const operatorId = useId();
  const noteId = useId();
  const trigger = recordTrigger.trigger;
  const watched =
    trigger.kind === "field-changed" || trigger.kind === "threshold-crossed"
      ? referenced(trigger, sandboxModule, design)
      : undefined;
  const eventFields =
    trigger.kind === "threshold-crossed"
      ? fields.filter(thresholdFieldFits)
      : fields;
  const fitsEvent =
    watched !== undefined &&
    (trigger.kind !== "threshold-crossed" || thresholdFieldFits(watched));
  const notes = [gap?.reason, note];
  const describedBy = notes.some(Boolean) ? noteId : undefined;
  return (
    <div
      role="group"
      aria-label="When settings"
      data-step-key="trigger"
      aria-describedby={describedBy}
      className="grid min-w-0 gap-3 @min-[24rem]/detail:gap-2"
    >
      {/* Module first, then the event (T2): nothing is chosen for you. */}
      <SettingRow id={moduleId} label="Module" picker>
        <TriggerPicker
          id={moduleId}
          label="Event module"
          value={sandboxModule ? sandboxModule.id : ""}
          groups={moduleChoiceGroups(design)}
          placeholder="Choose a module"
          searchPlaceholder="Find a module"
          missing={gap?.part === "module"}
          describedBy={gap?.part === "module" ? noteId : undefined}
          onChange={(next) =>
            onChange(changeTriggerModule(recordTrigger, next))
          }
        />
      </SettingRow>
      <SettingRow id={eventId} label="Event">
        <NativeSelect
          id={eventId}
          className="w-full"
          value={trigger.kind}
          onChange={(event) =>
            onChange(
              changeTriggerEvent(
                recordTrigger,
                event.target.value as SandboxTriggerDraft["trigger"]["kind"],
                design,
              ),
            )
          }
        >
          <NativeSelectOption value="record-created">
            Item added
          </NativeSelectOption>
          <NativeSelectOption value="field-changed">
            Field changed
          </NativeSelectOption>
          <NativeSelectOption value="threshold-crossed">
            Threshold crossed
          </NativeSelectOption>
          <NativeSelectOption value="schedule">Schedule</NativeSelectOption>
        </NativeSelect>
      </SettingRow>
      {trigger.kind === "schedule" ? (
        <>
          <SettingRow id={frequencyId} label="Frequency">
            <NativeSelect
              id={frequencyId}
              className="w-full"
              value={trigger.frequency}
              onChange={(event) =>
                onChange({
                  ...recordTrigger,
                  trigger: scheduleFrequencyChange(
                    trigger,
                    event.target.value as "daily" | "weekly",
                  ),
                })
              }
            >
              <NativeSelectOption value="daily">Daily</NativeSelectOption>
              <NativeSelectOption value="weekly">Weekly</NativeSelectOption>
            </NativeSelect>
          </SettingRow>
          {trigger.frequency === "weekly" ? (
            <SettingRow id={weekdayId} label="Weekday">
              <NativeSelect
                id={weekdayId}
                className="w-full"
                value={String(trigger.weekday ?? 1)}
                onChange={(event) =>
                  onChange({
                    ...recordTrigger,
                    trigger: {
                      ...trigger,
                      weekday: Number(event.target.value),
                    },
                  })
                }
              >
                {weekdayOptions.map((weekday) => (
                  <NativeSelectOption key={weekday.value} value={weekday.value}>
                    {weekday.label}
                  </NativeSelectOption>
                ))}
              </NativeSelect>
            </SettingRow>
          ) : null}
          <SettingRow id={timeId} label="Time">
            <Input
              id={timeId}
              type="time"
              className="max-w-40"
              value={trigger.time}
              onChange={(event) =>
                onChange({
                  ...recordTrigger,
                  trigger: { ...trigger, time: event.target.value },
                })
              }
            />
          </SettingRow>
        </>
      ) : null}
      {sandboxModule &&
      (trigger.kind === "field-changed" ||
        trigger.kind === "threshold-crossed") ? (
        <SettingRow id={fieldId} label="Field" picker>
          <FieldPicker
            id={fieldId}
            label="Event field"
            fields={eventFields}
            value={fitsEvent ? trigger.fieldId : ""}
            missing={gap?.part === "field"}
            describedBy={gap?.part === "field" ? noteId : undefined}
            onChange={(next) => {
              const nextField = eventFields.find((item) => item.id === next);
              onChange({
                ...recordTrigger,
                trigger:
                  trigger.kind === "field-changed"
                    ? { ...trigger, fieldId: next }
                    : {
                        ...trigger,
                        fieldId: next,
                        value: defaultLiteral(nextField),
                      },
              });
            }}
          />
        </SettingRow>
      ) : null}
      {sandboxModule && trigger.kind === "threshold-crossed" ? (
        <>
          <SettingRow id={operatorId} label="Operator">
            <OperatorSelect
              id={operatorId}
              label="Threshold operator"
              value={trigger.operator}
              field={fitsEvent ? watched : undefined}
              onChange={(operator) =>
                onChange({
                  ...recordTrigger,
                  trigger: { ...trigger, operator },
                })
              }
            />
          </SettingRow>
          <ValueEditor
            layout="row"
            design={design}
            trigger={recordTrigger}
            target={fitsEvent ? watched : undefined}
            value={trigger.value}
            onChange={(value) =>
              onChange({ ...recordTrigger, trigger: { ...trigger, value } })
            }
          />
        </>
      ) : null}
      <StepNote id={noteId} notes={notes} />
    </div>
  );
}

// An inline row (TRIG layout): one line from a 704px detail (1600px wide
// screens); narrower, two lines, the field then operator and value; on a
// phone, the field, the operator, and the value each take a line.
const inlineRow =
  "grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-2 gap-y-2 @min-[24rem]/detail:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto] @min-[44rem]/detail:grid-cols-[minmax(0,1fr)_8rem_minmax(0,1.4fr)_auto]";
const firstCell =
  "col-start-1 row-start-1 @min-[24rem]/detail:col-span-2 @min-[44rem]/detail:col-span-1";
const secondCell =
  "col-start-1 row-start-2 @min-[44rem]/detail:col-start-2 @min-[44rem]/detail:row-start-1";
const valueCell =
  "col-start-1 row-start-3 @min-[24rem]/detail:col-start-2 @min-[24rem]/detail:row-start-2 @min-[44rem]/detail:col-start-3 @min-[44rem]/detail:row-start-1";
const removeCell =
  "col-start-2 row-start-1 @min-[24rem]/detail:col-start-3 @min-[44rem]/detail:col-start-4";

function Conditions({
  design,
  trigger: recordTrigger,
  sandboxModule,
  fields,
  gaps,
  stepErrors,
  onChange,
}: {
  design: SandboxDocumentDesign;
  trigger: SandboxTriggerDraft;
  sandboxModule: SandboxDocumentModule | undefined;
  fields: readonly SandboxDocumentField[];
  gaps: readonly TriggerDraftGap[];
  stepErrors: ReadonlyMap<string, string>;
  onChange: Change;
}) {
  const baseId = useId();
  const conditions = recordTrigger.conditionGroup.conditions;
  const update = (index: number, condition: SandboxTriggerCondition) =>
    onChange({
      ...recordTrigger,
      conditionGroup: {
        ...recordTrigger.conditionGroup,
        conditions: replaceAt(conditions, index, condition),
      },
    });
  return (
    <div className="grid min-w-0 gap-2">
      {/* With no condition the trigger runs every time. */}
      {conditions.length ? null : (
        <p className="text-muted-foreground text-sm">Always</p>
      )}
      {/* All or Any matters only from two conditions. */}
      {conditions.length >= 2 ? (
        <NativeSelect
          aria-label="Condition group operator"
          className="w-full max-w-60"
          value={recordTrigger.conditionGroup.operator}
          onChange={(event) =>
            onChange({
              ...recordTrigger,
              conditionGroup: {
                ...recordTrigger.conditionGroup,
                operator: event.target.value as "all" | "any",
              },
            })
          }
        >
          <NativeSelectOption value="all">
            All conditions match
          </NativeSelectOption>
          <NativeSelectOption value="any">
            Any condition matches
          </NativeSelectOption>
        </NativeSelect>
      ) : null}
      {conditions.map((condition, index) => {
        const step = `condition:${condition.id}`;
        const gap = gaps.find((item) => item.step === step);
        const target = referenced(condition.field, sandboxModule, design);
        const noteId = `${baseId}-condition-${index}`;
        const notes = [
          gap?.reason,
          stepErrors.get(step),
          operatorNote(condition.operator, target),
        ];
        const describedBy = notes.some(Boolean) ? noteId : undefined;
        return (
          <div
            key={condition.id}
            role="group"
            aria-label={`Condition ${index + 1}`}
            data-step-key={step}
            aria-describedby={describedBy}
            className="grid min-w-0 gap-1"
          >
            <div className={inlineRow}>
              <div className={cn("min-w-0", firstCell)}>
                <FieldPicker
                  label={`Condition ${index + 1} field`}
                  fields={fields}
                  value={target ? target.id : ""}
                  missing={gap?.part === "field"}
                  describedBy={gap?.part === "field" ? noteId : undefined}
                  onChange={(next) => {
                    const field = fields.find((item) => item.id === next);
                    if (!sandboxModule || !field) return;
                    update(index, {
                      ...condition,
                      field: { moduleId: sandboxModule.id, fieldId: next },
                      value: defaultLiteral(field),
                    });
                  }}
                />
              </div>
              <OperatorSelect
                label={`Condition ${index + 1} operator`}
                className={secondCell}
                value={condition.operator}
                field={target}
                describedBy={describedBy}
                onChange={(operator) =>
                  update(index, { ...condition, operator })
                }
              />
              <div className={cn("min-w-0", valueCell)}>
                <ValueEditor
                  layout="inline"
                  design={design}
                  trigger={recordTrigger}
                  target={target}
                  value={condition.value}
                  onChange={(value) => update(index, { ...condition, value })}
                />
              </div>
              <div className={removeCell}>
                <RemoveButton
                  label={`Remove condition ${index + 1}`}
                  onClick={() =>
                    onChange({
                      ...recordTrigger,
                      conditionGroup: {
                        ...recordTrigger.conditionGroup,
                        conditions: conditions.filter(
                          (item) => item.id !== condition.id,
                        ),
                      },
                    })
                  }
                />
              </div>
            </div>
            <StepNote id={noteId} notes={notes} />
          </div>
        );
      })}
      {sandboxModule ? (
        <AddButton
          disabled={conditions.length >= 20}
          onClick={() => onChange(addTriggerCondition(recordTrigger, design))}
        >
          Add condition
        </AddButton>
      ) : null}
    </div>
  );
}

function Actions({
  design,
  trigger: recordTrigger,
  sandboxModule,
  fields,
  gaps,
  stepErrors,
  onChange,
}: {
  design: SandboxDocumentDesign;
  trigger: SandboxTriggerDraft;
  sandboxModule: SandboxDocumentModule | undefined;
  fields: readonly SandboxDocumentField[];
  gaps: readonly TriggerDraftGap[];
  stepErrors: ReadonlyMap<string, string>;
  onChange: Change;
}) {
  const baseId = useId();
  const emptyId = `${baseId}-empty`;
  const update = (index: number, action: SandboxTriggerAction) =>
    onChange({
      ...recordTrigger,
      actions: replaceAt(recordTrigger.actions, index, action),
    });
  const noActions = gaps.find((gap) => gap.step === "actions");
  return (
    <div
      className="grid min-w-0 gap-2"
      data-step-key="actions"
      aria-describedby={sandboxModule && noActions ? emptyId : undefined}
    >
      {recordTrigger.actions.map((action, index) => {
        const step = `action:${action.id}`;
        const noteId = `${baseId}-action-${index}`;
        const remove = (
          <div className={removeCell}>
            <RemoveButton
              label={`Remove action ${index + 1}`}
              onClick={() =>
                onChange({
                  ...recordTrigger,
                  actions: recordTrigger.actions.filter(
                    (item) => item.id !== action.id,
                  ),
                })
              }
            />
          </div>
        );
        if (action.kind !== "set-field")
          return (
            <div
              key={action.id}
              role="group"
              aria-label={`Action ${index + 1}`}
              className="grid min-w-0 gap-2"
            >
              <div className="flex min-w-0 items-center justify-between gap-2">
                <p className="text-warn-text min-w-0 text-sm font-medium">
                  {`${action.kind.charAt(0).toUpperCase()}${action.kind.slice(1)} · can't publish yet`}
                </p>
                {remove}
              </div>
              <Alert variant="destructive" role="alert">
                This imported action is not supported for publishing. Remove it
                or replace it with Set field.
              </Alert>
            </div>
          );
        const gap = gaps.find((item) => item.step === step);
        const target = referenced(action.target, sandboxModule, design);
        const notes = [gap?.reason, stepErrors.get(step)];
        return (
          <div
            key={action.id}
            role="group"
            aria-label={`Action ${index + 1}`}
            data-step-key={step}
            aria-describedby={notes.some(Boolean) ? noteId : undefined}
            className="grid min-w-0 gap-1"
          >
            <div className={inlineRow}>
              <div className={cn("min-w-0", firstCell)}>
                <FieldPicker
                  label="Set field target"
                  fields={fields}
                  value={target ? target.id : ""}
                  missing={gap?.part === "field"}
                  describedBy={gap?.part === "field" ? noteId : undefined}
                  onChange={(next) => {
                    const field = fields.find((item) => item.id === next);
                    if (!sandboxModule || !field) return;
                    update(index, {
                      ...action,
                      target: { moduleId: sandboxModule.id, fieldId: next },
                      value: defaultLiteral(field),
                    });
                  }}
                />
              </div>
              <span
                aria-hidden="true"
                className="text-muted-foreground hidden text-center text-sm @min-[44rem]/detail:col-start-2 @min-[44rem]/detail:row-start-1 @min-[44rem]/detail:block"
              >
                set to
              </span>
              {/* Narrower, the hidden "set to" frees the second line. */}
              <div className="col-start-1 row-start-2 min-w-0 @min-[24rem]/detail:col-span-2 @min-[44rem]/detail:col-span-1 @min-[44rem]/detail:col-start-3 @min-[44rem]/detail:row-start-1">
                <ValueEditor
                  layout="inline"
                  design={design}
                  trigger={recordTrigger}
                  target={target}
                  value={action.value}
                  onChange={(value) => update(index, { ...action, value })}
                />
              </div>
              {remove}
            </div>
            <StepNote id={noteId} notes={notes} />
          </div>
        );
      })}
      {sandboxModule ? (
        <>
          {/* Then offers only what publishes (TRIG-7): Set a field on the
              trigger's own module. */}
          <AddButton
            disabled={recordTrigger.actions.length >= 20}
            missing={Boolean(noActions)}
            onClick={() => onChange(addTriggerAction(recordTrigger, design))}
          >
            Add action
          </AddButton>
          <StepNote id={emptyId} notes={[noActions?.reason]} />
        </>
      ) : (
        <p className="text-muted-foreground text-sm">Choose a module first.</p>
      )}
    </div>
  );
}
