import { expect, test } from "@playwright/test";

import { ApiContractError } from "../../../src/lib/api";
import {
  readPlatformSearch,
  searchDestination,
  type PlatformSearchItem,
  type PlatformSearchKind,
} from "../../../src/components/systems/platform/adapters/platform-search-api";
import { ids, installFetch, pagination } from "./fixtures";
import { wirePagination } from "../../helpers/pagination";

// Search reads one card of ten hits per kind and links each hit to the screen
// that owns it. A page that is not the requested kind, size or offset is
// refused, so a card never shows hits it did not ask for. The http journey
// "Search queries four kinds, pages within cards and uses typed destinations"
// keeps one link per kind and the unopenable result without a link.

function hit(overrides: Partial<PlatformSearchItem> = {}): PlatformSearchItem {
  return {
    kind: "record",
    id: ids.result,
    title: "Pump inspection",
    context_label: "Maintenance",
    module_id: ids.module,
    board_id: null,
    department_id: null,
    can_open: true,
    ...overrides,
  };
}

const destinations: {
  name: string;
  item: PlatformSearchItem;
  href: string | null;
}[] = [
  {
    name: "a record opens its module view",
    item: hit(),
    href: `/openview?section=views&module=${ids.module}&record=${ids.result}`,
  },
  {
    name: "a person opens the People directory",
    item: hit({ kind: "person", module_id: null }),
    href: `/access?view=people&user=${ids.result}`,
  },
  {
    name: "a post opens its Board's posts",
    item: hit({ kind: "post", module_id: null, board_id: ids.board }),
    href: `/boards?board=${ids.board}&section=posts&post=${ids.result}`,
  },
  {
    name: "an event opens its Board's calendar",
    item: hit({ kind: "event", module_id: null, board_id: ids.board }),
    href: `/boards?board=${ids.board}&section=calendar&event=${ids.result}`,
  },
  {
    name: "UF-C4.2 a library file opens Files in its department, searched by its name",
    item: hit({
      kind: "file",
      title: "harbor rate card.pdf",
      module_id: null,
      department_id: ids.department,
    }),
    href: `/platform?section=files&department=${ids.department}&search=harbor%20rate%20card.pdf`,
  },
  {
    name: "a result the reader cannot open has no destination",
    item: hit({ can_open: false }),
    href: null,
  },
];

for (const row of destinations)
  test(`search destination: ${row.name}`, () => {
    expect(searchDestination(row.item)).toBe(row.href);
  });

test("FX-S3-3 a file name with & # and markup stays one search value with no fragment", () => {
  const name = "a&search=x#y<b>.pdf";
  const href = searchDestination(
    hit({
      kind: "file",
      title: name,
      module_id: null,
      department_id: ids.department,
    }),
  );
  const url = new URL(href ?? "", "http://x");
  expect(url.pathname).toBe("/platform");
  expect([...url.searchParams.keys()]).toEqual([
    "section",
    "department",
    "search",
  ]);
  expect(url.searchParams.getAll("search")).toEqual([name]);
  expect(url.hash).toBe("");
});

type PageRow = {
  name: string;
  kind?: PlatformSearchKind;
  offset?: number;
  body: unknown;
};

