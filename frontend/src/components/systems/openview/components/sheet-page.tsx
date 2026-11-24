"use client";

import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import type { Route } from "next";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
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
import { personCardOptions } from "@/components/profile/adapters/profile-queries";
import { useWorkspaceDisplayRegion } from "@/components/use-display-region";
import { GuardedWorkspaceLink } from "@/components/workspace-navigation-guard";
import { subscribeWorkspaceInvalidations } from "@/components/systems/shared/adapters/invalidation-events";
import { ApiError } from "@/lib/api";
import { apiErrorReference } from "@/lib/api-errors";
import { cn } from "@/lib/utils";

import {
  worksheetDetailOptions,
  worksheetKeys,
  worksheetPlaceOptions,
  worksheetSharesOptions,
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
} from "../adapters/worksheets-api";
import { authMeOptions } from "../adapters/openview-queries";
import { sheetHref } from "./sheet-display";
import { SheetGridView, type SheetConflict } from "./sheet-grid-view";
import {
  SheetPresenceAvatars,
  type PresencePerson,
} from "./sheet-presence-avatars";
import { useSheetPresence } from "./use-sheet-presence";
import { presenceOutlines } from "../domain/sheet-presence";
import type { SaveResult } from "./sheet-row-form";
import { SheetHeaderActions } from "./sheet-header-actions";
import { useSheetOrganizationName } from "./use-sheet-organization";
import {
  openLine,
  sharedWithWords,
  sheetRole,
  type SheetRole,
} from "../domain/sheet-share";
// The editing dialogs load on first use, apart from the grid.
const SheetRowForm = lazy(() =>
  import("./sheet-row-form").then((module) => ({
    default: module.SheetRowForm,
  })),
);
const SheetDeleteRowDialog = lazy(() => import("./sheet-delete-row-dialog"));
import {
  cellConflict,
  conflictWords,
  inputValue,
  storeRow,
  emptyRowStore,
  gridColumns,
  pagesForRange,
  rowAt,
  rowIndex,
  rowQueryKey,
  sortLabel,
  storeRowPage,
  type GridColumn,
  type GridFormat,
  type RowStore,
} from "../domain/sheet-grid";

// A sheet's own page (docs/specs/sheets.md P3, P6, F7, N4, N6 to N8, L2,
// L7, L10; Screens 3, 5 and 9): a header with the actions the viewer may use
// over one grid pane that scrolls alone. Import and Make a copy arrive in F7.

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SEARCH_DELAY_MS = 300;
function isNotFound(error: unknown) {
  return error instanceof ApiError && error.status === 404;
}

/** A row write's 404: the row, not the sheet, is gone (parent decision). */
function isRowGone(error: unknown) {
  return (
    isNotFound(error) && (error as ApiError).code === "worksheet_row_not_found"
  );
}

/** Only `worksheet_not_found` from a write means the sheet is gone. */
function isSheetGone(error: unknown) {
  return (
    isNotFound(error) && (error as ApiError).code === "worksheet_not_found"
  );
}

const ROW_GONE = "This row was deleted by someone else.";

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
        This sheet does not exist, or you cannot open it.
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

function AccessChip({
  sheet,
  role,
}: {
  sheet: WorksheetDetail;
  role: SheetRole;
}) {
  // Only the owner of a sheet that is not open reads its shares (route 16).
  const shares = useQuery({
    ...worksheetSharesOptions(sheet.id),
    enabled: role === "owner" && sheet.shared === true,
  });
  const [Icon, words] =
    role === "open"
      ? [Lock, "Read-only"]
      : role === "owner"
        ? sheet.shared
          ? [Users, shares.data ? sharedWithWords(shares.data) : "Shared"]
          : [Lock, "Only you"]
        : role === "edit"
          ? [Pencil, `You can edit · shared by ${sheet.owner.displayName}`]
          : [Eye, `You can view · shared by ${sheet.owner.displayName}`];
  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium",
        role === "open"
          ? "bg-warn-tint text-warn-text"
          : "bg-muted text-muted-foreground",
      )}
    >
      <Icon aria-hidden="true" className="size-3.5 shrink-0" />
      <span>{words}</span>
    </span>
  );
}

