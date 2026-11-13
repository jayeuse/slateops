"use client";

import { useQuery } from "@tanstack/react-query";
import { useId, type FocusEvent, type KeyboardEvent } from "react";
import type { OpenViewDataSourceField } from "../adapters/views-api";
import {
  assignableUsersOptions,
  authMeOptions,
} from "../adapters/openview-queries";
import {
  selectOptions,
  type RecordFormErrors,
  type RecordFormValue,
  type RecordFormValues,
} from "../domain/record-form";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { PersonCardPopover } from "@/components/person-card";

type RecordFormFieldsProps = {
  moduleId: string;
  fields: readonly OpenViewDataSourceField[];
  values: RecordFormValues;
  errors: RecordFormErrors;
  disabled: boolean;
  onChange: (fieldId: string, value: RecordFormValue) => void;
};

const INPUT_TYPES: Partial<Record<OpenViewDataSourceField["type"], string>> = {
  email: "email",
  url: "url",
  number: "number",
  int: "number",
  date: "date",
  datetime: "datetime-local",
};

function PersonSelect({
  id,
  moduleId,
  value,
  disabled,
  invalid,
  describedBy,
  onChange,
}: {
  id: string;
  moduleId: string;
  value: string;
  disabled: boolean;
  invalid: boolean;
  describedBy: string | undefined;
  onChange: (value: string) => void;
}) {
  const identity = useQuery(authMeOptions()).data;
  const people = useQuery(assignableUsersOptions(moduleId, ""));
  const firstPage = people.data;
  const meOnFirstPage = identity
    ? firstPage?.items.find((person) => person.id === identity.id)
    : undefined;
  // "Me" shows only when the assignable read returns the signed-in person.
  // Off a first page that has more people, one more read by the person's
  // username, which names only them, finds them (DR-SI-4.2).
  const lookUp = Boolean(
    identity && firstPage && !meOnFirstPage && firstPage.pagination.hasMore,
  );
  const found = useQuery(
    assignableUsersOptions(
      moduleId,
      identity?.username.slice(0, 100) ?? "",
      lookUp,
    ),
  );
  const me =
    meOnFirstPage ??
    (lookUp
      ? found.data?.items.find((person) => person.id === identity?.id)
      : undefined);
  const listed = (firstPage?.items ?? []).filter(
    (person) => person.id !== me?.id,
  );
  const known =
    !value || value === me?.id || listed.some((person) => person.id === value);
  const selected = !people.isError
    ? me && me.id === value
      ? me
      : listed.find((person) => person.id === value)
    : undefined;
  return (
    <>
      <Select
        id={id}
        className="min-h-11"
        value={value}
        // While the read by name runs, the options would still move.
        disabled={disabled || people.isPending || (lookUp && found.isPending)}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        onValueChange={onChange}
      >
        <option value="">
          {people.isPending
            ? "Loading people…"
            : people.isError
              ? "People could not be loaded"
              : "No one"}
        </option>
        {/* First after the empty choice; the person is not listed again
            (DR-SI-4.1). */}
        {me ? (
          <option
            value={me.id}
          >{`Me (${me.displayName ?? me.username})`}</option>
        ) : null}
        {known ? null : <option value={value}>Current person</option>}
        {listed.map((person) => (
          <option key={person.id} value={person.id}>
            {person.displayName ?? person.username}
          </option>
        ))}
      </Select>
      {selected ? (
        <PersonCardPopover
          personId={selected.id}
          label={selected.displayName ?? selected.username}
        />
      ) : null}
    </>
  );
}

/** What an in-place control on the Details tab adds to the form control. */
export type InPlaceControlProps = {
  /** The Details row label that names the control. */
  labelledBy: string;
  /** The value is saving (DR-2.4). */
  busy: boolean;
  /**
   * A commit is running (DR-2.13). The control keeps focus and stays in the
   * tab order, but takes no input: `aria-disabled`, not `disabled`, which
   * would drop the focus of the person who just used it.
   */
  locked: boolean;
  /** The lock has lasted past 300 ms: the control takes the disabled look. */
  dimmed: boolean;
  /** A date input's commit and Escape (DR-2.3). */
  onBlur?: (event: FocusEvent<HTMLInputElement>) => void;
  onKeyDown?: (event: KeyboardEvent<HTMLInputElement>) => void;
};

/**
 * The control of one field: the Edit form's, and the same control in place
 * on the Details tab (DR-2.2) when `inPlace` is given.
 */
