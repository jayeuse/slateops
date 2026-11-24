"use client";

import {
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { Route } from "next";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Link2,
  Lock,
  Sheet as SheetIcon,
  Trash2,
} from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { LoadingRegion } from "@/components/ui/loading-region";
import { Skeleton } from "@/components/ui/skeleton";
import { personCardOptions } from "@/components/profile/adapters/profile-queries";
import { useWorkspaceDisplayRegion } from "@/components/use-display-region";
import { GuardedWorkspaceLink } from "@/components/workspace-navigation-guard";
import { ApiError } from "@/lib/api";
import { apiErrorReference } from "@/lib/api-errors";

import { useOpenViewAccessDenied } from "../adapters/openview-access";
import {
  authMeOptions,
  extendsRead,
  readStamp,
} from "../adapters/openview-queries";
import {
  worksheetDetailOptions,
  worksheetKeys,
} from "../adapters/worksheet-queries";
import {
  listRecordAppearances,
  recordAppearancesOptions,
  type SheetAppearance,
} from "../adapters/worksheet-appears-api";
import {
  cellView,
  gridColumns,
  type GridColumn,
  type GridFormat,
  type SheetColumnType,
} from "../domain/sheet-grid";
import { sheetHref } from "./sheet-display";

// The record panel's Appears in (docs/specs/sheets.md N5, V7; Screens 6;
// SH-28): every row that links to this record in a sheet the viewer can
// see, read only. Each row opens to its values, as its sheet shows them, and
// to its sheet at that row. Loaded on first use of the Sheets tab. A
// `worksheets` event or a resync reads the first page again through the
// OpenView query bridge (`openViewKeysForEntity`).

/** A person cell names the person, as the sheet's grid does. */
function PersonName({ id }: { id: string }) {
  const identity = useQuery(authMeOptions());
  const viewer = identity.data
    ? { id: identity.data.id, role: identity.data.role ?? "guest" }
    : null;
  const card = useQuery({
    ...personCardOptions(viewer ?? { id: "", role: "member" }, id),
    enabled: Boolean(viewer),
  });
  // Nothing while the name loads; never a placeholder that reads as a name.
  if (card.isError) return <>Unknown person</>;
  return <>{card.data?.data.display_name ?? null}</>;
}

/** A column as route 23 names it, when the sheet's own columns are unread. */
function plainColumn(column: SheetAppearance["columns"][number]): GridColumn {
  return {
    key: column.key,
    name: column.name,
    type: column.type as SheetColumnType,
    readOnly: true,
    numeric: false,
    group: null,
  };
}

/** One value in the grid's look: state words muted, a failed sum warned. */
function Value({
  column,
  cell,
  format,
}: {
  column: GridColumn;
  cell: SheetAppearance["cells"][string] | undefined;
  format: GridFormat;
}) {
  const view = cellView(column, cell, format);
  if (view.kind === "blank") return null;
  if (view.kind === "link") return <>{view.label}</>;
  if (view.kind === "unlinked") return <>{view.text}</>;
  if (view.kind === "state")
    return (
      <span className="text-muted-foreground inline-flex items-center gap-1.5 italic">
        {view.state === "no_access" ? (
          <Lock aria-hidden="true" className="size-3.5 shrink-0" />
        ) : view.state === "deleted" ? (
          <Trash2 aria-hidden="true" className="size-3.5 shrink-0" />
        ) : null}
        <span className="pr-0.5">{view.words}</span>
      </span>
    );
  if (view.kind === "error")
    return (
      <span className="text-warn-text inline-flex items-center gap-1.5">
        <AlertTriangle aria-hidden="true" className="size-3.5 shrink-0" />
        {view.words}
      </span>
    );
  if (column.type === "user") return <PersonName id={view.text} />;
  return <>{view.text}</>;
}

// Values line up with the entry's title: the row's padding, its icon and the
// gap after it (px-3, size-4, gap-x-2.5).
const VALUES_INSET = "pr-3 pl-[2.375rem]";