/** Why an open sheet is read-only (L10), directly under its title. */
function OpenLine({ sheet }: { sheet: WorksheetDetail }) {
  const organization = useSheetOrganizationName();
  return (
    <p className="mt-1.5 max-w-3xl text-sm">{openLine(sheet, organization)}</p>
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
            Sheet order
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
      currency: region?.currency,
    }),
    [region?.locale, region?.timezone, region?.currency],
  );
  // Keyed on the structure: a rename or a new row count is no new columns,
  // so it neither resubscribes the events nor rereads the rows.
  const columns = useMemo(
    () => gridColumns(sheet.structure),
    [sheet.structure],
  );
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<WorksheetRowSort | null>(null);
  const [gone, setGone] = useState(false);
  const [failure, setFailure] = useState<unknown>(null);
  const queryKey = rowQueryKey({ sort, search });
  const [store, setStore] = useState<RowStore>(() => emptyRowStore(queryKey));
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
  // The row form follows its row by id: a refresh may move rows.
  const [formRowId, setFormRowId] = useState<string | null>(null);
  const formIndex = formRowId === null ? -1 : rowIndex(store, formRowId);
  const formRow = formIndex >= 0 ? rowAt(store, formIndex) : undefined;
  // A row that a loaded list no longer holds closes its form.
  if (formRowId !== null && formIndex < 0 && store.total !== null)
    setFormRowId(null);
  // A sheet that is gone takes its cached detail along, so a later visit
  // never shows its title first.
  const markGone = useCallback(() => {
    client.removeQueries({ queryKey: worksheetKeys.detail(sheet.id) });
    setGone(true);
  }, [client, sheet.id]);
  // A saved column list rereads the rows: new columns have cells.
  const seenRevision = useRef(sheet.revision);
  useEffect(() => {
    if (seenRevision.current === sheet.revision) return;
    seenRevision.current = sheet.revision;
    setGeneration((value) => value + 1);
  }, [sheet.revision]);

  /**
   * Saves cells of one row (route 12); `expected` is what the person saw.
   * The grid shows a refusal over itself; the row form shows its own.
   */
  const saveCells = async (
    row: WorksheetRow,
    cells: Record<string, WorksheetCellChange>,
    conflictOf: {
      key: string;
      columnName: string;
      draft: string;
      /** The form's text per column, for the column the conflict names. */
      drafts?: Record<string, string>;
    },
    from: "grid" | "form" = "grid",
  ): Promise<SaveResult> => {
    sequence.current += 1;
    const asked = sequence.current;
    setSavingCount((value) => value + 1);
    try {
      const saved = await updateWorksheetCells(sheet.id, row.id, cells);
      setStore((current) => storeRow(current, saved, asked));
      setSaveError(null);
      setConflict((current) => (current?.rowId === row.id ? null : current));
      return { outcome: "saved" };
    } catch (error) {
      const found = cellConflict(error);
      if (found) {
        setStore((current) => storeRow(current, found.current, asked));
        // The column the person changed that someone else changed too.
        const key =
          Object.keys(cells).find((item) => found.keys.includes(item)) ??
          conflictOf.key;
        const column = columns.find((item) => item.key === key);
        const named = {
          key,
          columnName: column?.name ?? conflictOf.columnName,
          draft: conflictOf.drafts?.[key] ?? conflictOf.draft,
          changedBy: found.changedBy,
        };
        setConflict({ rowId: row.id, ...named });
        return {
          outcome: "conflict",
          current: found.current,
          line: `${conflictWords(found.changedBy)} It now shows the newer values. Your ${named.columnName} (${named.draft}) was not saved.`,
        };
      }
      if (isRowGone(error)) {
        // The edit or the form ends, and the rows on screen are read again.
        setSaveError(ROW_GONE);
        setGeneration((value) => value + 1);
        return { outcome: "gone" };
      }
      if (isSheetGone(error)) {
        markGone();
        return { outcome: "refused", message: "" };
      }
      const detailKey =
        error instanceof ApiError &&
        typeof error.details === "object" &&
        error.details !== null &&
        "key" in error.details &&
        typeof error.details.key === "string"
          ? error.details.key
          : null;
      const columnName =
        columns.find((item) => item.key === detailKey)?.name ??
        conflictOf.columnName;
      const message = `${columnName}: ${
        error instanceof ApiError &&
        (error.status === 403 || error.status === 422)
          ? error.message
          : "The change could not be saved. Try again."
      }`;
      if (from === "grid") setSaveError(message);
      return { outcome: "refused", message };
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
    ).then((result) => result.outcome);

  const saveRow = async (
    cells: Record<string, WorksheetCellChange>,
    drafts: Record<string, string>,
  ): Promise<SaveResult> => {
    const row = formRow;
    const key = Object.keys(cells)[0];
    const column = columns.find((item) => item.key === key);
    if (!row || !key || !column)
      return { outcome: "refused", message: "The row could not be saved." };
    return saveCells(
      row,
      cells,
      { key, columnName: column.name, draft: drafts[key] ?? "", drafts },
      "form",
    );
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
    } catch (error) {
      if (isRowGone(error)) {
        setSaveError(ROW_GONE);
        setGeneration((value) => value + 1);
      } else if (isSheetGone(error)) markGone();
      else setSaveError("The row could not be deleted. Try again.");
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
      const { outcome } = await saveCells(row, cells, {
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
  // Totals cover every row whatever the search, so a new key keeps them.
  if (store.queryKey !== queryKey)
    setStore(emptyRowStore(queryKey, store.totals));

  // The search waits for typing to pause; sort and search are never saved.
  useEffect(() => {
    const timer = window.setTimeout(
      () => setSearch(typed.trim()),
      SEARCH_DELAY_MS,
    );
    return () => window.clearTimeout(timer);
  }, [typed]);

  // Each search and sort has its own load markers and requests: leaving it
  // aborts what it still waits for and forgets what it loaded, so a return
  // to it loads again (its store starts empty).
  const requests = useRef(new Set<AbortController>());
  useEffect(() => {
    const open = requests.current;
    const markers = loading.current;
    return () => {
      for (const controller of open) controller.abort();
      open.clear();
      markers.clear();
    };
  }, [queryKey]);

  const load = useCallback(
    (offset: number, refresh: number) => {
      const marker = `${queryKey}|${offset}|${refresh}`;
      if (loading.current.has(marker)) return;
      loading.current.add(marker);
      sequence.current += 1;
      const asked = sequence.current;
      const controller = new AbortController();
      requests.current.add(controller);
      queryWorksheetRows(sheet.id, {
        sort,
        search,
        offset,
        signal: controller.signal,
      })
        .then((page) => {
          setStore((current) =>
            storeRowPage(current, queryKey, offset, page, asked),
          );
          setFailure(null);
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          loading.current.delete(marker);
          if (isNotFound(error)) {
            // A sheet that became hidden leaves no title behind (V7).
            void client.resetQueries({
              queryKey: worksheetKeys.place(sheet.id),
            });
            markGone();
          } else setFailure(error);
        })
        .finally(() => requests.current.delete(controller));
    },
    [client, sheet.id, sort, search, queryKey, markGone],
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

  // An address with a row (Appears in, Screens 6): in the sheet's own order
  // the page holding row n is read; when row n is still that row, the grid
  // shows it lit, with focus on its first cell. Either way the row then
  // leaves the address.
  const params = useSearchParams();
  const router = useRouter();
  const [target, setTarget] = useState(() => {
    if (!params.has("row") && !params.has("n")) return null;
    const rowId = params.get("row") ?? "";
    const n = Number(params.get("n"));
    return UUID.test(rowId) && Number.isSafeInteger(n) && n >= 1
      ? { rowId, index: n - 1 }
      : { rowId, index: -1 };
  });
  const [highlight, setHighlight] = useState<{ index: number } | null>(null);

  // Who else has the sheet open, and where (PR1, PR2). Names and photos
  // come from the person cards the viewer reads here, so nothing from the
  // channel becomes text.
  const presence = useSheetPresence(sheet.id);
  const identity = useQuery(authMeOptions());
  const viewer = identity.data
    ? { id: identity.data.id, role: identity.data.role ?? "guest" }
    : null;
  const cards = useQueries({
    queries: presence.peers.map((peer) => ({
      ...personCardOptions(viewer ?? { id: "", role: "member" }, peer.userId),
      enabled: Boolean(viewer),
    })),
    combine: cardData,
  });
  const people = useMemo(() => {
    const known = new Map<string, PresencePerson>();
    presence.peers.forEach((peer, index) => {
      const card = cards[index];
      if (card)
        known.set(peer.userId, {
          name: card.display_name,
          avatarUrl: card.avatar_url,
        });
    });
    return known;
  }, [presence.peers, cards]);
  const columnKeys = useMemo(
    () => new Set(columns.map((column) => column.key)),
    [columns],
  );
  // Each loaded row's place, once per load, for the rings.
  const rowPlaces = useMemo(() => {
    const places = new Map<string, number>();
    for (const [offset, rows] of Object.entries(store.pages))
      rows.forEach((row, at) => places.set(row.id, Number(offset) + at));
    return places;
  }, [store.pages]);
  const outlines = useMemo(
    () =>
      presenceOutlines(
        presence.peers,
        (rowId) => rowPlaces.get(rowId) ?? -1,
        columnKeys,
        (userId) => people.get(userId)?.name,
      ),
    [presence.peers, rowPlaces, columnKeys, people],
  );
  useEffect(() => {
    if (!target) return;
    const settled = () => {
      setTarget(null);
      router.replace(sheetHref(sheet.id) as Route, { scroll: false });
    };
    if (target.index < 0 || sort || search) return settled();
    if (store.total === null) return;
    if (target.index >= store.total) return settled();
    const row = rowAt(store, target.index);
    if (!row) {
      for (const offset of pagesForRange(
        target.index,
        target.index,
        store.total,
      ))
        load(offset, generation);
      return;
    }
    if (row.id === target.rowId) setHighlight({ index: target.index });
    settled();
  }, [target, sort, search, store, load, generation, router, sheet.id]);

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
  // The source sheets of From another sheet columns that the viewer can see
  // (a hidden source carries no id): their changes reach this sheet (D7.3a).
  const sourceSheets = useMemo(
    () =>
      new Set(
        sheet.structure.columns.flatMap((column) =>
          "sheet_lookup" in column
            ? [column.sheet_lookup.sourceWorksheetId]
            : [],
        ),
      ),
    [sheet.structure.columns],
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
        event.entity === "worksheets" &&
        event.worksheetId &&
        sourceSheets.has(event.worksheetId)
      )
        refresh();
      else if (
        event.entity === "records" &&
        event.moduleId &&
        linkModules.has(event.moduleId)
      )
        refresh();
    }, rereadAll);
  }, [client, sheet.id, linkModules, sourceSheets]);

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
  const role = sheetRole(sheet);
  const canEdit = role === "owner" || role === "edit";
  // Route 6 takes a masked column back unchanged (D14 S1).
  const canChangeColumns = canEdit;
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
            <AccessChip sheet={sheet} role={role} />
          </div>
          <SheetMeta sheet={sheet} />
          {role === "open" ? <OpenLine sheet={sheet} /> : null}
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-2">
          <SheetPresenceAvatars peers={presence.peers} people={people} />
          <SheetHeaderActions
            sheet={sheet}
            role={role}
            onFailure={setSaveError}
            onGone={markGone}
            onRowsChanged={() => {
              void client.invalidateQueries({
                queryKey: worksheetKeys.detail(sheet.id),
              });
              setGeneration((value) => value + 1);
            }}
          />
        </div>
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
        totals={store.totals}
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
        onOpenRow={(index) => setFormRowId(rowAt(store, index)?.id ?? null)}
        onPaste={(index, column, grid) => void paste(index, column, grid)}
        highlight={highlight}
        onCellFocus={(index, columnKey) => {
          const row = rowAt(store, index);
          if (row) presence.move({ rowId: row.id, columnKey });
        }}
        outlines={outlines}
      />
      {formRow ? (
        <Suspense fallback={null}>
          <SheetRowForm
            key={formRow.id}
            row={formRow}
            index={formIndex}
            total={store.total ?? 0}
            sheetTitle={sheet.title}
            columns={columns}
            format={format}
            readOnly={!canEdit}
            sheetId={sheet.id}
            onSave={saveRow}
            onDelete={(row, index) => {
              setFormRowId(null);
              setDeleting({ row, index });
            }}
            onMove={(index) => {
              const next = rowAt(store, index);
              if (next) setFormRowId(next.id);
            }}
            onClose={() => setFormRowId(null)}
          />
        </Suspense>
      ) : null}
      {deleting ? (
        <Suspense fallback={null}>
          <SheetDeleteRowDialog
            index={deleting.index}
            onCancel={() => setDeleting(null)}
            onConfirm={() => void deleteRow()}
          />
        </Suspense>
      ) : null}
    </div>
  );
}

/** The person cards' data, kept the same while the cards are unchanged. */
function cardData(
  results: {
    data?: { data: { display_name: string; avatar_url: string | null } };
  }[],
) {
  return results.map((result) => result.data?.data);
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
