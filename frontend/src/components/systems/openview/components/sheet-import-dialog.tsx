"use client";

import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, FileText } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DialogFrameFooter,
  DialogFrameHeader,
  dialogFrameContentClass,
} from "@/components/ui/dialog-frame";
import { DisabledReason } from "@/components/ui/disabled-reason";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { workspaceCalendarQueryOptions } from "@/components/systems/manage/adapters/workspace-api";
import { useWorkspaceNavigationRequest } from "@/components/workspace-navigation-guard";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

import { fieldsFirstPageOptions } from "../adapters/openview-queries";
import { worksheetKeys } from "../adapters/worksheet-queries";
import {
  createWorksheet,
  getWorksheet,
  matchImportKeys,
  readImportFile,
  writeWorksheetRows,
  type WorksheetDetail,
} from "../adapters/worksheets-api";
import { gridColumns, type GridColumn } from "../domain/sheet-grid";
import {
  cellProblemWords,
  dataTemplate,
  decodeCsv,
  fileTable,
  importableColumn,
  importFileKind,
  importKey,
  importRows,
  keyChunks,
  matchCounts,
  parseCsv,
  rowBatches,
  rowResults,
  SHEET_MAX_ROWS,
  suggestColumnType,
  type ColumnPlan,
  type ImportCell,
  type KeyResult,
  type NewColumn,
  type NewColumnType,
} from "../domain/sheet-import";
import { sheetHref } from "./sheet-display";
import type { SheetAnchor } from "./sheet-lists";
import { moduleLabel, useSheetModules } from "./use-sheet-modules";

// The import preview (docs/specs/sheets.md X8 to X12, D9.3, Decisions 13 to
// 15; Screens 8): 1 File, 2 Columns, 3 Match the link column. CSV is read
// here; Excel by the server, one tab at a time. Nothing is written until the
// person confirms; then rows go in batches of 100, and a refused batch stops
// the import and says how many rows were added. Loaded on first use.

export type ImportTarget =
  | { kind: "new"; title: string; anchor: SheetAnchor }
  | { kind: "existing"; sheet: WorksheetDetail };

type Source = {
  file: File;
  kind: "csv" | "xlsx";
  rows: ImportCell[][];
  tabs: { index: number; name: string }[];
  tabIndex: number;
  formulaWithoutValue: number;
};

type Filter = "all" | "matched" | "unmatched" | "ambiguous";

const NEW_TYPES: { value: NewColumnType | "link"; label: string }[] = [
  { value: "text", label: "Text" },
  { value: "long_text", label: "Long text" },
  { value: "decimal", label: "Number" },
  { value: "int", label: "Whole number" },
  { value: "boolean", label: "Checkbox" },
  { value: "date", label: "Date" },
  { value: "datetime", label: "Date and time" },
  { value: "link", label: "Link to records" },
];

const TYPE_WORDS: Partial<Record<GridColumn["type"], string>> = {
  text: "Text",
  long_text: "Long text",
  email: "Email",
  url: "Web link",
  number: "Number",
  decimal: "Number",
  int: "Whole number",
  boolean: "Checkbox",
  date: "Date",
  datetime: "Date and time",
  select: "Choice list",
};

const PREVIEW_ROWS = 50;

function counted(count: number, one: string, many: string) {
  return `${count.toLocaleString("en-US")} ${count === 1 ? one : many}`;
}

/** Why a file could not be read, in the reader's words. */
function readFailure(error: unknown): string {
  if (error instanceof ApiError) {
    const details =
      typeof error.details === "object" && error.details !== null
        ? (error.details as Record<string, unknown>)
        : {};
    if (error.status === 413)
      return "This Excel file is too large to read. Save it as CSV and import that.";
    if (error.status === 403) return "Guests cannot import files.";
    if (error.code === "import_file_invalid") {
      if (details.reason === "macro")
        return "Macro-enabled Excel files cannot be imported. Save the file as .xlsx and try again.";
      if (details.reason === "archive_bounds")
        return "This file holds more than an import may unpack. Save it again as .xlsx, or as CSV.";
      if (details.reason === "limit")
        return "This Excel file is too large to read. Save it as CSV and import that.";
      return "This Excel file could not be read. Save it again as .xlsx, or as CSV.";
    }
    if (error.code === "worksheet_limit")
      return details.limit === "cell"
        ? "A cell in this tab holds more than a sheet cell can. Save it as CSV and import that."
        : "A sheet holds at most 10,000 rows and 100 columns, and this tab has more. Save a smaller part, or split the file.";
    if (error.code === "import_unavailable")
      return "This file took too long to read. Save it as CSV and import that.";
    if (error.code === "import_tab_invalid" || error.status === 422)
      return "This tab could not be read. Choose another tab.";
    if (error.status === 503)
      return "The file could not be read right now. Try again in a moment.";
  }
  if (error instanceof Error && !(error instanceof ApiError))
    return error.message;
  return "The file could not be read. Try again.";
}

/** Why a batch was refused, after the count of rows that were added. */
function batchFailure(
  error: unknown,
  sheetTitle: string,
  columns: readonly { key: string; name: string }[],
): string {
  if (error instanceof ApiError) {
    if (error.code === "structure_changed")
      return `The columns of ${sheetTitle} changed meanwhile, so the rest were not added.`;
    if (error.status === 403)
      return "You can no longer change this sheet, so the rest were not added.";
    if (error.status === 404)
      return "The sheet is no longer available, so the rest were not added.";
    if (error.status === 413)
      return "The rows were more than one request may carry, so the rest were not added.";
    if (error.status === 422) {
      const details =
        typeof error.details === "object" && error.details !== null
          ? (error.details as Record<string, unknown>)
          : {};
      const column = columns.find((item) => item.key === details.key);
      const reason = error.message.replace(/\.$/, "");
      return column
        ? `${column.name}: ${reason}. The rest were not added.`
        : `${reason}. The rest were not added.`;
    }
    return "The rest could not be added.";
  }
  return "";
}

