import { expect, test } from "@playwright/test";

import { PaginationControls } from "../../../src/components/ui/pagination-controls";
import { TablePagination } from "../../../src/components/ui/table-pagination";
import { staticMarkup } from "../sandbox/static-markup";

// The shared table footer and its page buttons. A list that the server caps
// at 10,000 rows sends the total 10,000 with the capped flag; the footer
// shows it as "10,000+", never clamps the range to it (U4), and Next follows
// `has_more` past the counted pages (U5, U6). Without `hasMore`, the Records
// lists keep today's behavior.

type Node = { props?: Record<string, unknown> | null };

/** The element with this accessible name in a rendered component tree. */
function byLabel(node: unknown, label: string): Node | undefined {
  if (Array.isArray(node))
    return node.map((child) => byLabel(child, label)).find(Boolean);
  if (typeof node !== "object" || node === null) return undefined;
  const props = (node as Node).props ?? {};
  if (props["aria-label"] === label) return node as Node;
  return byLabel(props.children, label);
}

/** The accessible name of the current page in a rendered component tree. */
function currentPage(node: unknown): unknown {
  if (Array.isArray(node))
    return node.map(currentPage).find((label) => label !== undefined);
  if (typeof node !== "object" || node === null) return undefined;
  const props = (node as Node).props ?? {};
  if (props["aria-current"] === "page") return props["aria-label"];
  return currentPage(props.children);
}

const footer = {
  ariaLabel: "Activity pages",
  pageSize: 10,
  onPageIndexChange: () => {},
};

test("the footer past row 10,000 reads the unclamped range of a capped total", () => {
  const html = staticMarkup(TablePagination, {
    ...footer,
    total: 10_000,
    totalIsCapped: true,
    hasMore: true,
    offset: 10_000,
    rowCount: 10,
  });
  expect(html).toContain("Showing 10,001–10,010 of 10,000+");
  expect(html).toContain('aria-label="Page 1,001 of 1,001+"');
});

test("the footer of an exact total keeps its clamped range and last page", () => {
  const html = staticMarkup(TablePagination, {
    ...footer,
    total: 1_234,
    offset: 1_230,
    rowCount: 4,
  });
  expect(html).toContain("Showing 1,231–1,234 of 1,234");
  expect(html).toContain('aria-label="Page 124 of 124"');
  expect(html).toMatch(
    /<button(?=[^>]*aria-label="Go to next page")[^>]*disabled=""/,
  );
});

test("Next follows has_more past the last counted page of a capped total", () => {
  const pages: number[] = [];
  const controls = {
    ariaLabel: "Activity pages",
    pageCount: 1_000,
    pageCountIsLowerBound: true,
    onPageIndexChange: (index: number) => pages.push(index),
  };
  const lastCounted = PaginationControls({
    ...controls,
    pageIndex: 999,
    hasMore: true,
  });
  const next = byLabel(lastCounted, "Go to next page");
  expect(next?.props?.disabled).toBe(false);
  (next?.props?.onClick as () => void)();
  expect(pages).toEqual([1_000]);
  const beyond = PaginationControls({
    ...controls,
    pageIndex: 1_000,
    hasMore: false,
  });
  expect(currentPage(beyond)).toBe("Page 1,001 of 1,001+");
  expect(byLabel(beyond, "Go to next page")?.props?.disabled).toBe(true);
});

test("without has_more the page buttons clamp to the page count as before", () => {
  const pages: number[] = [];
  const controls = PaginationControls({
    ariaLabel: "Record pages",
    pageCount: 3,
    pageIndex: 5,
    onPageIndexChange: (index) => pages.push(index),
  });
  expect(currentPage(controls)).toBe("Page 3 of 3");
  expect(byLabel(controls, "Go to next page")?.props?.disabled).toBe(true);
  (byLabel(controls, "Go to previous page")?.props?.onClick as () => void)();
  expect(pages).toEqual([1]);
});
