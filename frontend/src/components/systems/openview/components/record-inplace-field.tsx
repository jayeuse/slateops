"use client";

import { useState } from "react";
import type { OpenViewDataSourceField } from "../adapters/views-api";
import type { RecordFormValue } from "../domain/record-form";
import type { InPlaceFieldError } from "../domain/record-inplace-change";
import { FieldControl } from "./record-form-fields";
import { ErrorReference } from "@/components/ui/error-reference";

type RecordInPlaceFieldProps = {
  id: string;
  moduleId: string;
  /** The field from the complete catalog: its options and required rule. */
  field: OpenViewDataSourceField;
  /** The Details row label that names the control. */
  labelId: string;
  /** The stored value, as the control holds it. */
  value: RecordFormValue;
  /** The value being saved; the control shows it until the response. */
  saving: RecordFormValue | null;
  /** The fields are incomplete (DR-2.13): the control waits, disabled. */
  disabled: boolean;
  /** A commit on this record is running: the control takes no input. */
  locked: boolean;
  /** Changes when a commit settles or a value is put back: the draft resets. */
  settled: number;
  error: InPlaceFieldError | null;
  /** A picked, toggled, or entered value; `complete` is false for a partial date. */
  onCommit: (value: RecordFormValue, complete: boolean) => void;
};

/**
 * One value changed in place on the Details tab (DR-2.2, DR-2.3): a Choice
 * list commits on pick and a Checkbox on toggle; a Date or Date and time
 * keeps a draft and commits on Enter or when it loses focus, and Escape puts
 * back the stored value. The parent keys it by the stored value, so a saved
 * or refused value starts a new draft.
 */
export function RecordInPlaceField({
  id,
  moduleId,
  field,
  labelId,
  value,
  saving,
  disabled,
  locked,
  settled,
  error,
  onCommit,
}: RecordInPlaceFieldProps) {
  // The control stays mounted through a save, so it keeps focus; a new
  // stored value or a settled commit starts the draft again.
  const [draft, setDraft] = useState({ text: value, value, settled });
  if (draft.value !== value || draft.settled !== settled)
    setDraft({ text: value, value, settled });
  const text = draft.value === value ? draft.text : value;
  const typed = field.type === "date" || field.type === "datetime";
  const errorId = error ? `${id}-error` : undefined;
  const control = (
    <FieldControl
      id={id}
      moduleId={moduleId}
      field={field}
      value={saving ?? (typed ? text : value)}
      disabled={disabled}
      invalid={error !== null}
      describedBy={errorId}
      onChange={(next) => {
        if (locked) return;
        if (typed) setDraft({ text: next, value, settled });
        else onCommit(next, true);
      }}
      inPlace={{
        labelledBy: labelId,
        busy: saving !== null,
        locked,
        onBlur: typed
          ? (event) =>
              onCommit(
                event.currentTarget.value,
                !event.currentTarget.validity.badInput,
              )
          : undefined,
        onKeyDown: typed
          ? (event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                onCommit(
                  event.currentTarget.value,
                  !event.currentTarget.validity.badInput,
                );
              } else if (event.key === "Escape" && text !== value) {
                // The first Escape puts the value back; the next closes the sheet.
                event.preventDefault();
                event.stopPropagation();
                setDraft({ text: value, value, settled });
              }
            }
          : undefined,
      }}
    />
  );
  return (
    // The parent finds the control here to give focus back after a save.
    <div data-in-place-field={field.id} className="flex min-w-0 flex-col gap-1">
      {field.type === "boolean" ? (
        <div className="flex min-h-11 items-center xl:min-h-8">{control}</div>
      ) : (
        control
      )}
      {error ? (
        <p id={errorId} className="text-destructive text-sm">
          {error.message}
          <ErrorReference id={error.reference} />
        </p>
      ) : null}
    </div>
  );
}
