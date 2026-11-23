"use client";

import { useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import type { Route } from "next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Eye,
  Pencil,
  RotateCcw,
  Search,
  Sheet as SheetIcon,
  UserRound,
} from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LoadingRegion } from "@/components/ui/loading-region";
import { Skeleton } from "@/components/ui/skeleton";
import {
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useWorkspaceDisplayRegion } from "@/components/use-display-region";
import { apiErrorReference } from "@/lib/api-errors";
import {
  formatWorkspaceDate,
  type WorkspaceRegion,
} from "@/lib/date-time-display";
import { cn } from "@/lib/utils";

import {
  restoreWorksheet,
  type WorksheetLevel,
  type WorksheetSummary,
} from "../adapters/worksheets-api";
import {
  myWorksheetsOptions,
  worksheetKeys,
} from "../adapters/worksheet-queries";

// docs/specs/sheets.md P4 and Screens 7: the sheets a person owns and the
// sheets shared with them. Users read "sheet" only (P7).

type Show = "all" | "owned" | "shared" | "deleted";

const showOptions: { value: Show; label: string }[] = [
  { value: "all", label: "All" },
  { value: "owned", label: "Owned by me" },
  { value: "shared", label: "Shared with me" },
  { value: "deleted", label: "Deleted" },
];

const levelWords: Record<WorksheetLevel, string> = {
  owner: "Owner",
  edit: "Edit",
  view: "View",
};

const levelIcons: Record<WorksheetLevel, typeof Eye> = {
  owner: UserRound,
  edit: Pencil,
  view: Eye,
};

/**
 * Where the sheet sits. The summary carries only the record or module id, so
 * the cell names the kind until the list carries the record and module names.
 */
function anchorWords(sheet: WorksheetSummary): string {
  return sheet.moduleId ? "Module sheet" : "Record sheet";
}

function shortDate(value: string, region: WorkspaceRegion | undefined) {
  const options = { month: "short", day: "numeric" } as const;
  if (region) return formatWorkspaceDate(value, region, options);
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat(undefined, options).format(date);
}

function rowsWords(count: number) {
  return `${count} ${count === 1 ? "row" : "rows"}`;
}

function sheetHref(id: string) {
  return `/openview?sheet=${encodeURIComponent(id)}` as Route;
}

function Access({ level }: { level: WorksheetLevel }) {
  const Icon = levelIcons[level];
  return (
    <span className="text-muted-foreground inline-flex min-w-0 items-center gap-1.5">
      <Icon aria-hidden="true" className="size-3.5 shrink-0" />
      <span className="truncate">{levelWords[level]}</span>
    </span>
  );
}

function SheetName({
  sheet,
  link,
}: {
  sheet: WorksheetSummary;
  link: boolean;
}) {
  const content = (
    <>
      <SheetIcon
        aria-hidden="true"
        className="text-muted-foreground size-4 shrink-0"
      />
      <span className="truncate">{sheet.title}</span>
    </>
  );
  const className =
    "inline-flex max-w-full min-w-0 items-center gap-2.5 font-medium";
  return link ? (
    <Link
      href={sheetHref(sheet.id)}
      className={cn(
        className,
        "focus-visible:outline-ring rounded-sm outline-offset-2 after:absolute after:inset-0 focus-visible:outline-2",
      )}
    >
      {content}
    </Link>
  ) : (
    <span className={className}>{content}</span>
  );
}

function RestoreButton({
  sheet,
  pending,
  onRestore,
}: {
  sheet: WorksheetSummary;
  pending: boolean;
  onRestore: (sheet: WorksheetSummary) => void;
}) {
  if (sheet.myLevel !== "owner") return null;
  return (
    <Button
      variant="outline"
      className="min-h-11 xl:h-8 xl:min-h-8"
      aria-label={`Restore ${sheet.title}`}
      aria-disabled={pending || undefined}
      onClick={() => {
        if (!pending) onRestore(sheet);
      }}
    >
      <RotateCcw aria-hidden="true" />
      Restore
    </Button>
  );
}

const liveColumns = [
  ["Sheet", "w-[24%]"],
  ["On record", "w-[22%]"],
  ["Owner", "w-[18%]"],
  ["Your access", "w-[14%]"],
  ["Rows", "w-[8%]"],
  ["Last change", "w-[14%]"],
] as const;

const deletedColumns = [
  ["Sheet", "w-[34%]"],
  ["On record", "w-[32%]"],
  ["Deleted", "w-[16%]"],
  ["Actions", "w-[18%]"],
] as const;

