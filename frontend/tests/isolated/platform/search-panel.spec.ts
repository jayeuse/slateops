import { expect, test } from "@playwright/test";

import type { SearchHit } from "../../../src/components/systems/comms/contract/types";
import type { PlatformSearchItem } from "../../../src/components/systems/platform/adapters/platform-search-api";
import {
  PANEL_SCOPE,
  activeOrder,
  addressWordsOfAnotherScope,
  excerptParts,
  groupHeading,
  messageRows,
  moveActive,
  platformRows,
  rememberAddressWords,
  showAllHref,
} from "../../../src/components/systems/platform/helpers/search-panel";
import { ids } from "./fixtures";

// The header search panel (docs/specs/ux-friction-pass.md DR-4.3 to DR-4.7):
// six groups in a fixed order, a total in each heading, at most five rows,
// rows that open only when the reader may open them, and the keyboard order
// of the rows that open. The http journeys in tests/http/search-panel.spec.ts
// show these rules on screen.

const conversation = "7b000000-0000-4000-8000-000000000001";
const message = "7b000000-0000-4000-8000-000000000002";

function item(overrides: Partial<PlatformSearchItem> = {}): PlatformSearchItem {
  return {
    kind: "record",
    id: ids.result,
    title: "Harbor Freight Lines",
    context_label: "Customers · Sales",
    module_id: ids.module,
    board_id: null,
    department_id: null,
    can_open: true,
    ...overrides,
  };
}

function hit(overrides: Partial<SearchHit> = {}): SearchHit {
  return {
    message_id: message,
    conversation_id: conversation,
    conversation_name: "sales-desk",
    seq: 4,
    author_id: ids.user,
    author_name: "Ana Cruz",
    created_at: "2026-11-10T09:00:00Z",
    excerpt: "the Harbor delivery moves to Friday",
    matches: [{ start: 4, end: 10 }],
    parent_id: null,
    ...overrides,
  };
}

test("UF-C4.1 the scope line names the six groups in their fixed order", () => {
  expect(PANEL_SCOPE).toBe(
    "Records · People · Posts · Events · Messages · Files",
  );
});

test("UF-C4.1 a group heading carries its total, and a capped total reads 1,000+", () => {
  expect(groupHeading("Records", 12, false)).toBe("Records · 12");
  expect(groupHeading("Messages", 1000, true)).toBe("Messages · 1,000+");
});

