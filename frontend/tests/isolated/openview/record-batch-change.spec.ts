import { expect, test } from "@playwright/test";

import type { RecordBatchResult } from "../../../src/components/systems/openview/adapters/record-batch-api";
import type {
  OpenViewDataSourceField,
  OpenViewQueryDefinition,
  OpenViewRecord,
} from "../../../src/components/systems/openview/adapters/views-api";
import {
  changeItems,
  changeOptions,
  finalChangeLabel,
  headerSelectionState,
  replacedByShowOnly,
  runListChange,
  selectedOnPage,
  selectionLabel,
  showOnlyOffered,
  toggleAllRows,
  toggleRow,
  undoSent,
  type SentRecord,
} from "../../../src/components/systems/openview/domain/record-batch-change";
import { ApiError } from "../../../src/lib/api";

// List actions of the OpenView table (candidates 1 and 5 of
// docs/specs/subtle-interactions.md): when "Show only" is offered, which
// values a field changes to, which rows a change sends, the selection rules,
// the page status words, and the Undo items.

const moduleId = "00000000-0000-4000-8000-000000000901";
const statusId = "00000000-0000-4000-8000-000000000911";
const paidId = "00000000-0000-4000-8000-000000000912";
const nameId = "00000000-0000-4000-8000-000000000913";
const ownerId = "00000000-0000-4000-8000-000000000914";
const rowId = (index: number) =>
  `00000000-0000-4000-8000-${String(920 + index).padStart(12, "0")}`;

function field(
  id: string,
  name: string,
  type: string,
  extra: Partial<OpenViewDataSourceField> = {},
): OpenViewDataSourceField {
  return {
    id,
    name,
    type,
    required: false,
    position: 0,
    config: {},
    ...extra,
  } as OpenViewDataSourceField;
}

const statusOptions = {
  options: [
    { id: "active", label: "Active" },
    { id: "former", label: "Former" },
  ],
};
const status = field(statusId, "Status", "select", {
  required: true,
  config: statusOptions,
});
const optionalStatus = field(statusId, "Status", "select", {
  config: statusOptions,
});
const paid = field(paidId, "Paid", "boolean");
const fields = [
  status,
  paid,
  field(nameId, "Name", "text"),
  field(ownerId, "Owner", "user"),
];

function row(
  index: number,
  data: Record<string, unknown>,
  updatedAt = `2026-11-13T08:0${index}:00Z`,
): OpenViewRecord {
  return {
    id: rowId(index),
    moduleId,
    data,
    displayValues: {},
    createdAt: "2026-11-01T08:00:00Z",
    updatedAt,
    deletedAt: null,
    isDeleted: false,
    performedBy: null,
  };
}

type Filter = OpenViewQueryDefinition["filters"][number];
const eq = (fieldId: string, value: unknown): Filter =>
  ({ fieldId, expectedType: "select", operator: "eq", value }) as Filter;

test("SI-C1.5 Show only is offered under All conditions only, and not for the condition already applied", () => {
  const cases: {
    case: string;
    logic: "and" | "or";
    filters: Filter[];
    value: unknown;
    offered: boolean;
  }[] = [
    {
      case: "no condition",
      logic: "and",
      filters: [],
      value: "former",
      offered: true,
    },
    {
      case: "All conditions, another field",
      logic: "and",
      filters: [eq(nameId, "Pump")],
      value: "former",
      offered: true,
    },
    {
      case: "All conditions, another value on the field",
      logic: "and",
      filters: [eq(statusId, "active")],
      value: "former",
      offered: true,
    },
    {
      case: "the same condition is applied",
      logic: "and",
      filters: [eq(statusId, "former")],
      value: "former",
      offered: false,
    },
    {
      case: "Any condition with one applied condition",
      logic: "or",
      filters: [eq(nameId, "Pump")],
      value: "former",
      offered: false,
    },
    {
      case: "Any condition with two applied conditions",
      logic: "or",
      filters: [eq(nameId, "Pump"), eq(statusId, "active")],
      value: "former",
      offered: false,
    },
    {
      case: "Any condition whose only row is unfinished",
      logic: "or",
      filters: [eq(nameId, "")],
      value: "former",
      offered: true,
    },
    {
      case: "an empty value",
      logic: "and",
      filters: [],
      value: null,
      offered: false,
    },
  ];
  for (const item of cases)
    expect(
      showOnlyOffered(
        { logic: item.logic, filters: item.filters },
        statusId,
        item.value,
      ),
      item.case,
    ).toBe(item.offered);
});

