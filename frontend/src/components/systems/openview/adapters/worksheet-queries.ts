"use client";

import { queryOptions } from "@tanstack/react-query";
import { listMyWorksheets } from "./worksheets-api";

// Sheet reads (docs/specs/sheets.md). They live apart from openview-queries.ts,
// which the shell imports, so no sheet code rides in the shell's chunk. The
// keys start with "openview", so OpenView's resync marks them stale too. The
// client is already one per account and organization (`AppPage` keys its
// provider by `${verifiedUserId}:${organizationId}`), so the keys hold no ids.
// My sheets needs no records.read: these reads never touch the OpenView
// access latch.

export type MyWorksheetsList = "exclude" | "only";

export const worksheetKeys = {
  all: ["openview", "worksheets"] as const,
  mine: (deleted: MyWorksheetsList) =>
    ["openview", "worksheets", "mine", deleted] as const,
};

export const myWorksheetsOptions = (deleted: MyWorksheetsList) =>
  queryOptions({
    queryKey: worksheetKeys.mine(deleted),
    queryFn: ({ signal }) => listMyWorksheets({ deleted, signal }),
  });
