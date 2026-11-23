"use client";

import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { DialogCloseButton } from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspaceDisplayRegion } from "@/components/use-display-region";
import { ApiError } from "@/lib/api";
import { formatWorkspaceDateTime } from "@/lib/date-time";

import {
  listWorksheetHistory,
  type WorksheetDetail,
  type WorksheetRevision,
} from "../adapters/worksheets-api";
import {
  cellView,
  gridColumns,
  type GridColumn,
  type GridFormat,
} from "../domain/sheet-grid";
import { usePersonName } from "./sheet-grid-view";

// Sheet history (docs/specs/sheets.md H3, SH-46): every row change of the
// sheet, newest first, with its author, time and values. Cells read as the
// grid shows them, so a link the reader cannot read is "No access" (N4).

const ACTION_WORDS: Record<WorksheetRevision["action"], string> = {
  create: "Added a row",
  update: "Changed",
  delete: "Deleted a row",
  restore: "Restored a row",
};

function PersonValue({ id }: { id: string }) {
  return <>{usePersonName(id)}</>;
}

function CellText({
  column,
  cell,
  format,
}: {
  column: GridColumn;
  cell: WorksheetRevision["cells"][string] | undefined;
  format: GridFormat;
}) {
  const view = cellView(column, cell, format);
  if (view.kind === "blank") return <>Empty</>;
  if (view.kind === "link") return <>{view.label}</>;
  if (view.kind === "state" || view.kind === "error") return <>{view.words}</>;
  if (column.type === "user" && view.kind === "value")
    return <PersonValue id={view.text} />;
  return <>{view.text}</>;
}

function Entry({
  entry,
  columns,
  format,
}: {
  entry: WorksheetRevision;
  columns: readonly GridColumn[];
  format: GridFormat;
}) {
  const first = columns[0];
  const firstView = first
    ? cellView(first, entry.cells[first.key], format)
    : null;
  const rowName =
    firstView?.kind === "link"
      ? firstView.label
      : firstView?.kind === "value" || firstView?.kind === "unlinked"
        ? firstView.text
        : null;
  const changed = columns.filter((column) =>
    entry.changedKeys.includes(column.key),
  );
  const what =
    entry.action === "update"
      ? `Changed ${changed.map((column) => column.name).join(", ") || "a row"}`
      : ACTION_WORDS[entry.action];
  const region = { locale: format.locale, timezone: format.timezone };
  return (
    <li className="flex flex-col gap-1.5 py-3">
      <p className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm">
        <span className="font-medium">
          {entry.author?.displayName ?? "Someone"}
        </span>
        <time
          dateTime={entry.createdAt}
          className="text-muted-foreground text-xs tabular-nums"
        >
          {formatWorkspaceDateTime(entry.createdAt, region)}
        </time>
      </p>
      <p className="text-sm">
        {what}
        {rowName && first?.key && !entry.changedKeys.includes(first.key)
          ? ` · ${rowName}`
          : ""}
      </p>
      {changed.length ? (
        <dl className="text-muted-foreground grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 text-sm">
          {changed.map((column) => (
            <div key={column.key} className="contents">
              <dt>{`${column.name}: `}</dt>
              <dd className="text-foreground min-w-0 break-words">
                <CellText
                  column={column}
                  cell={entry.cells[column.key]}
                  format={format}
                />
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </li>
  );
}

export default function SheetHistoryPanel({
  sheet,
  onClose,
  onGone,
}: {
  sheet: WorksheetDetail;
  onClose: () => void;
  onGone: () => void;
}) {
  const region = useWorkspaceDisplayRegion();
  const format = useMemo<GridFormat>(
    () => ({
      locale: region?.locale ?? "en-US",
      timezone: region?.timezone ?? "UTC",
    }),
    [region?.locale, region?.timezone],
  );
  const columns = useMemo(() => gridColumns(sheet.structure), [sheet]);
  const [entries, setEntries] = useState<WorksheetRevision[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    listWorksheetHistory(sheet.id, { offset, signal: controller.signal }).then(
      (page) => {
        setEntries((current) =>
          offset === 0 ? page.items : [...(current ?? []), ...page.items],
        );
        setHasMore(page.hasMore);
        setFailed(false);
        setLoading(false);
      },
      (error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 404) onGone();
        else {
          setFailed(true);
          setLoading(false);
        }
      },
    );
    return () => controller.abort();
  }, [sheet.id, offset, attempt, onGone]);

  return (
    <Sheet
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent className="w-[min(100vw,28rem)] gap-2">
        <div className="pr-10">
          <SheetTitle>Sheet history</SheetTitle>
          <SheetDescription>
            Every row change of {sheet.title}, newest first.
          </SheetDescription>
        </div>
        <DialogCloseButton />
        {entries === null && loading ? (
          <div aria-busy="true" className="flex flex-col gap-3 pt-2">
            <span role="status" className="sr-only">
              Loading the history…
            </span>
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : null}
        {entries && entries.length === 0 ? (
          <p className="text-muted-foreground text-sm">No changes yet.</p>
        ) : null}
        {entries && entries.length > 0 ? (
          <ul className="divide-border flex flex-col divide-y">
            {entries.map((entry) => (
              <Entry
                key={entry.id}
                entry={entry}
                columns={columns}
                format={format}
              />
            ))}
          </ul>
        ) : null}
        {failed ? (
          <div
            role="alert"
            className="text-danger-text flex flex-wrap items-center gap-x-3 gap-y-1 text-sm"
          >
            The history could not be loaded.
            <Button
              variant="outline"
              className="min-h-11 xl:h-8 xl:min-h-8"
              onClick={() => {
                setLoading(true);
                setAttempt((value) => value + 1);
              }}
            >
              Retry
            </Button>
          </div>
        ) : null}
        {hasMore && !failed ? (
          <Button
            variant="outline"
            className="min-h-11 xl:h-8 xl:min-h-8"
            aria-busy={loading || undefined}
            onClick={() => {
              if (loading || !entries) return;
              setLoading(true);
              setOffset(entries.length);
            }}
          >
            Show older changes
          </Button>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
