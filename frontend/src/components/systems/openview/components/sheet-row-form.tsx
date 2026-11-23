"use client";

import { useId, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, Trash2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { GuardedWorkspaceLink } from "@/components/workspace-navigation-guard";

import { catalogFirstPageOptions } from "../adapters/openview-queries";
import type {
  WorksheetCellChange,
  WorksheetRow,
} from "../adapters/worksheets-api";
import {
  cellView,
  editInput,
  inputValue,
  type GridColumn,
  type GridFormat,
} from "../domain/sheet-grid";
import { recordHref, usePersonName } from "./sheet-grid-view";
import { SheetLinkPicker } from "./sheet-link-picker";
import SheetPersonPicker from "./sheet-person-picker";

// The phone's row form (docs/specs/sheets.md P5, F4, SH-50, Screens 9): one
// row in a bottom panel, its fields grouped by column group, 44px fields;
// lookup and computed fields read-only; Save row sends only the changed
// cells, each with the value the person saw. A conflict reloads the form
// from the newer row and says so; a refusal keeps what the person typed.

/** What a save of the form's cells came to (route 12). */
export type SaveResult =
  | { outcome: "saved" }
  | { outcome: "conflict"; current: WorksheetRow; line: string }
  | { outcome: "refused"; message: string };

type Picked = { id: string; label: string } | null;

function drafted(
  columns: readonly GridColumn[],
  row: WorksheetRow,
  format: GridFormat,
) {
  return Object.fromEntries(
    columns.map((column) => [
      column.key,
      editInput(column, row.cells[column.key], format),
    ]),
  );
}

function PersonText({ id }: { id: string }) {
  return <>{usePersonName(id)}</>;
}

/** A 44px field that opens a picker; its name says what it holds. */
function PickButton({
  column,
  label,
  empty,
  onClick,
}: {
  column: string;
  label: string | null;
  empty: string;
  onClick: () => void;
}) {
  return (
    <Button
      type="button"
      variant="outline"
      className="h-11 min-h-11 justify-between text-base font-normal"
      aria-label={`${column}: ${label ?? "none"}`}
      onClick={onClick}
    >
      <span className="truncate">{label ?? empty}</span>
      <ChevronDown aria-hidden="true" />
    </Button>
  );
}

function PersonPickButton({
  id,
  column,
  onClick,
}: {
  id: string;
  column: string;
  onClick: () => void;
}) {
  return (
    <PickButton
      column={column}
      label={usePersonName(id)}
      empty="Choose a person"
      onClick={onClick}
    />
  );
}

/** A read-only field: shaded text, named by its label. */
function ReadOnlyBox({
  labelId,
  children,
}: {
  labelId: string;
  children: ReactNode;
}) {
  return (
    <div
      role="textbox"
      aria-readonly="true"
      aria-labelledby={labelId}
      className="bg-muted text-foreground flex min-h-11 items-center rounded-md border px-3 text-base break-words"
    >
      {children}
    </div>
  );
}

export function SheetRowForm({
  row,
  index,
  total,
  sheetTitle,
  sheetId,
  columns,
  format,
  readOnly,
  onSave,
  onDelete,
  onMove,
  onClose,
}: {
  row: WorksheetRow;
  index: number;
  total: number;
  sheetTitle: string;
  sheetId: string;
  columns: readonly GridColumn[];
  format: GridFormat;
  readOnly: boolean;
  onSave: (
    cells: Record<string, WorksheetCellChange>,
    drafts: Record<string, string>,
  ) => Promise<SaveResult>;
  onDelete: (row: WorksheetRow, index: number) => void;
  onMove: (index: number) => void;
  onClose: () => void;
}) {
  const id = useId();
  // The fields start from the row as the person opened it; that is also
  // what each save says it saw (F4). A conflict starts them again.
  const [seen, setSeen] = useState(row);
  const [drafts, setDrafts] = useState<Record<string, string>>(() =>
    drafted(columns, row, format),
  );
  const [saving, setSaving] = useState(false);
  // Picked links and people by column key (null removes).
  const [picked, setPicked] = useState<Record<string, Picked>>({});
  const [picking, setPicking] = useState<GridColumn | null>(null);
  const [notice, setNotice] = useState<{
    kind: "conflict" | "refused";
    text: string;
  } | null>(null);
  const catalog = useQuery(catalogFirstPageOptions());
  const moduleName = (moduleId: string | undefined) =>
    catalog.data?.items.find((item) => item.id === moduleId)?.name ?? null;
  const first = columns[0];
  const firstView = first
    ? cellView(first, seen.cells[first.key], format)
    : null;
  const title =
    firstView?.kind === "link"
      ? firstView.label
      : firstView?.kind === "value" || firstView?.kind === "unlinked"
        ? firstView.text
        : `Row ${index + 1}`;

  const save = async () => {
    if (saving) return;
    const changes: Record<string, WorksheetCellChange> = {};
    const texts: Record<string, string> = {};
    for (const column of columns) {
      if (column.readOnly) continue;
      if (column.type === "link" || column.type === "user") {
        if (!(column.key in picked)) continue;
        const choice = picked[column.key];
        changes[column.key] = {
          value:
            column.type === "link"
              ? choice
                ? { record_id: choice.id }
                : null
              : (choice?.id ?? null),
          expected: seen.cells[column.key] ?? { value: null },
        };
        texts[column.key] = choice?.label ?? "";
        continue;
      }
      const before = editInput(column, seen.cells[column.key], format);
      if (drafts[column.key] === before) continue;
      changes[column.key] = {
        value: inputValue(column, drafts[column.key] ?? ""),
        expected: seen.cells[column.key] ?? { value: null },
      };
      texts[column.key] = drafts[column.key] ?? "";
    }
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }
    setSaving(true);
    setNotice(null);
    const result = await onSave(changes, texts);
    setSaving(false);
    if (result.outcome === "saved") onClose();
    else if (result.outcome === "conflict") {
      // The newer row replaces what the form showed.
      setSeen(result.current);
      setDrafts(drafted(columns, result.current, format));
      setPicked({});
      setNotice({ kind: "conflict", text: result.line });
    } else if (result.message)
      setNotice({ kind: "refused", text: result.message });
  };

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="-m-4 flex max-h-[88dvh] w-[calc(100%+2rem)] max-w-none flex-col gap-0 self-end rounded-b-none p-0">
        <header className="flex items-center gap-1 border-b py-1.5 pr-1 pl-4">
          <div className="min-w-0 flex-1">
            <DialogTitle className="truncate text-base">{title}</DialogTitle>
            <DialogDescription className="text-xs tabular-nums">
              Row {index + 1} of {total} · {sheetTitle}
            </DialogDescription>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="size-11"
            aria-label="Previous row"
            disabled={index === 0}
            onClick={() => onMove(index - 1)}
          >
            <ChevronUp aria-hidden="true" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="size-11"
            aria-label="Next row"
            disabled={index >= total - 1}
            onClick={() => onMove(index + 1)}
          >
            <ChevronDown aria-hidden="true" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="size-11"
            aria-label="Close"
            onClick={onClose}
          >
            <X aria-hidden="true" />
          </Button>
        </header>
        <form
          className="flex min-h-0 flex-col gap-3 overflow-y-auto px-4 py-3"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          {columns.map((column, position) => {
            const previous = columns[position - 1];
            const groupHeading =
              column.group && column.group !== previous?.group
                ? column.group
                : null;
            const fixed = readOnly || column.readOnly;
            const cell = seen.cells[column.key];
            const view = cellView(column, cell, format);
            const labelId = `${id}-${column.key}`;
            const shown: ReactNode =
              view.kind === "blank" ? null : view.kind === "link" ? (
                view.label
              ) : view.kind === "state" || view.kind === "error" ? (
                view.words
              ) : column.type === "user" && view.kind === "value" ? (
                <PersonText id={view.text} />
              ) : (
                view.text
              );
            const lookupModule =
              column.type === "lookup"
                ? moduleName(
                    columns.find((item) => item.key === column.lookupLinkKey)
                      ?.linkModuleId,
                  )
                : null;
            // The record a link field names: the one picked, else the cell's.
            const linked =
              column.type === "link" && column.linkModuleId
                ? column.key in picked
                  ? picked[column.key]
                  : view.kind === "link"
                    ? { id: view.recordId, label: view.label }
                    : null
                : null;
            let control: ReactNode;
            if (fixed)
              control = <ReadOnlyBox labelId={labelId}>{shown}</ReadOnlyBox>;
            else if (
              column.type === "user" &&
              !(column.key in picked) &&
              view.kind === "value"
            )
              control = (
                <PersonPickButton
                  id={view.text}
                  column={column.name}
                  onClick={() => setPicking(column)}
                />
              );
            else if (column.type === "link" || column.type === "user")
              control = (
                <PickButton
                  column={column.name}
                  label={
                    column.key in picked
                      ? (picked[column.key]?.label ?? null)
                      : view.kind === "link"
                        ? view.label
                        : null
                  }
                  empty={
                    column.type === "link"
                      ? "Choose a record"
                      : "Choose a person"
                  }
                  onClick={() => setPicking(column)}
                />
              );
            else if (column.type === "select")
              control = (
                <NativeSelect
                  aria-labelledby={labelId}
                  className="w-full [&_select]:h-11 [&_select]:text-base"
                  value={drafts[column.key] ?? ""}
                  onChange={(event) =>
                    setDrafts((current) => ({
                      ...current,
                      [column.key]: event.target.value,
                    }))
                  }
                >
                  <NativeSelectOption value="">None</NativeSelectOption>
                  {Object.entries(column.options ?? {}).map(([key, label]) => (
                    <NativeSelectOption key={key} value={key}>
                      {label}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
              );
            else
              control = (
                <Input
                  aria-labelledby={labelId}
                  className={
                    column.numeric
                      ? "h-11 min-h-11 text-right text-base tabular-nums"
                      : "h-11 min-h-11 text-base"
                  }
                  inputMode={column.numeric ? "decimal" : undefined}
                  value={drafts[column.key] ?? ""}
                  onChange={(event) =>
                    setDrafts((current) => ({
                      ...current,
                      [column.key]: event.target.value,
                    }))
                  }
                />
              );
            return (
              <div key={column.key} className="flex flex-col gap-1">
                {groupHeading ? (
                  <h3 className="text-muted-foreground pt-1 text-xs font-semibold">
                    {groupHeading}
                  </h3>
                ) : null}
                <span id={labelId} className="text-sm font-medium">
                  {column.name}
                </span>
                {control}
                {linked && column.linkModuleId ? (
                  <GuardedWorkspaceLink
                    href={recordHref(column.linkModuleId, linked.id)}
                    className="text-action-text inline-flex min-h-11 items-center self-start text-sm font-medium underline underline-offset-4"
                  >
                    Open {linked.label}&apos;s record
                  </GuardedWorkspaceLink>
                ) : null}
                {column.type === "lookup" ? (
                  <span className="text-muted-foreground text-xs">
                    {lookupModule
                      ? `Lookup from ${lookupModule}. Read-only.`
                      : "Lookup. Read-only."}
                  </span>
                ) : column.readOnly ? (
                  <span className="text-muted-foreground text-xs">
                    Read-only.
                  </span>
                ) : null}
              </div>
            );
          })}
          {notice ? (
            <p
              role={notice.kind === "conflict" ? "status" : "alert"}
              className={
                notice.kind === "conflict"
                  ? "bg-warn-tint text-foreground rounded-md p-3 text-sm"
                  : "text-danger-text text-sm"
              }
            >
              {notice.text}
            </p>
          ) : null}
          <div className="bg-card sticky bottom-0 flex items-center justify-end gap-2 border-t pt-3">
            {readOnly ? (
              <Button
                type="button"
                variant="outline"
                className="min-h-11"
                onClick={onClose}
              >
                Close
              </Button>
            ) : (
              <>
                <Button
                  type="button"
                  variant="ghost"
                  className="text-danger-text mr-auto min-h-11"
                  onClick={() => onDelete(seen, index)}
                >
                  <Trash2 aria-hidden="true" />
                  Delete row
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  className="min-h-11"
                  onClick={onClose}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  className="min-h-11 flex-1"
                  pending={saving}
                  pendingLabel="Saving…"
                >
                  Save row
                </Button>
              </>
            )}
          </div>
        </form>
      </DialogContent>
      {picking?.type === "link" && picking.linkModuleId ? (
        <SheetLinkPicker
          columnName={picking.name}
          moduleId={picking.linkModuleId}
          current={(() => {
            const choice =
              picking.key in picked
                ? picked[picking.key]
                : (() => {
                    const view = cellView(
                      picking,
                      seen.cells[picking.key],
                      format,
                    );
                    return view.kind === "link"
                      ? { id: view.recordId, label: view.label }
                      : null;
                  })();
            return choice ? { recordId: choice.id, label: choice.label } : null;
          })()}
          onClose={() => setPicking(null)}
          onPick={(recordId, label) => {
            setPicked((current) => ({
              ...current,
              [picking.key]: recordId ? { id: recordId, label } : null,
            }));
            setPicking(null);
          }}
        />
      ) : null}
      {picking?.type === "user" ? (
        <SheetPersonPicker
          sheetId={sheetId}
          columnName={picking.name}
          hasPerson={
            picking.key in picked
              ? Boolean(picked[picking.key])
              : cellView(picking, seen.cells[picking.key], format).kind ===
                "value"
          }
          onClose={() => setPicking(null)}
          onPick={(personId, name) => {
            setPicked((current) => ({
              ...current,
              [picking.key]: personId ? { id: personId, label: name } : null,
            }));
            setPicking(null);
          }}
        />
      ) : null}
    </Dialog>
  );
}
