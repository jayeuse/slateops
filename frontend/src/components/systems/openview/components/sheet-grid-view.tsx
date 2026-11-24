"use client";

import {
  lazy,
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import type { Route } from "next";
import { useRouter } from "next/navigation";
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
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  GuardedWorkspaceLink,
  useWorkspaceNavigationRequest,
} from "@/components/workspace-navigation-guard";
import { personCardOptions } from "@/components/profile/adapters/profile-queries";
import { cn } from "@/lib/utils";

import { authMeOptions } from "../adapters/openview-queries";
import {
  editableColumn,
  type WorksheetCell,
  type WorksheetDetail,
  type WorksheetRow,
  type WorksheetTotal,
} from "../adapters/worksheets-api";
import {
  cellView,
  conflictWords,
  datetimeValue,
  editInput,
  gridBands,
  inputValue,
  parsePastedGrid,
  rowAt,
  rowIndex,
  totalView,
  type GridColumn,
  type GridFormat,
  type RowStore,
  type SheetColumnType,
} from "../domain/sheet-grid";
import { SheetColumnPopover } from "./sheet-column-popover";
import type { SheetPreviewRow } from "./sheet-computed-field";
// The pickers load on first use, apart from the grid.
const SheetLinkPicker = lazy(() =>
  import("./sheet-link-picker").then((module) => ({
    default: module.SheetLinkPicker,
  })),
);
const SheetPersonPicker = lazy(() => import("./sheet-person-picker"));

// The sheet grid (docs/specs/sheets.md P3, P9, F4, SH-54): one tab stop,
// arrow keys between cells, Enter edits, Escape leaves, a 2px action
// outline on the focused cell. Rows are virtualized; the focused row stays
// rendered while it scrolls away.

// The selected tint laid over each cell of a lit row, so the pinned cells'
// card fill and a read-only column's muted fill keep showing under it.
const LIT_ROW =
  "bg-[image:linear-gradient(color-mix(in_oklab,var(--ink)_var(--tint-selected),transparent),color-mix(in_oklab,var(--ink)_var(--tint-selected),transparent))]";

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

export type SaveOutcome = "saved" | "conflict" | "refused" | "gone";

export type SheetConflict = {
  rowId: string;
  key: string;
  columnName: string;
  /** What the person typed, as they typed it. */
  draft: string;
  /** Who changed the cell, when the editor can see them. */
  changedBy: string | null;
};

/** Cells an editor changes: every column but lookups and computed ones. */
function editable(column: GridColumn) {
  return !column.readOnly;
}

/** A linked record's address on its module page. */
export function recordHref(moduleId: string, recordId: string): Route {
  return `/openview?section=views&module=${encodeURIComponent(moduleId)}&record=${encodeURIComponent(recordId)}` as Route;
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
  phone,
}: {
  column: GridColumn;
  cell: WorksheetCell | undefined;
  format: GridFormat;
  /** On a phone a tap opens the row form, which links the record. */
  phone: boolean;
}) {
  const view = cellView(column, cell, format);
  if (view.kind === "blank") return null;
  if (view.kind === "link")
    return column.linkModuleId && !phone ? (
      <GuardedWorkspaceLink
        tabIndex={-1}
        href={recordHref(column.linkModuleId, view.recordId)}
        className="text-action-text block truncate font-medium hover:underline"
      >
        {view.label}
      </GuardedWorkspaceLink>
    ) : (
      <span className="text-action-text block truncate font-medium">
        {view.label}
      </span>
    );
  if (view.kind === "state")
    return (
      <span
        className={cn(
          // A block flex fills the cell, so long words truncate inside it.
          "text-muted-foreground flex max-w-full min-w-0 items-center gap-1.5 pr-px italic",
          column.numeric && "justify-end",
        )}
      >
        {view.state === "no_access" ? (
          <Lock aria-hidden="true" className="size-3.5 shrink-0" />
        ) : view.state === "deleted" ? (
          <Trash2 aria-hidden="true" className="size-3.5 shrink-0" />
        ) : null}
        {/* Room for the italic's last glyph at the clip edge. */}
        <span className="truncate pr-0.5">{view.words}</span>
      </span>
    );
  if (view.kind === "error")
    return (
      <span
        className={cn(
          "text-warn-text flex max-w-full min-w-0 items-center gap-1.5",
          column.numeric && "justify-end",
        )}
      >
        <AlertTriangle aria-hidden="true" className="size-3.5 shrink-0" />
        <span className="truncate" title={view.words}>
          {view.words}
        </span>
      </span>
    );
  if (column.type === "user" && view.kind === "value")
    return <PersonName id={view.text} />;
  // A From another sheet column's type is not in the structure: each cell
  // that holds a number lines up as one (Product Designer, F6).
  const numberFromSheet =
    column.type === "sheet_lookup" &&
    cell !== undefined &&
    "value" in cell &&
    (typeof cell.value === "number" ||
      (typeof cell.value === "string" && /^-?\d+(\.\d+)?$/.test(cell.value)));
  return (
    <span
      className={cn(
        "block truncate",
        numberFromSheet && "text-right tabular-nums",
      )}
    >
      {view.text}
    </span>
  );
}