test("DR-SI-1.4 Show only replaces every applied condition on its field and keeps the rest", () => {
  const cases: { case: string; filter: Filter; replaced: boolean }[] = [
    { case: "is Active", filter: eq(statusId, "active"), replaced: true },
    {
      case: "is not Prospect",
      filter: { ...eq(statusId, "prospect"), operator: "neq" } as Filter,
      replaced: true,
    },
    { case: "an unfinished row", filter: eq(statusId, ""), replaced: false },
    { case: "another field", filter: eq(nameId, "Pump"), replaced: false },
  ];
  for (const item of cases)
    expect(replacedByShowOnly(item.filter, statusId), item.case).toBe(
      item.replaced,
    );
});

test("SI-C1.13 a required Choice list offers no None, an optional one offers None last, a Checkbox On and Off", () => {
  expect(changeOptions(status)).toEqual([
    { value: "active", label: "Active" },
    { value: "former", label: "Former" },
  ]);
  expect(changeOptions(optionalStatus)).toEqual([
    { value: "active", label: "Active" },
    { value: "former", label: "Former" },
    { value: null, label: "None" },
  ]);
  expect(changeOptions(paid)).toEqual([
    { value: true, label: "On" },
    { value: false, label: "Off" },
  ]);
});

test("SI-C1.13 a pick of the value a record holds sends nothing; another value sends the row's revision", () => {
  const former = row(1, { [statusId]: "former" });
  const blank = row(2, { [statusId]: "" });
  expect(changeItems([former], statusId, "former")).toEqual([]);
  // A stored empty value already is "None".
  expect(changeItems([blank], statusId, null)).toEqual([]);
  expect(changeItems([former], statusId, "active")).toEqual([
    {
      recordId: rowId(1),
      revision: "2026-11-13T08:01:00Z",
      fieldId: statusId,
      value: "active",
    },
  ]);
});

test("SI-C5.2 the final action counts only the rows that change, and SI-5.5 caps a request at 100", () => {
  const rows = Array.from({ length: 10 }, (_, index) =>
    row(index, { [statusId]: index < 2 ? "former" : "active" }),
  );
  expect(changeItems(rows, statusId, "former")).toHaveLength(8);
  const cases = [
    {
      input: { selected: 10, picked: false, changing: 0 },
      label: { label: "Change records", enabled: false },
    },
    {
      input: { selected: 10, picked: true, changing: 8 },
      label: { label: "Change 8 records", enabled: true },
    },
    {
      input: { selected: 10, picked: true, changing: 1 },
      label: { label: "Change 1 record", enabled: true },
    },
    {
      input: { selected: 10, picked: true, changing: 0 },
      label: { label: "All 10 already have this value", enabled: false },
    },
    {
      input: { selected: 101, picked: true, changing: 101 },
      label: { label: "Select at most 100 records", enabled: false },
    },
  ];
  for (const item of cases)
    expect(finalChangeLabel(item.input), JSON.stringify(item.input)).toEqual(
      item.label,
    );
});

