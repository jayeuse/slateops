import { expect, test } from "@playwright/test";

import { listRecordAppearances } from "../../../src/components/systems/openview/adapters/worksheet-appears-api";
import { ApiContractError } from "../../../src/lib/api";
import { wirePagination } from "../../helpers/pagination";
import { installSyncFetch as installFetch } from "../helpers/fake-fetch";

// docs/specs/sheets.md N5, V7, D10 route 23 (SH-28): the rows that link to a
// record, in sheets the viewer can see, a page at a time.

const recordId = "00000000-0000-4000-8000-0000000005c1";
const sheetId = "00000000-0000-4000-8000-0000000005c2";
const ownerId = "00000000-0000-4000-8000-0000000005c3";
const rowId = "00000000-0000-4000-8000-0000000005c4";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const item = {
  worksheet_id: sheetId,
  worksheet_title: "Class 1A",
  owner: { id: ownerId, display_name: "Andrea Villamor" },
  row_id: rowId,
  row_number: 7,
  column_key: "c1",
  column_name: "Student",
  columns: [
    { key: "c1", name: "Student", type: "link" },
    { key: "c2", name: "Quiz 1", type: "int" },
  ],
  cells: {
    c1: { link: { record_id: recordId, label: "Alyssa Mercado" } },
    c2: { value: 18 },
  },
};

test("a record's appearances are read a page at a time, in the reader's words", async () => {
  const mock = installFetch(() =>
    json({
      items: [item],
      pagination: wirePagination({
        limit: 25,
        offset: 25,
        count: 1,
        total: 26,
      }),
    }),
  );
  try {
    const page = await listRecordAppearances(recordId, 25);
    expect(String(mock.requests[0].input)).toBe(
      `/api/records/${recordId}/worksheet-rows?limit=25&offset=25`,
    );
    expect(page).toEqual({
      items: [
        {
          sheetId,
          sheetTitle: "Class 1A",
          owner: { id: ownerId, displayName: "Andrea Villamor" },
          rowId,
          rowNumber: 7,
          columnKey: "c1",
          columnName: "Student",
          columns: [
            { key: "c1", name: "Student", type: "link" },
            { key: "c2", name: "Quiz 1", type: "int" },
          ],
          cells: item.cells,
        },
      ],
      total: 26,
      hasMore: false,
      // The next page starts after this one's window, not after the rows it
      // holds: a row hidden after counting would be read twice.
      nextOffset: 50,
    });
  } finally {
    mock.restore();
  }
});

test("a no-access cell carries no record id or label (N4)", async () => {
  const mock = installFetch(() =>
    json({
      items: [
        {
          ...item,
          cells: { c1: { state: "no_access", label: "Alyssa Mercado" } },
        },
      ],
      pagination: wirePagination({ limit: 25, count: 1, total: 1 }),
    }),
  );
  try {
    await expect(listRecordAppearances(recordId, 0)).rejects.toThrow(
      ApiContractError,
    );
  } finally {
    mock.restore();
  }
});

test("a computed cell that cannot be worked out and a several-matches cell keep their shape", async () => {
  const cells = {
    c1: { link: { record_id: recordId, label: "Alyssa Mercado" } },
    c2: { value: null, error: "division_by_zero" },
    c3: { state: "multiple_matches", count: 3 },
  };
  const mock = installFetch(() =>
    json({
      items: [{ ...item, cells }],
      pagination: wirePagination({ limit: 25, count: 1, total: 1 }),
    }),
  );
  try {
    const page = await listRecordAppearances(recordId, 0);
    expect(page.items[0].cells).toEqual(cells);
  } finally {
    mock.restore();
  }
});
