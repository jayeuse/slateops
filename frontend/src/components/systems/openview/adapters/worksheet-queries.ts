"use client";

import { queryOptions } from "@tanstack/react-query";
import {
  listModuleWorksheets,
  listMyWorksheets,
  listRecordWorksheets,
} from "./worksheets-api";

// Sheet reads (docs/specs/sheets.md). They live apart from openview-queries.ts,
// which the shell imports, so no sheet code rides in the shell's chunk. The
// keys start with "openview", so OpenView's resync marks them stale too. The
// client is already one per account and organization (`AppPage` keys its
// provider by `${verifiedUserId}:${organizationId}`), so the keys hold no ids.
// My sheets needs no records.read, so it never touches the OpenView access
// latch; a record's and a module's sheets need module read and report to it.

export type MyWorksheetsList = "exclude" | "only";

export const worksheetKeys = {
  all: ["openview", "worksheets"] as const,
  mine: (deleted: MyWorksheetsList) =>
    ["openview", "worksheets", "mine", deleted] as const,
  onRecord: (recordId: string) =>
    ["openview", "worksheets", "record", recordId] as const,
  onModule: (moduleId: string) =>
    ["openview", "worksheets", "module", moduleId] as const,
};

export const myWorksheetsOptions = (deleted: MyWorksheetsList) =>
  queryOptions({
    queryKey: worksheetKeys.mine(deleted),
    queryFn: ({ signal }) => listMyWorksheets({ deleted, signal }),
  });

/** A record's Sheets tab (route 2); the tab's count reads the same entry. */
export const recordWorksheetsOptions = (recordId: string) =>
  queryOptions({
    queryKey: worksheetKeys.onRecord(recordId),
    queryFn: ({ signal }) => listRecordWorksheets(recordId, signal),
  });

/** A module page's Sheets view (route 2a); the switch's count reads it too. */
export const moduleWorksheetsOptions = (moduleId: string) =>
  queryOptions({
    queryKey: worksheetKeys.onModule(moduleId),
    queryFn: ({ signal }) => listModuleWorksheets(moduleId, signal),
  });
