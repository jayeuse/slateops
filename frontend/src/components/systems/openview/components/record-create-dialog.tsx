"use client";

import { useEffect, useRef, useState } from "react";
import { getApiFieldErrors } from "@/lib/api";
import type {
  OpenViewDataSourceField,
  OpenViewQueryDefinition,
  OpenViewRecord,
} from "../adapters/views-api";
import { createOpenViewRecord } from "../adapters/records-api";
import { createStartingValues } from "../domain/create-starting-values";
import {
  encodeRecordForm,
  initialFormValues,
  serverFieldMessage,
  type RecordFormErrors,
  type RecordFormValues,
} from "../domain/record-form";
import { RecordFormFields } from "./record-form-fields";
import { statusLinkClassName } from "./record-selection-bar";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DisabledReason } from "@/components/ui/disabled-reason";
import {
  DialogFrameFooter,
  DialogFrameHeader,
  dialogFrameContentClass,
} from "@/components/ui/dialog-frame";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { apiErrorMessage } from "@/lib/api-errors";
import { useErrorText } from "@/lib/use-error-text";

type RecordCreateDialogProps = {
  open: boolean;
  moduleId: string;
  moduleName: string;
  fields: readonly OpenViewDataSourceField[];
  /** The page's applied definition: its conditions give starting values. */
  definition: Pick<OpenViewQueryDefinition, "logic" | "filters">;
  /** The signed-in person, the only User starting value (DR-SI-2.3). */
  identityId: string | null;
  /** A record's name, as the list shows it ("" or "—" when it has none). */
  titleOf: (record: OpenViewRecord) => string;
  onOpenChange: (open: boolean) => void;
  /**
   * The dialog is done with records made in it (SI-3.4), in the order they
   * were made. `open`: the record whose sheet opens now (Create, or "Open
   * record"); null when the dialog just closed.
   */
  onCreated: (
    made: readonly OpenViewRecord[],
    open: OpenViewRecord | null,
  ) => void;
};

/** The first control of the form, for focus after "add another". */
const FIRST_CONTROL =
  'input:not([type="hidden"]):not([tabindex="-1"]):not([aria-hidden="true"]), select, textarea, button:not([tabindex="-1"])';

/** DR-SI-3.3: "<Title> created.", or "Record created." with no title. */
function createdWords(title: string): string {
  const name = title.trim();
  return name && name !== "—" ? `${name} created.` : "Record created.";
}

