"use client";

import { useId } from "react";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { PaginationControls } from "@/components/ui/pagination-controls";
import { listNumberText, listTotalText } from "@/lib/list-pagination";
import { cn } from "@/lib/utils";

export const TABLE_PAGE_SIZE_OPTIONS = [5, 10, 25, 50] as const;
// Ten rows fit a laptop screen and keep paging rare in small directories.
export const DEFAULT_TABLE_PAGE_SIZE = 10;

type TablePaginationProps = {
  ariaLabel: string;
  total: number;
  offset: number;
  rowCount: number;
  pageSize: number;
  onPageIndexChange: (pageIndex: number) => void;
  onPageSizeChange?: (pageSize: number) => void;
  disabled?: boolean;
  className?: string;
  /** Whether the server has rows after this page; Next follows it (U6). */
  hasMore?: boolean;
  /** The server capped `total` at 10,000: it is a lower bound (U1 to U5). */
  totalIsCapped?: boolean;
};

/** The table footer pattern used across the workspace; callers own paging. */
export function TablePagination({
  ariaLabel,
  total,
  offset,
  rowCount,
  pageSize,
  onPageIndexChange,
  onPageSizeChange,
  disabled = false,
  className,
  hasMore,
  totalIsCapped = false,
}: TablePaginationProps) {
  const id = useId();
  const first = rowCount === 0 ? 0 : offset + 1;
  // A capped total is a lower bound, so the range end is never clamped to it.
  const last =
    rowCount === 0
      ? 0
      : totalIsCapped
        ? offset + rowCount
        : Math.min(offset + rowCount, total);
  return (
    <div
      className={cn(
        "bg-card flex flex-col gap-3 border-t p-4 lg:flex-row lg:items-center lg:justify-between",
        className,
      )}
    >
      <p
        className="text-muted-foreground text-sm tabular-nums"
        aria-live="polite"
      >
        Showing {listNumberText(first)}–{listNumberText(last)} of{" "}
        {listTotalText(total, totalIsCapped)}
      </p>
      <fieldset
        disabled={disabled}
        className="flex min-w-0 flex-wrap items-center gap-3 lg:justify-end"
      >
        <legend className="sr-only">{ariaLabel} controls</legend>
        {onPageSizeChange ? (
          <div className="flex items-center gap-2">
            <label htmlFor={id} className="text-muted-foreground text-sm">
              Rows per page
            </label>
            <NativeSelect
              id={id}
              className="w-20 [&_select]:min-h-11"
              value={String(pageSize)}
              onChange={(event) => {
                const next = Number(event.target.value);
                if (TABLE_PAGE_SIZE_OPTIONS.some((size) => size === next))
                  onPageSizeChange(next);
              }}
            >
              {TABLE_PAGE_SIZE_OPTIONS.map((size) => (
                <NativeSelectOption key={size} value={String(size)}>
                  {size}
                </NativeSelectOption>
              ))}
            </NativeSelect>
          </div>
        ) : null}
        <PaginationControls
          ariaLabel={ariaLabel}
          className="w-auto justify-end"
          pageCount={Math.max(1, Math.ceil(total / pageSize))}
          pageIndex={Math.floor(offset / pageSize)}
          onPageIndexChange={onPageIndexChange}
          hasMore={hasMore}
          pageCountIsLowerBound={totalIsCapped}
        />
      </fieldset>
    </div>
  );
}
