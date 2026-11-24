"use client";

import { queryOptions } from "@tanstack/react-query";
import { z } from "zod";

import { openViewReadFetch } from "./openview-access";
import { worksheetKeys } from "./worksheet-queries";
import { worksheetRowSchema } from "./worksheets-api";

// Appears in (docs/specs/sheets.md N5, V7, D10 route 23; SH-28): the rows
// that link to a record, in the sheets the viewer can see, with their cells
// as the viewer sees them. A view, not stored, and different per person. It
// needs the record readable, so it reports to the OpenView read latch.

const uuid = z.string().uuid();

const appearanceSchema = z
  .object({
    worksheet_id: uuid,
    worksheet_title: z.string(),
    owner: z.object({ id: uuid, display_name: z.string() }).strict(),
    row_id: uuid,
    row_number: z.number().int().min(0),
    column_key: z.string(),
    column_name: z.string(),
    columns: z.array(
      z
        .object({ key: z.string(), name: z.string(), type: z.string() })
        .strict(),
    ),
    // Masked per viewer, as route 9 gives them (N4: no id, no label).
    cells: worksheetRowSchema.shape.cells,
  })
  .strict()
  .transform((wire) => ({
    sheetId: wire.worksheet_id,
    sheetTitle: wire.worksheet_title,
    owner: { id: wire.owner.id, displayName: wire.owner.display_name },
    rowId: wire.row_id,
    rowNumber: wire.row_number,
    columnKey: wire.column_key,
    columnName: wire.column_name,
    columns: wire.columns,
    cells: wire.cells,
  }));

export type SheetAppearance = z.output<typeof appearanceSchema>;

const pageSchema = z
  .object({
    items: z.array(appearanceSchema),
    pagination: z
      .object({
        limit: z.number().int().min(1).max(100),
        offset: z.number().int().min(0),
        count: z.number().int().min(0),
        total: z.number().int().min(0),
        has_more: z.boolean(),
        total_is_capped: z.boolean().optional(),
      })
      .strict(),
  })
  .strict()
  .transform(({ items, pagination }) => ({
    items,
    total: pagination.total,
    hasMore: pagination.has_more,
    // After this page's window, not its rows: a row hidden after the count
    // leaves a page short, and the next page must not read it again.
    nextOffset: pagination.offset + pagination.limit,
  }));

export type SheetAppearancePage = z.output<typeof pageSchema>;

export const APPEARANCES_PAGE = 25;

/**
 * A page of the rows that link to a record (route 23), by sheet title and
 * then row position, with an exact total. A record the person cannot read
 * answers the same 404 as a missing one.
 */
export function listRecordAppearances(
  recordId: string,
  offset: number,
  signal?: AbortSignal,
): Promise<SheetAppearancePage> {
  const query = new URLSearchParams({
    limit: String(APPEARANCES_PAGE),
    offset: String(offset),
  });
  return openViewReadFetch(
    `/records/${encodeURIComponent(uuid.parse(recordId))}/worksheet-rows?${query}`,
    pageSchema,
    { cache: "no-store", signal },
  );
}

/**
 * The first page is cached, and a `worksheets` event or a resync reads it
 * again (`openViewKeysForEntity`); later pages are the panel's own.
 */
export const recordAppearancesOptions = (recordId: string) =>
  queryOptions({
    queryKey: worksheetKeys.appears(recordId),
    queryFn: ({ signal }) => listRecordAppearances(recordId, 0, signal),
  });