type Written =
  | {
      kind: "partial";
      added: number;
      total: number;
      words: string;
      emptied: number;
      sheetId: string;
    }
  | {
      kind: "unknown";
      added: number;
      total: number;
      emptied: number;
      sheetId: string;
    }
  // Every row was added, and the server stored some cells empty.
  | {
      kind: "done";
      added: number;
      total: number;
      emptied: number;
      sheetId: string;
    }
  // The create's answer was lost: the sheet may or may not exist (N11).
  | { kind: "lost-create" };

/** Why the new sheet was not made, in the reader's words. */
function createFailure(error: ApiError, onModule: boolean): string {
  if (error.status === 409)
    return onModule
      ? "This module was closed, so it cannot hold a new sheet."
      : "This record was deleted or its module was closed, so it cannot hold a new sheet.";
  if (error.status === 404)
    return "A chosen module, or this record, is no longer available. Nothing was added.";
  if (error.status === 403) return "Guests cannot create sheets.";
  return "The sheet could not be made. Nothing was added. Try again.";
}

/** The kind of column a file cannot fill, for the line under Not added. */
const UNFILLED: Partial<Record<GridColumn["type"], string>> = {
  lookup: "lookup",
  computed: "computed",
  user: "person",
  sheet_lookup: "From another sheet",
};

/** The server's count of cells it stored empty (R5), or nothing. */
function emptiedWords(count: number): string {
  if (!count) return "";
  return count === 1
    ? "1 cell did not fit its column and was added empty."
    : `${counted(count, "cell", "cells")} did not fit their column and were added empty.`;
}

/** Column keys and types: a saved list with the same ones takes the same rows. */
function columnShape(structure: WorksheetDetail["structure"]): string {
  return structure.columns
    .map((column) => `${column.key}:${column.type}`)
    .join(",");
}

