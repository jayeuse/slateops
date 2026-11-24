"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import type { Route } from "next";
import { Eye, Lock, Pencil, Sheet as SheetIcon, Users } from "lucide-react";

import {
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { GuardedWorkspaceLink } from "@/components/workspace-navigation-guard";
import { cn } from "@/lib/utils";

import {
  formatWorkspaceDate,
  type WorkspaceRegion,
} from "@/lib/date-time-display";

import type {
  WorksheetLevel,
  WorksheetSummary,
} from "../adapters/worksheets-api";

// Words and marks that every sheet list shares (docs/specs/sheets.md
// Screens 1 and 7). Users read "sheet" only (P7).

const levelWords: Record<Exclude<WorksheetLevel, "owner">, string> = {
  edit: "Edit",
  view: "View",
};

/**
 * The person's access in words (Screens 7): "Owner · shared", "Owner · only
 * you", "Edit", "View", and the group when only a group's share gives it,
 * as in "View · CCS Faculty".
 */
export function sheetAccessWords(sheet: WorksheetSummary): string {
  if (sheet.myLevel === "owner")
    return sheet.shared ? "Owner · shared" : "Owner · only you";
  const level = levelWords[sheet.myLevel];
  return sheet.accessGroup ? `${level} · ${sheet.accessGroup}` : level;
}

function AccessIcon({ sheet }: { sheet: WorksheetSummary }) {
  const className = "size-3.5 shrink-0";
  if (sheet.myLevel === "owner")
    return sheet.shared ? (
      <Users aria-hidden="true" className={className} />
    ) : (
      <Lock aria-hidden="true" className={className} />
    );
  return sheet.myLevel === "edit" ? (
    <Pencil aria-hidden="true" className={className} />
  ) : (
    <Eye aria-hidden="true" className={className} />
  );
}

/** The record tab's shorter words (Screens 1): "Shared", "Only you", "Edit", "View". */
function shortAccessWords(sheet: WorksheetSummary): string {
  if (sheet.myLevel === "owner") return sheet.shared ? "Shared" : "Only you";
  return levelWords[sheet.myLevel];
}

/** The person's access to a sheet, as a mark and its words. */
export function SheetAccess({
  sheet,
  short = false,
}: {
  sheet: WorksheetSummary;
  short?: boolean;
}) {
  return (
    <span className="text-muted-foreground inline-flex min-w-0 items-center gap-1.5">
      <AccessIcon sheet={sheet} />
      <span className="truncate">
        {short ? shortAccessWords(sheet) : sheetAccessWords(sheet)}
      </span>
    </span>
  );
}

/** Where a sheet sits: "Andrea Villamor · Faculty Members", or its module. */
export function sheetAnchorWords(sheet: WorksheetSummary): string {
  return sheet.moduleId
    ? sheet.moduleName
    : `${sheet.anchorTitle} · ${sheet.moduleName}`;
}

/** "Nov 21" in the workspace's region, or the device's while it loads. */
export function sheetShortDate(
  value: string,
  region: WorkspaceRegion | undefined,
) {
  const options = { month: "short", day: "numeric" } as const;
  if (region) return formatWorkspaceDate(value, region, options);
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat(undefined, options).format(date);
}

export function sheetRowsWords(count: number) {
  return `${count} ${count === 1 ? "row" : "rows"}`;
}

/** Where a sheet opens (P6); the sheet page arrives with it. */
/**
 * The line under My sheets when the list is longer than one read: the
 * newest sheets are shown (parent decision on N5); null when all are shown.
 */
export function cappedListWords(shown: number, total: number): string | null {
  return shown < total
    ? `Showing ${shown.toLocaleString("en-US")} of ${total.toLocaleString("en-US")} sheets.`
    : null;
}

export function sheetHref(id: string) {
  return `/openview?sheet=${encodeURIComponent(id)}`;
}

/**
 * The details line of a sheet on a record or module: its rows, its owner
 * when that is someone else, and its last change.
 */
export function sheetDetails(
  sheet: WorksheetSummary,
  region: WorkspaceRegion | undefined,
) {
  return [
    sheetRowsWords(sheet.liveRowCount),
    sheet.myLevel === "owner" ? null : sheet.owner.displayName,
    `changed ${sheetShortDate(sheet.updatedAt, region)}`,
  ]
    .filter(Boolean)
    .join(" · ");
}

/** A sheet's name with its mark; a link to the sheet when it can open. */
export function SheetName({
  sheet,
  link,
  guarded = false,
}: {
  sheet: WorksheetSummary;
  link: boolean;
  /** Through the navigation guard, where a page can hold a draft. */
  guarded?: boolean;
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
  if (!link) return <span className={className}>{content}</span>;
  const linkClass = cn(
    className,
    "focus-visible:outline-ring rounded-sm outline-offset-2 after:absolute after:inset-0 focus-visible:outline-2",
  );
  const href = sheetHref(sheet.id) as Route;
  return guarded ? (
    <GuardedWorkspaceLink href={href} className={linkClass}>
      {content}
    </GuardedWorkspaceLink>
  ) : (
    <Link href={href} className={linkClass}>
      {content}
    </Link>
  );
}

/** One table of sheets (Screens 7): a fixed header and one row per sheet. */
export function SheetsTable({
  label,
  columns,
  empty,
  children,
}: {
  label: string;
  columns: readonly (readonly [string, string])[];
  empty: ReactNode;
  children: ReactNode;
}) {
  return (
    <table
      aria-label={label}
      className="w-full table-fixed caption-bottom text-sm"
    >
      <colgroup>
        {columns.map(([name, width]) => (
          <col key={name} className={width} />
        ))}
      </colgroup>
      <TableHeader className="bg-card sticky top-0 z-[1]">
        <TableRow className="hover:bg-transparent">
          {columns.map(([name]) => (
            <TableHead
              key={name}
              className="text-muted-foreground h-9 px-4 text-xs"
            >
              {name === "Actions" ? (
                <span className="sr-only">Actions</span>
              ) : (
                name
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

/** A sheet as a table row: name, owner, access, rows and last change. */
export function SheetTableRow({
  sheet,
  region,
  anchor,
  guarded = false,
}: {
  sheet: WorksheetSummary;
  region: WorkspaceRegion | undefined;
  /** My sheets names where each sheet sits; a module's own list does not. */
  anchor: boolean;
  guarded?: boolean;
}) {
  return (
    <TableRow className="hover:bg-tint-hover relative h-11">
      <TableCell className="truncate px-4">
        <SheetName sheet={sheet} link guarded={guarded} />
      </TableCell>
      {anchor ? (
        <TableCell className="truncate px-4">
          {sheetAnchorWords(sheet)}
        </TableCell>
      ) : null}
      <TableCell className="truncate px-4">{sheet.owner.displayName}</TableCell>
      <TableCell className="px-4">
        <SheetAccess sheet={sheet} />
      </TableCell>
      <TableCell className="px-4 tabular-nums">{sheet.liveRowCount}</TableCell>
      <TableCell className="px-4 tabular-nums">
        <time dateTime={sheet.updatedAt}>
          {sheetShortDate(sheet.updatedAt, region)}
        </time>
      </TableCell>
    </TableRow>
  );
}
