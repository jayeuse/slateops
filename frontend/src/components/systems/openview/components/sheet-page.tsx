"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import type { Route } from "next";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowUpDown,
  Check,
  Eye,
  Lock,
  Pencil,
  Search,
  Users,
  X,
} from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspaceDisplayRegion } from "@/components/use-display-region";
import { GuardedWorkspaceLink } from "@/components/workspace-navigation-guard";
import { subscribeWorkspaceInvalidations } from "@/components/systems/shared/adapters/invalidation-events";
import { ApiError } from "@/lib/api";
import { apiErrorReference } from "@/lib/api-errors";

import {
  worksheetDetailOptions,
  worksheetKeys,
  worksheetPlaceOptions,
} from "../adapters/worksheet-queries";
import {
  createWorksheetRow,
  deleteWorksheetRow,
  queryWorksheetRows,
  updateWorksheetCells,
  type WorksheetCell,
  type WorksheetCellChange,
  type WorksheetDetail,
  type WorksheetRow,
  type WorksheetRowSort,
  type WorksheetTotal,
} from "../adapters/worksheets-api";
import {
  SheetGridView,
  type SaveOutcome,
  type SheetConflict,
} from "./sheet-grid-view";
import { SheetRowForm } from "./sheet-row-form";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  cellConflict,
  inputValue,
  storeRow,
  emptyRowStore,
  gridColumns,
  pagesForRange,
  rowAt,
  rowQueryKey,
  sortLabel,
  storeRowPage,
  type GridColumn,
  type GridFormat,
  type RowStore,
} from "../domain/sheet-grid";

// A sheet's own page (docs/specs/sheets.md P3, P6, F7, N4, N6 to N8,
// Screens 3 and 9): a header over one grid pane that scrolls alone. This
// unit reads; editing, sharing, export and import arrive in later units, so
// their actions do not show yet.

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SEARCH_DELAY_MS = 300;
function isNotFound(error: unknown) {
  return error instanceof ApiError && error.status === 404;
}

/** Phones read 44px rows (Screens 9); wider screens 40px. */
function usePhoneRows() {
  return useSyncExternalStore(
    (notify) => {
      const query = window.matchMedia("(max-width: 767px)");
      query.addEventListener("change", notify);
      return () => query.removeEventListener("change", notify);
    },
    () => window.matchMedia("(max-width: 767px)").matches,
    () => false,
  );
}

function SheetNotFound() {
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-4 sm:px-5 sm:py-6">
      <h1
        data-slot="page-title"
        className="text-2xl font-semibold tracking-tight sm:text-3xl"
      >
        Sheet not found
      </h1>
      <p className="text-muted-foreground text-sm">
        This sheet does not exist, or it is not shared with you.
      </p>
      <p>
        <Link
          href="/openview?section=sheets"
          className="text-action-text inline-flex min-h-11 items-center font-medium underline underline-offset-4"
        >
          My sheets
        </Link>
      </p>
    </div>
  );
}

function SheetLoading() {
  return (
    <div
      className="flex min-h-0 flex-1 flex-col gap-3 p-4 sm:px-5 sm:py-6"
      aria-busy="true"
    >
      <span role="status" className="sr-only">
        Loading the sheet…
      </span>
      <Skeleton className="h-9 w-64" />
      <Skeleton className="h-5 w-96 max-w-full" />
      <Skeleton className="min-h-0 w-full flex-1" />
    </div>
  );
}

function AccessChip({ sheet }: { sheet: WorksheetDetail }) {
  const [Icon, words] =
    sheet.state === "open"
      ? [Lock, "Read-only"]
      : sheet.myLevel === "owner"
        ? sheet.shared
          ? [Users, "Shared"]
          : [Lock, "Only you"]
        : sheet.myLevel === "edit"
          ? [Pencil, `You can edit · shared by ${sheet.owner.displayName}`]
          : [Eye, `You can view · shared by ${sheet.owner.displayName}`];
  return (
    <span className="bg-muted text-muted-foreground inline-flex min-h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium">
      <Icon aria-hidden="true" className="size-3.5 shrink-0" />
      <span>{words}</span>
    </span>
  );
}

