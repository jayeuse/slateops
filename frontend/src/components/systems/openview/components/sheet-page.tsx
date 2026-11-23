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
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  AlignLeft,
  ArrowUpDown,
  Calendar,
  Check,
  CheckSquare,
  Eye,
  Hash,
  Link2,
  List,
  Lock,
  Mail,
  Pencil,
  Search,
  Sheet as SheetIcon,
  Sigma,
  Trash2,
  Type,
  UserRound,
  Users,
  X,
  type LucideIcon,
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
import { cn } from "@/lib/utils";

import {
  worksheetDetailOptions,
  worksheetKeys,
  worksheetPlaceOptions,
} from "../adapters/worksheet-queries";
import {
  queryWorksheetRows,
  type WorksheetDetail,
  type WorksheetRowSort,
  type WorksheetTotal,
} from "../adapters/worksheets-api";
import {
  cellView,
  emptyRowStore,
  gridBands,
  gridColumns,
  pagesForRange,
  rowAt,
  rowQueryKey,
  sortLabel,
  storeRowPage,
  totalView,
  type GridColumn,
  type GridFormat,
  type RowStore,
  type SheetColumnType,
} from "../domain/sheet-grid";

// A sheet's own page (docs/specs/sheets.md P3, P6, F7, N4, N6 to N8,
// Screens 3 and 9): a header over one grid pane that scrolls alone. This
// unit reads; editing, sharing, export and import arrive in later units, so
// their actions do not show yet.

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SEARCH_DELAY_MS = 300;
// The fixed band: row number and first column. On a phone the two make one
// 160px first column (Screens 9).
const ROW_NUMBER_WIDTH = 56;
const PHONE_ROW_NUMBER_WIDTH = 40;

const TYPE_ICONS: Record<SheetColumnType, LucideIcon> = {
  text: Type,
  long_text: AlignLeft,
  email: Mail,
  url: Link2,
  number: Hash,
  int: Hash,
  decimal: Hash,
  boolean: CheckSquare,
  date: Calendar,
  datetime: Calendar,
  user: UserRound,
  select: List,
  link: Link2,
  lookup: Eye,
  computed: Sigma,
  sheet_lookup: SheetIcon,
};

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

function CellContent({
  column,
  view,
}: {
  column: GridColumn;
  view: ReturnType<typeof cellView>;
}) {
  if (view.kind === "blank") return null;
  if (view.kind === "link")
    return column.linkModuleId ? (
      <GuardedWorkspaceLink
        href={
          `/openview?section=views&module=${encodeURIComponent(column.linkModuleId)}&record=${encodeURIComponent(view.recordId)}` as Route
        }
        className="text-action-text block truncate font-medium hover:underline"
      >
        {view.label}
      </GuardedWorkspaceLink>
    ) : (
      <span className="block truncate">{view.label}</span>
    );
  if (view.kind === "state")
    return (
      <span className="text-muted-foreground inline-flex min-w-0 items-center gap-1.5 italic">
        {view.state === "no_access" ? (
          <Lock aria-hidden="true" className="size-3.5 shrink-0" />
        ) : view.state === "deleted" ? (
          <Trash2 aria-hidden="true" className="size-3.5 shrink-0" />
        ) : null}
        <span className="truncate">{view.words}</span>
      </span>
    );
  return (
    <span className="block truncate">
      {view.kind === "unlinked" ? view.text : view.text}
    </span>
  );
}

type GridProps = {
  sheet: WorksheetDetail;
  store: RowStore;
  totals: Record<string, WorksheetTotal>;
  searching: boolean;
  format: GridFormat;
  phone: boolean;
  onRange: (start: number, end: number) => void;
};