// An edit and a picker follow their row by id, holding the row as it was
// when they started: a refresh may move rows meanwhile (review B1).
type Editing = {
  row: WorksheetRow;
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
  /** Owners and Edit recipients change columns (route 6). */
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
  /** A row an address named (Appears in): shown, focused and lit once. */
  highlight?: { index: number } | null;
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
  highlight = null,
}: SheetGridViewProps) {
  "use no memo"; // TanStack's mutable virtualizer must be read on every range update.
  const pane = useRef<HTMLDivElement | null>(null);
  // The pinned first column has its own band cell; the bands run from the
  // second column, under which they scroll (Product Designer F6-B1).
  const bands = useMemo(() => gridBands(columns.slice(1)), [columns]);
  const [active, setActive] = useState({ row: 0, col: 0 });
  const [editing, setEditing] = useState<Editing | null>(null);
  // A row that a loaded list no longer holds (deleted meanwhile) ends its
  // edit, so the grid's keys work again.
  if (editing && store.total !== null && rowIndex(store, editing.row.id) < 0)
    setEditing(null);
  const [picking, setPicking] = useState<{
    row: WorksheetRow;
    key: string;
    kind: "link" | "person";
  } | null>(null);
  const router = useRouter();
  const requestNavigation = useWorkspaceNavigationRequest();
  const [focusTick, setFocusTick] = useState(0);
  const cancelled = useRef(false);
  // The row an address named: lit for about two seconds; only it changes.
  const [lit, setLit] = useState<number | null>(null);
  const reveal = useRef<number | null>(null);
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
  const grouped =
    Boolean(columns[0]?.group) || bands.some((band) => band.label !== null);
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

  // Row 1 as the grid shows it, for a computed column's preview.
  const previewRow = (): SheetPreviewRow | null => {
    const row = rowAt(store, 0);
    const first = columns[0];
    if (!row || !first) return null;
    const view = cellView(first, row.cells[first.key], format);
    const label =
      view.kind === "value" || view.kind === "unlinked"
        ? view.text
        : view.kind === "link"
          ? view.label
          : view.kind === "blank"
            ? "blank"
            : view.words;
    return { label, cells: row.cells };
  };
  // A deleted column's header leaves: focus moves to the header after it,
  // or to the last one, so it never lands on nothing.
  const afterColumnDeleted = (index: number) => {
    setActive({
      row: -1,
      col: Math.max(0, Math.min(index, columns.length - 1)),
    });
    setFocusTick((tick) => tick + 1);
  };

  // Moving focus: scroll the row into view, then focus its cell. Row -1 is
  // the header row: its column settings, then Add column.
  useEffect(() => {
    if (focusTick === 0) return;
    const selector =
      active.row < 0
        ? `[data-header="${active.col}"]`
        : active.col < 0
          ? `[data-row-actions="${active.row}"]`
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

  // A named row comes to the middle of the pane; its first cell takes focus
  // once the virtualizer has drawn it (a far row is not drawn yet).
  useEffect(() => {
    if (!highlight) return;
    reveal.current = highlight.index;
    setActive({ row: highlight.index, col: 0 });
    virtual.scrollToIndex(highlight.index, { align: "center" });
    setLit(highlight.index);
    const timer = window.setTimeout(() => setLit(null), 2_000);
    return () => window.clearTimeout(timer);
    // Only a new request lights a row.
  }, [highlight]);
  useEffect(() => {
    if (reveal.current === null) return;
    const cell = pane.current?.querySelector<HTMLElement>(
      `[data-cell="${reveal.current}:${columns[0]?.key ?? ""}"]`,
    );
    if (!cell) return;
    reveal.current = null;
    cell.focus({ preventScroll: true });
  });

  const focusCell = (row: number, col: number) => {
    const nextRow = Math.max(
      canChangeColumns ? -1 : 0,
      Math.min(row, Math.max(count - 1, 0)),
    );
    const lastCol =
      columns.length - 1 + (nextRow < 0 && canChangeColumns ? 1 : 0);
    // Left of the first cell, an editor reaches the row's actions.
    const firstCol = nextRow >= 0 && canEdit && !phone ? -1 : 0;
    setActive({
      row: nextRow,
      col: Math.max(firstCol, Math.min(col, lastCol)),
    });
    setFocusTick((value) => value + 1);
  };

  const startEdit = (index: number, col: number) => {
    const row = rowAt(store, index);
    const column = columns[col];
    if (!canEdit || !row || !column || !editable(column)) return;
    // A new edit commits on its own blur, whatever the last one did.
    cancelled.current = false;
    const cell = row.cells[column.key];
    if (column.type === "link" || column.type === "user") {
      setPicking({
        row,
        key: column.key,
        kind: column.type === "link" ? "link" : "person",
      });
      return;
    }
    if (column.type === "boolean") {
      const current = cell && "value" in cell ? cell.value === true : false;
      void onSave(row, column, !current, cell ?? { value: null }, "");
      return;
    }
    const seed = editInput(column, cell, format);
    setEditing({
      row,
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
    const row = editing.row;
    if (!column || draft === editing.seed) {
      leaveEditor(cell);
      return;
    }
    const value =
      column.type === "datetime"
        ? datetimeValue(draft, format.timezone)
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
      active.row >= 0 &&
      active.col >= 0
    ) {
      event.preventDefault();
      if (canEdit) startEdit(active.row, active.col);
      else if (event.key === "Enter") openLinkedRecord(active.row, active.col);
    }
  };

  /** A reader opens the record a link cell names (Enter). */
  function openLinkedRecord(index: number, col: number) {
    const column = columns[col];
    const cell = column ? rowAt(store, index)?.cells[column.key] : undefined;
    if (!column?.linkModuleId || !cell || !("link" in cell)) return;
    const href = recordHref(column.linkModuleId, cell.link.record_id);
    const go = () => router.push(href);
    if (requestNavigation(href, go)) go();
  }

  const pinned = "sticky z-10 bg-card";
  const headerRows = grouped ? 2 : 1;
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
    const shine = lit === item.index;
    rows.push(
      <tr
        key={row?.id ?? `pending-${item.index}`}
        role="row"
        aria-rowindex={headerRows + item.index + 1}
        data-highlighted={shine || undefined}
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
            "text-muted-foreground left-0 border-b px-1 text-right text-xs tabular-nums",
            // A conflict row keeps its warn tint, as its other cells do.
            note ? "bg-warn-tint" : "group-hover:over-tint-hover",
            shine && LIT_ROW,
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
                      data-row-actions={item.index}
                      tabIndex={
                        active.row === item.index && active.col === -1 ? 0 : -1
                      }
                      onFocus={() => setActive({ row: item.index, col: -1 })}
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
            row !== undefined &&
            editing?.row.id === row.id &&
            editing.key === column.key;
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
              // On a phone a tap opens the row, the name included: the
              // link does not navigate (Screens 9).
              onClickCapture={(event) => {
                if (!phone || !row) return;
                if (
                  event.target instanceof Element &&
                  event.target.closest("a")
                )
                  event.preventDefault();
                onOpenRow(item.index);
              }}
              onDoubleClick={() => {
                if (!phone) startEdit(item.index, index);
              }}
              className={cn(
                "focus-visible:outline-action-text relative min-w-0 border-b border-l px-3 outline-offset-[-2px] focus:outline-2 focus:outline-solid",
                index === 0 && pinned,
                index === 0 &&
                  (note ? "bg-warn-tint" : "group-hover:over-tint-hover"),
                column.readOnly && "bg-muted/40",
                note &&
                  conflict.key === column.key &&
                  "shadow-[inset_0_0_0_2px_var(--warn)]",
                column.numeric && "text-right tabular-nums",
                isActive && "outline-action-text",
                shine && LIT_ROW,
              )}
              style={index === 0 ? { left: numberWidth } : undefined}
            >
              {isEditing && editing ? (
                column.type === "select" ? (
                  <NativeSelect
                    autoFocus
                    aria-label={`${column.name}, row ${item.index + 1}`}
                    className="absolute inset-0 w-full [&_select]:h-full [&_select]:rounded-none [&_select]:border-2 [&_select]:border-[color:var(--action-text)]"
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
                    <NativeSelectOption value="">None</NativeSelectOption>
                    {Object.entries(column.options ?? {}).map(([id, label]) => (
                      <NativeSelectOption key={id} value={id}>
                        {label}
                      </NativeSelectOption>
                    ))}
                  </NativeSelect>
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
                    className={cn(
                      "border-action-text bg-background absolute inset-0 h-full w-full border-2 px-3 text-sm outline-none",
                      column.numeric && "text-right tabular-nums",
                    )}
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
                  phone={phone}
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
                <b>{conflictWords(conflict.changedBy)}</b> It now shows the
                newer values. Your {conflict.columnName} ({conflict.draft}) was
                not saved.
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
    const index = rowIndex(store, entry.rowId);
    const col = columns.findIndex((column) => column.key === entry.key);
    const row = index >= 0 ? rowAt(store, index) : undefined;
    const column = columns[col];
    if (!row || !column) return;
    onDismissConflict();
    setActive({ row: index, col });
    cancelled.current = false;
    setEditing({
      row,
      key: column.key,
      draft: entry.draft,
      seed: editInput(column, row.cells[column.key], format),
      expected: row.cells[column.key] ?? { value: null },
    });
  }

  const pickingColumn = picking
    ? columns.find((column) => column.key === picking.key)
    : undefined;
  const pickingRow = picking?.row;
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
        aria-rowcount={
          headerRows +
          count +
          (canEdit ? 1 : 0) +
          (totalKeys.length > 0 ? 1 : 0)
        }
        aria-readonly={!canEdit || undefined}
        onKeyDown={onGridKey}
        onPaste={(event) => {
          // A paste starts at a cell: never at a row's actions or a header.
          if (!canEdit || editing || active.row < 0 || active.col < 0) return;
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
                colSpan={2}
                role={columns[0]?.group ? "columnheader" : "presentation"}
                scope={columns[0]?.group ? "colgroup" : undefined}
                className={cn(
                  pinned,
                  "text-muted-foreground left-0 h-8 border-b px-3 text-left text-xs font-semibold",
                )}
                style={{ width: numberWidth + firstWidth }}
              >
                {columns[0]?.group ?? null}
              </th>
              {bands.map((band, index) => (
                <th
                  key={`${band.label ?? "none"}-${index}`}
                  colSpan={band.span}
                  role="columnheader"
                  scope="colgroup"
                  className="text-muted-foreground h-8 border-b border-l px-3 text-left text-xs font-semibold"
                >
                  {/* The name keeps clear of the pinned column while its
                      band scrolls under it. */}
                  <span
                    className="sticky inline-block"
                    style={{ left: numberWidth + firstWidth + 12 }}
                  >
                    {band.label}
                  </span>
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
                  {canChangeColumns && stored ? (
                    <SheetColumnPopover
                      sheet={sheet}
                      column={editableColumn(stored)}
                      locale={format.locale}
                      preview={previewRow}
                      onDeleted={() => afterColumnDeleted(index)}
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
                  locale={format.locale}
                  preview={previewRow}
                  onDeleted={() => undefined}
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
      {picking && pickingColumn && pickingRow ? (
        <Suspense fallback={null}>
          {(() => {
            const col = columns.findIndex((c) => c.key === pickingColumn.key);
            const index = Math.max(rowIndex(store, picking.row.id), 0);
            const cell = pickingRow.cells[pickingColumn.key];
            const close = () => {
              setPicking(null);
              focusCell(index, col);
            };
            const save = (value: unknown) => {
              setPicking(null);
              void onSave(
                pickingRow,
                pickingColumn,
                value,
                cell ?? { value: null },
                "",
              ).then(() => focusCell(index, col));
            };
            if (picking.kind === "person")
              return (
                <SheetPersonPicker
                  sheetId={sheet.id}
                  columnName={pickingColumn.name}
                  hasPerson={Boolean(cell && "value" in cell && cell.value)}
                  onClose={close}
                  onPick={(personId) => save(personId)}
                />
              );
            return pickingColumn.linkModuleId ? (
              <SheetLinkPicker
                columnName={pickingColumn.name}
                moduleId={pickingColumn.linkModuleId}
                current={
                  cell && "link" in cell
                    ? {
                        recordId: cell.link.record_id,
                        label: cell.link.label,
                      }
                    : null
                }
                onClose={close}
                onPick={(recordId) =>
                  save(recordId ? { record_id: recordId } : null)
                }
              />
            ) : null;
          })()}
        </Suspense>
      ) : null}
    </div>
  );
}
