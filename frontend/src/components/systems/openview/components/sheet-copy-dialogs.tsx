"use client";

import { isEditionRefusal } from "@/lib/api-errors";
import { lazy, Suspense, useId, useState } from "react";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DisabledReason } from "@/components/ui/disabled-reason";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DialogFrameFooter,
  DialogFrameHeader,
  dialogFrameContentClass,
} from "@/components/ui/dialog-frame";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { useWorkspaceNavigationRequest } from "@/components/workspace-navigation-guard";
import { ApiError } from "@/lib/api";
import { apiErrorReference } from "@/lib/api-errors";
import { cn } from "@/lib/utils";

import {
  worksheetKeys,
  worksheetPlaceOptions,
} from "../adapters/worksheet-queries";
import {
  createWorksheet,
  type WorksheetDetail,
} from "../adapters/worksheets-api";
import { sheetHref } from "./sheet-display";
import { moduleLabel, useSheetModules } from "./use-sheet-modules";

// Make a copy (docs/specs/sheets.md L6, D9.5, Screens 5) and New sheet from
// this structure (X7, D9.5, Screens 3), both a new private sheet that the
// person owns, made by route 3 and opened at once. Loaded on first use.

const SheetLinkPicker = lazy(() =>
  import("./sheet-link-picker").then((module) => ({
    default: module.SheetLinkPicker,
  })),
);

const TITLE_MAX = 200;

function refusal(
  error: unknown,
  action: "copied" | "created",
  onModule = false,
): string {
  if (error instanceof ApiError) {
    if (error.code === "copy_too_large")
      return "This sheet has too many rows to copy (over 5,000). Export it and import the file instead.";
    if (error.code === "worksheet_copy_forbidden")
      return "Only the owner can copy a sheet that is not open.";
    if (isEditionRefusal(error)) return error.message;
    if (error.status === 403) return "Guests cannot create sheets.";
    if (error.status === 409)
      return onModule
        ? "This module was closed, so it cannot hold a new sheet."
        : "This record was deleted or its module was closed, so it cannot hold a new sheet.";
    if (error.status === 404)
      return action === "copied"
        ? "This sheet is no longer available."
        : "The sheet, or the place you chose, is no longer available.";
    if (error.status === 422) return "Check the name and try again.";
  }
  return action === "copied"
    ? "The copy could not be made. Try again."
    : "The sheet could not be created. Try again.";
}

function useOpenCreated(onClose: () => void) {
  const client = useQueryClient();
  const router = useRouter();
  const requestNavigation = useWorkspaceNavigationRequest();
  return (sheet: WorksheetDetail) => {
    void client.invalidateQueries({ queryKey: worksheetKeys.all });
    onClose();
    const href = sheetHref(sheet.id);
    const resume = () => router.push(href as Route);
    if (requestNavigation(href, resume)) resume();
  };
}

type Props = { sheet: WorksheetDetail; onClose: () => void };

