import { expect, test } from "@playwright/test";
import { keysetPageOf } from "../../helpers/pagination";

const recordId = "00000000-0000-4000-8000-000000000015";
const fieldId = "00000000-0000-4000-8000-000000000016";

function edge(index: number) {
  const suffix = String(index).padStart(12, "0");
  return {
    id: `00000000-0000-4000-8000-${suffix}`,
    field_id: fieldId,
    source_record_id: recordId,
    target_record_id: `10000000-0000-4000-8000-${suffix}`,
    created_at: "2026-10-01T00:00:00Z",
    visibility: "available",
  };
}

test("record links return one explicit page and preserve its cursor continuation", async () => {
  // A visible page must not trigger an eager crawl or conceal its
  // continuation; the next page sends the cursor of the page before.
  const { listOpenViewRecordLinks } =
    await import("../../../src/components/systems/openview/adapters/records-api");
  const all = Array.from({ length: 101 }, (_, index) => edge(index + 1));
  const pages: string[] = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = ((input: RequestInfo | URL) => {
    const query = new URL(String(input), "http://localhost").searchParams;
    const cursor = query.get("cursor");
    pages.push(cursor ? `cursor=${cursor}` : `offset=${query.get("offset")}`);
    const offset = cursor ? Number(cursor.replace("after-", "")) : 0;
    const items = all.slice(offset, offset + 100);
    return Promise.resolve(
      Response.json(
        keysetPageOf(items, { limit: 100, offset, total: all.length }),
      ),
    );
  }) as typeof fetch;
  try {
    const links = await listOpenViewRecordLinks(recordId);
    expect(links.items).toHaveLength(100);
    expect(links.pagination.hasMore).toBe(true);
    expect(links.pagination.total).toBe(101);
    expect(pages).toEqual(["offset=0"]);
    const next = await listOpenViewRecordLinks(recordId, {
      limit: 100,
      cursor: links.pagination.nextCursor ?? undefined,
    });
    expect(next.items).toHaveLength(1);
    expect(next.pagination.hasMore).toBe(false);
    expect(pages).toEqual(["offset=0", "cursor=after-100"]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("record links read a capped keyset page and refuse more links without a cursor", async () => {
  const { listOpenViewRecordLinks } =
    await import("../../../src/components/systems/openview/adapters/records-api");
  const { ApiContractError } = await import("../../../src/lib/api");
  const pagination = {
    limit: 100,
    offset: 0,
    count: 1,
    total: 10_000,
    has_more: true,
    total_is_capped: true,
  };
  let cursor: string | null = "cursor-after-1";
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (() =>
    Promise.resolve(
      Response.json({
        items: [edge(1)],
        pagination: { ...pagination, next_cursor: cursor },
      }),
    )) as typeof fetch;
  try {
    const page = await listOpenViewRecordLinks(recordId);
    expect(page.pagination).toEqual({
      limit: 100,
      offset: 0,
      count: 1,
      total: 10_000,
      hasMore: true,
      totalIsCapped: true,
      nextCursor: "cursor-after-1",
    });
    cursor = null;
    await expect(listOpenViewRecordLinks(recordId)).rejects.toBeInstanceOf(
      ApiContractError,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
