"use client";

import { queryOptions } from "@tanstack/react-query";
import { getOpenViewRecord } from "./records-api";
import {
  getWorksheet,
  listModuleWorksheets,
  listMyWorksheets,
  listRecordWorksheets,
  listWorksheetShares,
  type WorksheetDetail,
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
  detail: (id: string) => ["openview", "worksheets", "detail", id] as const,
  /** The owner's shares (route 16): the chip and the Share dialog. */
  shares: (id: string) => ["openview", "worksheets", "shares", id] as const,
  /** Where a sheet sits; the header's breadcrumb reads it (no fetch). */
  place: (id: string) => ["openview", "worksheets", "place", id] as const,
  /** A record's Appears in, first page (route 23). */
  appears: (recordId: string) =>
    ["openview", "worksheets", "appears", recordId] as const,
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

/** One sheet (route 4); its rows are kept by the page, never cached. */
export const worksheetDetailOptions = (id: string) =>
  queryOptions({
    queryKey: worksheetKeys.detail(id),
    queryFn: ({ signal }) => getWorksheet(id, signal),
  });

/** The owner's shares of a sheet that is not open (route 16). */
export const worksheetSharesOptions = (id: string) =>
  queryOptions({
    queryKey: worksheetKeys.shares(id),
    queryFn: ({ signal }) => listWorksheetShares(id, signal),
  });

/** The department, module and record a sheet's breadcrumb names. */
export type WorksheetPlace = {
  sheetTitle: string;
  moduleId: string;
  moduleName: string;
  recordId: string | null;
  recordTitle: string | null;
};

/**
 * A record sheet's summary names its record but not the record's module;
 * one record read gives it (a module sheet needs none).
 */
export const worksheetPlaceOptions = (
  id: string,
  detail: WorksheetDetail | undefined,
) =>
  queryOptions({
    queryKey: worksheetKeys.place(id),
    enabled: Boolean(detail),
    queryFn: async (): Promise<WorksheetPlace> => {
      if (!detail) throw new Error("The sheet is not loaded");
      const moduleId =
        detail.moduleId ??
        (await getOpenViewRecord(detail.recordId ?? "")).moduleId;
      return {
        sheetTitle: detail.title,
        moduleId,
        moduleName: detail.moduleName,
        recordId: detail.recordId,
        recordTitle: detail.recordId ? detail.anchorTitle : null,
      };
    },
  });