test("UF-C4.1 a group lists at most five rows, and a row the reader cannot open has no destination", () => {
  const items = Array.from({ length: 6 }, (_, index) =>
    item({
      id: `50000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
      title: `Record ${index + 1}`,
    }),
  );
  items[1] = { ...items[1], can_open: false };
  const rows = platformRows(items);
  expect(rows.map((row) => row.title)).toEqual([
    "Record 1",
    "Record 2",
    "Record 3",
    "Record 4",
    "Record 5",
  ]);
  expect(rows[1].href).toBeNull();
  expect(rows[0].href).toBe(
    `/openview?section=views&module=${ids.module}&record=50000000-0000-4000-8000-000000000001`,
  );
  expect(rows[0].context).toBe("Customers · Sales");
});

test("UF-C4.5 a message opens at its message in OpenComms, and its line names the conversation, author and date", () => {
  const [row] = messageRows([hit()], (value) => `day of ${value}`);
  expect(row.href).toBe(
    `/comms?conversation=${conversation}&message=${message}`,
  );
  expect(row.context).toBe(
    "sales-desk · Ana Cruz · day of 2026-11-10T09:00:00Z",
  );
  expect(row.title).toBe("the Harbor delivery moves to Friday");
});

test("UF-C4.1 an excerpt marks the matched words by code point, so a wide character before them keeps the mark in place", () => {
  expect(excerptParts("🚢 Harbor delivery", [{ start: 2, end: 8 }])).toEqual([
    { text: "🚢 ", marked: false },
    { text: "Harbor", marked: true },
    { text: " delivery", marked: false },
  ]);
  expect(excerptParts("no match here", [])).toEqual([
    { text: "no match here", marked: false },
  ]);
});

test("UF-C4.1 arrow keys move across groups over the rows that open, and wrap at either end", () => {
  const groups = [
    platformRows([
      item({ id: "50000000-0000-4000-8000-000000000001" }),
      item({ id: "50000000-0000-4000-8000-000000000002", can_open: false }),
    ]),
    messageRows([hit()], (value) => value),
  ];
  const order = activeOrder(groups);
  expect(order).toEqual([
    "record-50000000-0000-4000-8000-000000000001",
    `message-${message}`,
  ]);
  expect(moveActive(order, order[0], 1)).toBe(order[1]);
  expect(moveActive(order, order[1], 1)).toBe(order[0]);
  expect(moveActive(order, order[0], -1)).toBe(order[1]);
  expect(moveActive(order, null, 1)).toBe(order[0]);
  expect(moveActive([], null, 1)).toBeNull();
});

test("UF-C4.5 Show all results opens the Search page with the typed words", () => {
  expect(showAllHref("harbor rate & card")).toBe(
    "/platform?section=search&q=harbor%20rate%20%26%20card",
  );
});

// Security review S3-6: the tab records which account and organization wrote
// or filled each value of the address words, not only the latest one, so
// older words of another account never fill the field.
const ADDRESS_WORDS_KEY = "slateops-search-address-words";
const A = "account-a:organization-1";
const B = "account-b:organization-1";

function withTabStorage(run: (storage: Map<string, string>) => void) {
  const storage = new Map<string, string>();
  const global = globalThis as { window?: unknown };
  const previous = global.window;
  global.window = {
    sessionStorage: {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => void storage.set(key, value),
    },
  };
  try {
    run(storage);
  } finally {
    global.window = previous;
  }
}

test("S6-AC1 every value an account wrote stays its own, not only the latest", () => {
  withTabStorage(() => {
    rememberAddressWords("q", A, "alpha");
    rememberAddressWords("q", A, "beta");
    expect(addressWordsOfAnotherScope("q", B, "alpha")).toBe(true);
    expect(addressWordsOfAnotherScope("q", B, "beta")).toBe(true);
  });
});

test("S6-AC2 another account's later words do not free the earlier words", () => {
  withTabStorage(() => {
    rememberAddressWords("q", A, "alpha");
    rememberAddressWords("q", A, "beta");
    rememberAddressWords("q", B, "gamma");
    expect(addressWordsOfAnotherScope("q", B, "alpha")).toBe(true);
    expect(addressWordsOfAnotherScope("q", B, "beta")).toBe(true);
    expect(addressWordsOfAnotherScope("q", B, "gamma")).toBe(false);
    expect(addressWordsOfAnotherScope("q", A, "gamma")).toBe(true);
  });
});

test("S6-AC3 words nobody wrote are free, and the last writer of a value owns it", () => {
  withTabStorage(() => {
    expect(addressWordsOfAnotherScope("q", B, "pasted link")).toBe(false);
    rememberAddressWords("q", A, "shared");
    rememberAddressWords("q", B, "shared");
    expect(addressWordsOfAnotherScope("q", B, "shared")).toBe(false);
    expect(addressWordsOfAnotherScope("q", A, "shared")).toBe(true);
    // Each name keeps its own record.
    expect(addressWordsOfAnotherScope("search", A, "shared")).toBe(false);
  });
});

test("S6-AC4 at most 50 values per name are kept, and an old or broken record reads as empty", () => {
  withTabStorage((storage) => {
    for (let index = 1; index <= 51; index += 1)
      rememberAddressWords("q", A, `word ${index}`);
    // The oldest value is trimmed; the 50 latest stay.
    expect(addressWordsOfAnotherScope("q", B, "word 1")).toBe(false);
    expect(addressWordsOfAnotherScope("q", B, "word 2")).toBe(true);
    expect(addressWordsOfAnotherScope("q", B, "word 51")).toBe(true);

    storage.set(
      ADDRESS_WORDS_KEY,
      JSON.stringify({ q: { scope: A, value: "alpha" } }),
    );
    expect(addressWordsOfAnotherScope("q", B, "alpha")).toBe(false);
    storage.set(ADDRESS_WORDS_KEY, "{not json");
    expect(addressWordsOfAnotherScope("q", B, "alpha")).toBe(false);
    rememberAddressWords("q", A, "alpha");
    expect(addressWordsOfAnotherScope("q", B, "alpha")).toBe(true);
  });
});
