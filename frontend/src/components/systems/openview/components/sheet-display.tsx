"use client";

import { Eye, Lock, Pencil, Users } from "lucide-react";

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