export default function SheetImportDialog({
  target,
  initialFile,
  onClose,
  onImported,
}: {
  target: ImportTarget;
  initialFile: File | null;
  onClose: () => void;
  /** Rows were added to the open sheet (some or all). */
  onImported?: () => void;
}) {
  const id = useId();
  const client = useQueryClient();
  const router = useRouter();
  const requestNavigation = useWorkspaceNavigationRequest();
  // The organization's locale and time zone, never the person's own view of
  // them: a file's numbers and times are the organization's (D1, O4).
  const calendar = useQuery(workspaceCalendarQueryOptions());
  const locale = calendar.data?.locale;
  const timezone = calendar.data?.timezone;
  const catalog = useSheetModules();
  const { modules } = catalog;
  // The route 21 read in flight: a new file or tab, or closing, aborts it.
  const fileRead = useRef<AbortController | null>(null);
  useEffect(() => () => fileRead.current?.abort(), []);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const reads = useRef(0);
  const [source, setSource] = useState<Source | null>(null);
  const [reading, setReading] = useState(false);
  const [readError, setReadError] = useState<string | null>(null);
  const [headerRow, setHeaderRow] = useState(0);
  // Per file column: a sheet column key (existing sheet) or a type (new
  // sheet); "" is Not added.
  const [mapping, setMapping] = useState<string[]>([]);
  const [linkModule, setLinkModule] = useState("");
  const [keyFile, setKeyFile] = useState<number | null>(null);
  const [keyField, setKeyField] = useState("");
  const [unmatched, setUnmatched] = useState<"keep" | "skip">("keep");
  const [filter, setFilter] = useState<Filter>("all");
  const [found, setFound] = useState<{
    signature: string;
    map: Map<string, KeyResult>;
  } | null>(null);
  const [matchFailed, setMatchFailed] = useState(false);
  const [matchTry, setMatchTry] = useState(0);
  const [progress, setProgress] = useState<{
    done: number;
    total: number;
  } | null>(null);
  const [written, setWritten] = useState<Written | null>(null);
  const writing = progress !== null;

  const existing = target.kind === "existing" ? target.sheet : null;
  const sheetTitle = existing
    ? existing.title
    : target.kind === "new"
      ? target.title
      : "";
  const sheetColumns = useMemo(
    () => (existing ? gridColumns(existing.structure) : []),
    [existing],
  );

  // ------------------------------------------------------------- the file

  const table = useMemo(
    () => (source ? fileTable(source.rows, headerRow) : null),
    [source, headerRow],
  );

  const defaults = (
    headers: string[],
    body: ImportCell[][],
    region: { locale: string },
  ) =>
    headers.map((header, index) => {
      // A column with no values (Excel keeps leading empty columns) is
      // not added unless the person adds it.
      if (
        body.every((cells) => {
          const cell = cells[index] ?? null;
          return cell === null || String(cell).trim() === "";
        })
      )
        return "";
      if (existing) {
        const same = sheetColumns.find(
          (column) =>
            column.name.trim().toLowerCase() === header.trim().toLowerCase(),
        );
        return same && importableColumn(same) ? same.key : "";
      }
      return suggestColumnType(
        body.map((cells) => cells[index] ?? null),
        region.locale,
      ).type;
    });

  const applyTable = (
    rows: ImportCell[][],
    row: number,
    region: { locale: string },
  ) => {
    const next = fileTable(rows, row);
    const map = defaults(
      next.headers,
      next.body.map((item) => item.cells),
      region,
    );
    // One link column per import: only the first that maps to one keeps it.
    let linked = false;
    const single = map.map((value) => {
      const isLink = existing
        ? sheetColumns.find((column) => column.key === value)?.type === "link"
        : value === "link";
      if (!isLink) return value;
      if (linked) return "";
      linked = true;
      return value;
    });
    setMapping(single);
    const link = single.findIndex((value) =>
      existing
        ? sheetColumns.find((column) => column.key === value)?.type === "link"
        : value === "link",
    );
    setKeyFile(link >= 0 ? link : null);
    setKeyField("");
  };

  const read = async (file: File, tab = 0) => {
    const asked = (reads.current += 1);
    setReadError(null);
    setWritten(null);
    let kind: "csv" | "xlsx";
    try {
      kind = importFileKind(file);
    } catch (error) {
      setSource(null);
      setReadError(readFailure(error));
      return;
    }
    setReading(true);
    // A new read stops the one before it; closing stops this one (N9, F7-S1).
    fileRead.current?.abort();
    const controller = new AbortController();
    fileRead.current = controller;
    try {
      let next: Source;
      if (kind === "csv") {
        const text = decodeCsv(await file.arrayBuffer());
        next = {
          file,
          kind,
          rows: await parseCsv(text, { signal: controller.signal }),
          tabs: [],
          tabIndex: 0,
          formulaWithoutValue: 0,
        };
      } else {
        const parsed = await readImportFile(file, tab, controller.signal);
        next = { file, kind, ...parsed };
      }
      // Types are suggested in the organization's locale, so the read waits
      // for its settings.
      const region =
        calendar.data ??
        (await client.fetchQuery(workspaceCalendarQueryOptions()));
      if (asked !== reads.current) return;
      const first = Math.max(
        0,
        next.rows.findIndex((cells) =>
          cells.some((cell) => cell !== null && String(cell).trim() !== ""),
        ),
      );
      setSource(next);
      setReadError(null);
      setHeaderRow(first);
      applyTable(next.rows, first, region);
    } catch (error) {
      if (asked !== reads.current || fileRead.current?.signal.aborted) return;
      // Another tab of the same file that cannot be read keeps the file
      // and its tabs, so the person can choose again.
      if (!(source && source.file === file)) setSource(null);
      setReadError(readFailure(error));
    } finally {
      if (asked === reads.current) setReading(false);
    }
  };

  // The file chosen in New sheet is read once, when the preview opens.
  const firstRead = useRef(false);
  useEffect(() => {
    if (firstRead.current || !initialFile) return;
    firstRead.current = true;
    void read(initialFile);
    // Strict Mode's dev cleanup aborts the read: the next mount reads again.
    return () => {
      firstRead.current = false;
    };
  }, [initialFile]);

  // ------------------------------------------------------------ the plan

  const headers = table?.headers ?? [];
  const body = table?.body ?? [];
  const isLinkChoice = (value: string) =>
    existing
      ? sheetColumns.find((column) => column.key === value)?.type === "link"
      : value === "link";
  const linkIndex = mapping.findIndex(isLinkChoice);
  const linkColumn =
    existing && linkIndex >= 0
      ? sheetColumns.find((column) => column.key === mapping[linkIndex])
      : undefined;
  const linkModuleId = existing ? (linkColumn?.linkModuleId ?? "") : linkModule;
  const linkModuleOf = modules.find((module) => module.id === linkModuleId);
  const linkName = existing
    ? (linkColumn?.name ?? "")
    : linkIndex >= 0
      ? headers[linkIndex]
      : "";
  const keyIndex = keyFile ?? linkIndex;

  const fields = useQuery({
    ...fieldsFirstPageOptions(linkModuleId),
    enabled: linkIndex >= 0 && Boolean(linkModuleId),
  });
  // The catalog lists scalar fields only, the ones route 22 can match on.
  const keyFields = useMemo(() => fields.data?.items ?? [], [fields.data]);
  const fieldId =
    keyField ||
    (
      keyFields.find((field) => field.id === linkModuleOf?.titleFieldId) ??
      keyFields[0]
    )?.id ||
    "";
  const fieldName = keyFields.find((field) => field.id === fieldId)?.name ?? "";
  const fieldsFailed =
    linkIndex >= 0 && Boolean(linkModuleId) && fields.isError;

  const keys = useMemo(
    () =>
      linkIndex >= 0 && keyIndex >= 0
        ? body.map((row) =>
            importKey(row.cells[keyIndex] ?? null, source?.kind ?? "csv"),
          )
        : [],
    [body, linkIndex, keyIndex, source?.kind],
  );
  const keySignature = useMemo(() => keys.join("\u0000"), [keys]);
  const signature = `${linkModuleId}|${fieldId}|${keySignature}|${matchTry}`;
  // A link column is matched before anything can be written (SH-35): until
  // its module's fields are read and every key has an answer, it waits.
  const matching = linkIndex >= 0 && found?.signature !== signature;

  // Keys are matched in chunks of 2,000, one request after another (route 22).
  useEffect(() => {
    setMatchFailed(false);
    // A file past the row limit is never matched (F7-S1).
    if (
      linkIndex < 0 ||
      !linkModuleId ||
      !fieldId ||
      keys.length > SHEET_MAX_ROWS
    )
      return;
    const controller = new AbortController();
    void (async () => {
      const map = new Map<string, KeyResult>();
      try {
        for (const chunk of keyChunks(keys)) {
          const answer = await matchImportKeys({
            moduleId: linkModuleId,
            fieldId,
            keys: chunk,
            signal: controller.signal,
          });
          for (const [key, result] of answer) map.set(key, result);
        }
        if (!controller.signal.aborted) setFound({ signature, map });
      } catch {
        if (!controller.signal.aborted) setMatchFailed(true);
      }
    })();
    return () => controller.abort();
    // `signature` names every input of the request.
  }, [signature]);

  const results = useMemo(
    () =>
      found && found.signature === signature ? rowResults(keys, found.map) : [],
    [found, signature, keys],
  );
  const counts = matchCounts(results);
  const withoutMatch = counts.unmatched + counts.ambiguous;

  // The columns written, in file order; for a new sheet, keys c1 to cn.
  const added = useMemo(
    () =>
      mapping
        .map((value, fileIndex) => ({ value, fileIndex }))
        .filter((item) => item.value !== ""),
    [mapping],
  );
  // Lookups by Map, not by searching lists (F7-S1): a file may have up to
  // 1,000 columns.
  const newKeys = useMemo(
    () =>
      new Map(
        added.map((item, position) => [item.fileIndex, `c${position + 1}`]),
      ),
    [added],
  );
  const newKey = (fileIndex: number) => newKeys.get(fileIndex) ?? "c0";
  const columnsByKey = useMemo(
    () => new Map(sheetColumns.map((column) => [column.key, column])),
    [sheetColumns],
  );
  const plan = useMemo(
    (): ColumnPlan[] =>
      added
        .filter((item) => item.fileIndex !== linkIndex)
        .flatMap(({ value, fileIndex }): ColumnPlan[] => {
          if (existing) {
            const column = columnsByKey.get(value);
            return column ? [{ fileIndex, target: column }] : [];
          }
          return [
            {
              fileIndex,
              target: {
                key: newKeys.get(fileIndex) ?? "c0",
                name: headers[fileIndex],
                type: value as NewColumnType,
              },
            },
          ];
        }),
    [added, linkIndex, existing, columnsByKey, newKeys, headers],
  );
  const linkKey =
    linkIndex < 0 ? null : existing ? mapping[linkIndex] : newKey(linkIndex);
  // The preview's counts and warnings and the rows that are written are one
  // computation, made again only when one of its inputs changes.
  const sourceKind = source?.kind ?? "csv";
  const built = useMemo(
    () =>
      locale && timezone
        ? importRows({
            body,
            plan,
            link:
              linkKey && keyIndex >= 0
                ? { key: linkKey, fileIndex: keyIndex, results, unmatched }
                : null,
            locale,
            timezone,
            source: sourceKind,
          })
        : {
            rows: [],
            problems: new Map<string, number>(),
            skipped: 0,
            oversized: 0,
            cleared: [],
          },
    [
      body,
      plan,
      linkKey,
      keyIndex,
      results,
      unmatched,
      locale,
      timezone,
      sourceKind,
    ],
  );
  // Two file columns into one sheet column wait for a choice (N2).
  const doubled = existing
    ? sheetColumns.flatMap((column) => {
        const files = mapping.flatMap((value, index) =>
          value === column.key ? [headers[index]] : [],
        );
        return files.length > 1 ? [{ column: column.name, files }] : [];
      })
    : [];
  const tooWide = !existing && added.length > 100;
  const rowCount = built.rows.length;
  const existingRows = existing?.liveRowCount ?? 0;
  const overLimit = existingRows + rowCount > SHEET_MAX_ROWS;

  const blocked = (() => {
    if (calendar.isError)
      return "The organization's settings could not be read. Try again.";
    if (!locale || !timezone) return "Wait for the organization's settings.";
    if (reading) return "Wait for the file to be read.";
    if (!source || !table) return "Choose a file first.";
    if (!added.length) return "Add at least one column.";
    if (doubled.length) return "Choose one file column for each sheet column.";
    if (tooWide) return "A sheet holds at most 100 columns.";
    if (linkIndex >= 0 && !linkModuleId)
      return "Choose the module the link column links to.";
    if (fieldsFailed || matchFailed)
      return "The matching could not be checked. Try it again.";
    if (linkIndex >= 0 && fields.isSuccess && !fieldId)
      return `${linkModuleOf?.name ?? "The module"} has no field to match by.`;
    // Before the matching: a file this long is never matched (F7 review 5).
    if (overLimit || existingRows + body.length > SHEET_MAX_ROWS)
      return "A sheet holds at most 10,000 rows.";
    if (matching) return "Wait for the matching to finish.";
    if (rowCount === 0) return "There are no rows to add.";
    return null;
  })();

  // ---------------------------------------------------------------- write

  const finishNew = (sheetId: string) => {
    void client.invalidateQueries({ queryKey: worksheetKeys.all });
    onClose();
    const href = sheetHref(sheetId);
    const resume = () => router.push(href as Route);
    if (requestNavigation(href, resume)) resume();
  };

  const confirm = async () => {
    if (blocked || writing || written) return;
    let rows = built.rows;
    let sheetId: string;
    let revision: number;
    let keyNames: { key: string; name: string }[] = sheetColumns;
    let shape = existing ? columnShape(existing.structure) : "";
    if (target.kind === "new") {
      const columns: NewColumn[] = added.map(({ value, fileIndex }) => {
        const name = headers[fileIndex];
        if (value === "link")
          return {
            name,
            type: "link",
            link: {
              moduleName: linkModuleOf?.name ?? "",
              departmentName: linkModuleOf?.departmentName ?? "",
            },
          };
        if (value === "decimal") {
          const suggested = suggestColumnType(
            body.map((row) => row.cells[fileIndex] ?? null),
            locale ?? "",
          );
          return { name, type: "decimal", places: suggested.places ?? 2 };
        }
        return { name, type: value as Exclude<NewColumnType, "decimal"> };
      });
      setProgress({ done: 0, total: rows.length });
      let created: WorksheetDetail;
      try {
        created = await createWorksheet({
          ...(target.anchor.kind === "record"
            ? { recordId: target.anchor.recordId }
            : { moduleId: target.anchor.moduleId }),
          title: target.title,
          source: {
            kind: "template",
            template: dataTemplate(target.title, columns),
            moduleMapping: linkKey ? { [linkKey]: linkModuleId } : {},
          },
        });
      } catch (error) {
        setProgress(null);
        if (error instanceof ApiError && error.status < 500)
          setReadError(createFailure(error, target.anchor.kind === "module"));
        // A lost answer or a server failure: the sheet may exist, so no
        // retry is offered.
        else setWritten({ kind: "lost-create" });
        return;
      }
      // The server may give the columns new keys; they keep their order.
      const keyOf = new Map(
        added.map((_, index) => [
          `c${index + 1}`,
          created.structure.columns[index]?.key ?? `c${index + 1}`,
        ]),
      );
      rows = rows.map((cells) =>
        Object.fromEntries(
          Object.entries(cells).map(([key, value]) => [
            keyOf.get(key) ?? key,
            value,
          ]),
        ),
      );
      keyNames = created.structure.columns;
      shape = columnShape(created.structure);
      sheetId = created.id;
      revision = created.revision;
    } else {
      sheetId = target.sheet.id;
      revision = target.sheet.revision;
    }
    let done = 0;
    // Rows written so far, and the cells the import itself sent empty in
    // them (times it could not read), told with the server's count.
    let sentRows = 0;
    const cleared = built.cleared;
    let emptied = 0;
    setProgress({ done, total: rows.length });
    let batches = rowBatches(rows, revision);
    // A column list saved meanwhile (a rename, a group) leaves the columns
    // as they were: the batch goes again at the new version (N7), and the
    // rest are cut again for the new version's body size.
    let retries = 0;
    for (let index = 0; index < batches.length;) {
      try {
        const result = await writeWorksheetRows(
          sheetId,
          revision,
          batches[index],
        );
        done += result.added;
        emptied += result.emptied;
        for (const count of cleared.slice(
          sentRows,
          sentRows + batches[index].length,
        ))
          emptied += count;
        sentRows += batches[index].length;
        setProgress({ done, total: rows.length });
        index += 1;
      } catch (error) {
        if (
          error instanceof ApiError &&
          error.code === "structure_changed" &&
          retries < 3
        ) {
          retries += 1;
          const fresh = await getWorksheet(sheetId).catch(() => null);
          if (fresh && columnShape(fresh.structure) === shape) {
            revision = fresh.revision;
            batches = [
              ...batches.slice(0, index),
              ...rowBatches(batches.slice(index).flat(), revision),
            ];
            continue;
          }
        }
        setProgress(null);
        // A lost answer may or may not have added its rows: say so, and
        // never send the batch again from here (route 14 is not idempotent).
        setWritten(
          error instanceof ApiError
            ? {
                kind: "partial",
                added: done,
                total: rows.length,
                words: batchFailure(error, sheetTitle, keyNames),
                emptied,
                sheetId,
              }
            : {
                kind: "unknown",
                added: done,
                total: rows.length,
                emptied,
                sheetId,
              },
        );
        return;
      }
    }
    setProgress(null);
    // The server's count of cells stored empty is the answer (R5): the
    // dialog stays to say it.
    if (emptied > 0) {
      setWritten({
        kind: "done",
        added: done,
        total: rows.length,
        emptied,
        sheetId,
      });
      return;
    }
    if (target.kind === "new") finishNew(sheetId);
    else {
      onImported?.();
      onClose();
    }
  };

  const closeAfter = () => {
    if (written?.kind === "lost-create") onClose();
    else if (written && target.kind === "new") finishNew(written.sheetId);
    else {
      // Some rows may have been added: the sheet reads its rows again.
      if (written) onImported?.();
      onClose();
    }
  };

  // ---------------------------------------------------------------- render

  const title =
    target.kind === "new"
      ? `New sheet ${target.title} from a file`
      : `Add rows to ${target.sheet.title} from a file`;
  const place =
    target.kind === "new"
      ? target.anchor.kind === "record"
        ? `On ${target.anchor.recordTitle} · ${target.anchor.moduleName}`
        : `On ${target.anchor.moduleName}`
      : target.sheet.recordId
        ? `On ${target.sheet.anchorTitle} · ${target.sheet.moduleName}`
        : `On ${target.sheet.moduleName}`;
  const primary =
    target.kind === "new"
      ? `Create ${target.title} with ${counted(rowCount, "row", "rows")}`
      : `Add ${counted(rowCount, "row", "rows")} to ${target.sheet.title}`;
  const shown = results.length
    ? body
        .map((row, index) => ({ row, result: results[index] }))
        .filter(({ result }) => filter === "all" || result.state === filter)
    : [];
  const keptWords = unmatched === "keep" ? "kept as text" : "skipped";
  const resultWords = (result: KeyResult) =>
    result.state === "matched"
      ? `Matched · ${result.label}`
      : result.state === "ambiguous"
        ? `Matched more than once · ${keptWords}`
        : `Not matched · ${keptWords}`;
  const step = (number: number, heading: string, content: ReactNode) => (
    <li className="flex flex-col gap-3 border-t pt-4 first:border-t-0 first:pt-0">
      <h3 className="flex items-center gap-2 text-sm font-semibold">
        <span
          aria-hidden="true"
          className="bg-muted text-muted-foreground inline-flex size-6 items-center justify-center rounded-full text-xs tabular-nums"
        >
          {number}
        </span>
        <span className="sr-only">{number}. </span>
        {heading}
      </h3>
      {content}
    </li>
  );
  const selectClass = "w-full [&_select]:h-11 xl:[&_select]:h-8";
  // Ten rows from the first row with a value, which may be past row 10.
  const headerChoices = source
    ? Math.min(
        source.rows.length,
        Math.max(
          10,
          source.rows.findIndex((cells) =>
            cells.some((cell) => cell !== null && String(cell).trim() !== ""),
          ) + 10,
        ),
      )
    : 0;

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !writing) closeAfter();
      }}
    >
      <DialogContent className={cn(dialogFrameContentClass, "sm:max-w-4xl")}>
        <DialogFrameHeader
          title={<DialogTitle>{title}</DialogTitle>}
          description={<DialogDescription>{place}</DialogDescription>}
          closeLabel="Close the import"
          closeDisabled={writing}
          onClose={closeAfter}
        />
        <input
          ref={fileInput}
          type="file"
          accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          aria-label="Choose a file"
          tabIndex={-1}
          className="sr-only"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void read(file);
          }}
        />
        <ol className="flex flex-col gap-4">
          {step(
            1,
            "File",
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center gap-3 rounded-md border p-3">
                <FileText
                  aria-hidden="true"
                  className="text-muted-foreground size-4 shrink-0"
                />
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-sm font-medium">
                    {source?.file.name ?? "No file chosen"}
                  </span>
                  <span className="text-muted-foreground text-xs" role="status">
                    {reading
                      ? "Reading the file…"
                      : table
                        ? `${counted(table.body.length, "row", "rows")} under the header row`
                        : "A CSV or Excel (.xlsx) file."}
                  </span>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  className="min-h-11 xl:h-8 xl:min-h-8"
                  disabled={writing || Boolean(written)}
                  onClick={() => fileInput.current?.click()}
                >
                  {source ? "Choose another file" : "Choose a file"}
                </Button>
              </div>
              {source ? (
                <div className="flex flex-wrap gap-3">
                  {source.kind === "xlsx" ? (
                    <label className="flex min-w-40 flex-col gap-1 text-xs font-medium">
                      Tab
                      <NativeSelect
                        className={selectClass}
                        value={String(source.tabIndex)}
                        disabled={reading || writing}
                        onChange={(event) =>
                          void read(source.file, Number(event.target.value))
                        }
                      >
                        {source.tabs.map((tab) => (
                          <NativeSelectOption key={tab.index} value={tab.index}>
                            {tab.name}
                          </NativeSelectOption>
                        ))}
                      </NativeSelect>
                    </label>
                  ) : null}
                  <label className="flex min-w-40 flex-col gap-1 text-xs font-medium">
                    Header row
                    <NativeSelect
                      className={selectClass}
                      value={String(headerRow)}
                      disabled={writing}
                      onChange={(event) => {
                        const row = Number(event.target.value);
                        setHeaderRow(row);
                        if (locale) applyTable(source.rows, row, { locale });
                      }}
                    >
                      {Array.from({ length: headerChoices }, (_, index) => (
                        <NativeSelectOption key={index} value={index}>
                          {`Row ${index + 1}`}
                        </NativeSelectOption>
                      ))}
                    </NativeSelect>
                  </label>
                </div>
              ) : null}
              {readError ? (
                <Alert variant="destructive">{readError}</Alert>
              ) : null}
              {calendar.isError ? (
                <Alert
                  variant="destructive"
                  className="flex flex-wrap items-center gap-x-4 gap-y-2"
                >
                  <p className="min-w-0 flex-1">
                    The organization&apos;s settings could not be read.
                  </p>
                  <Button
                    type="button"
                    variant="outline"
                    className="min-h-11 xl:h-8 xl:min-h-8"
                    onClick={() => void calendar.refetch()}
                  >
                    Retry
                  </Button>
                </Alert>
              ) : null}
              {source && source.formulaWithoutValue > 0 ? (
                <p className="text-warn-text flex items-start gap-2 text-sm">
                  <AlertTriangle
                    aria-hidden="true"
                    className="mt-0.5 size-4 shrink-0"
                  />
                  {source.formulaWithoutValue === 1
                    ? "1 cell has a formula with no saved result. It is added empty."
                    : `${counted(source.formulaWithoutValue, "cell", "cells")} have a formula with no saved result. They are added empty.`}
                </p>
              ) : null}
            </div>,
          )}
          {table
            ? step(
                2,
                "Columns",
                <div className="flex flex-col gap-3">
                  {!existing && catalog.failed ? (
                    <Alert
                      variant="destructive"
                      className="flex flex-wrap items-center gap-x-4 gap-y-2"
                    >
                      <p className="min-w-0 flex-1">
                        The modules could not be listed.
                      </p>
                      <Button
                        type="button"
                        variant="outline"
                        className="min-h-11 xl:h-8 xl:min-h-8"
                        onClick={catalog.retry}
                      >
                        Retry
                      </Button>
                    </Alert>
                  ) : null}
                  {existing ? (
                    <p className="text-muted-foreground text-sm">
                      {`${existing.title} has ${counted(existingRows, "row", "rows")}. These rows are added after them.`}
                    </p>
                  ) : null}
                  <div
                    role="group"
                    aria-label="File columns"
                    className="grid grid-cols-1 items-center gap-x-3 gap-y-2 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1.4fr)]"
                  >
                    <span className="text-muted-foreground hidden text-xs font-medium sm:block">
                      In the file
                    </span>
                    <span className="hidden sm:block" />
                    <span className="text-muted-foreground hidden text-xs font-medium sm:block">
                      {existing ? `In ${existing.title}` : "In the new sheet"}
                    </span>
                    {headers.map((header, index) => {
                      const value = mapping[index] ?? "";
                      const takenLink = linkIndex >= 0 && linkIndex !== index;
                      // A same-named column that a file cannot fill says so.
                      const unfilled =
                        existing && value === ""
                          ? sheetColumns.find(
                              (column) =>
                                !importableColumn(column) &&
                                UNFILLED[column.type] &&
                                column.name.trim().toLowerCase() ===
                                  header.trim().toLowerCase(),
                            )
                          : undefined;
                      return (
                        <div key={`${index}-${header}`} className="contents">
                          <span className="truncate text-sm font-medium max-sm:pt-2">
                            {header}
                          </span>
                          <ArrowRight
                            aria-hidden="true"
                            className="text-muted-foreground hidden size-4 sm:block"
                          />
                          <div className="flex flex-col gap-2 sm:flex-row">
                            <NativeSelect
                              aria-label={header}
                              className={selectClass}
                              value={value}
                              disabled={writing || Boolean(written)}
                              onChange={(event) => {
                                const next = [...mapping];
                                next[index] = event.target.value;
                                setMapping(next);
                                if (isLinkChoice(event.target.value)) {
                                  setKeyFile(index);
                                  setKeyField("");
                                } else if (index === linkIndex)
                                  setKeyFile(null);
                              }}
                            >
                              <NativeSelectOption value="">
                                Not added
                              </NativeSelectOption>
                              {existing
                                ? sheetColumns
                                    .filter(importableColumn)
                                    .map((column) => (
                                      <NativeSelectOption
                                        key={column.key}
                                        value={column.key}
                                        disabled={
                                          column.type === "link" && takenLink
                                        }
                                      >
                                        {column.type === "link"
                                          ? `${column.name} (link to ${modules.find((module) => module.id === column.linkModuleId)?.name ?? "records"})`
                                          : `${column.name} (${TYPE_WORDS[column.type] ?? "Text"})`}
                                      </NativeSelectOption>
                                    ))
                                : NEW_TYPES.map((type) => (
                                    <NativeSelectOption
                                      key={type.value}
                                      value={type.value}
                                      disabled={
                                        type.value === "link" && takenLink
                                      }
                                    >
                                      {type.label}
                                    </NativeSelectOption>
                                  ))}
                            </NativeSelect>
                            {!existing && value === "link" ? (
                              <NativeSelect
                                aria-label={`${header} links to`}
                                className={selectClass}
                                value={linkModule}
                                disabled={writing || Boolean(written)}
                                onChange={(event) => {
                                  setLinkModule(event.target.value);
                                  setKeyField("");
                                }}
                              >
                                <NativeSelectOption value="">
                                  Choose a module
                                </NativeSelectOption>
                                {modules.map((module) => (
                                  <NativeSelectOption
                                    key={module.id}
                                    value={module.id}
                                  >
                                    {moduleLabel(module)}
                                  </NativeSelectOption>
                                ))}
                              </NativeSelect>
                            ) : null}
                          </div>
                          {unfilled ? (
                            <span className="text-muted-foreground text-xs sm:col-start-3">
                              {`${unfilled.name} is a ${UNFILLED[unfilled.type]} column. Files cannot fill it.`}
                            </span>
                          ) : null}
                        </div>
                      );
                    })}
                  </div>
                </div>,
              )
            : null}
          {table && linkIndex >= 0 && linkModuleId
            ? step(
                3,
                `Match the ${linkName} column`,
                <div className="flex flex-col gap-3">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <span>{`Find each row's record in ${linkModuleOf?.name ?? "the module"} by`}</span>
                    <NativeSelect
                      aria-label="Column in the file"
                      className="[&_select]:h-11 xl:[&_select]:h-8"
                      value={String(keyIndex)}
                      disabled={writing || Boolean(written)}
                      onChange={(event) =>
                        setKeyFile(Number(event.target.value))
                      }
                    >
                      {headers.map((header, index) => (
                        <NativeSelectOption
                          key={`${index}-${header}`}
                          value={index}
                        >
                          {header}
                        </NativeSelectOption>
                      ))}
                    </NativeSelect>
                    <span aria-hidden="true">=</span>
                    <NativeSelect
                      aria-label={`Field in ${linkModuleOf?.name ?? "the module"}`}
                      className="[&_select]:h-11 xl:[&_select]:h-8"
                      value={fieldId}
                      disabled={writing || Boolean(written)}
                      onChange={(event) => setKeyField(event.target.value)}
                    >
                      {keyFields.map((field) => (
                        <NativeSelectOption key={field.id} value={field.id}>
                          {field.name}
                        </NativeSelectOption>
                      ))}
                    </NativeSelect>
                    <span className="text-muted-foreground basis-full text-xs">
                      Only records you can read count as matches.
                    </span>
                  </div>
                  {fieldsFailed ? (
                    <Alert
                      variant="destructive"
                      className="flex flex-wrap items-center gap-x-4 gap-y-2"
                    >
                      <p className="min-w-0 flex-1">
                        {`The fields of ${linkModuleOf?.name ?? "the module"} could not be read.`}
                      </p>
                      <Button
                        type="button"
                        variant="outline"
                        className="min-h-11 xl:h-8 xl:min-h-8"
                        onClick={() => void fields.refetch()}
                      >
                        Retry
                      </Button>
                    </Alert>
                  ) : matchFailed ? (
                    <Alert
                      variant="destructive"
                      className="flex flex-wrap items-center gap-x-4 gap-y-2"
                    >
                      <p className="min-w-0 flex-1">
                        The rows could not be matched.
                      </p>
                      <Button
                        type="button"
                        variant="outline"
                        className="min-h-11 xl:h-8 xl:min-h-8"
                        onClick={() => setMatchTry((value) => value + 1)}
                      >
                        Retry
                      </Button>
                    </Alert>
                  ) : matching ? (
                    <p role="status" className="text-muted-foreground text-sm">
                      {fieldName ? `Matching by ${fieldName}…` : "Matching…"}
                    </p>
                  ) : (
                    <>
                      <div
                        role="group"
                        aria-label="Rows by result"
                        className="flex flex-wrap gap-1"
                      >
                        {(
                          [
                            ["all", "All", results.length],
                            ["matched", "Matched", counts.matched],
                            ["unmatched", "Not matched", counts.unmatched],
                            [
                              "ambiguous",
                              "Matched more than once",
                              counts.ambiguous,
                            ],
                          ] as const
                        ).map(([value, label, count]) => (
                          <Button
                            key={value}
                            type="button"
                            variant={filter === value ? "outline" : "ghost"}
                            aria-pressed={filter === value}
                            className="min-h-11 gap-1.5 xl:h-8 xl:min-h-8"
                            onClick={() => setFilter(value)}
                          >
                            {value === "matched" ? (
                              <span
                                aria-hidden="true"
                                className="bg-flow size-2 rounded-full"
                              />
                            ) : value !== "all" ? (
                              <span
                                aria-hidden="true"
                                className="bg-warn size-2 rounded-full"
                              />
                            ) : null}
                            {label}
                            <span className="tabular-nums">{` ${count.toLocaleString("en-US")}`}</span>
                          </Button>
                        ))}
                      </div>
                      {withoutMatch > 0 ? (
                        <div
                          role="radiogroup"
                          aria-labelledby={`${id}-unmatched`}
                          className="flex flex-col gap-1"
                        >
                          <span
                            id={`${id}-unmatched`}
                            className="text-sm font-medium"
                          >
                            {`The ${counted(withoutMatch, "row", "rows")} without one match`}
                          </span>
                          {(
                            [
                              [
                                "keep",
                                `Keep them, with the ${headers[keyIndex]?.toLowerCase() ?? "key"} as unlinked text`,
                              ],
                              ["skip", "Skip them"],
                            ] as const
                          ).map(([value, label]) => (
                            <label
                              key={value}
                              className="flex min-h-11 items-center gap-2 text-sm xl:min-h-8"
                            >
                              <input
                                type="radio"
                                name={`${id}-unmatched`}
                                value={value}
                                checked={unmatched === value}
                                disabled={writing || Boolean(written)}
                                onChange={() => setUnmatched(value)}
                                className="size-4 accent-[var(--action)]"
                              />
                              {label}
                            </label>
                          ))}
                        </div>
                      ) : null}
                      <div className="max-h-72 overflow-auto rounded-md border">
                        <table
                          aria-label="Rows to add"
                          className="w-full text-sm"
                        >
                          <thead className="bg-card sticky top-0">
                            <tr className="text-muted-foreground text-left text-xs">
                              <th
                                scope="col"
                                className="border-b px-3 py-2 font-medium"
                              >
                                File row
                              </th>
                              <th
                                scope="col"
                                className="border-b px-3 py-2 font-medium"
                              >
                                {headers[keyIndex]}
                              </th>
                              <th
                                scope="col"
                                className="border-b px-3 py-2 font-medium"
                              >
                                Result
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {shown
                              .slice(0, PREVIEW_ROWS)
                              .map(({ row, result }) => (
                                <tr key={row.fileRow}>
                                  <td className="text-muted-foreground border-b px-3 py-2 tabular-nums">
                                    {row.fileRow}
                                  </td>
                                  <td className="max-w-64 truncate border-b px-3 py-2">
                                    {String(row.cells[keyIndex] ?? "")}
                                  </td>
                                  <td className="border-b px-3 py-2">
                                    <span className="inline-flex items-center gap-2">
                                      <span
                                        aria-hidden="true"
                                        className={cn(
                                          "size-2 shrink-0 rounded-full",
                                          result.state === "matched"
                                            ? "bg-flow"
                                            : "bg-warn",
                                        )}
                                      />
                                      {resultWords(result)}
                                    </span>
                                  </td>
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>
                      {shown.length > PREVIEW_ROWS ? (
                        <p className="text-muted-foreground text-xs">
                          {`Showing the first ${PREVIEW_ROWS} of ${counted(shown.length, "row", "rows")}.`}
                        </p>
                      ) : null}
                    </>
                  )}
                </div>,
              )
            : null}
        </ol>
        {table &&
        (built.problems.size > 0 ||
          overLimit ||
          doubled.length > 0 ||
          tooWide ||
          built.oversized > 0) ? (
          <div className="flex flex-col gap-1.5">
            {doubled.map(({ column, files }) => (
              <p key={column} className="text-danger-text text-sm">
                {`${files.length === 2 ? "Two" : files.length} file columns go into ${column}: ${files.join(" and ")}. Choose one.`}
              </p>
            ))}
            {tooWide ? (
              <p className="text-danger-text text-sm">
                {`A sheet holds at most 100 columns, and this file adds ${added.length}. Leave some Not added.`}
              </p>
            ) : null}
            {built.oversized > 0 ? (
              <p className="text-warn-text flex items-start gap-2 text-sm">
                <AlertTriangle
                  aria-hidden="true"
                  className="mt-0.5 size-4 shrink-0"
                />
                {built.oversized === 1
                  ? "1 row is larger than a row can be (32 KiB). It is not added."
                  : `${counted(built.oversized, "row", "rows")} are larger than a row can be (32 KiB). They are not added.`}
              </p>
            ) : null}
            {[...built.problems].map(([key, count]) => {
              const target = plan.find(
                (item) => item.target.key === key,
              )?.target;
              return target ? (
                <p
                  key={key}
                  className="text-warn-text flex items-start gap-2 text-sm"
                >
                  <AlertTriangle
                    aria-hidden="true"
                    className="mt-0.5 size-4 shrink-0"
                  />
                  {cellProblemWords(target, count)}
                </p>
              ) : null;
            })}
            {overLimit ? (
              <p className="text-danger-text text-sm">
                {`${sheetTitle} would have ${counted(existingRows + rowCount, "row", "rows")}. A sheet holds at most 10,000 rows.`}
              </p>
            ) : null}
          </div>
        ) : null}
        <DialogFrameFooter>
          {written ? (
            <Alert
              variant={written.kind === "done" ? "success" : "destructive"}
            >
              {written.kind === "lost-create"
                ? "The sheet may have been created. Check My sheets before you try again."
                : [
                    written.kind === "done"
                      ? `${counted(written.added, "row was", "rows were")} added.`
                      : `${written.added.toLocaleString("en-US")} of ${counted(written.total, "row was", "rows were")} added.`,
                    written.kind === "partial"
                      ? written.words
                      : written.kind === "unknown"
                        ? "The connection was lost, so the next rows may or may not have been added. Open the sheet to check."
                        : "",
                    emptiedWords(written.emptied),
                  ]
                    .filter(Boolean)
                    .join(" ")}
            </Alert>
          ) : progress ? (
            <p
              role="status"
              className="text-muted-foreground text-sm tabular-nums"
            >
              {`Adding rows… ${progress.done.toLocaleString("en-US")} of ${progress.total.toLocaleString("en-US")}`}
            </p>
          ) : (
            <p className="text-muted-foreground text-sm">
              Nothing is added until you confirm.
            </p>
          )}
          <DialogFooter className="mt-0">
            {written ? (
              <Button
                className="min-h-11 xl:h-8 xl:min-h-8"
                onClick={closeAfter}
              >
                {target.kind === "new" && written.kind !== "lost-create"
                  ? "Open the sheet"
                  : "Close"}
              </Button>
            ) : (
              <>
                <Button
                  type="button"
                  variant="ghost"
                  className="min-h-11 xl:h-8 xl:min-h-8"
                  disabled={writing}
                  onClick={onClose}
                >
                  Cancel
                </Button>
                <DisabledReason stable reason={writing ? null : blocked}>
                  <Button
                    type="button"
                    className="min-h-11 xl:h-8 xl:min-h-8"
                    pending={writing}
                    pendingLabel="Adding rows…"
                    onClick={() => void confirm()}
                  >
                    {primary}
                  </Button>
                </DisabledReason>
              </>
            )}
          </DialogFooter>
        </DialogFrameFooter>
      </DialogContent>
    </Dialog>
  );
}