test("SI-C5.1 a click toggles one row, Shift-click selects the range, and the header selects the page", () => {
  const page = [rowId(1), rowId(2), rowId(3), rowId(4)];
  const first = toggleRow({ ids: [], anchor: null }, page, rowId(1), false);
  expect(first).toEqual({ ids: [rowId(1)], anchor: rowId(1) });
  const range = toggleRow(first, page, rowId(4), true);
  expect(range.ids).toEqual(page);
  expect(toggleRow(range, page, rowId(2), false).ids).toEqual([
    rowId(1),
    rowId(3),
    rowId(4),
  ]);
  expect(toggleAllRows({ ids: [rowId(2)], anchor: null }, page).ids).toEqual(
    page,
  );
  expect(toggleAllRows({ ids: page, anchor: null }, page).ids).toEqual([]);
  // DR-SI-5.10: a re-read keeps only the selected rows still on the page.
  expect(
    selectedOnPage({ ids: [rowId(1), rowId(9)], anchor: null }, page),
  ).toEqual([rowId(1)]);
  // DR-SI-5.1: a row with no title still has a named box.
  expect(selectionLabel("Ana Cruz")).toBe("Select Ana Cruz");
  expect(selectionLabel("—")).toBe("Select record");
  expect(selectionLabel("")).toBe("Select record");
  expect(selectionLabel(undefined)).toBe("Select record");
  expect(headerSelectionState(0, 4)).toBe("none");
  expect(headerSelectionState(2, 4)).toBe("some");
  expect(headerSelectionState(4, 4)).toBe("all");
});

const sentRows: SentRecord[] = [
  { recordId: rowId(1), title: "Ana Cruz", previous: "active" },
  { recordId: rowId(2), title: "Ben Ortiz", previous: "active" },
  { recordId: rowId(3), title: "Chen Wu", previous: "active" },
  { recordId: rowId(4), title: "Dana Lim", previous: "active" },
  { recordId: rowId(5), title: "Eli Park", previous: "active" },
];

function updated(index: number, updatedAt: string): RecordBatchResult {
  return {
    status: "updated",
    recordId: rowId(index),
    record: row(index, { [statusId]: "former" }, updatedAt),
  };
}

const mixedResults: RecordBatchResult[] = [
  updated(1, "2026-11-13T09:01:00Z"),
  updated(2, "2026-11-13T09:02:00Z"),
  { status: "stale", recordId: rowId(3) },
  { status: "forbidden", recordId: rowId(4) },
  {
    status: "invalid",
    recordId: rowId(5),
    errors: [
      {
        code: "invalid_user",
        fieldId: ownerId,
        message: "Choose a person who can read this module",
      },
    ],
    truncated: false,
  },
];

function change(options: {
  results?: RecordBatchResult[];
  error?: unknown;
  scope: "cell" | "selection";
  undo?: boolean;
  sent?: SentRecord[];
  value?: unknown;
}) {
  const sent = options.sent ?? sentRows;
  return runListChange({
    field: status,
    fields,
    sent,
    items: sent.map((record) => ({
      recordId: record.recordId,
      revision: "2026-11-13T08:00:00Z",
      fieldId: statusId,
      value: options.value ?? "former",
    })),
    scope: options.scope,
    undo: options.undo ?? false,
    send: async () => {
      if (options.error) throw options.error;
      return options.results ?? [];
    },
  });
}

test("SI-C5.6 Undo covers only the updated records, each with its previous value and the revision the change returned", async () => {
  const outcome = await change({ results: mixedResults, scope: "selection" });
  expect(outcome.notice.undo?.items).toEqual([
    {
      recordId: rowId(1),
      revision: "2026-11-13T09:01:00Z",
      fieldId: statusId,
      value: "active",
    },
    {
      recordId: rowId(2),
      revision: "2026-11-13T09:02:00Z",
      fieldId: statusId,
      value: "active",
    },
  ]);
  expect(outcome.updated.map((record) => record.id)).toEqual([
    rowId(1),
    rowId(2),
  ]);
  expect(outcome.readAgain).toBe(true);
  // The Undo's own request names the two records by their titles.
  expect(undoSent(outcome.notice.undo!).map((record) => record.title)).toEqual([
    "Ana Cruz",
    "Ben Ortiz",
  ]);
});