function NameField({
  id,
  value,
  missing,
  onChange,
}: {
  id: string;
  value: string;
  missing: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <Field>
      <FieldLabel htmlFor={`${id}-name`}>Name</FieldLabel>
      <Input
        id={`${id}-name`}
        className="min-h-11 xl:h-8 xl:min-h-8"
        maxLength={TITLE_MAX}
        autoComplete="off"
        value={value}
        aria-invalid={missing || undefined}
        aria-describedby={missing ? `${id}-missing` : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
      {missing ? (
        <p id={`${id}-missing`} className="text-destructive text-sm">
          Enter a name.
        </p>
      ) : null}
    </Field>
  );
}

/** Make a copy: the same columns, rows and links, on the same record. */
export function SheetCopyDialog({ sheet, onClose }: Props) {
  const id = useId();
  const [name, setName] = useState(`${sheet.title} (copy)`.slice(0, TITLE_MAX));
  const [missing, setMissing] = useState(false);
  const opened = useOpenCreated(onClose);
  const copy = useMutation({
    mutationFn: (title: string) =>
      createWorksheet({
        ...(sheet.recordId
          ? { recordId: sheet.recordId }
          : { moduleId: sheet.moduleId ?? "" }),
        title,
        source: { kind: "copy", worksheetId: sheet.id },
      }),
    onSuccess: opened,
  });
  const pending = copy.isPending;
  const submit = () => {
    if (pending) return;
    const title = name.trim();
    setMissing(!title);
    if (title) copy.mutate(title);
  };
  const close = () => {
    if (!pending) onClose();
  };
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <DialogContent className={cn(dialogFrameContentClass, "sm:max-w-md")}>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <DialogFrameHeader
            title={<DialogTitle>{`Make a copy of ${sheet.title}`}</DialogTitle>}
            closeLabel="Close Make a copy"
            closeDisabled={pending}
            onClose={close}
          />
          <div className="flex flex-col gap-1.5">
            <NameField
              id={id}
              value={name}
              missing={missing}
              onChange={(value) => {
                setName(value);
                if (missing && value.trim()) setMissing(false);
              }}
            />
            <p className="text-muted-foreground text-sm">
              {sheet.recordId
                ? `On ${sheet.anchorTitle} · ${sheet.moduleName}, the same record.`
                : `On ${sheet.moduleName}, the same module.`}
            </p>
          </div>
          <p className="bg-muted flex items-start gap-2.5 rounded-md p-3 text-sm">
            <Copy aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <span>
              You get the same columns, rows and links. Only you can see the
              copy until you share it.
            </span>
          </p>
          {copy.isError ? (
            <Alert
              variant="destructive"
              reference={apiErrorReference(copy.error)}
            >
              <p>{refusal(copy.error, "copied", !sheet.recordId)}</p>
            </Alert>
          ) : null}
          <DialogFrameFooter>
            <DialogFooter className="mt-0">
              <Button
                type="button"
                variant="ghost"
                className="min-h-11"
                disabled={pending}
                onClick={close}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                className="min-h-11"
                pending={pending}
                pendingLabel="Copying…"
              >
                Make a copy
              </Button>
            </DialogFooter>
          </DialogFrameFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

type Place =
  | { kind: "record"; moduleId: string; recordId: string; recordTitle: string }
  | { kind: "module"; moduleId: string };

/**
 * New sheet from this structure: the same columns, groups, computed columns
 * and totals, no rows and no shares, on a record or module the person
 * chooses (by default where this sheet is).
 */
export function SheetFromStructureDialog({ sheet, onClose }: Props) {
  const id = useId();
  const placeRead = useQuery(worksheetPlaceOptions(sheet.id, sheet));
  const { modules } = useSheetModules();
  const [name, setName] = useState(sheet.title);
  const [missing, setMissing] = useState(false);
  const [chosen, setChosen] = useState<Place | null>(null);
  const [picking, setPicking] = useState(false);
  // The record last picked; it stays a choice while its module is chosen.
  const [picked, setPicked] = useState<Extract<
    Place,
    { kind: "record" }
  > | null>(null);
  const opened = useOpenCreated(onClose);
  const sourceModule = placeRead.data?.moduleId ?? sheet.moduleId ?? "";
  const place: Place | null =
    chosen ??
    (sheet.recordId && sourceModule
      ? {
          kind: "record",
          moduleId: sourceModule,
          recordId: sheet.recordId,
          recordTitle: sheet.anchorTitle,
        }
      : sourceModule
        ? { kind: "module", moduleId: sourceModule }
        : null);
  const moduleOf = modules.find((module) => module.id === place?.moduleId);
  const moduleName =
    moduleOf?.name ??
    (place?.moduleId === sourceModule ? sheet.moduleName : "the module");
  const create = useMutation({
    mutationFn: (title: string) => {
      if (!place) throw new Error("No place chosen");
      return createWorksheet({
        ...(place.kind === "record"
          ? { recordId: place.recordId }
          : { moduleId: place.moduleId }),
        title,
        source: { kind: "structure", worksheetId: sheet.id },
      });
    },
    onSuccess: opened,
  });
  const pending = create.isPending;
  const submit = () => {
    if (pending || !place) return;
    const title = name.trim();
    setMissing(!title);
    if (title) create.mutate(title);
  };
  const close = () => {
    if (!pending) onClose();
  };
  if (picking && place)
    return (
      <Suspense fallback={null}>
        <SheetLinkPicker
          columnName="a record"
          moduleId={place.moduleId}
          current={null}
          onClose={() => setPicking(false)}
          onPick={(recordId, label) => {
            setPicking(false);
            if (!recordId) return;
            const next = {
              kind: "record" as const,
              moduleId: place.moduleId,
              recordId,
              recordTitle: label,
            };
            setPicked(next);
            setChosen(next);
          }}
        />
      </Suspense>
    );
  const radio = (
    value: "record" | "module",
    label: string,
    checked: boolean,
    onChoose: () => void,
  ) => (
    <label className="flex min-h-11 items-center gap-2 text-sm xl:min-h-8">
      <input
        type="radio"
        name={`${id}-place`}
        value={value}
        checked={checked}
        disabled={pending}
        onChange={onChoose}
        className="size-4 accent-[var(--action)]"
      />
      {label}
    </label>
  );
  const sourceRecord =
    sheet.recordId && sourceModule
      ? {
          kind: "record" as const,
          moduleId: sourceModule,
          recordId: sheet.recordId,
          recordTitle: sheet.anchorTitle,
        }
      : null;
  const lastRecord = picked ?? sourceRecord;
  const recordPlace =
    place?.kind === "record"
      ? place
      : lastRecord && lastRecord.moduleId === place?.moduleId
        ? lastRecord
        : null;
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <DialogContent className={cn(dialogFrameContentClass, "sm:max-w-md")}>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <DialogFrameHeader
            title={<DialogTitle>New sheet from this structure</DialogTitle>}
            description={
              <DialogDescription>
                Same columns, groups, computed columns and totals. No rows and
                no shares.
              </DialogDescription>
            }
            closeLabel="Close New sheet from this structure"
            closeDisabled={pending}
            onClose={close}
          />
          <NameField
            id={id}
            value={name}
            missing={missing}
            onChange={(value) => {
              setName(value);
              if (missing && value.trim()) setMissing(false);
            }}
          />
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Module
            <NativeSelect
              className="w-full [&_select]:h-11 xl:[&_select]:h-8"
              value={place?.moduleId ?? ""}
              disabled={pending}
              onChange={(event) =>
                setChosen({ kind: "module", moduleId: event.target.value })
              }
            >
              {place && !moduleOf ? (
                <NativeSelectOption value={place.moduleId}>
                  {moduleName}
                </NativeSelectOption>
              ) : null}
              {modules.map((module) => (
                <NativeSelectOption key={module.id} value={module.id}>
                  {moduleLabel(module)}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </label>
          <div
            role="radiogroup"
            aria-labelledby={`${id}-place`}
            className="flex flex-col"
          >
            <span id={`${id}-place`} className="text-sm font-medium">
              Put it on
            </span>
            {recordPlace
              ? radio(
                  "record",
                  `${recordPlace.recordTitle} · ${moduleName}`,
                  place?.kind === "record",
                  () => setChosen(recordPlace),
                )
              : null}
            {radio(
              "module",
              `The ${moduleName} module`,
              place?.kind === "module",
              () =>
                place
                  ? setChosen({ kind: "module", moduleId: place.moduleId })
                  : undefined,
            )}
            <Button
              type="button"
              variant="ghost"
              className="min-h-11 self-start xl:h-8 xl:min-h-8"
              disabled={pending || !place}
              onClick={() => setPicking(true)}
            >
              {recordPlace ? "Choose another record" : "Choose a record"}
            </Button>
          </div>
          {create.isError ? (
            <Alert
              variant="destructive"
              reference={apiErrorReference(create.error)}
            >
              <p>
                {refusal(create.error, "created", place?.kind === "module")}
              </p>
            </Alert>
          ) : null}
          <DialogFrameFooter>
            <p className="text-muted-foreground text-sm">
              Only you can see it until you share it.
            </p>
            <DialogFooter className="mt-0">
              <Button
                type="button"
                variant="ghost"
                className="min-h-11"
                disabled={pending}
                onClick={close}
              >
                Cancel
              </Button>
              <DisabledReason
                stable
                reason={
                  place || pending
                    ? null
                    : "Wait for the sheet's place to load."
                }
              >
                <Button
                  type="submit"
                  className="min-h-11"
                  pending={pending}
                  pendingLabel="Creating…"
                >
                  Create sheet
                </Button>
              </DisabledReason>
            </DialogFooter>
          </DialogFrameFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
