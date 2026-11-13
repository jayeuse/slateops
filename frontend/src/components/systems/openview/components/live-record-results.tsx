"use client";

import { useSyncExternalStore, type MouseEvent, type ReactNode } from "react";
import type {
  OpenViewDataSourceField,
  OpenViewPresentation,
  OpenViewRecord,
} from "../adapters/views-api";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { TablePagination } from "@/components/ui/table-pagination";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  formatOpenViewFieldValue,
  LiveRecordCards,
  NewRecordTag,
  RecordPersonCard,
} from "./live-record-cards";
import { openViewRecordFieldValue } from "../domain/record-display";
import { selectionLabel } from "../domain/record-batch-change";
import { formatWorkspaceDate, type WorkspaceRegion } from "@/lib/date-time";
import { cn } from "@/lib/utils";
import {
  openRowClassName,
  RowOpenButton,
  tintRowClassName,
} from "@/components/systems/access/components/row-open-button";

const headClassName = "text-muted-foreground h-9 px-4 text-xs font-medium";
/** A sticky cell keeps the row's tint over the cells scrolling under it. */
const pinnedCellClassName =
  "bg-card sticky z-10 group-hover:bg-[color-mix(in_oklab,var(--ink)_6%,var(--card))] group-data-[state=selected]:bg-[color-mix(in_oklab,var(--ink)_14%,var(--card))]";

type RecordPage = {
  rows: readonly OpenViewRecord[];
  offset: number;
  total: number;
  hasMore: boolean;
  loading: boolean;
};

type ResultsPresentation = Pick<
  OpenViewPresentation,
  "primaryFieldId" | "secondaryFieldId" | "cardSize" | "wrap" | "density"
>;

type LiveRecordResultsProps = {
  region: WorkspaceRegion | undefined;
  page: RecordPage;
  cardLayout: "grid" | "gallery" | null;
  cardFields: readonly OpenViewDataSourceField[];
  tableFields: readonly OpenViewDataSourceField[];
  pinnedFieldId: string | null;
  presentation: ResultsPresentation;
  pending: boolean;
  pageSize: number;
  /** The record open in the sheet, tinted in the list. */
  selectedId: string | null;
  /**
   * A record this page just created that matches the view: shown first with
   * a "New" tag, once, and never counted by the pager (DR-6.3, DR-6.4).
   * Off unless the page passes it.
   */
  newRecord?: OpenViewRecord | null;
  /**
   * Candidate 1: a Choice list value as its menu (DR-SI-1.1, DR-SI-1.2).
   * Returns null where the value stays as now. Off unless the page passes it.
   */
  choiceCell?: ChoiceCellRenderer | null;
  /** The field of the phone row's chip: the quick-filter field (OD14). */
  chipFieldId?: string | null;
  /** Candidate 5: a writer's row selection (DR-SI-5.1 to DR-SI-5.3). */
  selection?: RowSelectionProps | null;
  /** The record whose change runs: its row waits to open (DR-SI-1.6). */
  busyRecordId?: string | null;
  onOpenRecord: (recordId: string) => void;
  onPageIndexChange: (pageIndex: number) => void;
  onPageSizeChange: (pageSize: number) => void;
};

export type ChoiceCellRenderer = (
  row: OpenViewRecord,
  field: OpenViewDataSourceField,
  variant: "cell" | "chip",
) => ReactNode | null;

export type RowSelectionProps = {
  selectedIds: ReadonlySet<string>;
  disabled: boolean;
  /** `range`: Shift was held, so the rows from the last toggled one join. */
  onToggle: (recordId: string, range: boolean) => void;
  onToggleAll: () => void;
};

const NARROW_QUERY = "(max-width: 47.99rem)";

