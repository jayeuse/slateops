"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw, Search } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LoadingRegion } from "@/components/ui/loading-region";
import { Skeleton } from "@/components/ui/skeleton";
import { TableCell, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useWorkspaceDisplayRegion } from "@/components/use-display-region";
import { apiErrorReference } from "@/lib/api-errors";
import { cn } from "@/lib/utils";

import {
  restoreWorksheet,
  type WorksheetSummary,
} from "../adapters/worksheets-api";
import {
  myWorksheetsOptions,
  worksheetKeys,
} from "../adapters/worksheet-queries";
import {
  SheetAccess,
  SheetName,
  SheetTableRow,
  SheetsTable,
  sheetAnchorWords,
  sheetRowsWords,
  sheetShortDate,
} from "./sheet-display";

// docs/specs/sheets.md P4 and Screens 7: the sheets a person owns and the
// sheets shared with them. Users read "sheet" only (P7).

type Show = "all" | "owned" | "shared" | "deleted";

const showOptions: { value: Show; label: string }[] = [
  { value: "all", label: "All" },
  { value: "owned", label: "Owned by me" },
  { value: "shared", label: "Shared with me" },
  { value: "deleted", label: "Deleted" },
];

/** When a deleted sheet was deleted; its last change is the fallback. */
function deletedOn(sheet: WorksheetSummary) {
  return sheet.deletedAt ?? sheet.updatedAt;
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
              <SheetsTable
                label="My sheets"
                columns={isDeleted ? deletedColumns : liveColumns}
                empty={empty}
              >
                {rows.map((sheet) =>
                  isDeleted ? (
                    <TableRow key={sheet.id} className="h-11">
                      <TableCell className="truncate px-4">
                        <SheetName sheet={sheet} link={false} />
                      </TableCell>
                      <TableCell className="truncate px-4">
                        {sheetAnchorWords(sheet)}
                      </TableCell>
                      <TableCell className="px-4 tabular-nums">
                        <time dateTime={deletedOn(sheet)}>
                          {sheetShortDate(deletedOn(sheet), region)}
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
                    <SheetTableRow
                      key={sheet.id}
                      sheet={sheet}
                      region={region}
                      anchor
                    />
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
                        <SheetAccess sheet={sheet} />
                      )}
                    </span>
                    <span className="text-muted-foreground truncate text-xs tabular-nums">
                      {isDeleted
                        ? `Deleted ${sheetShortDate(deletedOn(sheet), region)} · ${sheetAnchorWords(sheet)}`
                        : `${sheetAnchorWords(sheet)} · ${sheetRowsWords(sheet.liveRowCount)} · ${sheetShortDate(sheet.updatedAt, region)}`}
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