function Values({
  recordId,
  appearance,
  format,
}: {
  recordId: string;
  appearance: SheetAppearance;
  format: GridFormat;
}) {
  const client = useQueryClient();
  // The sheet's columns give choice names, places and currency; the viewer
  // can see the sheet, or it would not be listed (V7).
  const detail = useQuery(worksheetDetailOptions(appearance.sheetId));
  // A sheet that went away since the list was read: no values, and the list
  // is read again (it drops the row too).
  const missing =
    detail.error instanceof ApiError && detail.error.status === 404;
  useEffect(() => {
    if (missing)
      void client.invalidateQueries({
        queryKey: worksheetKeys.appears(recordId),
      });
  }, [missing, client, recordId]);
  const columns = useMemo(
    () =>
      detail.data
        ? gridColumns(detail.data.structure)
        : appearance.columns.map(plainColumn),
    [detail.data, appearance.columns],
  );
  if (missing) return null;
  if (detail.isPending)
    return (
      <div
        className={`flex flex-col gap-2 pb-3 ${VALUES_INSET}`}
        aria-hidden="true"
      >
        <Skeleton className="h-3 w-2/3" />
        <Skeleton className="h-3 w-1/2" />
      </div>
    );
  // The whole row; the column that links here holds this record, by title.
  const query = new URLSearchParams({
    row: appearance.rowId,
    n: String(appearance.rowNumber),
  });
  return (
    <>
      <dl
        className={`grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)] gap-x-3 gap-y-1.5 text-sm ${VALUES_INSET}`}
      >
        {columns.map((column) => (
          <div key={column.key} className="contents">
            <dt className="text-muted-foreground truncate">{column.name}</dt>
            <dd className="min-w-0 break-words">
              <Value
                column={column}
                cell={appearance.cells[column.key]}
                format={format}
              />
            </dd>
          </div>
        ))}
      </dl>
      <div className={`pt-1 pb-3 ${VALUES_INSET}`}>
        <GuardedWorkspaceLink
          href={`${sheetHref(appearance.sheetId)}&${query}` as Route}
          className="text-action-text inline-flex min-h-11 items-center gap-1.5 text-sm font-medium underline-offset-4 hover:underline xl:min-h-8"
        >
          Open the sheet at this row
          <ArrowRight aria-hidden="true" className="size-3.5" />
        </GuardedWorkspaceLink>
      </div>
    </>
  );
}

