/**
 * What a dashboard widget says about itself: its generated title, the number
 * a Number widget shows, and how many rows a table or list shows at its height
 * (docs/specs/openview-dashboard.md, BD4). Widgets store no title of their
 * own, so the title comes from the query (or a saved Chart's name).
 */
import type { OpenViewAggregateSnapshotResult } from "../adapters/analytics-api";
import type { OpenViewDashboardWidgetConfig } from "../adapters/dashboards-api";
import type { OpenViewDataSourceField } from "../adapters/views-api";
import type { WidgetKind } from "./dashboard-grid";

const KIND_LABELS: Record<WidgetKind, string> = {
  number: "Number",
  bar: "Bar chart",
  line: "Line chart",
  pie: "Pie chart",
  table: "Table",
  records: "Records",
};

export function kindLabel(kind: WidgetKind): string {
  return KIND_LABELS[kind];
}

// DR-9.4: a measure in plain words ("Total credit limit"). A count reads as
// the module's name, so it has no words here.
const AGGREGATION_WORDS = {
  count: () => "",
  sum: (measure: string) => `Total ${measure}`,
  average: (measure: string) => `Average ${measure}`,
  min: (measure: string) => `Smallest ${measure}`,
  max: (measure: string) => `Largest ${measure}`,
  distinct: (measure: string) => `Different ${measure} values`,
} as const;

/**
 * A field name inside a title: its leading capital is lowered, unless its
 * first word is all capitals ("VAT amount" stays; "Credit limit" reads
 * "credit limit").
 */
function measureWords(name: string): string {
  const first = name.split(/\s/)[0] ?? "";
  const capitals = first.length > 1 && first === first.toUpperCase();
  return capitals ? name : name.charAt(0).toLowerCase() + name.slice(1);
}

const BUCKET_WORDS = {
  day: "day",
  week: "week",
  month: "month",
  quarter: "quarter",
  year: "year",
} as const;

/**
 * "Quotes by Status", "Total amount by Region", "Sales Orders per week",
 * "Quotes" (DR-9.4, BD16 as changed by the UX friction pass); a saved Chart
 * keeps its name. Without its module's names (a locked or loading widget)
 * the title is the widget's kind.
 */
export function widgetTitle(input: {
  kind: WidgetKind;
  config: OpenViewDashboardWidgetConfig | null;
  savedName: string | null;
  moduleName: string | null;
  fields: readonly OpenViewDataSourceField[];
}): string {
  if (input.savedName) return input.savedName;
  const { config, moduleName } = input;
  if (!config || !moduleName) return kindLabel(input.kind);
  const name = (id: string | undefined) =>
    input.fields.find((field) => field.id === id)?.name;
  const query = config.query;
  if (!("mode" in query)) return moduleName;
  const measure = query.measure ? name(query.measure.fieldId) : undefined;
  // A measure missing from the field list reads "value".
  const what =
    query.aggregation === "count"
      ? moduleName
      : AGGREGATION_WORDS[query.aggregation](
          measure ? measureWords(measure) : "value",
        );
  if (input.kind === "number") return what;
  if (query.mode === "date_series")
    return `${what} per ${BUCKET_WORDS[query.bucket ?? "day"]}`;
  const dimension = name(query.dimension.fieldId);
  return dimension ? `${what} by ${dimension}` : what;
}

/**
 * A Number shows one figure for all of its groups: the record count, a sum,
 * the smallest or the largest. Averages and distinct counts cannot be added
 * across groups, so they show only when there is one group.
 */
export function numberValue(
  result: OpenViewAggregateSnapshotResult,
  aggregation: keyof typeof AGGREGATION_WORDS,
): number | null {
  const values = result.items
    .map((item) => (item.value === null ? null : Number(item.value)))
    .filter(
      (value): value is number => value !== null && Number.isFinite(value),
    );
  switch (aggregation) {
    case "count":
      return result.items.reduce((total, item) => total + item.recordCount, 0);
    case "sum":
      return values.reduce((total, value) => total + value, 0);
    case "min":
      return values.length ? Math.min(...values) : null;
    case "max":
      return values.length ? Math.max(...values) : null;
    default:
      return result.items.length === 1 && values.length === 1
        ? values[0]
        : null;
  }
}

/**
 * Rows a table or records list shows at a height: four at two grid rows (the
 * size rules were checked at the 112px row minimum), three more for each
 * further row, and five on a phone, where the widget sets its own height.
 */
export function rowsForSpan(rowSpan: number | null): number {
  if (rowSpan === null) return 5;
  return 4 + Math.max(0, rowSpan - 2) * 3;
}

/** "1–4 of 12": the compact pager of a table widget. */
export function pageRange(offset: number, count: number, total: number) {
  if (total === 0 || count === 0) return `0 of ${total}`;
  return `${offset + 1}–${offset + count} of ${total}`;
}