export function FieldControl({
  id,
  moduleId,
  field,
  value,
  disabled,
  invalid,
  describedBy,
  onChange,
  inPlace,
}: {
  id: string;
  moduleId: string;
  field: OpenViewDataSourceField;
  value: RecordFormValue;
  disabled: boolean;
  invalid: boolean;
  describedBy: string | undefined;
  onChange: (value: RecordFormValue) => void;
  inPlace?: InPlaceControlProps;
}) {
  const text = typeof value === "string" ? value : "";
  const common = {
    id,
    disabled,
    "aria-invalid": invalid || undefined,
    "aria-describedby": describedBy,
    ...(inPlace
      ? {
          "aria-labelledby": inPlace.labelledBy,
          "aria-busy": inPlace.busy || undefined,
          "aria-disabled": inPlace.locked || undefined,
          "data-waiting": (inPlace.dimmed && !inPlace.busy) || undefined,
        }
      : {}),
  };
  // In place, a control is 32px from 1280px and 44px below it (G5). The
  // saving control looks busy at once; the others, locked against input,
  // take the disabled look only when the save runs past 300 ms (DR-2.13).
  // Nothing fades: only the control the person used changes at once (G1).
  const locked =
    "transition-none aria-busy:cursor-progress aria-busy:opacity-50 aria-disabled:cursor-not-allowed data-[waiting]:opacity-50";
  const height = inPlace ? `min-h-11 xl:h-8 xl:min-h-8 ${locked}` : "min-h-11";
  if (field.type === "boolean")
    return (
      <Checkbox
        {...common}
        // In place on a phone the target is 44px square: the area sits on
        // the 14px padding box of the bordered 16px box (14 + 2 × 15). From
        // 1280px the shared size stays (QA-D1, G5).
        className={
          inPlace
            ? `${locked} after:-inset-[15px] xl:after:-inset-x-3 xl:after:-inset-y-2`
            : undefined
        }
        checked={value === true}
        onCheckedChange={(checked) => onChange(checked === true)}
      />
    );
  if (field.type === "long_text")
    return (
      <Textarea
        {...common}
        rows={4}
        value={text}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  if (field.type === "select") {
    const options = selectOptions(field);
    const known = !text || options.some((option) => option.id === text);
    return (
      <Select
        {...common}
        className={height}
        value={text}
        onValueChange={onChange}
      >
        {/* In place, a required Choice list has no empty choice unless it
            holds no value yet (DR-2.3). */}
        {inPlace && field.required && text ? null : (
          <option value="">
            {field.required ? "Choose an option" : "None"}
          </option>
        )}
        {inPlace && !known ? (
          <option value={text}>Unavailable option</option>
        ) : null}
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </Select>
    );
  }
  if (field.type === "user")
    return (
      <PersonSelect
        id={id}
        moduleId={moduleId}
        value={text}
        disabled={disabled}
        invalid={invalid}
        describedBy={describedBy}
        onChange={onChange}
      />
    );
  return (
    <Input
      {...common}
      className={height}
      onBlur={inPlace?.onBlur}
      onKeyDown={inPlace?.onKeyDown}
      readOnly={inPlace?.locked || undefined}
      type={INPUT_TYPES[field.type] ?? "text"}
      inputMode={field.type === "decimal" ? "decimal" : undefined}
      step={
        field.type === "number" ? "any" : field.type === "int" ? 1 : undefined
      }
      value={text}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

/** One labelled control for each editable field of a record. */
export function RecordFormFields({
  moduleId,
  fields,
  values,
  errors,
  disabled,
  onChange,
}: RecordFormFieldsProps) {
  const prefix = useId();
  return (
    <FieldGroup className="gap-4">
      {fields.map((field) => {
        const id = `${prefix}-${field.id}`;
        const error = errors[field.id];
        const errorId = error ? `${id}-error` : undefined;
        const control = (
          <FieldControl
            id={id}
            moduleId={moduleId}
            field={field}
            value={values[field.id] ?? ""}
            disabled={disabled}
            invalid={Boolean(error)}
            describedBy={errorId}
            onChange={(value) => onChange(field.id, value)}
          />
        );
        return (
          <Field key={field.id} className="min-w-0">
            {field.type === "boolean" ? (
              <div className="flex min-h-11 items-center gap-3">
                {control}
                <FieldLabel htmlFor={id}>{field.name}</FieldLabel>
              </div>
            ) : (
              <>
                <FieldLabel htmlFor={id}>
                  {field.name}
                  {field.required ? (
                    <span className="text-muted-foreground font-normal">
                      {" "}
                      (required)
                    </span>
                  ) : null}
                </FieldLabel>
                {control}
              </>
            )}
            {error ? (
              <p id={errorId} className="text-destructive text-sm">
                {error}
              </p>
            ) : null}
          </Field>
        );
      })}
    </FieldGroup>
  );
}