function Entry({
  recordId,
  appearance,
  viewerId,
  format,
  showColumn,
}: {
  recordId: string;
  appearance: SheetAppearance;
  viewerId: string | undefined;
  format: GridFormat;
  /** The row links here through more than one column: name this one. */
  showColumn: boolean;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const owner =
    appearance.owner.id === viewerId
      ? `${appearance.owner.displayName} (you)`
      : appearance.owner.displayName;
  const line = [owner, `row ${appearance.rowNumber}`]
    .concat(showColumn ? [appearance.columnName] : [])
    .join(" · ");
  const Chevron = open ? ChevronUp : ChevronDown;
  return (
    <li>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={`${id}-values`}
        onClick={() => setOpen((value) => !value)}
        className="hover:bg-tint-hover focus-visible:outline-ring grid min-h-14 w-full grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-2.5 gap-y-0.5 px-3 py-2 text-left outline-offset-[-2px] focus-visible:outline-2"
      >
        <SheetIcon
          aria-hidden="true"
          className="text-muted-foreground row-span-2 size-4 shrink-0"
        />
        <span className="truncate text-sm font-medium">
          {appearance.sheetTitle}
        </span>
        <Chevron
          aria-hidden="true"
          className="text-muted-foreground row-span-2 size-4"
        />
        <span className="text-muted-foreground truncate text-xs tabular-nums">
          {line}
        </span>
      </button>
      <div id={`${id}-values`} hidden={!open}>
        {open ? (
          <Values recordId={recordId} appearance={appearance} format={format} />
        ) : null}
      </div>
    </li>
  );
}

function AppearsSkeleton() {
  return (
    <div
      className="flex flex-col gap-2 rounded-md border p-3"
      aria-hidden="true"
    >
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-3 w-1/3" />
    </div>
  );
}

type MorePages = {
  /** The first-page read these pages follow (`readStamp`). */
  readAt: number;
  items: SheetAppearance[];
  hasMore: boolean;
  nextOffset: number;
};

export default function RecordAppearsIn({ recordId }: { recordId: string }) {
  const id = useId();
  const list = useRef<HTMLUListElement | null>(null);
  const denied = useOpenViewAccessDenied();
  const region = useWorkspaceDisplayRegion();
  const format = useMemo<GridFormat>(
    () => ({
      locale: region?.locale ?? "en-US",
      timezone: region?.timezone ?? "UTC",
    }),
    [region?.locale, region?.timezone],
  );
  const identity = useQuery(authMeOptions());
  const first = useQuery(recordAppearancesOptions(recordId));
  // Later pages belong to the read of the first page that they follow.
  const [more, setMore] = useState<MorePages | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreFailed, setMoreFailed] = useState(false);
  // The entry to focus once it renders: the first new one after Show more;
  // the first one after Retry, once a newer read than `after` has arrived.
  const [focusAt, setFocusAt] = useState<{
    index: number;
    after?: number;
  } | null>(null);
  const reading = useRef<AbortController | null>(null);
  const extra = more && extendsRead(more.readAt, first) ? more : null;
  const items = first.data
    ? [...first.data.items, ...(extra?.items ?? [])]
    : [];
  const hasMore = extra ? extra.hasMore : (first.data?.hasMore ?? false);
  const nextOffset = extra?.nextOffset ?? first.data?.nextOffset ?? 0;
  const readAt = readStamp(first);

  // A new read of the first page, or leaving, drops a page still on its way.
  useEffect(() => () => reading.current?.abort(), [readAt]);

  // A layout effect, in the commit that removes the button that held focus:
  // the record dialog's focus manager finds focus on the body after that
  // commit and takes it to the dialog on the next frame, which a passive
  // effect may run after (the Access editors' fix, a1258f2e).
  useLayoutEffect(() => {
    if (focusAt === null) return;
    if (focusAt.after !== undefined && readAt === focusAt.after) return;
    const entry = list.current?.querySelectorAll<HTMLButtonElement>(
      ":scope > li > button",
    )[focusAt.index];
    if (!entry) return;
    entry.focus();
    setFocusAt(null);
  }, [focusAt, readAt, items.length]);

  const loadMore = async () => {
    if (reading.current) return;
    const controller = new AbortController();
    reading.current = controller;
    const at = readAt;
    const shown = items.length;
    setLoadingMore(true);
    setMoreFailed(false);
    try {
      const page = await listRecordAppearances(
        recordId,
        nextOffset,
        controller.signal,
      );
      if (controller.signal.aborted) return;
      setMore((current) => ({
        readAt: at,
        items: [
          ...(current && current.readAt === at ? current.items : []),
          ...page.items,
        ],
        hasMore: page.hasMore,
        nextOffset: page.nextOffset,
      }));
      if (page.items.length > 0) setFocusAt({ index: shown });
    } catch {
      if (!controller.signal.aborted) setMoreFailed(true);
    } finally {
      if (reading.current === controller) reading.current = null;
      setLoadingMore(false);
    }
  };

  const retry = async () => {
    // Asked before the read, so the commit that brings the list focuses it.
    setFocusAt({ index: 0, after: readAt });
    const result = await first.refetch();
    if (!result.data?.items.length || result.isError) setFocusAt(null);
  };

  // A record that left answers 404; the panel says so itself.
  const gone = first.error instanceof ApiError && first.error.status === 404;
  if (denied || gone) return null;
  const total = first.data?.total;
  // A row that links here through two columns is listed twice; each entry
  // then names its column (Product Designer).
  const perRow = new Map<string, number>();
  for (const item of items)
    perRow.set(item.rowId, (perRow.get(item.rowId) ?? 0) + 1);
  return (
    <section aria-labelledby={id} className="flex min-w-0 flex-col gap-2">
      <div className="flex min-h-11 items-center gap-2 xl:min-h-8">
        <h3 id={id} className="text-sm font-semibold">
          Appears in
        </h3>
        {total ? (
          <span className="text-muted-foreground text-sm tabular-nums">
            {total.toLocaleString("en-US")}
          </span>
        ) : null}
      </div>
      {first.isError && !first.data ? (
        <Alert
          variant="destructive"
          reference={apiErrorReference(first.error)}
          className="flex flex-wrap items-center gap-x-4 gap-y-2"
        >
          <p className="min-w-0 flex-1">Appears in could not be loaded.</p>
          <Button
            variant="outline"
            className="min-h-11 shrink-0 xl:h-8 xl:min-h-8"
            onClick={() => void retry()}
          >
            Retry
          </Button>
        </Alert>
      ) : (
        <LoadingRegion
          loading={first.isPending}
          label="Loading Appears in…"
          skeleton={<AppearsSkeleton />}
        >
          {items.length > 0 ? (
            <ul
              ref={list}
              aria-labelledby={id}
              className="divide-border divide-y rounded-md border"
            >
              {items.map((appearance) => (
                <Entry
                  key={`${appearance.rowId}:${appearance.columnKey}`}
                  recordId={recordId}
                  appearance={appearance}
                  viewerId={identity.data?.id}
                  format={format}
                  showColumn={(perRow.get(appearance.rowId) ?? 0) > 1}
                />
              ))}
            </ul>
          ) : (
            <ul
              aria-labelledby={id}
              className="rounded-md border border-dashed"
            >
              <li className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-2.5 gap-y-0.5 px-3 py-3">
                <Link2
                  aria-hidden="true"
                  className="text-muted-foreground row-span-2 size-4"
                />
                <span className="text-sm font-medium">No rows link here</span>
                <span className="text-muted-foreground text-xs">
                  Rows of sheets you can see that link to this record show here.
                </span>
              </li>
            </ul>
          )}
          {first.isError ? (
            // A background read failed: the list stays as it was.
            <p
              role="status"
              className="text-danger-text flex flex-wrap items-center gap-x-2 text-sm"
            >
              Appears in could not be refreshed.
              <Button
                variant="ghost"
                className="min-h-11 xl:h-8 xl:min-h-8"
                pending={first.isFetching}
                pendingLabel="Retrying…"
                onClick={() => void retry()}
              >
                Retry
              </Button>
            </p>
          ) : null}
          {hasMore ? (
            <Button
              variant="ghost"
              className="min-h-11 self-start xl:h-8 xl:min-h-8"
              pending={loadingMore}
              pendingLabel="Loading…"
              onClick={() => void loadMore()}
            >
              Show more
            </Button>
          ) : null}
          {moreFailed ? (
            <p role="alert" className="text-danger-text text-sm">
              More rows could not be loaded. Try again.
            </p>
          ) : null}
        </LoadingRegion>
      )}
    </section>
  );
}
