import { expect, test } from "@playwright/test";
import type {
  OpenViewDataSourceField,
  OpenViewQueryDefinition,
} from "../../../src/components/systems/openview/adapters/views-api";
import {
  emptyDefinition,
  emptyPresentation,
} from "../../../src/components/systems/openview/domain/server-view-draft";
import { decodeTemporaryView } from "../../../src/components/systems/openview/domain/temporary-view";
import {
  groupCondition,
  widgetLinkChanges,
  widgetLinkDefinition,
  windowConditions,
  zonedMidnight,
  type WidgetLinkInput,
} from "../../../src/components/systems/openview/domain/widget-records-link";

// docs/specs/subtle-interactions.md, candidate 6 (SI-0.1, SI-6.1 to SI-6.4,
// DR-SI-6.2, DR-SI-6.3, DR-SI-6.6): a dashboard link opens exactly the
// records its figure or group row counts, or there is no link.

const moduleId = "00000000-0000-4000-8000-0000000006a1";
const ids = {
  status: "00000000-0000-4000-8000-0000000006b1",
  name: "00000000-0000-4000-8000-0000000006b2",
  closedOn: "00000000-0000-4000-8000-0000000006b3",
  createdAt: "00000000-0000-4000-8000-0000000006b4",
  owner: "00000000-0000-4000-8000-0000000006b5",
  active: "00000000-0000-4000-8000-0000000006b6",
  amount: "00000000-0000-4000-8000-0000000006b7",
  hidden: "00000000-0000-4000-8000-0000000006b8",
};
const former = "00000000-0000-4000-8000-0000000006c1";
const current = "00000000-0000-4000-8000-0000000006c2";
const person = "00000000-0000-4000-8000-0000000006d1";

function field(
  id: string,
  name: string,
  type: OpenViewDataSourceField["type"],
  position: number,
  config: Record<string, unknown> = {},
): OpenViewDataSourceField {
  return { id, moduleId, name, type, required: false, position, config };
}

const fields = [
  field(ids.status, "Status", "select", 0, {
    options: [
      { id: former, label: "Former" },
      { id: current, label: "Current" },
    ],
  }),
  field(ids.name, "Name", "text", 1),
  field(ids.closedOn, "Closed on", "date", 2),
  field(ids.createdAt, "Created at", "datetime", 3),
  field(ids.owner, "Owner", "user", 4),
  field(ids.active, "Active", "boolean", 5),
  field(ids.amount, "Amount", "decimal", 6),
];

const status = { fieldId: ids.status, expectedType: "select" } as const;
const name = { fieldId: ids.name, expectedType: "text" } as const;
const closedOn = { fieldId: ids.closedOn, expectedType: "date" } as const;
const createdAt = { fieldId: ids.createdAt, expectedType: "datetime" } as const;

const isFormer = { ...status, operator: "eq", value: former } as const;
const nameIsAda = { ...name, operator: "eq", value: "Ada" } as const;

function definition(
  overrides: Partial<OpenViewQueryDefinition> = {},
): OpenViewQueryDefinition {
  return {
    version: 1,
    logic: "and",
    columns: [],
    filters: [],
    sort: [],
    deleted: "exclude",
    search: null,
    searchFields: [],
    ...overrides,
  };
}

function input(overrides: Partial<WidgetLinkInput> = {}): WidgetLinkInput {
  return {
    definition: definition(),
    window: null,
    fields,
    timezone: "Asia/Manila",
    ...overrides,
  };
}

test("SI-C6.1: a Date window becomes on-or-after and on-or-before conditions on its field", () => {
  expect(
    windowConditions(
      { dateField: closedOn, fromDate: "2026-10-01", toDate: "2026-10-31" },
      fields,
      null,
    ),
  ).toEqual([
    { ...closedOn, operator: "gte", value: "2026-10-01" },
    { ...closedOn, operator: "lte", value: "2026-10-31" },
  ]);
});

test("SI-C6.1: a Date-and-time window runs from local midnight to the next local midnight with each date's own offset", () => {
  const cases = [
    // One day in the fixture workspace's zone.
    {
      timezone: "Asia/Manila",
      fromDate: "2026-10-26",
      toDate: "2026-10-26",
      from: "2026-10-26T00:00:00+08:00",
      until: "2026-10-27T00:00:00+08:00",
    },
    // Across the spring daylight-saving date: the two ends differ.
    {
      timezone: "America/New_York",
      fromDate: "2026-03-07",
      toDate: "2026-03-08",
      from: "2026-03-07T00:00:00-05:00",
      until: "2026-03-09T00:00:00-04:00",
    },
    // Across the autumn daylight-saving date.
    {
      timezone: "America/New_York",
      fromDate: "2026-10-31",
      toDate: "2026-11-01",
      from: "2026-10-31T00:00:00-04:00",
      until: "2026-11-02T00:00:00-05:00",
    },
    // A half-hour zone and a zero offset.
    {
      timezone: "Asia/Kolkata",
      fromDate: "2026-01-01",
      toDate: "2026-01-31",
      from: "2026-01-01T00:00:00+05:30",
      until: "2026-02-01T00:00:00+05:30",
    },
    {
      timezone: "UTC",
      fromDate: "2026-12-31",
      toDate: "2026-12-31",
      from: "2026-12-31T00:00:00+00:00",
      until: "2027-01-01T00:00:00+00:00",
    },
  ];
  for (const item of cases)
    expect(
      windowConditions(
        {
          dateField: createdAt,
          fromDate: item.fromDate,
          toDate: item.toDate,
        },
        fields,
        item.timezone,
      ),
      `${item.timezone} ${item.fromDate} to ${item.toDate}`,
    ).toEqual([
      { ...createdAt, operator: "gte", value: item.from },
      { ...createdAt, operator: "lt", value: item.until },
    ]);
});