function SheetMeta({ sheet }: { sheet: WorksheetDetail }) {
  const place = useQuery(worksheetPlaceOptions(sheet.id, sheet)).data;
  const rows = `${sheet.liveRowCount} ${sheet.liveRowCount === 1 ? "row" : "rows"}`;
  const owner = `Owner: ${sheet.myLevel === "owner" ? "you" : sheet.owner.displayName}`;
  const recordLink =
    sheet.recordId && place
      ? (`/openview?section=views&module=${encodeURIComponent(place.moduleId)}&record=${encodeURIComponent(sheet.recordId)}` as Route)
      : null;
  return (
    <p className="text-muted-foreground mt-1 text-sm tabular-nums">
      On{" "}
      {sheet.recordId ? (
        recordLink ? (
          <GuardedWorkspaceLink
            href={recordLink}
            className="text-action-text font-medium hover:underline"
          >
            {sheet.anchorTitle}
          </GuardedWorkspaceLink>
        ) : (
          sheet.anchorTitle
        )
      ) : (
        sheet.moduleName
      )}
      {sheet.recordId ? ` · ${sheet.moduleName}` : ""} · {rows} · {owner}
    </p>
  );
}

function SortControl({
  columns,
  sort,
  onSort,
}: {
  columns: readonly GridColumn[];
  sort: WorksheetRowSort | null;
  onSort: (sort: WorksheetRowSort | null) => void;
}) {
  const sorted = sort
    ? columns.find((column) => column.key === sort.key)
    : undefined;
  const label = sorted && sort ? sortLabel(sorted, sort.order) : "Sort";
  const choices = columns.filter((column) => column.type !== "sheet_lookup");
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant={sort ? "outline" : "ghost"}
            aria-label={label}
            className="min-h-11 max-w-64 shrink-0 max-sm:w-11 max-sm:px-0 xl:h-8 xl:min-h-8"
          />
        }
      >
        <ArrowUpDown aria-hidden="true" />
        <span className="truncate max-sm:sr-only">{label}</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-80 overflow-y-auto">
        {sort ? (
          <DropdownMenuItem onClick={() => onSort(null)}>
            Saved order
          </DropdownMenuItem>
        ) : null}
        {choices.flatMap((column) =>
          (["asc", "desc"] as const).map((order) => {
            const current = sort?.key === column.key && sort.order === order;
            return (
              <DropdownMenuItem
                key={`${column.key}-${order}`}
                onClick={() => onSort({ key: column.key, order })}
              >
                <span className="flex-1">{sortLabel(column, order)}</span>
                {current ? <Check aria-hidden="true" /> : null}
              </DropdownMenuItem>
            );
          }),
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function SheetView({ sheet }: { sheet: WorksheetDetail }) {
  const client = useQueryClient();
  const region = useWorkspaceDisplayRegion();
  const phone = usePhoneRows();
  const format = useMemo<GridFormat>(
    () => ({
      locale: region?.locale ?? "en-US",
      timezone: region?.timezone ?? "UTC",
    }),
    [region?.locale, region?.timezone],
  );
  const columns = useMemo(() => gridColumns(sheet.structure), [sheet]);
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<WorksheetRowSort | null>(null);
  const [gone, setGone] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const queryKey = rowQueryKey({ sort, search });
  const [store, setStore] = useState<RowStore>(() => emptyRowStore(queryKey));
  const [totals, setTotals] = useState<Record<string, WorksheetTotal>>({});
  const [generation, setGeneration] = useState(0);
  const loading = useRef(new Set<string>());
  // Each request is numbered, so a slow, older answer never wins (sheet-grid).
  const sequence = useRef(0);
  const range = useRef<[number, number]>([0, 0]);
  const [conflict, setConflict] = useState<SheetConflict | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [pasteNote, setPasteNote] = useState<string | null>(null);
  const [savingCount, setSavingCount] = useState(0);
  const [deleting, setDeleting] = useState<{
    row: WorksheetRow;
    index: number;
  } | null>(null);
  const [formRow, setFormRow] = useState<number | null>(null);
  // A saved column list rereads the rows: new columns have cells.
  const seenRevision = useRef(sheet.revision);
  useEffect(() => {
    if (seenRevision.current === sheet.revision) return;
    seenRevision.current = sheet.revision;
    setGeneration((value) => value + 1);
  }, [sheet.revision]);

  /** Saves cells of one row (route 12); `expected` is what the person saw. */
  const saveCells = async (
    row: WorksheetRow,
    cells: Record<string, WorksheetCellChange>,
    conflictOf: { key: string; columnName: string; draft: string },
  ): Promise<SaveOutcome> => {
    sequence.current += 1;
    const asked = sequence.current;
    setSavingCount((value) => value + 1);
    try {
      const saved = await updateWorksheetCells(sheet.id, row.id, cells);
      setStore((current) => storeRow(current, saved, asked));
      setSaveError(null);
      setConflict((current) => (current?.rowId === row.id ? null : current));
      return "saved";
    } catch (error) {
      const found = cellConflict(error);
      if (found) {
        setStore((current) => storeRow(current, found.current, asked));
        setConflict({ rowId: row.id, ...conflictOf });
        return "conflict";
      }
      if (isNotFound(error)) {
        setGone(true);
        return "refused";
      }
      setSaveError(
        `${conflictOf.columnName}: ${
          error instanceof ApiError &&
          (error.status === 403 || error.status === 422)
            ? error.message
            : "The change could not be saved. Try again."
        }`,
      );
      return "refused";
    } finally {
      setSavingCount((value) => value - 1);
    }
  };

  const saveCell = (
    row: WorksheetRow,
    column: GridColumn,
    value: unknown,
    expected: WorksheetCell,
    draft: string,
  ) =>
    saveCells(
      row,
      { [column.key]: { value, expected } },
      { key: column.key, columnName: column.name, draft },
    );

  const saveRow = async (cells: Record<string, WorksheetCellChange>) => {
    const row = formRow === null ? undefined : rowAt(store, formRow);
    const key = Object.keys(cells)[0];
    const column = columns.find((item) => item.key === key);
    if (!row || !key || !column) return false;
    const outcome = await saveCells(row, cells, {
      key,
      columnName: column.name,
      draft: String(cells[key]?.value ?? ""),
    });
    return outcome === "saved";
  };

  const addRow = async () => {
    try {
      await createWorksheetRow(sheet.id);
      // The new row is at the end of the saved order: show that order.
      setTyped("");
      setSearch("");
      setSort(null);
      setGeneration((value) => value + 1);
    } catch {
      setSaveError("The row could not be added. Try again.");
    }
  };

  const deleteRow = async () => {
    if (!deleting) return;
    const { row } = deleting;
    setDeleting(null);
    try {
      await deleteWorksheetRow(sheet.id, row);
      setGeneration((value) => value + 1);
    } catch {
      setSaveError("The row could not be deleted. Try again.");
    }
  };

  /** A pasted block fills cells from the focused one, row by row (X11). */
  const paste = async (index: number, start: number, grid: string[][]) => {
    let pasted = 0;
    for (const [offset, line] of grid.entries()) {
      const row = rowAt(store, index + offset);
      if (!row) break;
      const cells: Record<string, WorksheetCellChange> = {};
      for (const [step, text] of line.entries()) {
        const column = columns[start + step];
        if (
          !column ||
          column.readOnly ||
          column.type === "user" ||
          column.type === "link"
        )
          continue;
        cells[column.key] = {
          value: inputValue(column, text),
          expected: row.cells[column.key] ?? { value: null },
        };
      }
      const first = Object.keys(cells)[0];
      const column = columns.find((item) => item.key === first);
      if (!first || !column) continue;
      const outcome = await saveCells(row, cells, {
        key: first,
        columnName: column.name,
        draft: line.join(" "),
      });
      if (outcome === "saved") pasted += Object.keys(cells).length;
      else break;
    }
    setPasteNote(
      pasted ? `Pasted ${pasted} ${pasted === 1 ? "cell" : "cells"}.` : null,
    );
  };
  if (store.queryKey !== queryKey) setStore(emptyRowStore(queryKey));

  // The search waits for typing to pause; sort and search are never saved.
  useEffect(() => {
    const timer = window.setTimeout(
      () => setSearch(typed.trim()),
      SEARCH_DELAY_MS,
    );
    return () => window.clearTimeout(timer);
  }, [typed]);

  const load = useCallback(
    (offset: number, refresh: number) => {
      const marker = `${queryKey}|${offset}|${refresh}`;
      if (loading.current.has(marker)) return;
      loading.current.add(marker);
      sequence.current += 1;
      const asked = sequence.current;
      queryWorksheetRows(sheet.id, { sort, search, offset })
        .then((page) => {
          setStore((current) =>
            storeRowPage(current, queryKey, offset, page, asked),
          );
          setTotals(page.totals);
          setFailure(null);
        })
        .catch((error: unknown) => {
          loading.current.delete(marker);
          if (isNotFound(error)) {
            // A sheet that became hidden leaves no title behind (V7).
            void client.resetQueries({
              queryKey: worksheetKeys.place(sheet.id),
            });
            setGone(true);
          } else setFailure(error);
        });
    },
    [client, sheet.id, sort, search, queryKey],
  );

  const onRange = useCallback(
    (start: number, end: number) => {
      range.current = [start, end];
      const total = store.total;
      const offsets = total === null ? [0] : pagesForRange(start, end, total);
      for (const offset of offsets)
        if (!store.pages[offset] || generation > 0) load(offset, generation);
    },
    [store.total, store.pages, load, generation],
  );

  // The first page of each search and sort.
  useEffect(() => {
    load(0, generation);
  }, [load, generation]);

  // Live refresh: this sheet's events and the records of its link columns'
  // modules refetch the pages on screen; a resync refetches everything.
  const linkModules = useMemo(
    () =>
      new Set(
        columns.flatMap((column) =>
          column.linkModuleId ? [column.linkModuleId] : [],
        ),
      ),
    [columns],
  );
  useEffect(() => {
    const refresh = () => setGeneration((value) => value + 1);
    // A resync, and the stream's opening one, reread the sheet and its rows:
    // a change may have been missed while nothing listened.
    const rereadAll = () => {
      void client.invalidateQueries({
        queryKey: worksheetKeys.detail(sheet.id),
      });
      void client.invalidateQueries({
        queryKey: worksheetKeys.place(sheet.id),
      });
      refresh();
    };
    return subscribeWorkspaceInvalidations((event) => {
      if (event.type === "resync") {
        rereadAll();
        return;
      }
      if (event.entity === "worksheets" && event.worksheetId === sheet.id) {
        // A rename reaches the header and its breadcrumb.
        void client.invalidateQueries({
          queryKey: worksheetKeys.detail(sheet.id),
        });
        void client.invalidateQueries({
          queryKey: worksheetKeys.place(sheet.id),
        });
        refresh();
      } else if (
        event.entity === "records" &&
        event.moduleId &&
        linkModules.has(event.moduleId)
      )
        refresh();
    }, rereadAll);
  }, [client, sheet.id, linkModules]);

  // A refresh rereads the pages on screen in place, so rows never blank.
  // Each page loads once per generation, so a rerun asks for nothing new.
  useEffect(() => {
    if (generation === 0) return;
    const [start, end] = range.current;
    const total = store.total;
    for (const offset of total === null
      ? [0]
      : pagesForRange(start, end, total))
      load(offset, generation);
  }, [generation, load, store.total]);

  if (gone) return <SheetNotFound />;
  const searching = search.length > 0;
  const canEdit = sheet.state !== "open" && sheet.myLevel !== "view";
  // Route 6 takes every column back; a masked one cannot be sent (D14 S1).
  const canChangeColumns =
    canEdit && !sheet.structure.columns.some((column) => "state" in column);
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3 p-4 sm:px-5 sm:py-4">
      <header className="flex min-w-0 flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
            <h1
              data-slot="page-title"
              className="min-w-0 truncate text-2xl font-semibold tracking-tight sm:text-3xl"
            >
              {sheet.title}
            </h1>
            <AccessChip sheet={sheet} />
          </div>
          <SheetMeta sheet={sheet} />
        </div>
        {/* Import, Export, Share and More arrive with their units. */}
      </header>
      <div
        role="toolbar"
        aria-label="Sheet controls"
        className="flex min-w-0 items-center gap-2"
      >
        <div className="relative min-w-0 flex-1 sm:w-72 sm:flex-none">
          <Search
            aria-hidden="true"
            className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
          />
          <Input
            type="search"
            aria-label="Search this sheet"
            placeholder="Search this sheet"
            maxLength={200}
            className="min-h-11 pr-11 pl-9 xl:h-8 xl:min-h-8"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
          />
          {typed ? (
            <Button
              variant="ghost"
              size="icon"
              className="absolute top-1/2 right-0 size-11 -translate-y-1/2 xl:size-8"
              aria-label="Clear search"
              onClick={() => setTyped("")}
            >
              <X aria-hidden="true" />
            </Button>
          ) : null}
        </div>
        <SortControl columns={columns} sort={sort} onSort={setSort} />
        {searching && store.total !== null ? (
          <span className="text-muted-foreground text-sm tabular-nums">
            {store.total} of {sheet.liveRowCount} rows
          </span>
        ) : null}
        {!canEdit ? null : conflict ? (
          <span
            role="status"
            className="text-warn-text ml-auto inline-flex items-center gap-1.5 text-sm"
          >
            <AlertTriangle aria-hidden="true" className="size-4" />1 change not
            saved
          </span>
        ) : (
          <span
            role="status"
            className="text-muted-foreground ml-auto inline-flex items-center gap-1.5 text-sm max-sm:hidden"
          >
            <Check aria-hidden="true" className="size-4" />
            {savingCount > 0 ? "Saving…" : "Saved"}
          </span>
        )}
      </div>
      {failure ? (
        <Alert
          variant="destructive"
          reference={apiErrorReference(failure)}
          className="flex flex-wrap items-center gap-x-4 gap-y-2"
        >
          <p className="min-w-0 flex-1">The rows could not be loaded.</p>
          <Button
            variant="outline"
            className="min-h-11 shrink-0 xl:h-8 xl:min-h-8"
            onClick={() => setGeneration((value) => value + 1)}
          >
            Retry
          </Button>
        </Alert>
      ) : null}
      {saveError ? (
        <Alert
          variant="destructive"
          className="flex flex-wrap items-center gap-x-4 gap-y-2"
        >
          <p className="min-w-0 flex-1">{saveError}</p>
          <Button
            variant="ghost"
            className="min-h-11 shrink-0 xl:h-8 xl:min-h-8"
            onClick={() => setSaveError(null)}
          >
            Dismiss
          </Button>
        </Alert>
      ) : null}
      {pasteNote ? (
        <p role="status" className="text-muted-foreground text-sm">
          {pasteNote}
        </p>
      ) : null}
      <SheetGridView
        sheet={sheet}
        columns={columns}
        store={store}
        totals={totals}
        searching={searching}
        format={format}
        phone={phone}
        canEdit={canEdit}
        canChangeColumns={canChangeColumns}
        conflict={conflict}
        onRange={onRange}
        onSave={saveCell}
        onDismissConflict={() => setConflict(null)}
        onAddRow={() => void addRow()}
        onDeleteRow={(row, index) => setDeleting({ row, index })}
        onOpenRow={setFormRow}
        onPaste={(index, column, grid) => void paste(index, column, grid)}
      />
      {formRow !== null && rowAt(store, formRow) ? (
        <SheetRowForm
          key={rowAt(store, formRow)?.id}
          row={rowAt(store, formRow) as WorksheetRow}
          index={formRow}
          total={store.total ?? 0}
          sheetTitle={sheet.title}
          columns={columns}
          format={format}
          readOnly={!canEdit}
          onSave={saveRow}
          onMove={(index) => {
            if (rowAt(store, index)) setFormRow(index);
          }}
          onClose={() => setFormRow(null)}
        />
      ) : null}
      <AlertDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogTitle>
            Delete row {deleting ? deleting.index + 1 : ""}?
          </AlertDialogTitle>
          <AlertDialogDescription>
            The row leaves this sheet for everyone who can see it.
          </AlertDialogDescription>
          <div className="flex justify-end gap-2">
            <AlertDialogCancel
              render={<Button variant="ghost" className="min-h-11" />}
            >
              Cancel
            </AlertDialogCancel>
            <Button
              variant="destructive"
              className="min-h-11"
              onClick={() => void deleteRow()}
            >
              Delete row
            </Button>
          </div>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

/** `/openview?sheet=<id>`: the same not-found page for a missing or hidden sheet (P6). */
export default function SheetPage({ sheetId }: { sheetId: string }) {
  const client = useQueryClient();
  const valid = UUID.test(sheetId);
  const detail = useQuery({
    ...worksheetDetailOptions(sheetId),
    enabled: valid,
  });
  const hidden = isNotFound(detail.error);
  // A sheet that became hidden leaves no title in the breadcrumb (V7).
  useEffect(() => {
    if (hidden)
      void client.resetQueries({ queryKey: worksheetKeys.place(sheetId) });
  }, [hidden, client, sheetId]);
  if (!valid || hidden) return <SheetNotFound />;
  if (detail.data) return <SheetView key={sheetId} sheet={detail.data} />;
  if (detail.isError)
    return (
      <div className="p-4 sm:px-5 sm:py-6">
        <Alert
          variant="destructive"
          reference={apiErrorReference(detail.error)}
          className="flex flex-wrap items-center gap-x-4 gap-y-2"
        >
          <p className="min-w-0 flex-1">The sheet could not be loaded.</p>
          <Button
            variant="outline"
            className="min-h-11 shrink-0 xl:h-8 xl:min-h-8"
            aria-disabled={detail.isFetching || undefined}
            onClick={() => {
              if (!detail.isFetching) void detail.refetch();
            }}
          >
            Retry
          </Button>
        </Alert>
      </div>
    );
  return <SheetLoading />;
}