test("DR-SI-5.8 a bulk change names how many changed and lists each record that did not, with its reason", async () => {
  const partial = await change({ results: mixedResults, scope: "selection" });
  expect(partial.notice).toMatchObject({
    message: "Status changed on 2 records.",
    notChangedLabel: "3 not changed",
    notChanged: [
      { recordId: rowId(3), title: "Chen Wu", reason: "Someone changed it" },
      { recordId: rowId(4), title: "Dana Lim", reason: "You cannot change it" },
      {
        recordId: rowId(5),
        title: "Eli Park",
        reason: "Not valid: Owner: Choose a person who can read this module.",
      },
    ],
  });

  const cases: {
    case: string;
    results?: RecordBatchResult[];
    error?: unknown;
    message: string;
    label: string | null;
    reference?: string;
    undo: boolean;
    readAgain: boolean;
  }[] = [
    {
      case: "all updated",
      results: [1, 2, 3, 4, 5].map((index) =>
        updated(index, "2026-11-13T09:00:00Z"),
      ),
      message: "Status changed on 5 records.",
      label: null,
      undo: true,
      readAgain: false,
    },
    {
      case: "none updated",
      results: sentRows.map((record) => ({
        status: "stale" as const,
        recordId: record.recordId,
      })),
      message: "No records changed.",
      label: "5 not changed",
      undo: false,
      readAgain: true,
    },
    {
      case: "a request failure",
      error: new ApiError(
        500,
        "Internal error",
        undefined,
        undefined,
        undefined,
        "req-500",
      ),
      message: "No records changed. Try again.",
      label: null,
      reference: "req-500",
      undo: false,
      readAgain: false,
    },
    {
      case: "an unconfirmed outcome (N-1)",
      error: new ApiError(503, "Batch outcome could not be confirmed"),
      message: "The result could not be confirmed.",
      label: null,
      undo: false,
      readAgain: true,
    },
  ];
  for (const item of cases) {
    const outcome = await change({
      results: item.results,
      error: item.error,
      scope: "selection",
    });
    expect(outcome.notice.message, item.case).toBe(item.message);
    expect(outcome.notice.notChangedLabel, item.case).toBe(item.label);
    expect(outcome.notice.reference, item.case).toBe(item.reference);
    expect(outcome.notice.undo !== null, item.case).toBe(item.undo);
    expect(outcome.readAgain, item.case).toBe(item.readAgain);
  }
});

test("DR-SI-1.9 a cell change reports in the Status words, and a refusal offers no Undo", async () => {
  const one = [sentRows[0]];
  const cases: {
    case: string;
    results?: RecordBatchResult[];
    error?: unknown;
    message: string;
    reference?: string;
    undo: boolean;
  }[] = [
    {
      case: "updated",
      results: [updated(1, "2026-11-13T09:01:00Z")],
      message: "Status changed to Former.",
      undo: true,
    },
    {
      case: "stale",
      results: [{ status: "stale", recordId: rowId(1) }],
      message:
        "Status not changed. Someone changed this record; it shows their value now.",
      undo: false,
    },
    {
      case: "forbidden",
      results: [{ status: "forbidden", recordId: rowId(1) }],
      message: "Status not changed. You cannot change this record.",
      undo: false,
    },
    {
      case: "invalid on another field (N-8)",
      results: [
        { ...mixedResults[4], recordId: rowId(1) } as RecordBatchResult,
      ],
      message:
        "Status not changed. Owner: Choose a person who can read this module.",
      undo: false,
    },
    {
      case: "a request failure",
      error: new ApiError(
        502,
        "Bad gateway",
        undefined,
        undefined,
        undefined,
        "req-502",
      ),
      message: "Status not changed. Try again.",
      reference: "req-502",
      undo: false,
    },
    {
      case: "an unconfirmed outcome (N-1)",
      error: new ApiError(503, "Batch outcome could not be confirmed"),
      message: "The result could not be confirmed.",
      undo: false,
    },
  ];
  for (const item of cases) {
    const outcome = await change({
      results: item.results,
      error: item.error,
      scope: "cell",
      sent: one,
    });
    expect(outcome.notice.message, item.case).toBe(item.message);
    expect(outcome.notice.reference, item.case).toBe(item.reference);
    expect(outcome.notice.undo !== null, item.case).toBe(item.undo);
  }
});

