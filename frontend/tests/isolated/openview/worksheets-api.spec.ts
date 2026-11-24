import { expect, test } from "@playwright/test";
import { ApiContractError, ApiError } from "../../../src/lib/api";
import {
  createWorksheet,
  getWorksheet,
  listModuleWorksheets,
  listMyWorksheets,
  listRecordWorksheets,
  queryWorksheetRows,
  restoreWorksheet,
  renameWorksheet,
  deleteWorksheet,
  listWorksheetHistory,
  listWorksheetShares,
  shareWorksheet,
  changeWorksheetShare,
  removeWorksheetShare,
  searchWorksheetShareCandidates,
  searchWorksheetPeople,
  exportWorksheet,
  saveWorksheetStructure,
  editableColumn,
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

// ---------------------------------------------------------------- F5

const personId = "00000000-0000-4000-8000-0000000005c1";
const groupId = "00000000-0000-4000-8000-0000000005c2";
const shareOne = "00000000-0000-4000-8000-0000000005c3";
const shareTwo = "00000000-0000-4000-8000-0000000005c4";

function sent(mock: ReturnType<typeof installFetch>) {
  return mock.requests.map(({ input, init }) => ({
    url: String(input),
    method: init?.method ?? "GET",
    ifMatch: new Headers(init?.headers).get("If-Match"),
    body: init?.body ? JSON.parse(String(init.body)) : null,
  }));
}

test("rename and delete send the sheet's version, and delete expects no body", async () => {
  const detail = {
    ...wireSummary(9, { title: "Class 1B" }),
    structure: {
      structureVersion: 1,
      nextColumnSeq: 1,
      columns: [],
      groups: [],
      totals: {},
    },
    etag: `"${sheetId(9)}:4"`,
    created_at: "2026-11-01T08:30:00Z",
  };
  const mock = installFetch((_input, init) =>
    init?.method === "DELETE"
      ? new Response(null, { status: 204 })
      : json(detail),
  );
  try {
    const renamed = await renameWorksheet(
      sheetId(9),
      `"${sheetId(9)}:3"`,
      "  Class 1B ",
    );
    const deleted = await deleteWorksheet(sheetId(9), `"${sheetId(9)}:4"`);
    expect(sent(mock)).toEqual([
      {
        url: `/api/worksheets/${sheetId(9)}`,
        method: "PATCH",
        ifMatch: `"${sheetId(9)}:3"`,
        body: { title: "Class 1B" },
      },
      {
        url: `/api/worksheets/${sheetId(9)}`,
        method: "DELETE",
        ifMatch: `"${sheetId(9)}:4"`,
        body: null,
      },
    ]);
    expect(renamed).toMatchObject({
      title: "Class 1B",
      etag: `"${sheetId(9)}:4"`,
    });
    expect(deleted).toBeNull();
  } finally {
    mock.restore();
  }
});

test("history is read newest first, with an unknown author kept as null", async () => {
  const mock = installFetch(() =>
    json({
      items: [
        {
          id: shareOne,
          row_id: shareTwo,
          revision: 2,
          action: "update",
          changed_keys: ["c3"],
          cells: {
            c1: { link: { record_id: personId, label: "Alyssa Mercado" } },
            c2: { state: "no_access" },
            c3: { value: 18 },
            c4: { value: null, error: "division_by_zero" },
          },
          author: null,
          created_at: "2026-11-22T09:00:00Z",
        },
      ],
      pagination: wirePagination({
        limit: 50,
        count: 1,
        total: 51,
        has_more: true,
      }),
    }),
  );
  try {
    const page = await listWorksheetHistory(sheetId(9), { offset: 0 });
    expect(sent(mock).map((request) => request.url)).toEqual([
      `/api/worksheets/${sheetId(9)}/history?limit=50&offset=0&sort_order=desc`,
    ]);
    expect(page).toEqual({
      hasMore: true,
      items: [
        {
          id: shareOne,
          rowId: shareTwo,
          revision: 2,
          action: "update",
          changedKeys: ["c3"],
          cells: {
            c1: { link: { record_id: personId, label: "Alyssa Mercado" } },
            c2: { state: "no_access" },
            c3: { value: 18 },
            c4: { value: null, error: "division_by_zero" },
          },
          author: null,
          createdAt: "2026-11-22T09:00:00Z",
        },
      ],
    });
  } finally {
    mock.restore();
  }
});

test("shares are read in full and keep a person who is no longer listed", async () => {
  const share = (id: string, extra: Record<string, unknown>) => ({
    id,
    level: "view",
    created_at: "2026-11-20T08:00:00Z",
    user: null,
    group: null,
    ...extra,
  });
  const mock = installFetch((input) =>
    new URL(String(input), "http://app.test").searchParams.get("offset") === "0"
      ? json({
          items: [
            share(shareOne, {
              subject: "user",
              level: "edit",
              user: {
                id: personId,
                display_name: "Diego Navarro",
                is_guest: false,
              },
            }),
          ],
          pagination: wirePagination({
            limit: 100,
            count: 1,
            total: 3,
            has_more: true,
          }),
        })
      : json({
          items: [
            share(shareTwo, {
              subject: "group",
              group: { id: groupId, name: "CCS Faculty", member_count: 12 },
            }),
            share(sheetId(77), { subject: "user" }),
          ],
          pagination: wirePagination({
            limit: 100,
            offset: 1,
            count: 2,
            total: 3,
          }),
        }),
  );
  try {
    const shares = await listWorksheetShares(sheetId(9));
    expect(sent(mock).map((request) => request.url)).toEqual([
      `/api/worksheets/${sheetId(9)}/shares?limit=100&offset=0`,
      `/api/worksheets/${sheetId(9)}/shares?limit=100&offset=1`,
    ]);
    expect(shares).toEqual([
      {
        id: shareOne,
        level: "edit",
        subject: "user",
        person: { id: personId, displayName: "Diego Navarro", isGuest: false },
      },
      {
        id: shareTwo,
        level: "view",
        subject: "group",
        group: { id: groupId, name: "CCS Faculty", memberCount: 12 },
      },
      { id: sheetId(77), level: "view", subject: "user", person: null },
    ]);
  } finally {
    mock.restore();
  }
});

test("a share names one person or one group, and a level change or removal names the share", async () => {
  const mock = installFetch((_input, init) =>
    init?.method === "DELETE"
      ? new Response(null, { status: 204 })
      : json(
          {
            id: shareOne,
            subject: "group",
            user: null,
            group: { id: groupId, name: "CCS Faculty", member_count: 12 },
            level: "view",
            created_at: "2026-11-20T08:00:00Z",
          },
          init?.method === "POST" ? 201 : 200,
        ),
  );
  try {
    await shareWorksheet(sheetId(9), { subject: "user", id: personId }, "edit");
    const made = await shareWorksheet(
      sheetId(9),
      { subject: "group", id: groupId },
      "view",
    );
    await changeWorksheetShare(sheetId(9), shareOne, "edit");
    await removeWorksheetShare(sheetId(9), shareOne);
    expect(
      sent(mock).map(({ url, method, body }) => [method, url, body]),
    ).toEqual([
      [
        "POST",
        `/api/worksheets/${sheetId(9)}/shares`,
        { subject: "user", user_id: personId, level: "edit" },
      ],
      [
        "POST",
        `/api/worksheets/${sheetId(9)}/shares`,
        { subject: "group", group_id: groupId, level: "view" },
      ],
      [
        "PATCH",
        `/api/worksheets/${sheetId(9)}/shares/${shareOne}`,
        { level: "edit" },
      ],
      ["DELETE", `/api/worksheets/${sheetId(9)}/shares/${shareOne}`, null],
    ]);
    expect(made).toEqual({
      id: shareOne,
      level: "view",
      subject: "group",
      group: { id: groupId, name: "CCS Faculty", memberCount: 12 },
    });
  } finally {
    mock.restore();
  }
});

test("share candidates and the people list search by trimmed text", async () => {
  const mock = installFetch((input) =>
    String(input).includes("/people")
      ? json({ people: [{ id: personId, display_name: "Diego Navarro" }] })
      : json({
          people: [
            { id: personId, display_name: "Diego Navarro", is_guest: true },
          ],
          groups: [{ id: groupId, name: "CCS Faculty", member_count: 1 }],
        }),
  );
  try {
    const candidates = await searchWorksheetShareCandidates(
      sheetId(9),
      "  die & co ",
    );
    const people = await searchWorksheetPeople(sheetId(9), "");
    expect(sent(mock).map((request) => request.url)).toEqual([
      `/api/worksheets/${sheetId(9)}/share-candidates?q=die+%26+co`,
      `/api/worksheets/${sheetId(9)}/people?q=`,
    ]);
    expect(candidates).toEqual({
      people: [{ id: personId, displayName: "Diego Navarro", isGuest: true }],
      groups: [{ id: groupId, name: "CCS Faculty", memberCount: 1 }],
    });
    expect(people).toEqual([{ id: personId, displayName: "Diego Navarro" }]);
  } finally {
    mock.restore();
  }
});

test("an export is a named attachment of the asked type, and a refusal keeps its code", async () => {
  const file = (type: string, name: string) =>
    new Response("Student,Quiz 1\nAlyssa,17\n", {
      status: 200,
      headers: {
        "Content-Type": type,
        "Content-Disposition": `attachment; filename="${name}"`,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  const answers = [
    file("text/csv; charset=utf-8", "class-1a-2026-11-24.csv"),
    file("application/json", "class-1a-template.json"),
    file("text/csv; charset=utf-8", "class-1a-2026-11-24.xlsx"),
    json(
      { detail: { code: "export_limit_exceeded", message: "Too many rows" } },
      422,
    ),
  ];
  const mock = installFetch(() => answers.shift() ?? json({}, 500));
  try {
    const csv = await exportWorksheet(sheetId(9), "csv");
    const template = await exportWorksheet(sheetId(9), "template");
    expect(csv.filename).toBe("class-1a-2026-11-24.csv");
    expect(await csv.blob.text()).toContain("Alyssa,17");
    expect(template.filename).toBe("class-1a-template.json");
    // An Excel request answered with a CSV file is not a download.
    await expect(exportWorksheet(sheetId(9), "xlsx")).rejects.toBeInstanceOf(
      ApiContractError,
    );
    const refused = await exportWorksheet(sheetId(9), "csv").catch(
      (error: unknown) => error,
    );
    expect(refused).toBeInstanceOf(ApiError);
    expect(refused).toMatchObject({
      status: 422,
      code: "export_limit_exceeded",
    });
    expect(
      sent(mock).map(({ method, url, body }) => [method, url, body]),
    ).toEqual(
      ["csv", "template", "xlsx", "csv"].map((format) => [
        "POST",
        `/api/worksheets/${sheetId(9)}/export`,
        { format },
      ]),
    );
  } finally {
    mock.restore();
  }
});

test("a computed cell that cannot be worked out, and a lookup with several matches, keep their marks instead of failing the page", async () => {
  const mock = installFetch(() =>
    json({
      items: [
        {
          id: sheetId(31),
          revision: 1,
          etag: `"${sheetId(31)}:1"`,
          position: 0,
          cells: {
            c3: { value: "22.5" },
            c4: { value: null, error: "division_by_zero" },
            c5: { value: null, error: "overflow" },
            c6: { state: "multiple_matches", count: 3 },
          },
        },
      ],
      pagination: {
        limit: 200,
        offset: 0,
        count: 1,
        total: 1,
        has_more: false,
      },
      totals: {},
    }),
  );
  try {
    const page = await queryWorksheetRows(sheetId(9), {
      sort: null,
      search: "",
      offset: 0,
    });
    expect(page.rows[0]?.cells).toEqual({
      c3: { value: "22.5" },
      c4: { value: null, error: "division_by_zero" },
      c5: { value: null, error: "overflow" },
      c6: { state: "multiple_matches", count: 3 },
    });
  } finally {
    mock.restore();
  }
});

test("a long stored expression reads, and a save sends a hidden-source column back as it came", async () => {
  // The stored form names keys and may be longer than the typed text (D7.1).
  const expression = Array.from({ length: 250 }, () => "{c1}").join(" + ");
  const hidden = {
    key: "c3",
    name: "From roster",
    type: "sheet_lookup",
    state: "no_access",
  } as const;
  const detail = {
    ...wireSummary(9),
    structure: {
      structureVersion: 1,
      nextColumnSeq: 4,
      columns: [
        { key: "c1", name: "Quiz", type: "int" },
        {
          key: "c2",
          name: "Total",
          type: "computed",
          computed: { expression, places: 2 },
        },
        hidden,
      ],
      groups: [{ name: "Prelim", keys: ["c1", "c2"] }],
      totals: {},
    },
    etag: `"${sheetId(9)}:3"`,
    created_at: "2026-11-01T08:30:00Z",
  };
  const mock = installFetch(() => json(detail));
  try {
    const read = await getWorksheet(sheetId(9));
    expect(expression.length).toBeGreaterThan(1000);
    expect(read.structure.columns[1]).toEqual({
      key: "c2",
      name: "Total",
      type: "computed",
      computed: { expression, places: 2 },
    });
    await saveWorksheetStructure(sheetId(9), `"${sheetId(9)}:3"`, {
      columns: read.structure.columns.map(editableColumn),
      groups: read.structure.groups,
      totals: {},
    });
    const sent = JSON.parse(String(mock.requests[1]?.init?.body)) as {
      columns: unknown[];
    };
    expect(sent.columns[2]).toEqual(hidden);
  } finally {
    mock.restore();
  }
});

test("a sheet list longer than the read's bound fails instead of showing part of it", async () => {
  let offset = 0;
  const mock = installFetch((input) => {
    offset = Number(
      new URL(String(input), "http://localhost").searchParams.get("offset"),
    );
    return json({
      items: Array.from({ length: 100 }, (_, index) =>
        wireSummary(offset + index + 1),
      ),
      pagination: wirePagination({
        limit: 100,
        offset,
        count: 100,
        total: 5_100,
        has_more: true,
      }),
    });
  });
  try {
    await expect(listMyWorksheets({ deleted: "exclude" })).rejects.toThrow(
      "The sheet list is longer than one read allows",
    );
    expect(mock.requests).toHaveLength(50);
  } finally {
    mock.restore();
  }
});

test("a From another sheet column carries its options or the no-access mark, never both or neither", async () => {
  const detail = (column: Record<string, unknown>) => ({
    ...wireSummary(1),
    structure: {
      structureVersion: 1,
      nextColumnSeq: 3,
      columns: [
        { key: "c1", name: "Student", type: "link", link: { moduleId } },
        { key: "c2", name: "Grade in 1A", type: "sheet_lookup", ...column },
      ],
      groups: [],
      totals: {},
    },
    etag: '"s:1"',
    created_at: "2026-11-01T08:30:00Z",
  });
  const options = {
    sheet_lookup: {
      sourceWorksheetId: sheetId(9),
      sourceColumnKey: "c4",
      linkKey: "c1",
      sourceLinkKey: "c1",
    },
  };
  for (const [column, accepted] of [
    [options, true],
    [{ state: "no_access" }, true],
    [{ ...options, state: "no_access" }, false],
    [{}, false],
  ] as const) {
    const mock = installFetch(() => json(detail(column)));
    try {
      const read = getWorksheet(sheetId(1));
      if (accepted)
        expect((await read).structure.columns[1]?.name).toBe("Grade in 1A");
      else await expect(read).rejects.toThrow(ApiContractError);
    } finally {
      mock.restore();
    }
  }
});
