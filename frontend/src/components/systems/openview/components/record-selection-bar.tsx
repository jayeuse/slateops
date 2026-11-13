"use client";

import { useId, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ErrorReference } from "@/components/ui/error-reference";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import type {
  OpenViewDataSourceField,
  OpenViewRecord,
} from "../adapters/views-api";
import {
  changeItems,
  changeOptions,
  finalChangeLabel,
  type ChangeOption,
  type ListChangeNotice,
} from "../domain/record-batch-change";

// Candidate 5 of docs/specs/subtle-interactions.md (comp `selection.html`):
// the selection bar that takes the toolbar row's place while rows are
// selected (DR-SI-5.4), its Change panel (DR-SI-5.6, DR-SI-5.7), and the
// page status actions of a list change: the "not changed" list and Undo
// (DR-SI-5.8, DR-SI-5.9, G8).

/** A quiet link button on the page meta line, as item 6's "Open record". */
export const statusLinkClassName =
  "text-action-text relative h-auto min-h-0! shrink-0 px-1.5 py-0 leading-6 whitespace-nowrap underline-offset-4 after:absolute after:inset-x-0 after:-inset-y-2.5 after:content-[''] hover:bg-transparent hover:underline xl:after:-inset-y-1";

const optionKey = (value: ChangeOption["value"]) => JSON.stringify(value);

/** The words of a list change; a screen reader also hears the count left. */
export function ListChangeWords({ notice }: { notice: ListChangeNotice }) {
  return (
    <>
      {notice.message}
      {notice.notChangedLabel ? (
        <span className="sr-only"> {notice.notChangedLabel}.</span>
      ) : null}
    </>
  );
}

