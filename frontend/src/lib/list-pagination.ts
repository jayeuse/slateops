/**
 * The counts of one list page, as an adapter parses them.
 *
 * A list that the server's shared count helper serves counts at most 10,000
 * rows. Above that it sends `total` 10,000 with `total_is_capped` true: the
 * total is then a lower bound, and only `has_more` says whether more rows
 * exist. Records lists keep their exact total and always send false.
 */
export type PageCounts = {
  offset: number;
  count: number;
  total: number;
  hasMore: boolean;
  totalIsCapped: boolean;
};

/** The wire block of a list page (`has_more`, `total_is_capped`). */
export type WirePageCounts = {
  offset: number;
  count: number;
  total: number;
  has_more: boolean;
  total_is_capped: boolean;
};

export function wirePageCounts(page: WirePageCounts): PageCounts {
  return {
    offset: page.offset,
    count: page.count,
    total: page.total,
    hasMore: page.has_more,
    totalIsCapped: page.total_is_capped,
  };
}

/**
 * The page ends inside the total. A capped total is a lower bound, so a page
 * past row 10,000 still fits.
 */
export function pageEndsWithinTotal(page: PageCounts): boolean {
  return page.totalIsCapped || page.offset + page.count <= page.total;
}

/**
 * `has_more` agrees with the total. With an exact total, more rows exist
 * exactly when the page ends before it. A capped total is a lower bound: a
 * page that ends before it must say that more rows exist; at or past it,
 * only `has_more` knows.
 */
export function hasMoreAgreesWithTotal(page: PageCounts): boolean {
  const end = page.offset + page.count;
  return page.totalIsCapped
    ? page.hasMore || end >= page.total
    : page.hasMore === end < page.total;
}

/** A count in list text, grouped in English: "1,234". */
export function listNumberText(value: number): string {
  return value.toLocaleString("en-US");
}

/**
 * A list total as the UI shows it (U1 to U3): grouped, with "+" when the
 * server capped it. The plus comes from the flag only; an exact total of
 * 10,000 shows "10,000". Visible and accessible text are the same string.
 */
export function listTotalText(total: number, capped: boolean): string {
  return `${listNumberText(total)}${capped ? "+" : ""}`;
}

/** "1 notification", "6,638 notifications", "10,000+ notifications". */
export function listCountText(
  total: number,
  capped: boolean,
  one: string,
  many: string,
): string {
  return `${listTotalText(total, capped)} ${total === 1 && !capped ? one : many}`;
}
