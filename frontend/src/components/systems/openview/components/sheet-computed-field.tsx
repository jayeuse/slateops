"use client";

import { useId, useRef, type ReactNode } from "react";
import { useQueries } from "@tanstack/react-query";
import { AlertCircle } from "lucide-react";

import { cn } from "@/lib/utils";

import { fieldsFirstPageOptions } from "../adapters/openview-queries";
import { worksheetDetailOptions } from "../adapters/worksheet-queries";
import type {
  WorksheetCell,
  WorksheetDetail,
} from "../adapters/worksheets-api";
import {
  EXPRESSION_FUNCTIONS,
  cellOperand,
  checkExpression,
  decimalMarkOf,
  editorExpression,
  evaluateExpression,
  type ExpressionColumn,
} from "../domain/sheet-expression";

// A computed column's expression (docs/specs/sheets.md K3 to K5, Screens 2):
// code type, buttons that insert a numeric column's name or a function, and
// the result for row 1 as a preview. The server checks and computes again;
// its refusal shows here with the name it is about marked. Loaded on first
// use of Computed.

export type SheetPreviewRow = {
  label: string;
  cells: Record<string, WorksheetCell>;
};

const NUMERIC_TYPES: ReadonlySet<string> = new Set([
  "number",
  "decimal",
  "int",
  "computed",
]);
// Source types whose numbers the source's structure does not settle.
const UNDECIDED_SOURCE: ReadonlySet<string> = new Set([
  "lookup",
  "sheet_lookup",
]);
const ERROR_WORDS: Record<string, string> = {
  division_by_zero: "Division by zero",
  overflow: "Number too large",
};

/**
 * Which columns hold numbers: number types and computed columns; a lookup
 * when its field does, a From another sheet column when its source column
 * does. Whatever the editor cannot decide (a read not answered yet, a source
 * that is itself a lookup or from another sheet, a source the person cannot
 * see) counts as numbers, and the server decides.
 */
function useExpressionColumns(sheet: WorksheetDetail): ExpressionColumn[] {
  const columns = sheet.structure.columns;
  const links = new Map(
    columns.flatMap((column) =>
      column.type === "link"
        ? [[column.key, column.link.moduleId] as const]
        : [],
    ),
  );
  const modules = [
    ...new Set(
      columns.flatMap((column) =>
        column.type === "lookup" && links.has(column.lookup.linkKey)
          ? [links.get(column.lookup.linkKey) ?? ""]
          : [],
      ),
    ),
  ];
  const sources = [
    ...new Set(
      columns.flatMap((column) =>
        "sheet_lookup" in column ? [column.sheet_lookup.sourceWorksheetId] : [],
      ),
    ),
  ];
  const fields = useQueries({
    queries: modules.map((moduleId) => fieldsFirstPageOptions(moduleId)),
  });
  const sheets = useQueries({
    queries: sources.map((id) => worksheetDetailOptions(id)),
  });
  const fieldType = new Map(
    fields.flatMap((query) =>
      (query.data?.items ?? []).map((field) => [field.id, field.type] as const),
    ),
  );
  const sourceType = new Map(
    sheets.flatMap((query, index) =>
      (query.data?.structure.columns ?? []).map(
        (column) => [`${sources[index]}:${column.key}`, column.type] as const,
      ),
    ),
  );
  return columns.flatMap((column): ExpressionColumn[] => {
    if (column.type === "lookup") {
      const type = fieldType.get(column.lookup.fieldId);
      return [
        {
          key: column.key,
          name: column.name,
          numeric: type === undefined || NUMERIC_TYPES.has(type),
        },
      ];
    }
    if (column.type === "sheet_lookup") {
      // A hidden source still has a name a computed column can read (K9).
      if (!("sheet_lookup" in column))
        return [{ key: column.key, name: column.name, numeric: true }];
      const type = sourceType.get(
        `${column.sheet_lookup.sourceWorksheetId}:${column.sheet_lookup.sourceColumnKey}`,
      );
      return [
        {
          key: column.key,
          name: column.name,
          numeric:
            type === undefined ||
            UNDECIDED_SOURCE.has(type) ||
            NUMERIC_TYPES.has(type),
        },
      ];
    }
    return [
      {
        key: column.key,
        name: column.name,
        numeric: NUMERIC_TYPES.has(column.type),
      },
    ];
  });
}

/** The typed text with the named columns marked, for the layer under it. */
function marked(text: string, names: readonly string[]): ReactNode[] {
  if (names.length === 0) return [text, "\n"];
  const wanted = new Set(names.map((name) => name.trim().toLowerCase()));
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(/\{([^}]*)\}/g)) {
    if (!wanted.has(match[1].trim().toLowerCase())) continue;
    const start = match.index ?? 0;
    parts.push(text.slice(last, start));
    parts.push(
      <mark
        key={start}
        className="bg-danger-tint text-danger-text rounded-[2px]"
      >
        {match[0]}
      </mark>,
    );
    last = start + match[0].length;
  }
  parts.push(text.slice(last), "\n");
  return parts;
}

