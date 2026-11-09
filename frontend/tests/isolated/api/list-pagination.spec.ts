import { expect, test } from "@playwright/test";

import {
  hasMoreAgreesWithTotal,
  listCountText,
  listTotalText,
  pageEndsWithinTotal,
  type PageCounts,
} from "../../../src/lib/list-pagination";

// A list that the shared count helper serves counts at most 10,000 rows. Above
// that the server sends `total` 10,000 with `total_is_capped` true: the total
// is a lower bound, so only `has_more` says whether more rows exist. Every
// adapter consistency check reads the page through these two rules.

const cases: {
  name: string;
  page: PageCounts;
  ends: boolean;
  more: boolean;
}[] = [
  {
    name: "exact total, a middle page",
    page: {
      offset: 0,
      count: 10,
      total: 25,
      hasMore: true,
      totalIsCapped: false,
    },
    ends: true,
    more: true,
  },
  {
    name: "exact total, the last page",
    page: {
      offset: 20,
      count: 5,
      total: 25,
      hasMore: false,
      totalIsCapped: false,
    },
    ends: true,
    more: true,
  },
  {
    name: "exact total, has_more on the last page",
    page: {
      offset: 20,
      count: 5,
      total: 25,
      hasMore: true,
      totalIsCapped: false,
    },
    ends: true,
    more: false,
  },
  {
    name: "exact total, a page that ends past the total",
    page: {
      offset: 20,
      count: 10,
      total: 25,
      hasMore: false,
      totalIsCapped: false,
    },
    ends: false,
    more: true,
  },
  {
    name: "capped total, the page at offset 9,990",
    page: {
      offset: 9990,
      count: 10,
      total: 10_000,
      hasMore: true,
      totalIsCapped: true,
    },
    ends: true,
    more: true,
  },
  {
    name: "capped total, a page past row 10,000",
    page: {
      offset: 10_000,
      count: 10,
      total: 10_000,
      hasMore: true,
      totalIsCapped: true,
    },
    ends: true,
    more: true,
  },
  {
    name: "capped total, the last page past row 10,000",
    page: {
      offset: 10_010,
      count: 3,
      total: 10_000,
      hasMore: false,
      totalIsCapped: true,
    },
    ends: true,
    more: true,
  },
  {
    name: "capped total, no more rows before row 10,000",
    page: {
      offset: 0,
      count: 10,
      total: 10_000,
      hasMore: false,
      totalIsCapped: true,
    },
    ends: true,
    more: false,
  },
];

for (const { name, page, ends, more } of cases) {
  test(`list page counts: ${name}`, () => {
    expect([pageEndsWithinTotal(page), hasMoreAgreesWithTotal(page)]).toEqual([
      ends,
      more,
    ]);
  });
}

test("a list total is grouped in English and capped totals end with a plus", () => {
  expect([
    listTotalText(7, false),
    listTotalText(1234, false),
    listTotalText(10_000, false),
    listTotalText(10_000, true),
  ]).toEqual(["7", "1,234", "10,000", "10,000+"]);
});

test("a counted noun stays singular only for an exact 1", () => {
  expect([
    listCountText(1, false, "notification", "notifications"),
    listCountText(6_638, false, "notification", "notifications"),
    listCountText(10_000, true, "notification", "notifications"),
  ]).toEqual([
    "1 notification",
    "6,638 notifications",
    "10,000+ notifications",
  ]);
});