function subscribeNarrow(onChange: () => void) {
  const query = window.matchMedia(NARROW_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/**
 * True below the md breakpoint, where records are two-line rows. One layout
 * renders at a time, so no record is in the page twice; the first render
 * assumes a wide screen.
 */
export function useNarrowScreen(): boolean {
  return useSyncExternalStore(
    subscribeNarrow,
    () => window.matchMedia(NARROW_QUERY).matches,
    () => false,
  );
}

/**
 * A cell's click opens the record, unless it hit a control of its own or
 * the selection cell (DR-SI-5.3). A click inside a cell's menu reaches the
 * row through React's portal bubbling, but it is not in the row.
 */
function opensRecord(event: MouseEvent<HTMLElement>): boolean {
  const target = event.target as Element;
  return (
    event.currentTarget.contains(target) &&
    !target.closest("button, a, [role=button], [data-row-select]")
  );
}

/** Whether Shift was held: a range selection, by pointer or Shift+Space. */
function withShift(event: Event | undefined): boolean {
  return Boolean(event && "shiftKey" in event && event.shiftKey === true);
}

function RowCheckbox({
  label,
  checked,
  selection,
  recordId,
  className,
}: {
  label: string;
  checked: boolean;
  selection: RowSelectionProps;
  recordId: string;
  className?: string;
}) {
  return (
    <Checkbox
      aria-label={label}
      checked={checked}
      disabled={selection.disabled}
      // Above the row's open button, whose hit area covers the row; 44 px
      // below 1280 px and 32 px from it.
      className={cn("z-10 after:-inset-3.5 xl:after:-inset-2", className)}
      onCheckedChange={(_checked, details) =>
        selection.onToggle(recordId, withShift(details.event))
      }
    />
  );
}

export function LiveRecordResults({
  region,
  page,
  cardLayout,
  cardFields,
  tableFields,
  pinnedFieldId,
  presentation,
  pending,
  pageSize,
  selectedId,
  newRecord = null,
  choiceCell = null,
  chipFieldId = null,
  selection = null,
  busyRecordId = null,
  onOpenRecord: openRecord,
  onPageIndexChange,
  onPageSizeChange,
}: LiveRecordResultsProps) {
  const narrow = useNarrowScreen();
  // DR-SI-1.6: the row of a running change waits to open.
  const onOpenRecord = (recordId: string) => {
    if (recordId !== busyRecordId) openRecord(recordId);
  };
  const chipField = chipFieldId
    ? tableFields.find((field) => field.id === chipFieldId)
    : undefined;
  const chip = (row: OpenViewRecord) =>
    choiceCell && chipField ? choiceCell(row, chipField, "chip") : null;
  const selectedCount = selection
    ? page.rows.filter((row) => selection.selectedIds.has(row.id)).length
    : 0;
  // The page's own row is the freshest copy, so it leads when the page has it.
  const rows = newRecord
    ? [
        page.rows.find((row) => row.id === newRecord.id) ?? newRecord,
        ...page.rows.filter((row) => row.id !== newRecord.id),
      ]
    : page.rows;
  const newTag = (row: OpenViewRecord) =>
    row.id === newRecord?.id ? <NewRecordTag /> : null;
  const cellValue = (row: OpenViewRecord, field: OpenViewDataSourceField) =>
    formatOpenViewFieldValue(
      openViewRecordFieldValue(row, field),
      field.type,
      region,
    );
  return (
    // The panel fills the page; only its rows scroll and the pager stays at
    // the bottom (OD6). The page header counts the records and reports a
    // refresh, so nothing here shifts while a page loads.
    <Card
      className="access-fill flex min-w-0 flex-col self-auto overflow-hidden"
      aria-label="Record results"
    >
      {cardLayout ? (
        <div className="min-h-0 overflow-x-auto xl:flex-1 xl:overflow-y-auto xl:overscroll-contain">
          <LiveRecordCards
            region={region}
            layout={cardLayout}
            rows={rows}
            newRecordId={newRecord?.id ?? null}
            fields={cardFields}
            primaryFieldId={presentation.primaryFieldId}
            secondaryFieldId={presentation.secondaryFieldId}
            cardSize={presentation.cardSize}
            wrap={presentation.wrap}
            onOpenRecord={onOpenRecord}
          />
        </div>
      ) : narrow ? (
        // Phones: a two-line row per record, its name, then the next two
        // filled fields (DESIGN.md, Access phone rows).
        <ul aria-label="Records" className="divide-border divide-y">
          {rows.map((row) => {
            const [first, ...rest] = tableFields;
            const title = first ? cellValue(row, first) : "Open record";
            const details = rest
              .map((field) => cellValue(row, field))
              .filter((value) => value && value !== "—")
              .slice(0, 2)
              .join(" · ");
            const label =
              first?.type === "user" ? `Open record: ${title}` : title;
            const rowChip = chip(row);
            const rowProps = {
              "data-record-id": row.id,
              "data-state": row.id === selectedId ? "selected" : undefined,
            };
            // DR-6.3: the new record's tag sits on its title line, so its
            // second line follows the title and tag; the button's hit area
            // still covers the row.
            if (row.id === newRecord?.id)
              return (
                <li
                  key={row.id}
                  {...rowProps}
                  className={cn(
                    openRowClassName,
                    tintRowClassName,
                    "flex min-h-14 flex-col justify-center px-4 py-1.5",
                  )}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    {selection ? (
                      <RowCheckbox
                        label={selectionLabel(first ? title : undefined)}
                        checked={selection.selectedIds.has(row.id)}
                        selection={selection}
                        recordId={row.id}
                        className="mr-1 shrink-0"
                      />
                    ) : null}
                    <RowOpenButton
                      title={title}
                      label={label}
                      className="min-h-0!"
                      onOpen={() => onOpenRecord(row.id)}
                    />
                    <NewRecordTag />
                    {rowChip ? (
                      <span className="ml-auto pl-2">{rowChip}</span>
                    ) : null}
                  </span>
                  {details ? (
                    <span className="text-muted-foreground block truncate text-xs">
                      {details}
                    </span>
                  ) : null}
                </li>
              );
            return (
              <li
                key={row.id}
                {...rowProps}
                className={cn(
                  openRowClassName,
                  tintRowClassName,
                  "flex min-h-14 items-center px-4 py-1.5",
                )}
              >
                {selection ? (
                  <RowCheckbox
                    label={selectionLabel(first ? title : undefined)}
                    checked={selection.selectedIds.has(row.id)}
                    selection={selection}
                    recordId={row.id}
                    className="mr-4 shrink-0"
                  />
                ) : null}
                {/* The name names the button; the second line describes it. */}
                <RowOpenButton
                  title={title}
                  subtitle={details || undefined}
                  label={label}
                  onOpen={() => onOpenRecord(row.id)}
                />
                {rowChip ? (
                  <span className="ml-auto pl-2">{rowChip}</span>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <div className="access-fill access-scroll-table">
          <Table className="min-w-[36rem] text-left text-sm">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                {selection ? (
                  <TableHead
                    scope="col"
                    className={cn(
                      headClassName,
                      "w-10 px-3",
                      pinnedFieldId && "bg-card sticky left-0 z-20",
                    )}
                  >
                    <Checkbox
                      aria-label="Select all on this page"
                      checked={
                        selectedCount > 0 && selectedCount === page.rows.length
                      }
                      indeterminate={
                        selectedCount > 0 && selectedCount < page.rows.length
                      }
                      disabled={selection.disabled || page.rows.length === 0}
                      className="z-10 after:-inset-3.5 xl:after:-inset-2"
                      onCheckedChange={() => selection.onToggleAll()}
                    />
                  </TableHead>
                ) : null}
                {tableFields.map((field) => (
                  <TableHead
                    key={field.id}
                    scope="col"
                    className={cn(
                      headClassName,
                      field.id === pinnedFieldId &&
                        cn(
                          "bg-card sticky z-20",
                          selection ? "left-10" : "left-0",
                        ),
                    )}
                  >
                    {field.name}
                  </TableHead>
                ))}
                <TableHead scope="col" className={headClassName}>
                  Updated
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                // OD6: one line per record; the whole row opens it.
                // A pinned cell is sticky, which keeps the open button's
                // overlay inside it, so the row opens the record itself.
                <TableRow
                  key={row.id}
                  data-record-id={row.id}
                  data-state={row.id === selectedId ? "selected" : undefined}
                  className={cn(
                    openRowClassName,
                    tintRowClassName,
                    "group",
                    presentation.density === "compact"
                      ? "h-11 xl:h-8"
                      : "h-11 xl:h-10",
                  )}
                  onClick={(event) => {
                    if (opensRecord(event)) onOpenRecord(row.id);
                  }}
                >
                  {selection ? (
                    <TableCell
                      data-row-select=""
                      className={cn(
                        "w-10 cursor-default px-3 py-0 align-middle",
                        // With a pinned column, the boxes stay in reach too.
                        pinnedFieldId && pinnedCellClassName,
                        pinnedFieldId && "left-0",
                      )}
                    >
                      <RowCheckbox
                        label={selectionLabel(
                          tableFields[0]
                            ? cellValue(row, tableFields[0])
                            : undefined,
                        )}
                        checked={selection.selectedIds.has(row.id)}
                        selection={selection}
                        recordId={row.id}
                      />
                    </TableCell>
                  ) : null}
                  {tableFields.map((field, index) => {
                    const value = cellValue(row, field);
                    return (
                      <TableCell
                        key={field.id}
                        className={cn(
                          "max-w-80 overflow-hidden px-4 align-middle xl:max-w-60",
                          presentation.wrap
                            ? cn(
                                "break-words whitespace-normal",
                                presentation.density === "compact"
                                  ? "py-1.5"
                                  : "py-2.5",
                              )
                            : "py-0 whitespace-nowrap",
                          field.id === pinnedFieldId &&
                            cn(
                              pinnedCellClassName,
                              selection ? "left-10" : "left-0",
                            ),
                        )}
                      >
                        {index === 0 ? (
                          <span className="flex min-w-0 items-center gap-2">
                            <RowOpenButton
                              title={
                                field.type === "user" ? "Open record" : value
                              }
                              label={
                                field.type === "user"
                                  ? `Open record: ${value}`
                                  : undefined
                              }
                              inline
                              onOpen={() => onOpenRecord(row.id)}
                            />
                            {newTag(row)}
                            {field.type === "user" ? (
                              <RecordPersonCard row={row} field={field} inline>
                                {value}
                              </RecordPersonCard>
                            ) : null}
                          </span>
                        ) : (
                          (field.type === "select" &&
                            choiceCell?.(row, field, "cell")) || (
                            <RecordPersonCard row={row} field={field} inline>
                              <span className="block truncate">{value}</span>
                            </RecordPersonCard>
                          )
                        )}
                      </TableCell>
                    );
                  })}
                  <TableCell className="text-muted-foreground px-4 py-0 align-middle whitespace-nowrap">
                    {region
                      ? formatWorkspaceDate(row.updatedAt, region)
                      : "Date unavailable"}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
      <TablePagination
        ariaLabel="Record result pages"
        total={page.total}
        offset={page.offset}
        rowCount={page.rows.length}
        pageSize={pageSize}
        onPageIndexChange={onPageIndexChange}
        onPageSizeChange={onPageSizeChange}
        disabled={page.loading || pending}
      />
    </Card>
  );
}
