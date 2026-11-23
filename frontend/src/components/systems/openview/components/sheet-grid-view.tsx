"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import type { Route } from "next";
import { useQuery } from "@tanstack/react-query";
import { defaultRangeExtractor, useVirtualizer } from "@tanstack/react-virtual";
import {
  AlertTriangle,
  AlignLeft,
  Calendar,
  CheckSquare,
  Eye,
  Hash,
  Link2,
  List,
  Lock,
  Mail,
  MoreHorizontal,
  Plus,
  Sheet as SheetIcon,
  Sigma,
  Trash2,
  Type,
  UserRound,
  type LucideIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { GuardedWorkspaceLink } from "@/components/workspace-navigation-guard";
import { personCardOptions } from "@/components/profile/adapters/profile-queries";
import { cn } from "@/lib/utils";

import { authMeOptions } from "../adapters/openview-queries";
import type {
  WorksheetCell,
  WorksheetDetail,
  WorksheetRow,
  WorksheetTotal,
} from "../adapters/worksheets-api";
import {
  cellView,
  editInput,
  gridBands,
  inputValue,
  parsePastedGrid,
  rowAt,
  totalView,
  type GridColumn,
  type GridFormat,
  type RowStore,
  type SheetColumnType,
} from "../domain/sheet-grid";
import { SheetColumnPopover } from "./sheet-column-popover";
import { SheetLinkPicker } from "./sheet-link-picker";

// The sheet grid (docs/specs/sheets.md P3, P9, F4, SH-54): one tab stop,
// arrow keys between cells, Enter edits, Escape leaves, a 2px action
// outline on the focused cell. Rows are virtualized; the focused row stays
// rendered while it scrolls away.

const ROW_NUMBER_WIDTH = 56;
const PHONE_ROW_NUMBER_WIDTH = 40;
const ADD_COLUMN_WIDTH = 48;

const TYPE_ICONS: Record<SheetColumnType, LucideIcon> = {
  text: Type,
  long_text: AlignLeft,
  email: Mail,
  url: Link2,
  number: Hash,
  int: Hash,
  decimal: Hash,
  boolean: CheckSquare,
  date: Calendar,
  datetime: Calendar,
  user: UserRound,
  select: List,
  link: Link2,
  lookup: Eye,
  computed: Sigma,
  sheet_lookup: SheetIcon,
};

export type SaveOutcome = "saved" | "conflict" | "refused";

export type SheetConflict = {
  rowId: string;
  key: string;
  columnName: string;
  /** What the person typed, as they typed it. */
  draft: string;
};

/** Cells an editor changes in place (person cells name people, read-only). */
function editable(column: GridColumn) {
  return !column.readOnly && column.type !== "user";
}

/** A person's name from their card, as bylines read it. */
export function usePersonName(id: string): string {
  const identity = useQuery(authMeOptions());
  const viewer = identity.data
    ? { id: identity.data.id, role: identity.data.role ?? "guest" }
    : null;
  const card = useQuery({
    ...personCardOptions(viewer ?? { id: "", role: "member" }, id),
    enabled: Boolean(viewer),
  });
  return card.data?.data.display_name ?? "Person";
}

function PersonName({ id }: { id: string }) {
  return <span className="block truncate">{usePersonName(id)}</span>;
}

function CellContent({
  column,
  cell,
  format,
}: {
  column: GridColumn;
  cell: WorksheetCell | undefined;
  format: GridFormat;
}) {
  const view = cellView(column, cell, format);
  if (view.kind === "blank") return null;
  if (view.kind === "link")
    return column.linkModuleId ? (
      <GuardedWorkspaceLink
        tabIndex={-1}
        href={
          `/openview?section=views&module=${encodeURIComponent(column.linkModuleId)}&record=${encodeURIComponent(view.recordId)}` as Route
        }
        className="text-action-text block truncate font-medium hover:underline"
      >
        {view.label}
      </GuardedWorkspaceLink>
    ) : (
      <span className="block truncate">{view.label}</span>
    );
  if (view.kind === "state")
    return (
      <span className="text-muted-foreground inline-flex min-w-0 items-center gap-1.5 italic">
        {view.state === "no_access" ? (
          <Lock aria-hidden="true" className="size-3.5 shrink-0" />
        ) : view.state === "deleted" ? (
          <Trash2 aria-hidden="true" className="size-3.5 shrink-0" />
        ) : null}
        <span className="truncate">{view.words}</span>
      </span>
    );
  if (column.type === "user" && view.kind === "value")
    return <PersonName id={view.text} />;
  return <span className="block truncate">{view.text}</span>;
}

type Editing = {
  index: number;
  key: string;
  draft: string;
  seed: string;
  expected: WorksheetCell;
};

export type SheetGridViewProps = {
  sheet: WorksheetDetail;
  columns: readonly GridColumn[];
  store: RowStore;
  totals: Record<string, WorksheetTotal>;
  searching: boolean;
  format: GridFormat;
  phone: boolean;
  /** Owners and Edit recipients of a sheet that is not open. */
  canEdit: boolean;
  /** Route 6 needs every column; a masked one makes it impossible. */
  canChangeColumns: boolean;
  conflict: SheetConflict | null;
  onRange: (start: number, end: number) => void;
  onSave: (
    row: WorksheetRow,
    column: GridColumn,
    value: unknown,
    expected: WorksheetCell,
    draft: string,
  ) => Promise<SaveOutcome>;
  onDismissConflict: () => void;
  onAddRow: () => void;
  onDeleteRow: (row: WorksheetRow, index: number) => void;
  onOpenRow: (index: number) => void;
  onPaste: (index: number, column: number, grid: string[][]) => void;
};

export function SheetGridView({
  sheet,
  columns,
  store,
  totals,
  searching,
  format,
  phone,
  canEdit,
  canChangeColumns,
  conflict,
  onRange,
  onSave,
  onDismissConflict,
  onAddRow,
  onDeleteRow,
  onOpenRow,
  onPaste,
}: SheetGridViewProps) {
  "use no memo"; // TanStack's mutable virtualizer must be read on every range update.
  const pane = useRef<HTMLDivElement | null>(null);
  const bands = useMemo(() => gridBands(columns), [columns]);
  const [active, setActive] = useState({ row: 0, col: 0 });
  const [editing, setEditing] = useState<Editing | null>(null);
  const [picking, setPicking] = useState<{ index: number; key: string } | null>(
    null,
  );
  const [focusTick, setFocusTick] = useState(0);
  const cancelled = useRef(false);
  const saving = useRef(false);
  const rowHeight = phone ? 44 : 40;
  const numberWidth = phone ? PHONE_ROW_NUMBER_WIDTH : ROW_NUMBER_WIDTH;
  const firstWidth = phone ? 160 - PHONE_ROW_NUMBER_WIDTH : 220;
  const widthOf = (column: GridColumn, index: number) =>
    index === 0 ? firstWidth : column.numeric ? 128 : 176;
  const tableWidth =
    numberWidth +
    columns.reduce((sum, column, index) => sum + widthOf(column, index), 0) +
    (canChangeColumns ? ADD_COLUMN_WIDTH : 0);
  const count = store.total ?? 0;
  const grouped = bands.some((band) => band.label !== null);
  const headerHeight = grouped ? 68 : 36;
  const totalKeys = Object.keys(totals);
  // eslint-disable-next-line react-hooks/incompatible-library -- This component explicitly opts out above; no virtualizer method is memoized or passed to memoized children.
  const virtual = useVirtualizer({
    count,
    getScrollElement: () => pane.current,
    estimateSize: () => rowHeight,
    overscan: 12,
    // The focused row stays rendered while it scrolls out of view.
    rangeExtractor: (range) => {
      const indexes = defaultRangeExtractor(range);
      return active.row >= 0 &&
        active.row < count &&
        !indexes.includes(active.row)
        ? [...indexes, active.row].sort((a, b) => a - b)
        : indexes;
    },
  });
  const items = virtual.getVirtualItems();
  const first = items[0]?.index ?? 0;
  const last = items.at(-1)?.index ?? 0;
  useEffect(() => {
    onRange(first, last);
  }, [first, last, count, onRange]);

  // Moving focus: scroll the row into view, then focus its cell. Row -1 is
  // the header row: its column settings, then Add column.
  useEffect(() => {
    if (focusTick === 0) return;
    const selector =
      active.row < 0
        ? `[data-header="${active.col}"]`
        : `[data-cell="${active.row}:${columns[active.col]?.key ?? ""}"]`;
    if (active.row >= 0) virtual.scrollToIndex(active.row, { align: "auto" });
    const frame = window.requestAnimationFrame(() => {
      pane.current
        ?.querySelector<HTMLElement>(selector)
        ?.focus({ preventScroll: false });
    });
    return () => window.cancelAnimationFrame(frame);
    // Only a new focus request moves focus.
  }, [focusTick]);

  const focusCell = (row: number, col: number) => {
    const nextRow = Math.max(
      canChangeColumns ? -1 : 0,
      Math.min(row, Math.max(count - 1, 0)),
    );
    const lastCol =
      columns.length - 1 + (nextRow < 0 && canChangeColumns ? 1 : 0);
    setActive({ row: nextRow, col: Math.max(0, Math.min(col, lastCol)) });
    setFocusTick((value) => value + 1);
  };

  const startEdit = (index: number, col: number) => {
    const row = rowAt(store, index);
    const column = columns[col];
    if (!canEdit || !row || !column || !editable(column)) return;
    const cell = row.cells[column.key];
    if (column.type === "link") {
      setPicking({ index, key: column.key });
      return;
    }
    if (column.type === "boolean") {
      const current = cell && "value" in cell ? cell.value === true : false;
      void onSave(row, column, !current, cell ?? { value: null }, "");
      return;
    }
    const seed = editInput(column, cell, format);
    setEditing({
      index,
      key: column.key,
      draft: seed,
      seed,
      // What the person saw when the edit started (F4).
      expected: cell ?? { value: null },
    });
  };

  // Leaving an editor puts focus back on its cell at once, so the next key
  // lands there; the input's blur then commits nothing.
  const leaveEditor = (cell: HTMLElement | null) => {
    cancelled.current = true;
    cell?.focus();
    setEditing(null);
  };

  const finishEdit = async (draft: string, cell: HTMLElement | null = null) => {
    if (!editing || saving.current) return;
    const column = columns.find((item) => item.key === editing.key);
    const row = rowAt(store, editing.index);
    if (!column || !row || draft === editing.seed) {
      leaveEditor(cell);
      return;
    }
    const value =
      column.type === "datetime" && draft
        ? new Date(draft).toISOString()
        : column.type === "select"
          ? draft || null
          : inputValue(column, draft);
    saving.current = true;
    const outcome = await onSave(row, column, value, editing.expected, draft);
    saving.current = false;
    if (outcome === "refused") return;
    leaveEditor(cell);
  };

  const onGridKey = (event: KeyboardEvent<HTMLTableElement>) => {
    // Keys from popovers and dialogs reach here through their portals.
    if (
      editing ||
      picking ||
      !(event.target instanceof Node) ||
      !event.currentTarget.contains(event.target)
    )
      return;
    const moves: Record<string, [number, number]> = {
      ArrowUp: [-1, 0],
      ArrowDown: [1, 0],
      ArrowLeft: [0, -1],
      ArrowRight: [0, 1],
    };
    const move = moves[event.key];
    if (move) {
      event.preventDefault();
      focusCell(active.row + move[0], active.col + move[1]);
    } else if (
      (event.key === "Enter" || event.key === "F2") &&
      active.row >= 0
    ) {
      event.preventDefault();
      startEdit(active.row, active.col);
    }
  };

  const pinned = "sticky z-10 bg-card";
  const spacer = (height: number, key: string) => (
    <tr key={key} aria-hidden="true" role="presentation">
      <td
        colSpan={columns.length + 2}
        style={{ height, padding: 0, border: 0 }}
      />
    </tr>
  );
  const rows: ReactNode[] = [];
  let edge = 0;
  for (const item of items) {
    if (item.start > edge)
      rows.push(spacer(item.start - edge, `gap-${item.index}`));
    edge = item.end;
    const row = rowAt(store, item.index);
    const note = conflict && row && conflict.rowId === row.id;
    rows.push(
      <tr
        key={row?.id ?? `pending-${item.index}`}
        role="row"
        aria-rowindex={item.index + 2}
        style={{ height: rowHeight }}
        className={cn(
          "hover:bg-tint-hover group",
          note && "bg-warn-tint hover:bg-warn-tint",
        )}
      >
        <td
          role="gridcell"
          className={cn(
            pinned,
            "text-muted-foreground group-hover:bg-tint-hover left-0 border-b px-1 text-right text-xs tabular-nums",
            note && "bg-warn-tint",
          )}
        >
          <span className="inline-flex items-center gap-0.5">
            {canEdit && row && !phone ? (
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <Button
                      variant="ghost"
                      size="icon"
                      tabIndex={-1}
                      aria-label={`Row ${item.index + 1} actions`}
                      className="size-6 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 data-popup-open:opacity-100"
                    />
                  }
                >
                  <MoreHorizontal aria-hidden="true" />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  <DropdownMenuItem
                    variant="destructive"
                    onClick={() => onDeleteRow(row, item.index)}
                  >
                    <Trash2 aria-hidden="true" />
                    Delete row
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : null}
            {item.index + 1}
          </span>
        </td>
        {columns.map((column, index) => {
          // The header row takes the tab stop only while it holds focus.
          const isActive =
            (active.row === item.index ||
              (active.row < 0 && item.index === 0)) &&
            active.col === index;
          const isEditing =
            editing?.index === item.index && editing.key === column.key;
          const fixed = !canEdit || !editable(column);
          return (
            <td
              key={column.key}
              role="gridcell"
              data-cell={`${item.index}:${column.key}`}
              tabIndex={isActive ? 0 : -1}
              aria-readonly={fixed || undefined}
              onFocus={() => {
                if (!isActive) setActive({ row: item.index, col: index });
              }}
              onClick={() => {
                if (phone && row) onOpenRow(item.index);
              }}
              onDoubleClick={() => {
                if (!phone) startEdit(item.index, index);
              }}
              className={cn(
                "focus-visible:outline-action-text relative min-w-0 border-b border-l px-3 outline-offset-[-2px] focus:outline-2 focus:outline-solid",
                index === 0 && pinned,
                index === 0 && "group-hover:bg-tint-hover",
                column.readOnly && "bg-muted/40",
                column.numeric && "text-right tabular-nums",
                isActive && "outline-action-text",
              )}
              style={index === 0 ? { left: numberWidth } : undefined}
            >
              {isEditing && editing ? (
                column.type === "select" ? (
                  <select
                    autoFocus
                    aria-label={`${column.name}, row ${item.index + 1}`}
                    className="border-action-text bg-background absolute inset-0 h-full w-full border-2 px-2 text-sm outline-none"
                    defaultValue={editing.draft}
                    onChange={(event) =>
                      void finishEdit(
                        event.target.value,
                        event.currentTarget.closest("td"),
                      )
                    }
                    onKeyDown={(event) => {
                      if (event.key === "Escape") {
                        event.stopPropagation();
                        leaveEditor(event.currentTarget.closest("td"));
                      }
                    }}
                  >
                    <option value="">None</option>
                    {Object.entries(column.options ?? {}).map(([id, label]) => (
                      <option key={id} value={id}>
                        {label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    autoFocus
                    aria-label={`${column.name}, row ${item.index + 1}`}
                    type={
                      column.type === "date"
                        ? "date"
                        : column.type === "datetime"
                          ? "datetime-local"
                          : "text"
                    }
                    inputMode={column.numeric ? "decimal" : undefined}
                    className="border-action-text bg-background absolute inset-0 h-full w-full border-2 px-3 text-sm outline-none"
                    value={editing.draft}
                    onChange={(event) =>
                      setEditing({ ...editing, draft: event.target.value })
                    }
                    onKeyDown={(event) => {
                      const cell = event.currentTarget.closest("td");
                      if (event.key === "Enter") {
                        event.preventDefault();
                        event.stopPropagation();
                        void finishEdit(editing.draft, cell);
                      } else if (event.key === "Escape") {
                        event.preventDefault();
                        event.stopPropagation();
                        leaveEditor(cell);
                      }
                    }}
                    onBlur={() => {
                      if (cancelled.current) {
                        cancelled.current = false;
                        return;
                      }
                      void finishEdit(editing.draft);
                    }}
                  />
                )
              ) : row ? (
                <CellContent
                  column={column}
                  cell={row.cells[column.key]}
                  format={format}
                />
              ) : (
                <Skeleton className="h-3 w-3/4" />
              )}
            </td>
          );
        })}
        {canChangeColumns ? (
          <td role="presentation" className="border-b" />
        ) : null}
      </tr>,
    );
    if (note && conflict)
      rows.push(
        <tr key={`conflict-${conflict.rowId}`} role="presentation">
          <td
            role="presentation"
            colSpan={columns.length + 2}
            className="bg-warn-tint border-warn-rule border-b px-3 py-2"
          >
            <div
              role="status"
              className="sticky left-3 flex max-w-[min(56rem,calc(100vw-4rem))] flex-wrap items-center gap-x-3 gap-y-2 text-sm"
            >
              <AlertTriangle
                aria-hidden="true"
                className="text-warn-text size-4 shrink-0"
              />
              <span className="min-w-0 flex-1">
                <b>Someone changed this row while you were editing it.</b> It
                now shows the newer values. Your {conflict.columnName} (
                {conflict.draft}) was not saved.
              </span>
              <Button
                variant="outline"
                className="min-h-11 xl:h-8 xl:min-h-8"
                onClick={() => requestEditAgain(conflict)}
              >
                Edit {conflict.columnName} again
              </Button>
              <Button
                variant="ghost"
                className="min-h-11 xl:h-8 xl:min-h-8"
                onClick={onDismissConflict}
              >
                Dismiss
              </Button>
            </div>
          </td>
        </tr>,
      );
  }
  if (edge < virtual.getTotalSize())
    rows.push(spacer(virtual.getTotalSize() - edge, "tail"));

  function requestEditAgain(entry: SheetConflict) {
    const index = (() => {
      for (const [offset, list] of Object.entries(store.pages)) {
        const at = list.findIndex((row) => row.id === entry.rowId);
        if (at >= 0) return Number(offset) + at;
      }
      return -1;
    })();
    const col = columns.findIndex((column) => column.key === entry.key);
    const row = index >= 0 ? rowAt(store, index) : undefined;
    const column = columns[col];
    if (!row || !column) return;
    onDismissConflict();
    setActive({ row: index, col });
    setEditing({
      index,
      key: column.key,
      draft: entry.draft,
      seed: editInput(column, row.cells[column.key], format),
      expected: row.cells[column.key] ?? { value: null },
    });
  }

  const pickingColumn = picking
    ? columns.find((column) => column.key === picking.key)
    : undefined;
  const pickingRow = picking ? rowAt(store, picking.index) : undefined;
  return (
    <div
      ref={pane}
      role="region"
      aria-label={`${sheet.title} rows`}
      className="bg-card relative min-h-0 flex-1 overflow-auto rounded-md border"
      style={{
        scrollPaddingTop: headerHeight,
        scrollPaddingBottom: totalKeys.length > 0 ? 48 : 0,
        scrollPaddingLeft: numberWidth + firstWidth,
      }}
    >
      <table
        role="grid"
        aria-label={sheet.title}
        aria-rowcount={count + 1}
        aria-readonly={!canEdit || undefined}
        onKeyDown={onGridKey}
        onPaste={(event) => {
          if (!canEdit || editing) return;
          const text = event.clipboardData.getData("text/plain");
          if (!text) return;
          event.preventDefault();
          onPaste(active.row, active.col, parsePastedGrid(text));
        }}
        className="table-fixed border-separate border-spacing-0 text-sm"
        style={{ width: tableWidth }}
      >
        <colgroup>
          <col style={{ width: numberWidth }} />
          {columns.map((column, index) => (
            <col key={column.key} style={{ width: widthOf(column, index) }} />
          ))}
          {canChangeColumns ? (
            <col style={{ width: ADD_COLUMN_WIDTH }} />
          ) : null}
        </colgroup>
        <thead className="bg-card sticky top-0 z-20">
          {grouped ? (
            <tr role="row">
              <th
                aria-hidden="true"
                role="presentation"
                className={cn(pinned, "left-0 h-8 border-b")}
              />
              {bands.map((band, index) => (
                <th
                  key={`${band.label ?? "none"}-${index}`}
                  colSpan={band.span}
                  role="presentation"
                  className="text-muted-foreground h-8 border-b border-l px-3 text-left text-xs font-semibold"
                >
                  {band.label}
                </th>
              ))}
              {canChangeColumns ? (
                <th role="presentation" className="border-b" />
              ) : null}
            </tr>
          ) : null}
          <tr role="row">
            <th
              role="columnheader"
              scope="col"
              className={cn(pinned, "left-0 h-9 border-b px-2 text-right")}
            >
              <span className="sr-only">Row</span>
            </th>
            {columns.map((column, index) => {
              const Icon = TYPE_ICONS[column.type];
              const label = (
                <span
                  className={cn(
                    "flex min-w-0 items-center gap-1.5",
                    column.numeric && "justify-end",
                  )}
                >
                  <Icon aria-hidden="true" className="size-3.5 shrink-0" />
                  <span className="truncate">{column.name}</span>
                  {column.readOnly ? (
                    <span className="sr-only">, read-only</span>
                  ) : null}
                </span>
              );
              const stored = sheet.structure.columns.find(
                (item) => item.key === column.key,
              );
              return (
                <th
                  key={column.key}
                  role="columnheader"
                  scope="col"
                  className={cn(
                    "text-muted-foreground h-9 border-b border-l px-3 text-left text-xs font-medium",
                    index === 0 && pinned,
                    column.numeric && "text-right",
                  )}
                  style={index === 0 ? { left: numberWidth } : undefined}
                >
                  {canChangeColumns && stored && !("state" in stored) ? (
                    <SheetColumnPopover
                      sheet={sheet}
                      column={stored}
                      trigger={
                        <button
                          type="button"
                          data-header={index}
                          tabIndex={-1}
                          onFocus={() => setActive({ row: -1, col: index })}
                          aria-label={`${column.name}, column settings`}
                          className="hover:text-foreground focus-visible:outline-ring w-full rounded-sm text-inherit outline-offset-2 focus-visible:outline-2"
                        />
                      }
                    >
                      {label}
                    </SheetColumnPopover>
                  ) : (
                    label
                  )}
                </th>
              );
            })}
            {canChangeColumns ? (
              <th role="presentation" className="h-9 border-b border-l px-1">
                <SheetColumnPopover
                  sheet={sheet}
                  column={null}
                  trigger={
                    <Button
                      variant="ghost"
                      size="icon"
                      data-header={columns.length}
                      tabIndex={-1}
                      onFocus={() =>
                        setActive({ row: -1, col: columns.length })
                      }
                      aria-label="Add column"
                      className="size-8"
                    />
                  }
                >
                  <Plus aria-hidden="true" />
                </SheetColumnPopover>
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {rows}
          {canEdit ? (
            <tr role="row">
              <td
                role="gridcell"
                colSpan={columns.length + 1 + (canChangeColumns ? 1 : 0)}
                className="border-b px-1 py-1"
              >
                <Button
                  variant="ghost"
                  className="sticky left-1 min-h-11 xl:h-8 xl:min-h-8"
                  onClick={onAddRow}
                >
                  <Plus aria-hidden="true" />
                  Add row
                </Button>
              </td>
            </tr>
          ) : null}
        </tbody>
        {totalKeys.length > 0 ? (
          <tfoot className="bg-card sticky bottom-0 z-20">
            <tr role="row">
              <td role="gridcell" className={cn(pinned, "left-0 border-t")} />
              {columns.map((column, index) => {
                const total = totals[column.key];
                const view = total
                  ? totalView(
                      column,
                      total,
                      {
                        first: column.key === totalKeys[0],
                        searching,
                        allRows: sheet.liveRowCount,
                      },
                      format,
                    )
                  : null;
                return (
                  <td
                    key={column.key}
                    role="gridcell"
                    className={cn(
                      "h-12 border-t border-l px-3 align-middle",
                      index === 0 && pinned,
                      column.numeric && "text-right",
                    )}
                    style={index === 0 ? { left: numberWidth } : undefined}
                  >
                    {view ? (
                      <span className="flex flex-col leading-tight">
                        <span className="text-muted-foreground text-xs">
                          {view.label}
                        </span>
                        <span className="font-semibold tabular-nums">
                          {view.text}
                        </span>
                      </span>
                    ) : null}
                  </td>
                );
              })}
              {canChangeColumns ? (
                <td role="presentation" className="border-t" />
              ) : null}
            </tr>
          </tfoot>
        ) : null}
      </table>
      {picking && pickingColumn?.linkModuleId && pickingRow ? (
        <SheetLinkPicker
          columnName={pickingColumn.name}
          moduleId={pickingColumn.linkModuleId}
          hasLink={Boolean(
            pickingRow.cells[pickingColumn.key] &&
            "link" in (pickingRow.cells[pickingColumn.key] ?? {}),
          )}
          onClose={() => {
            const col = columns.findIndex((c) => c.key === pickingColumn.key);
            setPicking(null);
            focusCell(picking.index, col);
          }}
          onPick={(recordId) => {
            const col = columns.findIndex((c) => c.key === pickingColumn.key);
            const index = picking.index;
            setPicking(null);
            void onSave(
              pickingRow,
              pickingColumn,
              recordId ? { record_id: recordId } : null,
              pickingRow.cells[pickingColumn.key] ?? { value: null },
              "",
            ).then(() => focusCell(index, col));
          }}
        />
      ) : null}
    </div>
  );
}
