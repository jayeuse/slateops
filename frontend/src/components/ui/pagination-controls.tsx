import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
} from "@/components/ui/pagination";
import { listNumberText } from "@/lib/list-pagination";
import { cn } from "@/lib/utils";

export type PaginationControlsProps = {
  ariaLabel: string;
  className?: string;
  pageCount: number;
  pageIndex: number;
  onPageIndexChange: (pageIndex: number) => void;
  /**
   * Whether the server has rows after this page. When given, Next follows it
   * and the page index is not clamped to `pageCount`; without it, the page
   * count decides (lists with an exact total, such as Records).
   */
  hasMore?: boolean;
  /** `pageCount` comes from a capped total, so it is a lower bound (U5). */
  pageCountIsLowerBound?: boolean;
};

export function PaginationControls({
  ariaLabel,
  className,
  pageCount,
  pageIndex,
  onPageIndexChange,
  hasMore,
  pageCountIsLowerBound = false,
}: PaginationControlsProps) {
  const totalPages = Math.max(1, pageCount);
  const followsServer = hasMore !== undefined;

  const safePageIndex = followsServer
    ? Math.max(pageIndex, 0)
    : Math.min(Math.max(pageIndex, 0), totalPages - 1);
  const lastPage = followsServer ? !hasMore : safePageIndex === totalPages - 1;
  // A capped count is a lower bound: never fewer pages than the current one.
  const shownPages = pageCountIsLowerBound
    ? Math.max(totalPages, safePageIndex + 1)
    : totalPages;

  function goTo(nextPageIndex: number) {
    onPageIndexChange(
      followsServer
        ? Math.max(nextPageIndex, 0)
        : Math.min(Math.max(nextPageIndex, 0), totalPages - 1),
    );
  }

  return (
    <Pagination
      className={cn("mx-0 w-full justify-start", className)}
      aria-label={ariaLabel}
    >
      <PaginationContent className="gap-2">
        <PaginationItem>
          <Button
            type="button"
            variant="secondary"
            size="icon"
            aria-label="Go to previous page"
            disabled={safePageIndex === 0}
            className="size-11"
            onClick={() => {
              if (safePageIndex > 0) goTo(safePageIndex - 1);
            }}
          >
            <ChevronLeft aria-hidden="true" />
          </Button>
        </PaginationItem>
        <PaginationItem>
          <span
            aria-current="page"
            aria-label={`Page ${listNumberText(safePageIndex + 1)} of ${listNumberText(shownPages)}${pageCountIsLowerBound ? "+" : ""}`}
            className="bg-muted flex size-11 items-center justify-center rounded-[var(--radius)] text-sm font-medium tabular-nums"
          >
            {safePageIndex + 1}
          </span>
        </PaginationItem>
        <PaginationItem>
          <Button
            type="button"
            variant="secondary"
            size="icon"
            aria-label="Go to next page"
            disabled={lastPage}
            className="size-11"
            onClick={() => {
              if (!lastPage) goTo(safePageIndex + 1);
            }}
          >
            <ChevronRight aria-hidden="true" />
          </Button>
        </PaginationItem>
      </PaginationContent>
    </Pagination>
  );
}