test("SI-C6.1: a midnight that a clock change skips or repeats takes the offset before the change, as the server does", () => {
  // Values from Python zoneinfo with fold=0, which the server's window uses
  // (backend/app/systems/sandbox/records/aggregation.py).
  expect(zonedMidnight("2026-09-06", "America/Santiago")).toBe(
    "2026-09-06T00:00:00-04:00",
  );
  expect(zonedMidnight("2026-03-08", "America/Havana")).toBe(
    "2026-03-08T00:00:00-05:00",
  );
  expect(zonedMidnight("2026-11-01", "America/Havana")).toBe(
    "2026-11-01T00:00:00-04:00",
  );
  expect(zonedMidnight("2026-11-01", "Not/AZone")).toBeNull();
});

test("SI-C6.1: an open-ended window adds no upper condition", () => {
  expect(
    windowConditions(
      { dateField: closedOn, fromDate: "2026-10-01", toDate: "9999-12-31" },
      fields,
      null,
    ),
  ).toEqual([{ ...closedOn, operator: "gte", value: "2026-10-01" }]);
  expect(
    windowConditions(
      { dateField: createdAt, fromDate: "2026-10-26", toDate: "9999-12-31" },
      fields,
      "Asia/Manila",
    ),
  ).toEqual([
    { ...createdAt, operator: "gte", value: "2026-10-26T00:00:00+08:00" },
  ]);
});

test("SI-C6.1: a window gives no link without the workspace timezone or a readable window field", () => {
  const timeWindow = {
    dateField: createdAt,
    fromDate: "2026-10-01",
    toDate: "2026-10-31",
  };
  // A Date-and-time window needs the workspace zone; a Date window does not.
  expect(
    widgetLinkDefinition(input({ window: timeWindow, timezone: null })),
  ).toBeNull();
  expect(
    widgetLinkDefinition(
      input({
        window: { ...timeWindow, dateField: closedOn },
        timezone: null,
      }),
    ),
  ).toEqual({
    logic: "and",
    filters: [
      { ...closedOn, operator: "gte", value: "2026-10-01" },
      { ...closedOn, operator: "lte", value: "2026-10-31" },
    ],
    deleted: "exclude",
    search: null,
  });
  // The field is not readable on the module page, or its type changed.
  expect(
    widgetLinkDefinition(
      input({
        window: {
          ...timeWindow,
          dateField: { fieldId: ids.hidden, expectedType: "datetime" },
        },
      }),
    ),
  ).toBeNull();
  expect(
    widgetLinkDefinition(
      input({
        window: {
          ...timeWindow,
          dateField: { fieldId: ids.closedOn, expectedType: "datetime" },
        },
      }),
    ),
  ).toBeNull();
});

test("SI-C6.2: a group row adds is <key>, and the empty group adds the stored empty operator", () => {
  const owner = { fieldId: ids.owner, expectedType: "user" } as const;
  const active = { fieldId: ids.active, expectedType: "boolean" } as const;
  const rows = [
    { group: { dimension: status, key: former }, condition: isFormer },
    {
      group: { dimension: status, key: null },
      condition: { ...status, operator: "empty", value: null },
    },
    {
      group: { dimension: name, key: "Ada" },
      condition: nameIsAda,
    },
    {
      group: { dimension: owner, key: person },
      condition: { ...owner, operator: "eq", value: person },
    },
    // The server keys a Checkbox group "true" or "false".
    {
      group: { dimension: active, key: "true" },
      condition: { ...active, operator: "eq", value: true },
    },
    {
      group: { dimension: active, key: "false" },
      condition: { ...active, operator: "eq", value: false },
    },
  ];
  for (const row of rows)
    expect(
      groupCondition(row.group, fields),
      `${row.group.dimension.expectedType} ${row.group.key}`,
    ).toEqual(row.condition);
});