/** "2 not changed" and Undo, directly after the status words (G8). */
export function ListChangeActions({
  notice,
  undoDisabled,
  onUndo,
  onOpenRecord,
}: {
  notice: ListChangeNotice;
  undoDisabled: boolean;
  onUndo: () => void;
  onOpenRecord: (recordId: string) => void;
}) {
  return (
    <>
      {notice.reference ? (
        <ErrorReference id={notice.reference} className="mt-0 text-xs" />
      ) : null}
      {notice.notChangedLabel ? (
        <Popover>
          <PopoverTrigger
            render={
              <Button
                type="button"
                variant="ghost"
                className={statusLinkClassName}
              />
            }
          >
            {notice.notChangedLabel}
          </PopoverTrigger>
          <PopoverContent
            align="start"
            aria-label="Records not changed"
            className="slim-ui w-80 gap-1 p-1"
          >
            <ul className="flex flex-col">
              {notice.notChanged.map((record) => (
                <li key={record.recordId}>
                  <button
                    type="button"
                    className="hover:bg-muted focus-visible:outline-ring flex min-h-11 w-full flex-col items-start justify-center rounded-sm px-2 py-1 text-left focus-visible:outline-2 xl:min-h-8"
                    onClick={() => onOpenRecord(record.recordId)}
                  >
                    <span className="font-medium">{record.title}</span>
                    <span className="text-muted-foreground text-xs">
                      {record.reason}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </PopoverContent>
        </Popover>
      ) : null}
      {notice.undo ? (
        <Button
          type="button"
          variant="ghost"
          className={statusLinkClassName}
          disabled={undoDisabled}
          onClick={onUndo}
        >
          Undo
        </Button>
      ) : null}
    </>
  );
}

type ChangeField = OpenViewDataSourceField;

/** The field's values, the final button and Cancel (DR-SI-5.6, DR-SI-5.7). */
function ChangePanel({
  field,
  rows,
  busy,
  onApply,
  onCancel,
}: {
  field: ChangeField;
  rows: readonly OpenViewRecord[];
  busy: boolean;
  onApply: (value: ChangeOption["value"]) => void;
  onCancel: () => void;
}) {
  const headingId = useId();
  const [picked, setPicked] = useState<string | null>(null);
  const options = changeOptions(field);
  const choice = options.find((option) => optionKey(option.value) === picked);
  const final = finalChangeLabel({
    selected: rows.length,
    picked: choice !== undefined,
    changing: choice ? changeItems(rows, field.id, choice.value).length : 0,
  });
  return (
    <div className="flex flex-col gap-3">
      <h3 id={headingId} className="text-sm font-medium">
        {field.name}
      </h3>
      <RadioGroup
        aria-labelledby={headingId}
        className="gap-0"
        value={picked ?? ""}
        disabled={busy}
        onValueChange={(value) => setPicked(String(value))}
      >
        {options.map((option) => (
          <label
            key={optionKey(option.value)}
            className="hover:bg-muted flex min-h-11 cursor-pointer items-center gap-2.5 rounded-sm px-2 text-sm xl:min-h-8"
          >
            <RadioGroupItem value={optionKey(option.value)} />
            {option.label}
          </label>
        ))}
      </RadioGroup>
      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button
          type="button"
          variant="outline"
          className="min-h-11 xl:min-h-8"
          disabled={busy}
          onClick={onCancel}
        >
          Cancel
        </Button>
        <Button
          type="button"
          className="min-h-11 xl:min-h-8"
          disabled={!final.enabled}
          pending={busy}
          pendingLabel="Changing…"
          onClick={() => {
            if (choice) onApply(choice.value);
          }}
        >
          {final.label}
        </Button>
      </div>
    </div>
  );
}

/**
 * DR-SI-5.4: "<n> selected", Change (the Choice list and Checkbox fields of
 * the view's query, DR-SI-5.5) and Clear selection. The page header and the
 * pager stay; a phone opens the Change panel as a bottom sheet.
 */
export function RecordSelectionBar({
  rows,
  fields,
  busy,
  narrow,
  onApply,
  onClear,
}: {
  /** The selected rows on this page. */
  rows: readonly OpenViewRecord[];
  fields: readonly ChangeField[];
  busy: boolean;
  narrow: boolean;
  onApply: (field: ChangeField, value: ChangeOption["value"]) => void;
  onClear: () => void;
}) {
  const changeButton = useRef<HTMLButtonElement | null>(null);
  const [editing, setEditing] = useState<ChangeField | null>(null);
  const close = () => {
    if (!busy) setEditing(null);
  };
  const panel = editing ? (
    <ChangePanel
      key={editing.id}
      field={editing}
      rows={rows}
      busy={busy}
      onApply={(value) => onApply(editing, value)}
      onCancel={close}
    />
  ) : null;
  return (
    <div
      role="toolbar"
      aria-label="Selected records"
      aria-disabled={busy || undefined}
      className="flex min-h-11 flex-wrap items-center gap-2"
    >
      <span className="text-sm font-medium tabular-nums">
        {rows.length} selected
      </span>
      <DropdownMenu>
        <DropdownMenuTrigger
          ref={changeButton}
          disabled={busy || fields.length === 0}
          render={
            <Button type="button" variant="outline" className="min-h-11" />
          }
        >
          Change
          <ChevronDown aria-hidden="true" className="text-muted-foreground" />
        </DropdownMenuTrigger>
        <DropdownMenuContent className="slim-ui min-w-48">
          {fields.map((field) => (
            <DropdownMenuItem
              key={field.id}
              className="min-h-11 xl:min-h-8"
              onClick={() => setEditing(field)}
            >
              {field.name}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <Button
        type="button"
        variant="ghost"
        className="ml-auto min-h-11"
        disabled={busy}
        onClick={onClear}
      >
        Clear selection
      </Button>
      {narrow ? (
        <Dialog
          open={editing !== null}
          onOpenChange={(open) => {
            if (!open) close();
          }}
        >
          <DialogContent className="max-w-none self-end rounded-b-none">
            <DialogTitle className="sr-only">
              Change {editing?.name ?? ""}
            </DialogTitle>
            {panel}
          </DialogContent>
        </Dialog>
      ) : (
        <Popover
          open={editing !== null}
          onOpenChange={(open) => {
            if (!open) close();
          }}
        >
          <PopoverContent
            anchor={changeButton}
            align="start"
            aria-label={`Change ${editing?.name ?? ""}`}
            className="slim-ui w-72"
            finalFocus={changeButton}
          >
            {panel}
          </PopoverContent>
        </Popover>
      )}
    </div>
  );
}
