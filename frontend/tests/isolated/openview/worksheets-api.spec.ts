import { expect, test } from "@playwright/test";
import { ApiContractError } from "../../../src/lib/api";
import {
  createWorksheet,
  getWorksheet,
  listModuleWorksheets,
  listMyWorksheets,
  listRecordWorksheets,
  queryWorksheetRows,
  restoreWorksheet,
} from "../../../src/components/systems/openview/adapters/worksheets-api";
import { wirePagination } from "../../helpers/pagination";
import { installSyncFetch as installFetch } from "../helpers/fake-fetch";

const ownerId = "00000000-0000-4000-8000-0000000005b1";
const recordId = "00000000-0000-4000-8000-0000000005b2";
const moduleId = "00000000-0000-4000-8000-0000000005b3";

function sheetId(n: number): string {
  return `00000000-0000-4000-8000-${n.toString(16).padStart(12, "0")}`;
}

function wireSummary(n: number, overrides: Record<string, unknown> = {}) {
  return {
    id: sheetId(n),
    record_id: recordId,
    module_id: null,
    title: `Class ${n}`,
    owner: { id: ownerId, display_name: "Andrea Villamor" },
    state: "private",
    my_level: "owner",
    live_row_count: 15,
    revision: 3,
    updated_at: "2026-11-21T08:30:00Z",
    is_deleted: false,
    deleted_at: null,
    anchor_title: "Andrea Villamor",
    module_name: "Faculty Members",
    shared: true,
    access_group: null,
    ...overrides,
  };
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("My sheets reads the complete list, newest change first, in the reader's words", async () => {
  const firstPage = Array.from({ length: 100 }, (_, index) =>
    wireSummary(index + 1),
  );
  const mock = installFetch((input) => {
    const url = new URL(String(input), "http://app.test");
    return url.searchParams.get("offset") === "0"
      ? json({
          items: firstPage,
          pagination: wirePagination({
            limit: 100,
            count: 100,
            total: 101,
            has_more: true,
          }),
        })
      : json({
          items: [
            wireSummary(101, {
              record_id: null,
              module_id: moduleId,
              my_level: "view",
              state: "open",
              anchor_title: "Faculty Members",
              shared: null,
              access_group: "CCS Faculty",
            }),
          ],
          pagination: wirePagination({
            limit: 100,
            offset: 100,
            count: 1,
            total: 101,
          }),
        });
  });
  try {
    const result = await listMyWorksheets({ deleted: "exclude" });

    expect(mock.requests.map(({ input }) => String(input))).toEqual([
      "/api/worksheets?limit=100&offset=0&sort_by=updated_at&sort_order=desc&deleted=exclude",
      "/api/worksheets?limit=100&offset=100&sort_by=updated_at&sort_order=desc&deleted=exclude",
    ]);
    expect(result.total).toBe(101);
    expect(result.items).toHaveLength(101);
    expect(result.items[0]).toEqual({
      id: sheetId(1),
      recordId,
      moduleId: null,
      title: "Class 1",
      owner: { id: ownerId, displayName: "Andrea Villamor" },
      state: "private",
      myLevel: "owner",
      liveRowCount: 15,
      revision: 3,
      updatedAt: "2026-11-21T08:30:00Z",
      isDeleted: false,
      deletedAt: null,
      anchorTitle: "Andrea Villamor",
      moduleName: "Faculty Members",
      shared: true,
      accessGroup: null,
    });
    expect(result.items[100]).toMatchObject({
      recordId: null,
      moduleId,
      myLevel: "view",
      state: "open",
    });
    expect(result.items[100]).toMatchObject({
      anchorTitle: "Faculty Members",
      shared: null,
      accessGroup: "CCS Faculty",
    });
  } finally {
    mock.restore();
  }
});

test("the Deleted list asks only for the person's own deleted sheets", async () => {
  const mock = installFetch(() =>
    json({
      items: [
        wireSummary(7, {
          is_deleted: true,
          deleted_at: "2026-11-19T02:00:00Z",
        }),
      ],
      pagination: wirePagination({ limit: 100, count: 1, total: 1 }),
    }),
  );
  try {
    const result = await listMyWorksheets({ deleted: "only" });
    expect(mock.requests.map(({ input }) => String(input))).toEqual([
      "/api/worksheets?limit=100&offset=0&sort_by=updated_at&sort_order=desc&deleted=only",
    ]);
    expect(result.items.map((item) => item.isDeleted)).toEqual([true]);
    expect(result.items.map((item) => item.deletedAt)).toEqual([
      "2026-11-19T02:00:00Z",
    ]);
  } finally {
    mock.restore();
  }
});

test("a sheet with an access level the screen does not know is refused", async () => {
  const mock = installFetch(() =>
    json({
      items: [wireSummary(1, { my_level: "admin" })],
      pagination: wirePagination({ limit: 100, count: 1, total: 1 }),
    }),
  );
  try {
    await expect(listMyWorksheets({ deleted: "exclude" })).rejects.toThrow(
      ApiContractError,
    );
  } finally {
    mock.restore();
  }
});

test("one sheet is read by its id and restored with a POST", async () => {
  const detail = {
    ...wireSummary(9),
    structure: {
      structureVersion: 1,
      nextColumnSeq: 3,
      columns: [
        { key: "c1", name: "Student", type: "text" },
        {
          key: "c2",
          name: "From roster",
          type: "sheet_lookup",
          state: "no_access",
        },
      ],
      groups: [],
      totals: { c1: "count" },
    },
    etag: `"${sheetId(9)}:3"`,
    created_at: "2026-11-01T08:30:00Z",
  };
  const mock = installFetch(() => json(detail));
  try {
    const read = await getWorksheet(sheetId(9));
    const restored = await restoreWorksheet(sheetId(9));

    expect(
      mock.requests.map(({ input, init }) => [
        String(input),
        init?.method ?? "GET",
      ]),
    ).toEqual([
      [`/api/worksheets/${sheetId(9)}`, "GET"],
      [`/api/worksheets/${sheetId(9)}/restore`, "POST"],
    ]);
    expect(read).toMatchObject({
      id: sheetId(9),
      title: "Class 9",
      etag: `"${sheetId(9)}:3"`,
      createdAt: "2026-11-01T08:30:00Z",
    });
    expect(read.structure.columns.map((column) => column.key)).toEqual([
      "c1",
      "c2",
    ]);
    expect(restored.id).toBe(sheetId(9));
  } finally {
    mock.restore();
  }
});

test("a record's and a module's sheets are read from their own lists", async () => {
  const mock = installFetch(() =>
    json({
      items: [wireSummary(3)],
      pagination: wirePagination({ limit: 100, count: 1, total: 1 }),
    }),
  );
  try {
    const onRecord = await listRecordWorksheets(recordId);
    const onModule = await listModuleWorksheets(moduleId);
    expect(mock.requests.map(({ input }) => String(input))).toEqual([
      `/api/records/${recordId}/worksheets?limit=100&offset=0&sort_by=updated_at&sort_order=desc&deleted=exclude`,
      `/api/modules/${moduleId}/worksheets?limit=100&offset=0&sort_by=updated_at&sort_order=desc&deleted=exclude`,
    ]);
    expect(onRecord).toMatchObject({ total: 1, items: [{ id: sheetId(3) }] });
    expect(onModule.total).toBe(1);
  } finally {
    mock.restore();
  }
});

test("a new blank sheet is created on exactly one record or module, with a trimmed name", async () => {
  const created = {
    ...wireSummary(11),
    structure: {
      structureVersion: 1,
      nextColumnSeq: 1,
      columns: [],
      groups: [],
      totals: {},
    },
    etag: `"${sheetId(11)}:1"`,
    created_at: "2026-11-22T08:30:00Z",
  };
  const mock = installFetch(() => json(created, 201));
  try {
    const sheet = await createWorksheet({ recordId, title: "  Class 4D  " });
    await createWorksheet({ moduleId, title: "Visit plan" });

    expect(
      mock.requests.map(({ input, init }) => [
        String(input),
        init?.method,
        JSON.parse(String(init?.body)),
      ]),
    ).toEqual([
      [
        "/api/worksheets",
        "POST",
        { record_id: recordId, title: "Class 4D", source: { kind: "blank" } },
      ],
      [
        "/api/worksheets",
        "POST",
        { module_id: moduleId, title: "Visit plan", source: { kind: "blank" } },
      ],
    ]);
    expect(sheet.id).toBe(sheetId(11));
  } finally {
    mock.restore();
  }
});

test("a sheet's rows are read a page at a time with its sort and search", async () => {
  const page = {
    items: [
      {
        id: sheetId(21),
        revision: 2,
        etag: `"${sheetId(21)}:2"`,
        position: 0,
        cells: {
          c1: { link: { record_id: recordId, label: "Ana Cruz" } },
          c2: { state: "no_access" },
          c3: { value: 18 },
          c4: { unlinked: "A. Cruz" },
        },
      },
    ],
    pagination: {
      limit: 200,
      offset: 200,
      count: 1,
      total: 201,
      has_more: false,
    },
    totals: { c3: { fn: "average", value: "17.5", hidden_count: 0 } },
  };
  const mock = installFetch(() => json(page));
  try {
    const result = await queryWorksheetRows(sheetId(9), {
      sort: { key: "c3", order: "desc" },
      search: "an",
      offset: 200,
    });
    expect(
      mock.requests.map(({ input, init }) => [
        String(input),
        init?.method,
        JSON.parse(String(init?.body)),
      ]),
    ).toEqual([
      [
        `/api/worksheets/${sheetId(9)}/rows/query`,
        "POST",
        {
          limit: 200,
          offset: 200,
          sort: { key: "c3", order: "desc" },
          search: "an",
        },
      ],
    ]);
    expect(result).toEqual({
      rows: page.items,
      total: 201,
      totals: page.totals,
    });
  } finally {
    mock.restore();
  }
});

test("an empty search and no sort are not sent", async () => {
  const mock = installFetch(() =>
    json({
      items: [],
      pagination: {
        limit: 200,
        offset: 0,
        count: 0,
        total: 0,
        has_more: false,
      },
      totals: {},
    }),
  );
  try {
    await queryWorksheetRows(sheetId(9), {
      sort: null,
      search: "  ",
      offset: 0,
    });
    expect(JSON.parse(String(mock.requests[0]?.init?.body))).toEqual({
      limit: 200,
      offset: 0,
    });
  } finally {
    mock.restore();
  }
});