function SheetsTable({
  deleted,
  empty,
  children,
}: {
  deleted: boolean;
  empty: ReactNode;
  children: ReactNode;
}) {
  const columns = deleted ? deletedColumns : liveColumns;
  return (
    <table
      aria-label="My sheets"
      className="w-full table-fixed caption-bottom text-sm"
    >
      <colgroup>
        {columns.map(([label, width]) => (
          <col key={label} className={width} />
        ))}
      </colgroup>
      <TableHeader className="bg-card sticky top-0 z-[1]">
        <TableRow className="hover:bg-transparent">
          {columns.map(([label]) => (
            <TableHead
              key={label}
              className="text-muted-foreground h-9 px-4 text-xs"
            >
              {label === "Actions" ? (
                <span className="sr-only">Actions</span>
              ) : (
                label
              )}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {empty ? (
          <TableRow className="hover:bg-transparent">
            <TableCell
              colSpan={columns.length}
              className="text-muted-foreground h-14 px-4 whitespace-normal"
            >
              {empty}
            </TableCell>
          </TableRow>
        ) : (
          children
        )}
      </TableBody>
    </table>
  );
}

function TableSkeleton() {
  return (
    <div className="flex flex-col gap-3 p-4">
      {[0, 1, 2, 3].map((row) => (
        <Skeleton key={row} className="h-6 w-full" />
      ))}
    </div>
  );
}

export function MySheets() {
  const client = useQueryClient();
  const live = useQuery(myWorksheetsOptions("exclude"));
  const deleted = useQuery(myWorksheetsOptions("only"));
  const region = useWorkspaceDisplayRegion();
  const [show, setShow] = useState<Show>("all");
  const [search, setSearch] = useState("");
  const restore = useMutation({
    mutationFn: (sheet: WorksheetSummary) => restoreWorksheet(sheet.id),
    onSuccess: () => client.invalidateQueries({ queryKey: worksheetKeys.all }),
  });

  const needle = search.trim().toLocaleLowerCase();
  const lists = useMemo(() => {
    const matches = (sheet: WorksheetSummary) =>
      !needle || sheet.title.toLocaleLowerCase().includes(needle);
    const all = (live.data?.items ?? []).filter(matches);
    return {
      all,
      owned: all.filter((sheet) => sheet.myLevel === "owner"),
      shared: all.filter((sheet) => sheet.myLevel !== "owner"),
      deleted: (deleted.data?.items ?? []).filter(matches),
    };
  }, [live.data, deleted.data, needle]);

  const read = show === "deleted" ? deleted : live;
  const total = live.data?.total;
  const counts: Record<Show, number | undefined> = {
    all: live.data ? lists.all.length : undefined,
    owned: live.data ? lists.owned.length : undefined,
    shared: live.data ? lists.shared.length : undefined,
    deleted: deleted.data ? lists.deleted.length : undefined,
  };
  const rows = lists[show];
  const isDeleted = show === "deleted";
  const empty = !read.data
    ? null
    : rows.length > 0
      ? null
      : needle
        ? "No sheets match this search."
        : isDeleted
          ? "No deleted sheets."
          : "No sheets yet. Open a record and use New sheet in its Sheets tab.";

  return (
    <div className="flex min-w-0 flex-col gap-3 xl:min-h-0 xl:flex-1">
      <header className="min-w-0">
        <h1
          data-slot="page-title"
          className="text-2xl font-semibold tracking-tight sm:text-3xl"
        >
          My sheets
        </h1>
        <p className="text-muted-foreground mt-1.5 text-sm tabular-nums">
          {total === 0
            ? "Sheets you own and sheets shared with you show here."
            : total === undefined
              ? "Sheets you own and sheets shared with you"
              : `Sheets you own and sheets shared with you · ${total} ${total === 1 ? "sheet" : "sheets"}`}
        </p>
      </header>

      <div
        role="toolbar"
        aria-label="My sheets controls"
        className="flex min-w-0 flex-wrap items-center gap-2"
      >
        <div className="relative w-full md:w-64">
          <Search
            aria-hidden="true"
            className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
          />
          <Input
            type="search"
            aria-label="Search sheets"
            placeholder="Search sheets"
            maxLength={100}
            className="min-h-11 pl-9 xl:h-8 xl:min-h-8"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <ToggleGroup
          aria-label="Show"
          variant="segmented"
          multiple={false}
          value={[show]}
          className="w-full max-w-full flex-nowrap overflow-x-auto overflow-y-hidden max-md:[mask-image:linear-gradient(to_right,black_calc(100%-2rem),transparent)] max-md:pr-8 md:w-fit [&>*]:shrink-0"
          onValueChange={(selection) => {
            const next = showOptions.find(
              (option) => option.value === selection[0],
            );
            if (next) setShow(next.value);
          }}
        >
          {showOptions.map((option) => (
            <ToggleGroupItem
              key={option.value}
              value={option.value}
              className="min-w-11 flex-none gap-1.5 px-2 text-sm whitespace-nowrap xl:min-w-0"
            >
              {option.label}
              {counts[option.value] === undefined ? null : (
                <span className="text-muted-foreground font-normal tabular-nums">
                  {counts[option.value]}
                </span>
              )}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      {restore.isError ? (
        <Alert
          variant="destructive"
          reference={apiErrorReference(restore.error)}
          className="flex flex-wrap items-center gap-x-4 gap-y-2"
        >
          <p className="min-w-0 flex-1">The sheet could not be restored.</p>
        </Alert>
      ) : null}

      {read.isError ? (
        <Alert
          variant="destructive"
          reference={apiErrorReference(read.error)}
          className="flex flex-wrap items-center gap-x-4 gap-y-2"
        >
          <p className="min-w-0 flex-1">Your sheets could not be loaded.</p>
          <Button
            variant="outline"
            className="min-h-11 shrink-0 xl:h-8 xl:min-h-8"
            aria-disabled={read.isFetching || undefined}
            onClick={() => {
              if (!read.isFetching) void read.refetch();
            }}
          >
            Retry
          </Button>
        </Alert>
      ) : (
        <section
          aria-label="Sheets"
          className="bg-card flex min-w-0 flex-col overflow-hidden rounded-md border xl:min-h-0 xl:flex-1"
        >
          <LoadingRegion
            loading={read.isPending}
            label="Loading your sheets…"
            skeleton={<TableSkeleton />}
            className="min-h-0 flex-1 overflow-auto"
          >
            <div className="hidden md:block">
              <SheetsTable deleted={isDeleted} empty={empty}>
                {rows.map((sheet) =>
                  isDeleted ? (
                    <TableRow key={sheet.id} className="h-11">
                      <TableCell className="truncate px-4">
                        <SheetName sheet={sheet} link={false} />
                      </TableCell>
                      <TableCell className="truncate px-4">
                        {anchorWords(sheet)}
                      </TableCell>
                      <TableCell className="px-4 tabular-nums">
                        <time dateTime={sheet.updatedAt}>
                          {shortDate(sheet.updatedAt, region)}
                        </time>
                      </TableCell>
                      <TableCell className="px-4 text-right">
                        <RestoreButton
                          sheet={sheet}
                          pending={restore.isPending}
                          onRestore={restore.mutate}
                        />
                      </TableCell>
                    </TableRow>
                  ) : (
                    <TableRow
                      key={sheet.id}
                      className="hover:bg-tint-hover relative h-11"
                    >
                      <TableCell className="truncate px-4">
                        <SheetName sheet={sheet} link />
                      </TableCell>
                      <TableCell className="truncate px-4">
                        {anchorWords(sheet)}
                      </TableCell>
                      <TableCell className="truncate px-4">
                        {sheet.owner.displayName}
                      </TableCell>
                      <TableCell className="px-4">
                        <Access level={sheet.myLevel} />
                      </TableCell>
                      <TableCell className="px-4 tabular-nums">
                        {sheet.liveRowCount}
                      </TableCell>
                      <TableCell className="px-4 tabular-nums">
                        <time dateTime={sheet.updatedAt}>
                          {shortDate(sheet.updatedAt, region)}
                        </time>
                      </TableCell>
                    </TableRow>
                  ),
                )}
              </SheetsTable>
            </div>
            <ul
              aria-label="My sheets"
              className="divide-border divide-y md:hidden"
            >
              {empty ? (
                <li className="text-muted-foreground px-4 py-4 text-sm">
                  {empty}
                </li>
              ) : (
                rows.map((sheet) => (
                  <li
                    key={sheet.id}
                    className={cn(
                      "relative grid min-h-15 grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-0.5 px-4 py-2",
                      !isDeleted && "hover:bg-tint-hover",
                    )}
                  >
                    <SheetName sheet={sheet} link={!isDeleted} />
                    <span className="row-span-2 justify-self-end text-sm">
                      {isDeleted ? (
                        <RestoreButton
                          sheet={sheet}
                          pending={restore.isPending}
                          onRestore={restore.mutate}
                        />
                      ) : (
                        <Access level={sheet.myLevel} />
                      )}
                    </span>
                    <span className="text-muted-foreground truncate text-xs tabular-nums">
                      {isDeleted
                        ? `Deleted ${shortDate(sheet.updatedAt, region)} · ${anchorWords(sheet)}`
                        : `${anchorWords(sheet)} · ${rowsWords(sheet.liveRowCount)} · ${shortDate(sheet.updatedAt, region)}`}
                    </span>
                  </li>
                ))
              )}
            </ul>
          </LoadingRegion>
        </section>
      )}
    </div>
  );
}