test("SI-C6.2: a group that cannot be stated as a condition stays plain text", () => {
  const rows = [
    // An empty text value: the module page drops an "is" with no value.
    { dimension: name, key: "" },
    // Longer than a condition value can be.
    { dimension: name, key: "a".repeat(4001) },
    // A Choice option that the field no longer has.
    { dimension: status, key: "00000000-0000-4000-8000-0000000006c9" },
    { dimension: { fieldId: ids.active, expectedType: "boolean" }, key: "yes" },
    // A field the person cannot read, a changed type, a non-group type.
    { dimension: { fieldId: ids.hidden, expectedType: "select" }, key: former },
    { dimension: { fieldId: ids.status, expectedType: "text" }, key: former },
    {
      dimension: { fieldId: ids.amount, expectedType: "decimal" },
      key: "12.5",
    },
  ] as const;
  for (const row of rows)
    expect(
      groupCondition(row, fields),
      `${row.dimension.expectedType} ${row.key.slice(0, 40)}`,
    ).toBeNull();
});

test("SI-C6.3: with Any condition a link adds a condition only over at most one condition, and then uses All conditions", () => {
  const anyOfTwo = definition({ logic: "or", filters: [isFormer, nameIsAda] });
  const window = {
    dateField: closedOn,
    fromDate: "2026-10-01",
    toDate: "2026-10-31",
  };
  // A figure with no window adds nothing, so it keeps the widget's logic.
  expect(widgetLinkDefinition(input({ definition: anyOfTwo }))).toEqual({
    logic: "or",
    filters: [isFormer, nameIsAda],
    deleted: "exclude",
    search: null,
  });
  expect(
    widgetLinkDefinition(input({ definition: anyOfTwo, window })),
  ).toBeNull();
  expect(
    widgetLinkDefinition(input({ definition: anyOfTwo }), {
      dimension: status,
      key: former,
    }),
  ).toBeNull();
  // One condition joined by Any condition: the link uses All conditions.
  expect(
    widgetLinkDefinition(
      input({ definition: definition({ logic: "or", filters: [nameIsAda] }) }),
      { dimension: status, key: former },
    ),
  ).toEqual({
    logic: "and",
    filters: [nameIsAda, isFormer],
    deleted: "exclude",
    search: null,
  });
  expect(
    widgetLinkDefinition(
      input({ definition: definition({ logic: "or" }), window }),
    ),
  ).toEqual({
    logic: "and",
    filters: [
      { ...closedOn, operator: "gte", value: "2026-10-01" },
      { ...closedOn, operator: "lte", value: "2026-10-31" },
    ],
    deleted: "exclude",
    search: null,
  });
});

test("SI-C6.1: the link carries the widget's deleted and search settings over the module's default view", () => {
  const widget = definition({
    filters: [nameIsAda],
    deleted: "exclude",
    search: "pump",
    searchFields: [name],
  });
  const changes = widgetLinkChanges(input({ definition: widget }), {
    dimension: status,
    key: null,
  });
  expect(changes).not.toBeNull();
  // The module's default view has its own search, deleted setting and filter.
  const defaultView = {
    name: "Open accounts",
    definition: {
      ...emptyDefinition(fields),
      filters: [{ ...status, operator: "eq" as const, value: current }],
      deleted: "include" as const,
      search: "old",
    },
    presentation: emptyPresentation(fields),
  };
  const opened = decodeTemporaryView(changes ?? "", defaultView, fields);
  expect(opened?.definition).toEqual({
    ...defaultView.definition,
    logic: "and",
    filters: [nameIsAda, { ...status, operator: "empty", value: null }],
    deleted: "exclude",
    search: "pump",
    searchFields: [name],
  });
  // Without a search, the default view's search is cleared too.
  const plain = widgetLinkChanges(input());
  expect(
    decodeTemporaryView(plain ?? "", defaultView, fields)?.definition,
  ).toEqual({
    ...defaultView.definition,
    logic: "and",
    filters: [],
    deleted: "exclude",
    search: null,
  });
});

test("SI-C6.1: no link when the widget's conditions would not survive the module page's address", () => {
  // An incomplete condition: the module page would drop it.
  expect(
    widgetLinkDefinition(
      input({
        definition: definition({
          filters: [{ ...name, operator: "eq", value: "" }],
        }),
      }),
    ),
  ).toBeNull();
  // More than ten conditions once the window is added.
  const nine = Array.from({ length: 9 }, (_, index) => ({
    ...name,
    operator: "neq" as const,
    value: `Name ${index}`,
  }));
  expect(
    widgetLinkDefinition(
      input({
        definition: definition({ filters: nine }),
        window: {
          dateField: closedOn,
          fromDate: "2026-10-01",
          toDate: "2026-10-31",
        },
      }),
    ),
  ).toBeNull();
  // An address longer than the module page reads.
  const long = definition({
    filters: ["a", "b", "c"].map((letter) => ({
      ...name,
      operator: "neq" as const,
      value: letter.repeat(2000),
    })),
  });
  expect(widgetLinkDefinition(input({ definition: long }))).not.toBeNull();
  expect(widgetLinkChanges(input({ definition: long }))).toBeNull();
});