function CreateForm({
  moduleId,
  moduleName,
  fields,
  definition,
  identityId,
  titleOf,
  onCancel,
  onCreated,
  onCreatedAnother,
  onOpenRecord,
  onDirty,
}: Omit<RecordCreateDialogProps, "open" | "onOpenChange" | "onCreated"> & {
  onCancel: () => void;
  /** Create: the record whose sheet opens. */
  onCreated: (record: OpenViewRecord) => void;
  /** "Create and add another": the dialog stays open. */
  onCreatedAnother: (record: OpenViewRecord) => void;
  onOpenRecord: (record: OpenViewRecord) => void;
  onDirty: () => void;
}) {
  const formRef = useRef<HTMLFormElement>(null);
  const fieldsRef = useRef<HTMLDivElement>(null);
  const focusFirstInvalid = () =>
    requestAnimationFrame(() =>
      formRef.current
        ?.querySelector<HTMLElement>('[aria-invalid="true"]')
        ?.focus(),
    );
  // SI-2.1: the applied conditions' values over the field defaults. They
  // are not changes: only a typed or picked value marks the dialog dirty.
  const [starting] = useState<RecordFormValues>(() => ({
    ...initialFormValues(fields, null),
    ...createStartingValues(fields, definition, identityId),
  }));
  const [values, setValues] = useState<RecordFormValues>(starting);
  const [errors, setErrors] = useState<RecordFormErrors>({});
  const [errorFailure, setError] = useErrorText();
  const error = errorFailure?.message ?? "";
  // Which button's create runs: only that one reads "Creating…".
  const [pending, setPending] = useState<"create" | "another" | null>(null);
  // DR-SI-3.3: the record "Create and add another" made last.
  const [lastCreated, setLastCreated] = useState<OpenViewRecord | null>(null);
  // Focus moves to the first field once the fields take input again.
  const [focusRequest, setFocusRequest] = useState(0);
  useEffect(() => {
    if (focusRequest === 0) return;
    fieldsRef.current?.querySelector<HTMLElement>(FIRST_CONTROL)?.focus();
  }, [focusRequest]);

  const create = async (another: boolean) => {
    const encoded = encodeRecordForm(fields, values, null);
    setErrors(encoded.errors);
    if (Object.keys(encoded.errors).length > 0) {
      focusFirstInvalid();
      return;
    }
    setPending(another ? "another" : "create");
    setError("");
    try {
      const record = await createOpenViewRecord({
        moduleId,
        data: encoded.data,
      });
      if (!another) {
        onCreated(record);
        return;
      }
      // DR-SI-3.3: the form starts again; the status names the record.
      setValues(starting);
      setLastCreated(record);
      setFocusRequest((request) => request + 1);
      onCreatedAnother(record);
    } catch (caught) {
      const known = new Set(fields.map((field) => field.id));
      const serverErrors = Object.fromEntries(
        Object.entries(getApiFieldErrors(caught))
          .filter(([fieldId]) => known.has(fieldId))
          .map(([fieldId, messages]) => [
            fieldId,
            serverFieldMessage(messages[0] ?? ""),
          ]),
      );
      setErrors(serverErrors);
      if (Object.keys(serverErrors).length > 0) focusFirstInvalid();
      if (Object.keys(serverErrors).length === 0)
        // The server's words never show (S1-C6); the shared path says it.
        setError(
          apiErrorMessage(caught, "The record could not be created."),
          caught,
        );
    } finally {
      setPending(null);
    }
  };

  return (
    <form
      ref={formRef}
      className="flex min-h-0 flex-col gap-4"
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        void create(false);
      }}
    >
      <div className="min-w-0">
        {lastCreated ? (
          // G7: a dialog change reports at the top of the dialog body. The
          // next success replaces it.
          <Alert
            variant="success"
            className="mb-4 flex flex-wrap items-center gap-x-2 gap-y-1 py-2.5"
          >
            <span>{createdWords(titleOf(lastCreated))}</span>
            <Button
              type="button"
              variant="ghost"
              className={statusLinkClassName}
              disabled={pending !== null}
              onClick={() => onOpenRecord(lastCreated)}
            >
              Open record
            </Button>
          </Alert>
        ) : null}
        {error ? (
          <Alert
            role="alert"
            variant="destructive"
            className="mb-4"
            reference={errorFailure?.reference}
          >
            {error}
          </Alert>
        ) : null}
        <div ref={fieldsRef}>
          <RecordFormFields
            moduleId={moduleId}
            fields={fields}
            values={values}
            errors={errors}
            disabled={pending !== null}
            onChange={(fieldId, value) => {
              onDirty();
              setValues((current) => ({ ...current, [fieldId]: value }));
              setErrors((current) =>
                Object.fromEntries(
                  Object.entries(current).filter(([id]) => id !== fieldId),
                ),
              );
            }}
          />
        </div>
      </div>
      <DialogFrameFooter>
        {/* DR-SI-3.1: Cancel, Create and add another, Create; below 640 px
          they stack, Create first. Enter in a field means Create. */}
        <DialogFooter className="mt-0">
          <Button
            type="button"
            variant="ghost"
            className="min-h-11"
            disabled={pending !== null}
            onClick={onCancel}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="outline"
            className="min-h-11"
            disabled={pending !== null}
            onClick={() => void create(true)}
          >
            {pending === "another" ? "Creating…" : "Create and add another"}
          </Button>
          <DisabledReason
            stable
            reason={
              pending === "another"
                ? "Wait for the current action to finish."
                : null
            }
          >
            <Button
              type="submit"
              className="min-h-11"
              pending={pending === "create"}
              pendingLabel="Creating…"
            >
              {`Create ${moduleName} record`}
            </Button>
          </DisabledReason>
        </DialogFooter>
      </DialogFrameFooter>
    </form>
  );
}

/** A dialog that adds one record to the current data source. */
export function RecordCreateDialog({
  open,
  moduleId,
  moduleName,
  fields,
  definition,
  identityId,
  titleOf,
  onOpenChange,
  onCreated,
}: RecordCreateDialogProps) {
  // Typed values are not dropped by an outside click or Escape.
  const [dirty, setDirty] = useState(false);
  // SI-3.4: the records "Create and add another" made while it is open.
  const [made, setMade] = useState<readonly OpenViewRecord[]>([]);
  // A create that answers after the dialog closed is not part of the next
  // session; it is reported on its own.
  const openNow = useRef(open);
  useEffect(() => {
    openNow.current = open;
  }, [open]);
  const finish = (
    records: readonly OpenViewRecord[],
    opened: OpenViewRecord | null,
  ) => {
    setDirty(false);
    setMade([]);
    onCreated(records, opened);
  };
  const changeOpen = (next: boolean) => {
    if (!next) {
      setDirty(false);
      if (made.length > 0) finish(made, null);
    }
    onOpenChange(next);
  };
  return (
    <Dialog open={open} dismissible={!dirty} onOpenChange={changeOpen}>
      <DialogContent className={cn(dialogFrameContentClass, "max-w-2xl")}>
        <DialogFrameHeader
          title={<DialogTitle>New record</DialogTitle>}
          description={
            <DialogDescription>
              Add a record to {moduleName}. Fields left empty use their default
              value.
            </DialogDescription>
          }
          closeLabel="Close without creating"
          onClose={() => changeOpen(false)}
        />
        {open ? (
          <CreateForm
            moduleId={moduleId}
            moduleName={moduleName}
            fields={fields}
            definition={definition}
            identityId={identityId}
            titleOf={titleOf}
            onCancel={() => changeOpen(false)}
            onDirty={() => setDirty(true)}
            onCreated={(record) => finish([...made, record], record)}
            onCreatedAnother={(record) => {
              if (!openNow.current) {
                onCreated([record], null);
                return;
              }
              // SI-3.5: the guard counts only values typed after it.
              setDirty(false);
              setMade((records) => [...records, record]);
            }}
            onOpenRecord={(record) => finish(made, record)}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
