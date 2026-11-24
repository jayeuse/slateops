"use client";

import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import type { ReactElement } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  myWorksheetsOptions,
  worksheetDetailOptions,
} from "../adapters/worksheet-queries";
import type { WorksheetDetail } from "../adapters/worksheets-api";

// A From another sheet column (docs/specs/sheets.md K9, D7.3a, Screens 2):
// another sheet the person can see, the pair of link columns that point to
// the same module, and the column to show. Rows match through the record
// both link columns point to. Loaded on first use of From another sheet.

export type FromSheetDraft = {
  sourceSheet: string;
  /** "<this sheet's link key>|<the source's link key>" */
  match: string;
  sourceColumn: string;
};

export default function SheetFromSheetField({
  sheet,
  value,
  onChange,
  field,
  selectClass,
}: {
  sheet: WorksheetDetail;
  value: FromSheetDraft;
  onChange: (patch: Partial<FromSheetDraft>) => void;
  field: (label: string, control: ReactElement, hint?: string) => ReactElement;
  selectClass: string;
}) {
  // My sheets lists every sheet the person can see (route 1).
  const sheets = useQuery(myWorksheetsOptions("exclude"));
  const source = useQuery({
    ...worksheetDetailOptions(value.sourceSheet),
    enabled: Boolean(value.sourceSheet),
  });
  const choices = (sheets.data?.items ?? []).filter(
    (item) => item.id !== sheet.id && !item.isDeleted,
  );
  const ownLinks = sheet.structure.columns.flatMap((column) =>
    column.type === "link" ? [column] : [],
  );
  const theirColumns = source.data?.structure.columns ?? [];
  const pairs = ownLinks.flatMap((own) =>
    theirColumns.flatMap((theirs) =>
      theirs.type === "link" && theirs.link.moduleId === own.link.moduleId
        ? [
            {
              value: `${own.key}|${theirs.key}`,
              label: `${own.name} (this sheet) = ${theirs.name} (${source.data?.title ?? ""})`,
            },
          ]
        : [],
    ),
  );
  const sourceLinkKey = value.match.split("|")[1] ?? "";
  const shown = theirColumns.filter(
    (column) =>
      !("state" in column && column.state) && column.key !== sourceLinkKey,
  );
  const sourceName = source.data?.title ?? "the sheet";

  return (
    <>
      {field(
        "Sheet",
        <NativeSelect
          className={selectClass}
          value={value.sourceSheet}
          onChange={(event) =>
            onChange({
              sourceSheet: event.target.value,
              match: "",
              sourceColumn: "",
            })
          }
        >
          <NativeSelectOption value="">
            {sheets.isPending ? "Loading sheets…" : "Choose a sheet"}
          </NativeSelectOption>
          {choices.map((item) => (
            <NativeSelectOption key={item.id} value={item.id}>
              {item.title}
            </NativeSelectOption>
          ))}
        </NativeSelect>,
        sheets.isError
          ? "Your sheets could not be loaded. Close this and try again."
          : undefined,
      )}
      {value.sourceSheet
        ? field(
            "Match rows by",
            <NativeSelect
              className={selectClass}
              value={value.match}
              disabled={pairs.length === 0}
              onChange={(event) => onChange({ match: event.target.value })}
            >
              <NativeSelectOption value="">
                {source.isPending ? "Loading…" : "Choose the link columns"}
              </NativeSelectOption>
              {pairs.map((pair) => (
                <NativeSelectOption key={pair.value} value={pair.value}>
                  {pair.label}
                </NativeSelectOption>
              ))}
            </NativeSelect>,
            ownLinks.length === 0
              ? "Add a Link to records column first. Rows match through the record it points to."
              : source.data && pairs.length === 0
                ? `${sourceName} has no link column to the same module as this sheet.`
                : undefined,
          )
        : null}
      {value.match
        ? field(
            "Shows",
            <NativeSelect
              className={selectClass}
              value={value.sourceColumn}
              onChange={(event) =>
                onChange({ sourceColumn: event.target.value })
              }
            >
              <NativeSelectOption value="">Choose a column</NativeSelectOption>
              {shown.map((column) => (
                <NativeSelectOption key={column.key} value={column.key}>
                  {column.name}
                </NativeSelectOption>
              ))}
            </NativeSelect>,
            `Read-only. It shows the value from the row of ${sourceName} that links to the same record.`,
          )
        : null}
    </>
  );
}
