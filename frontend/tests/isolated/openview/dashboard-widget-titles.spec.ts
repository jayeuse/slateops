import { expect, test } from "@playwright/test";
import type { OpenViewDashboardWidgetConfig } from "../../../src/components/systems/openview/adapters/dashboards-api";
import type { OpenViewDataSourceField } from "../../../src/components/systems/openview/adapters/views-api";
import type { WidgetKind } from "../../../src/components/systems/openview/domain/dashboard-grid";
import { widgetTitle } from "../../../src/components/systems/openview/domain/dashboard-widget-text";

const moduleId = "00000000-0000-4000-8000-000000000201";
const ids = {
  credit: "00000000-0000-4000-8000-000000000202",
  vat: "00000000-0000-4000-8000-000000000203",
  region: "00000000-0000-4000-8000-000000000204",
  status: "00000000-0000-4000-8000-000000000205",
  created: "00000000-0000-4000-8000-000000000206",
};

function field(
  id: string,
  name: string,
  type: OpenViewDataSourceField["type"],
): OpenViewDataSourceField {
  return { id, moduleId, name, type, required: false, position: 0, config: {} };
}

const fields = [
  field(ids.credit, "Credit limit", "decimal"),
  field(ids.vat, "VAT amount", "decimal"),
  field(ids.region, "Region", "select"),
  field(ids.status, "Status", "select"),
  field(ids.created, "Created on", "date"),
];

function config(query: Record<string, unknown>): OpenViewDashboardWidgetConfig {
  return { version: 1, query } as unknown as OpenViewDashboardWidgetConfig;
}

const reference = (fieldId: string) => ({ fieldId, expectedType: "decimal" });
const groups = (
  aggregation: string,
  measure: string | null,
  dimension = ids.status,
) =>
  config({
    mode: "groups",
    moduleId,
    aggregation,
    measure: measure ? reference(measure) : null,
    dimension: { fieldId: dimension, expectedType: "select" },
  });
const series = (aggregation: string, measure: string | null, bucket: string) =>
  config({
    mode: "date_series",
    moduleId,
    aggregation,
    measure: measure ? reference(measure) : null,
    dimension: { fieldId: ids.created, expectedType: "date" },
    bucket,
  });

// UF-C9.4 (DR-9.4, BD16 as changed): a widget's title follows its query in
// plain words; a saved chart keeps its name.
test("UF-C9.4: widget titles read as plain names that follow the query", () => {
  const cases: Array<
    [WidgetKind, OpenViewDashboardWidgetConfig, string | null, string]
  > = [
    ["number", groups("count", null), null, "Customers"],
    ["bar", groups("count", null), null, "Customers by Status"],
    ["number", groups("sum", ids.credit), null, "Total credit limit"],
    [
      "bar",
      groups("sum", ids.credit, ids.region),
      null,
      "Total credit limit by Region",
    ],
    ["number", groups("average", ids.credit), null, "Average credit limit"],
    ["number", groups("min", ids.credit), null, "Smallest credit limit"],
    ["number", groups("max", ids.credit), null, "Largest credit limit"],
    ["number", groups("distinct", ids.region), null, "Different region values"],
    // A first word in capitals keeps them.
    ["number", groups("sum", ids.vat), null, "Total VAT amount"],
    [
      "line",
      series("sum", ids.credit, "week"),
      null,
      "Total credit limit per week",
    ],
    ["line", series("count", null, "month"), null, "Customers per month"],
    ["bar", groups("sum", ids.credit), "Pipeline", "Pipeline"],
  ];
  expect(
    cases.map(([kind, widgetConfig, savedName]) =>
      widgetTitle({
        kind,
        config: widgetConfig,
        savedName,
        moduleName: "Customers",
        fields,
      }),
    ),
  ).toEqual(cases.map(([, , , title]) => title));
});
