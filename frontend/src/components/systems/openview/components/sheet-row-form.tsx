"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

import { usePersonName } from "./sheet-grid-view";
import { SheetLinkPicker } from "./sheet-link-picker";

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

// The phone's row form (docs/specs/sheets.md P5, SH-50, Screens 9): one row
// in a bottom panel, its fields grouped by column group, 44px inputs; lookup
// and computed fields read-only; Save row sends only the changed cells.

/** Columns a phone form changes (person fields read-only until F5's list). */
function editableHere(column: GridColumn) {
  return !column.readOnly && column.type !== "user";
}

export function SheetRowForm({
  row,
  index,
  total,
  sheetTitle,
  columns,
  format,
  readOnly,
  onSave,
  onMove,
  onClose,
}: {
  row: WorksheetRow;
  index: number;
  total: number;
  sheetTitle: string;
  columns: readonly GridColumn[];
  format: GridFormat;
  readOnly: boolean;
  onSave: (cells: Record<string, WorksheetCellChange>) => Promise<boolean>;
  onMove: (index: number) => void;
  onClose: () => void;
}) {
  // The fields start from the row as the person opened it; that is also
  // what each save says it saw (F4).
  const [seen] = useState(row);
  const [drafts, setDrafts] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      columns.map((column) => [
        column.key,
        editInput(column, row.cells[column.key], format),
      ]),
    ),
  );
  const [saving, setSaving] = useState(false);
  // Picked links: the record and its title, by column key (null removes).
  const [links, setLinks] = useState<
    Record<string, { id: string; label: string } | null>
  >({});
  const [picking, setPicking] = useState<GridColumn | null>(null);
  const first = columns[0];
  const firstView = first
    ? cellView(first, row.cells[first.key], format)
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
    for (const column of columns) {
      if (!editableHere(column)) continue;
      if (column.type === "link") {
        if (!(column.key in links)) continue;
        const picked = links[column.key];
        changes[column.key] = {
          value: picked ? { record_id: picked.id } : null,
          expected: seen.cells[column.key] ?? { value: null },
        };
        continue;
      }
      const before = editInput(column, seen.cells[column.key], format);
      if (drafts[column.key] === before) continue;
      changes[column.key] = {
        value: inputValue(column, drafts[column.key] ?? ""),
        expected: seen.cells[column.key] ?? { value: null },
      };
    }
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }
    setSaving(true);
    const saved = await onSave(changes);
    setSaving(false);
    if (saved) onClose();
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
            const fixed = readOnly || !editableHere(column);
            const view = cellView(column, row.cells[column.key], format);
            const shown =
              fixed && view.kind !== "blank"
                ? view.kind === "link"
                  ? view.label
                  : view.kind === "state"
                    ? view.words
                    : view.text
                : (drafts[column.key] ?? "");
            return (
              <div key={column.key} className="flex flex-col gap-1">
                {groupHeading ? (
                  <h3 className="text-muted-foreground pt-1 text-xs font-semibold uppercase">
                    {groupHeading}
                  </h3>
                ) : null}
                <label className="flex flex-col gap-1">
                  <span className="text-sm font-medium">{column.name}</span>
                  {column.type === "link" && !fixed ? (
                    <Button
                      type="button"
                      variant="outline"
                      className="h-11 min-h-11 justify-start text-base font-normal"
                      aria-label={`${column.name}: ${
                        column.key in links
                          ? (links[column.key]?.label ?? "none")
                          : view.kind === "link"
                            ? view.label
                            : "none"
                      }`}
                      onClick={() => setPicking(column)}
                    >
                      {column.key in links
                        ? (links[column.key]?.label ?? "Choose a record")
                        : view.kind === "link"
                          ? view.label
                          : "Choose a record"}
                    </Button>
                  ) : column.type === "user" && view.kind === "value" ? (
                    <PersonField id={view.text} />
                  ) : column.type === "select" && !fixed ? (
                    <select
                      className="border-input bg-background h-11 rounded-md border px-2 text-base"
                      value={drafts[column.key] ?? ""}
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [column.key]: event.target.value,
                        }))
                      }
                    >
                      <option value="">None</option>
                      {Object.entries(column.options ?? {}).map(
                        ([id, label]) => (
                          <option key={id} value={id}>
                            {label}
                          </option>
                        ),
                      )}
                    </select>
                  ) : (
                    <Input
                      className="h-11 min-h-11 text-base"
                      inputMode={column.numeric ? "decimal" : undefined}
                      readOnly={fixed}
                      value={shown}
                      onChange={(event) =>
                        setDrafts((current) => ({
                          ...current,
                          [column.key]: event.target.value,
                        }))
                      }
                    />
                  )}
                </label>
                {column.readOnly ? (
                  <span className="text-muted-foreground text-xs">
                    Read-only.
                  </span>
                ) : null}
              </div>
            );
          })}
          <div className="bg-card sticky bottom-0 flex justify-end gap-2 border-t pt-3">
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
      {picking?.linkModuleId ? (
        <SheetLinkPicker
          columnName={picking.name}
          moduleId={picking.linkModuleId}
          hasLink={
            picking.key in links
              ? Boolean(links[picking.key])
              : cellView(picking, row.cells[picking.key], format).kind ===
                "link"
          }
          onClose={() => setPicking(null)}
          onPick={(recordId, label) => {
            setLinks((current) => ({
              ...current,
              [picking.key]: recordId ? { id: recordId, label } : null,
            }));
            setPicking(null);
          }}
        />
      ) : null}
    </Dialog>
  );
}

function PersonField({ id }: { id: string }) {
  return (
    <Input
      className="h-11 min-h-11 text-base"
      readOnly
      value={usePersonName(id)}
    />
  );
}