const refused: PageRow[] = [
  {
    name: "a hit of another kind",
    body: {
      items: [hit({ kind: "post", module_id: null, board_id: ids.board })],
      pagination: pagination(1, { limit: 10 }),
    },
  },
  {
    name: "a page size other than ten",
    body: { items: [hit()], pagination: pagination(1) },
  },
  {
    name: "an offset that does not echo the request",
    body: {
      items: [hit()],
      pagination: pagination(1, { limit: 10, offset: 10 }),
    },
  },
  {
    name: "a count that differs from the hits",
    body: { items: [hit()], pagination: pagination(2, { limit: 10 }) },
  },
  {
    name: "more than ten hits",
    body: {
      items: Array.from({ length: 11 }, (_, index) =>
        hit({
          id: `50000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
        }),
      ),
      pagination: pagination(11, { limit: 10 }),
    },
  },
  {
    name: "a total below the hits on the page",
    body: {
      items: [hit()],
      pagination: { ...pagination(1, { limit: 10 }), total: 0 },
    },
  },
  {
    name: "a record hit with a Board",
    body: {
      items: [hit({ board_id: ids.board })],
      pagination: pagination(1, { limit: 10 }),
    },
  },
  {
    name: "a person hit with a module",
    kind: "person",
    body: {
      items: [hit({ kind: "person" })],
      pagination: pagination(1, { limit: 10 }),
    },
  },
  {
    name: "a post hit without a Board",
    kind: "post",
    body: {
      items: [hit({ kind: "post", module_id: null })],
      pagination: pagination(1, { limit: 10 }),
    },
  },
  {
    name: "UF-C4.2 a file hit without its department",
    kind: "file",
    body: {
      items: [hit({ kind: "file", module_id: null })],
      pagination: pagination(1, { limit: 10 }),
    },
  },
  {
    name: "UF-C4.2 a record hit with a department",
    body: {
      items: [hit({ department_id: ids.department })],
      pagination: pagination(1, { limit: 10 }),
    },
  },
  {
    name: "an extra field on a hit",
    body: {
      items: [{ ...hit(), snippet: "Private record text" }],
      pagination: pagination(1, { limit: 10 }),
    },
  },
  {
    name: "an extra field in the pagination",
    body: {
      items: [hit()],
      pagination: { ...pagination(1, { limit: 10 }), cursor: "next" },
    },
  },
];

for (const row of refused)
  test(`search page refuses ${row.name}`, async () => {
    const mock = installFetch(() => Response.json(row.body));
    try {
      await expect(
        readPlatformSearch("pump", row.kind ?? "record", row.offset ?? 0),
      ).rejects.toBeInstanceOf(ApiContractError);
      expect(mock.requests).toHaveLength(1);
    } finally {
      mock.restore();
    }
  });

test("search page reads ten hits of one kind by relevance", async () => {
  const mock = installFetch(() =>
    Response.json({ items: [hit()], pagination: pagination(1, { limit: 10 }) }),
  );
  try {
    const page = await readPlatformSearch("pump", "record", 0);
    expect(page.items).toEqual([hit()]);
    expect(String(mock.requests[0]?.input)).toBe(
      "/api/search?search=pump&kind=record&limit=10&offset=0&sort_by=relevance&sort_order=desc&deleted=exclude",
    );
    expect(mock.requests[0]?.init?.cache).toBe("no-store");
  } finally {
    mock.restore();
  }
});

test("UF-C4.1 the search panel reads five hits of one kind, and the page must echo five", async () => {
  const file = hit({
    kind: "file",
    module_id: null,
    department_id: ids.department,
  });
  const mock = installFetch(() =>
    Response.json({ items: [file], pagination: pagination(1, { limit: 5 }) }),
  );
  try {
    const page = await readPlatformSearch("harbor", "file", 0, undefined, 5);
    expect(page.items).toEqual([file]);
    expect(String(mock.requests[0]?.input)).toBe(
      "/api/search?search=harbor&kind=file&limit=5&offset=0&sort_by=relevance&sort_order=desc&deleted=exclude",
    );
  } finally {
    mock.restore();
  }
  const ten = installFetch(() =>
    Response.json({ items: [file], pagination: pagination(1, { limit: 10 }) }),
  );
  try {
    await expect(
      readPlatformSearch("harbor", "file", 0, undefined, 5),
    ).rejects.toBeInstanceOf(ApiContractError);
  } finally {
    ten.restore();
  }
});

test("search page accepts an empty later page after results were removed", async () => {
  const mock = installFetch(() =>
    Response.json({
      items: [],
      pagination: wirePagination({ limit: 10, offset: 10, count: 0, total: 4 }),
    }),
  );
  try {
    const page = await readPlatformSearch("pump", "record", 10);
    expect(page.items).toEqual([]);
  } finally {
    mock.restore();
  }
});