export default function SheetComputedField({
  sheet,
  self,
  stored,
  value,
  onChange,
  places,
  locale,
  preview,
  refusal,
}: {
  sheet: WorksheetDetail;
  /** The key of the column being edited or added. */
  self: string;
  /** The stored expression of the column being edited, if any. */
  stored: string | null;
  /** The typed text; null shows the stored expression unchanged. */
  value: string | null;
  onChange: (text: string, ok: boolean) => void;
  places: number | null;
  locale: string;
  preview: SheetPreviewRow | null;
  /** A refusal of the last save that is about this expression. */
  refusal: { words: string; reason: string } | null;
}) {
  const id = useId();
  const area = useRef<HTMLTextAreaElement | null>(null);
  const columns = useExpressionColumns(sheet);
  const mark = decimalMarkOf(locale);
  const text = value ?? (stored ? editorExpression(stored, columns, mark) : "");
  const check = checkExpression(text, columns, mark, self);
  const insertable = columns.filter(
    (column) => column.numeric && column.key !== self,
  );
  // While the person types, a problem shows at once; an empty field waits.
  // An untouched stored expression passed the server's check: no alarm.
  const problem = value !== null && !check.ok && text.trim() ? check : null;
  // A server refusal marks each typed name that its words name.
  const said = refusal?.words.toLowerCase() ?? "";
  const serverNames =
    refusal && !problem
      ? [...text.matchAll(/\{([^}]*)\}/g)]
          .map((match) => match[1])
          .filter(
            (name) => name.trim() && said.includes(name.trim().toLowerCase()),
          )
      : [];
  const names = problem?.names ?? serverNames;

  const change = (next: string) =>
    onChange(next, checkExpression(next, columns, mark, self).ok);

  const insert = (snippet: string, call: boolean) => {
    const field = area.current;
    const start = field?.selectionStart ?? text.length;
    const end = field?.selectionEnd ?? text.length;
    const chosen = text.slice(start, end);
    const piece = call ? `${snippet}(${chosen})` : snippet;
    const next = text.slice(0, start) + piece + text.slice(end);
    change(next);
    // Inside a function's brackets, or after a name.
    const caret = call
      ? start + snippet.length + 1 + chosen.length
      : start + piece.length;
    requestAnimationFrame(() => {
      area.current?.focus();
      area.current?.setSelectionRange(caret, caret);
    });
  };

  let line: ReactNode = null;
  if (problem)
    line = (
      <span className="text-danger-text flex items-start gap-1.5">
        <AlertCircle aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
        <span>{problem.words}</span>
      </span>
    );
  else if (check.ok && preview) {
    const result = evaluateExpression(check.node, (key) =>
      cellOperand(preview.cells[key]),
    );
    const shown =
      result.kind === "number"
        ? new Intl.NumberFormat(locale, {
            minimumFractionDigits: places ?? 0,
            maximumFractionDigits: places ?? 2,
          }).format(result.value)
        : result.kind === "blank"
          ? "blank"
          : result.kind === "no_access"
            ? "No access"
            : (ERROR_WORDS[result.error] ?? "Cannot be calculated");
    line = (
      <span className="text-muted-foreground tabular-nums">
        Row 1, {preview.label}: {shown}
      </span>
    );
  } else if (check.ok)
    line = (
      <span className="text-muted-foreground">
        The result for row 1 shows here once the sheet has a row.
      </span>
    );

  const button =
    "bg-muted hover:bg-accent focus-visible:outline-ring min-h-11 rounded-sm px-3 text-xs outline-offset-1 focus-visible:outline-2 xl:min-h-6 xl:px-2";
  const shared =
    "font-mono col-start-1 row-start-1 w-full min-h-16 rounded-[var(--radius)] border px-3 py-2 text-base break-words whitespace-pre-wrap md:text-sm";
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={`${id}-expression`} className="text-xs font-medium">
        Expression
      </label>
      <div className="grid">
        <div
          aria-hidden="true"
          className={cn(shared, "border-transparent text-transparent")}
        >
          {marked(text, names)}
        </div>
        <textarea
          ref={area}
          id={`${id}-expression`}
          spellCheck={false}
          autoComplete="off"
          maxLength={1000}
          rows={3}
          value={text}
          placeholder="{Quiz 1} + {Quiz 2}"
          aria-invalid={problem || refusal ? true : undefined}
          aria-describedby={
            refusal && !problem ? `${id}-result ${id}-refusal` : `${id}-result`
          }
          onChange={(event) => change(event.target.value)}
          className={cn(
            shared,
            "border-input placeholder:text-muted-foreground focus-visible:border-primary focus-visible:outline-ring aria-invalid:border-destructive relative resize-none bg-transparent text-[color:var(--data-ink)] focus-visible:outline-2 focus-visible:outline-offset-1",
          )}
        />
      </div>
      <p id={`${id}-result`} aria-live="polite" className="text-xs">
        {line}
      </p>
      {refusal && !problem ? (
        <p
          id={`${id}-refusal`}
          role="alert"
          className="text-danger-text flex items-start gap-1.5 text-xs"
        >
          <AlertCircle
            aria-hidden="true"
            className="mt-0.5 size-3.5 shrink-0"
          />
          <span>{refusal.words}</span>
        </p>
      ) : null}
      {insertable.length > 0 ? (
        <div
          role="group"
          aria-label="Insert a column"
          className="flex flex-wrap gap-1"
        >
          {insertable.map((column) => (
            <button
              key={column.key}
              type="button"
              className={button}
              onClick={() => insert(`{${column.name}}`, false)}
            >
              {`{${column.name}}`}
            </button>
          ))}
        </div>
      ) : null}
      <div
        role="group"
        aria-label="Insert a function"
        className="flex flex-wrap gap-1"
      >
        {EXPRESSION_FUNCTIONS.map((name) => (
          <button
            key={name}
            type="button"
            className={cn(button, "font-mono")}
            onClick={() => insert(name, true)}
          >
            {name}
          </button>
        ))}
      </div>
    </div>
  );
}