function SheetGrid({
  sheet,
  store,
  totals,
  searching,
  format,
  phone,
  onRange,
}: GridProps) {
  "use no memo"; // TanStack's mutable virtualizer must be read on every range update.
  const pane = useRef<HTMLDivElement | null>(null);
  const columns = useMemo(() => gridColumns(sheet.structure), [sheet]);
  const bands = useMemo(() => gridBands(columns), [columns]);
  const rowHeight = phone ? 44 : 40;
  const numberWidth = phone ? PHONE_ROW_NUMBER_WIDTH : ROW_NUMBER_WIDTH;
  const firstWidth = phone ? 160 - PHONE_ROW_NUMBER_WIDTH : 220;
  const widthOf = (column: GridColumn, index: number) =>
    index === 0 ? firstWidth : column.numeric ? 128 : 176;
  const tableWidth =
    numberWidth +
    columns.reduce((sum, column, index) => sum + widthOf(column, index), 0);
  const count = store.total ?? 0;
  // eslint-disable-next-line react-hooks/incompatible-library -- This component explicitly opts out above; no virtualizer method is memoized or passed to memoized children.
  const virtual = useVirtualizer({
    count,
    getScrollElement: () => pane.current,
    estimateSize: () => rowHeight,
    overscan: 12,
  });
  const items = virtual.getVirtualItems();
  const first = items[0]?.index ?? 0;
  const last = items.at(-1)?.index ?? 0;
  useEffect(() => {
    onRange(first, last);
  }, [first, last, count, onRange]);
  const top = items[0]?.start ?? 0;
  const bottom = Math.max(0, virtual.getTotalSize() - (items.at(-1)?.end ?? 0));
  const totalKeys = Object.keys(totals);
  const grouped = bands.some((band) => band.label !== null);
  const pinned = "sticky z-10 bg-card";
  return (
    <div
      ref={pane}
      role="region"
      aria-label={`${sheet.title} rows`}
      tabIndex={0}
      className="bg-card focus-visible:outline-ring relative min-h-0 flex-1 overflow-auto rounded-md border outline-offset-2 focus-visible:outline-2"
    >
      <table
        aria-label={sheet.title}
        aria-rowcount={count + 1}
        className="table-fixed border-separate border-spacing-0 text-sm"
        style={{ width: tableWidth }}
      >
        <colgroup>
          <col style={{ width: numberWidth }} />
          {columns.map((column, index) => (
            <col key={column.key} style={{ width: widthOf(column, index) }} />
          ))}
        </colgroup>
        <thead className="bg-card sticky top-0 z-20">
          {grouped ? (
            <tr>
              <th
                aria-hidden="true"
                className={cn(pinned, "left-0 h-8 border-b")}
              />
              {bands.map((band, index) => (
                <th
                  key={`${band.label ?? "none"}-${index}`}
                  colSpan={band.span}
                  scope={band.label ? "colgroup" : undefined}
                  className="text-muted-foreground h-8 border-b border-l px-3 text-left text-xs font-semibold"
                >
                  {band.label}
                </th>
              ))}
            </tr>
          ) : null}
          <tr>
            <th
              scope="col"
              className={cn(pinned, "left-0 h-9 border-b px-2 text-right")}
            >
              <span className="sr-only">Row</span>
            </th>
            {columns.map((column, index) => {
              const Icon = TYPE_ICONS[column.type];
              return (
                <th
                  key={column.key}
                  scope="col"
                  className={cn(
                    "text-muted-foreground h-9 border-b border-l px-3 text-left text-xs font-medium",
                    index === 0 && pinned,
                    column.numeric && "text-right",
                  )}
                  style={index === 0 ? { left: numberWidth } : undefined}
                >
                  <span
                    className={cn(
                      "flex min-w-0 items-center gap-1.5",
                      column.numeric && "justify-end",
                    )}
                  >
                    <Icon aria-hidden="true" className="size-3.5 shrink-0" />
                    <span className="truncate">{column.name}</span>
                    {column.readOnly ? (
                      <span className="sr-only">, read-only</span>
                    ) : null}
                  </span>
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {top > 0 ? (
            <tr aria-hidden="true">
              <td colSpan={columns.length + 1} style={{ height: top }} />
            </tr>
          ) : null}
          {items.map((item) => {
            const row = rowAt(store, item.index);
            return (
              <tr
                key={row?.id ?? `pending-${item.index}`}
                aria-rowindex={item.index + 2}
                style={{ height: rowHeight }}
                className="hover:bg-tint-hover group"
              >
                <td
                  className={cn(
                    pinned,
                    "text-muted-foreground group-hover:bg-tint-hover left-0 border-b px-2 text-right text-xs tabular-nums",
                  )}
                >
                  {item.index + 1}
                </td>
                {columns.map((column, index) => {
                  const view = row
                    ? cellView(column, row.cells[column.key], format)
                    : null;
                  return (
                    <td
                      key={column.key}
                      className={cn(
                        "min-w-0 border-b border-l px-3",
                        index === 0 && pinned,
                        index === 0 && "group-hover:bg-tint-hover",
                        column.readOnly && "bg-muted/40",
                        column.numeric && "text-right tabular-nums",
                      )}
                      style={index === 0 ? { left: numberWidth } : undefined}
                    >
                      {view ? (
                        <CellContent column={column} view={view} />
                      ) : (
                        <Skeleton className="h-3 w-3/4" />
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
          {bottom > 0 ? (
            <tr aria-hidden="true">
              <td colSpan={columns.length + 1} style={{ height: bottom }} />
            </tr>
          ) : null}
        </tbody>
        {totalKeys.length > 0 ? (
          <tfoot className="bg-card sticky bottom-0 z-20">
            <tr>
              <td className={cn(pinned, "left-0 border-t")} />
              {columns.map((column, index) => {
                const total = totals[column.key];
                const view = total
                  ? totalView(
                      column,
                      total,
                      {
                        first: column.key === totalKeys[0],
                        searching,
                        allRows: sheet.liveRowCount,
                      },
                      format,
                    )
                  : null;
                return (
                  <td
                    key={column.key}
                    className={cn(
                      "h-12 border-t border-l px-3 align-middle",
                      index === 0 && pinned,
                      column.numeric && "text-right",
                    )}
                    style={index === 0 ? { left: numberWidth } : undefined}
                  >
                    {view ? (
                      <span className="flex flex-col leading-tight">
                        <span className="text-muted-foreground text-xs">
                          {view.label}
                        </span>
                        <span className="font-semibold tabular-nums">
                          {view.text}
                        </span>
                      </span>
                    ) : null}
                  </td>
                );
              })}
            </tr>
          </tfoot>
        ) : null}
      </table>
    </div>
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
  const readOnly = sheet.state === "open" || sheet.myLevel === "view";
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
        {readOnly ? null : (
          <span className="text-muted-foreground ml-auto inline-flex items-center gap-1.5 text-sm max-sm:hidden">
            <Check aria-hidden="true" className="size-4" />
            Saved
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
      <SheetGrid
        sheet={sheet}
        store={store}
        totals={totals}
        searching={searching}
        format={format}
        phone={phone}
        onRange={onRange}
      />
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