test("DR-SI-1.8 and DR-SI-5.9 an Undo reports what went back, offers no further Undo, and a failed request keeps the offer", async () => {
  const cell = await change({
    results: [updated(1, "2026-11-13T09:05:00Z")],
    scope: "cell",
    undo: true,
    sent: [sentRows[0]],
    value: "active",
  });
  expect(cell.notice.message).toBe("Status changed back to Active.");
  expect(cell.notice.undo).toBeNull();

  const cellConflict = await change({
    results: [{ status: "stale", recordId: rowId(1) }],
    scope: "cell",
    undo: true,
    sent: [sentRows[0]],
    value: "active",
  });
  expect(cellConflict.notice.message).toBe(
    "Not undone. Someone changed this record after you.",
  );
  expect(cellConflict.readAgain).toBe(true);

  const back = await change({
    results: [1, 2, 3, 4, 5].map((index) =>
      updated(index, "2026-11-13T09:00:00Z"),
    ),
    scope: "selection",
    undo: true,
  });
  expect(back.notice.message).toBe("Status changed back on 5 records.");
  expect(back.notice.undo).toBeNull();

  const oneBack = await change({
    results: [updated(1, "2026-11-13T09:00:00Z")],
    scope: "selection",
    undo: true,
    sent: [sentRows[0]],
  });
  expect(oneBack.notice.message).toBe("Status changed back on 1 record.");

  const noneBack = await change({
    results: sentRows.map((record) => ({
      status: "stale" as const,
      recordId: record.recordId,
    })),
    scope: "selection",
    undo: true,
  });
  expect(noneBack.notice).toMatchObject({
    message: "No records changed back.",
    notChangedLabel: "5 not changed back",
  });
  expect(noneBack.notice.notChanged).toHaveLength(5);

  // DR-SI-1.8 with DR-SI-1.9: a refused cell Undo names the server's field.
  const cellRefusals: { results: RecordBatchResult[]; message: string }[] = [
    {
      results: [
        { ...mixedResults[4], recordId: rowId(1) } as RecordBatchResult,
      ],
      message: "Not undone. Owner: Choose a person who can read this module.",
    },
    {
      results: [{ status: "forbidden", recordId: rowId(1) }],
      message: "Not undone. You cannot change this record.",
    },
  ];
  for (const item of cellRefusals) {
    const refused = await change({
      results: item.results,
      scope: "cell",
      undo: true,
      sent: [sentRows[0]],
      value: "active",
    });
    expect(refused.notice.message).toBe(item.message);
    expect(refused.notice.undo).toBeNull();
  }

  const partBack = await change({
    results: [
      ...[1, 2, 3, 4].map((index) => updated(index, "2026-11-13T09:00:00Z")),
      { status: "stale", recordId: rowId(5) },
    ],
    scope: "selection",
    undo: true,
  });
  expect(partBack.notice).toMatchObject({
    message: "4 changed back.",
    notChangedLabel: "1 not changed back",
    notChanged: [
      { recordId: rowId(5), title: "Eli Park", reason: "Someone changed it" },
    ],
  });

  const failed = await change({
    error: new ApiError(
      500,
      "Internal error",
      undefined,
      undefined,
      undefined,
      "req-9",
    ),
    scope: "selection",
    undo: true,
  });
  expect(failed.notice.message).toBe("Not undone. Try again.");
  expect(failed.notice.reference).toBe("req-9");
  expect(failed.keepUndo).toBe(true);
});
