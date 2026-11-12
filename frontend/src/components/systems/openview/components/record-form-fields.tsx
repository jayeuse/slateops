"use client";

import { useQuery } from "@tanstack/react-query";
import { useId, type FocusEvent, type KeyboardEvent } from "react";
import type { OpenViewDataSourceField } from "../adapters/views-api";
import { assignableUsersOptions } from "../adapters/openview-queries";
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
  const people = useQuery(assignableUsersOptions(moduleId, ""));
  const listed = people.data?.items ?? [];
  const known = !value || listed.some((person) => person.id === value);
  const selected = !people.isError
    ? listed.find((person) => person.id === value)
    : undefined;
  return (
    <>
      <Select
        id={id}
        className="min-h-11"
        value={value}
        disabled={disabled || people.isPending}
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
        }
      : {}),
  };
  // In place, a control is 32px from 1280px and 44px below it (G5); while
  // locked it looks as a disabled control does.
  const locked = "aria-disabled:cursor-not-allowed aria-disabled:opacity-50";
  const height = inPlace ? `min-h-11 xl:h-8 xl:min-h-8 ${locked}` : "min-h-11";
  if (field.type === "boolean")
    return (
      <Checkbox
        {...common}
        className={inPlace ? locked : undefined}
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
