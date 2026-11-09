import type { Pagination } from "../../src/lib/api";

// Pagination blocks for mock bodies and fixtures. `wirePagination` and
// `parsedPagination` return the literal fields they are given; only the
// first-page defaults (offset 0, no more items) are filled in, and nothing is
// derived from the items. Keep expected values in assertions spelled out
// instead of building them here.

type PaginationFields = {
  limit: number;
  offset?: number;
  count: number;
  total: number;
};

/** The API wire block, as list endpoints send it (`has_more`). */
export function wirePagination({
  limit,
  offset = 0,
  count,
  total,
  has_more = false,
  total_is_capped = false,
}: PaginationFields & {
  has_more?: boolean;
  total_is_capped?: boolean;
}): Pagination {
  return { limit, offset, count, total, has_more, total_is_capped };
}

/**
 * A page of a list above 10,000 rows whose rows reach row 10,000. The server
 * caps `total` at 10,000 and sets `total_is_capped`; `has_more` stays true.
 * An exact-total check refuses this page; the lower-bound rule accepts it.
 */
export function cappedWirePagination({
  limit,
  offset = 9_990,
  count,
}: {
  limit: number;
  offset?: number;
  count: number;
}): Pagination {
  return {
    limit,
    offset,
    count,
    total: 10_000,
    has_more: true,
    total_is_capped: true,
  };
}

/** The parsed block that adapters return (`hasMore`). */
export function parsedPagination({
  limit,
  offset = 0,
  count,
  total,
  hasMore = false,
  totalIsCapped = false,
}: PaginationFields & { hasMore?: boolean; totalIsCapped?: boolean }) {
  return { limit, offset, count, total, hasMore, totalIsCapped };
}

/**
 * One page of a list response, as the API sends it, for fakes that page a
 * list.
 *
 * `count` is the number of items, `offset` defaults to 0 and `total` to the
 * number of items. `has_more` is true while later items exist, unless
 * `hasMore` sets it explicitly. `totalIsCapped` marks a total that the server
 * capped at 10,000.
 */
export function pageOf<T>(
  items: T[],
  {
    limit,
    offset = 0,
    total = items.length,
    hasMore = offset + items.length < total,
    totalIsCapped = false,
  }: {
    limit: number;
    offset?: number;
    total?: number;
    hasMore?: boolean;
    totalIsCapped?: boolean;
  },
) {
  return {
    items,
    pagination: {
      limit,
      offset,
      count: items.length,
      total,
      has_more: hasMore,
      total_is_capped: totalIsCapped,
    },
  };
}

/**
 * An opaque test cursor that names the row after a page. The frontend sends
 * a cursor back unchanged and never reads it.
 */
export function testCursor(nextOffset: number): string {
  return `after-${nextOffset}`;
}

/**
 * One page of a keyset list (audit, record history, relationships), as the
 * API sends it: `pageOf` plus `next_cursor`, a cursor exactly when more
 * items exist.
 */
export function keysetPageOf<T>(
  items: T[],
  options: {
    limit: number;
    offset?: number;
    total?: number;
    hasMore?: boolean;
    totalIsCapped?: boolean;
  },
) {
  const page = pageOf(items, options);
  return {
    ...page,
    pagination: {
      ...page.pagination,
      next_cursor: page.pagination.has_more
        ? testCursor(page.pagination.offset + items.length)
        : null,
    },
  };
}
