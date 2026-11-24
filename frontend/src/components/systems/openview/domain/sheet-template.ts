// A template file in the New sheet dialog (docs/specs/sheets.md X5, X6,
// D9.2; SH-33): read it, say what it holds, and suggest a module of this
// organization for each link column by name. The server validates the file
// again; this read refuses only what it must, so nothing is sent for a file
// that cannot be used.

export const TEMPLATE_KIND = "slateops-worksheet-template";
export const TEMPLATE_MAX_BYTES = 1024 * 1024;

export type TemplateLink = {
  key: string;
  name: string;
  moduleName: string;
  departmentName: string;
};

export type TemplateRead =
  | {
      ok: true;
      /** The file as parsed; route 3 takes it as it is. */
      template: Record<string, unknown>;
      title: string;
      summary: string;
      links: TemplateLink[];
    }
  | { ok: false; problem: string };

export const TEMPLATE_PROBLEMS = {
  invalid:
    "This file is not a sheet template. Choose a .json file that Download template made.",
  version:
    "This template has a version that this installation cannot read. Nothing was created.",
  sheetLookup:
    "This template has a From another sheet column, which a template cannot carry. Nothing was created.",
  large: "A template file can be at most 1 MiB.",
} as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function counted(count: number, one: string, many: string) {
  return `${count} ${count === 1 ? one : many}`;
}

/** "14 columns · 3 column groups · 1 computed column · totals". */
function summaryOf(
  columns: Record<string, unknown>[],
  groups: number,
  totals: number,
): string {
  const computed = columns.filter(
    (column) => column.type === "computed",
  ).length;
  return [
    counted(columns.length, "column", "columns"),
    groups ? counted(groups, "column group", "column groups") : null,
    computed ? counted(computed, "computed column", "computed columns") : null,
    totals ? "totals" : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export function readTemplate(text: string): TemplateRead {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return { ok: false, problem: TEMPLATE_PROBLEMS.invalid };
  }
  if (!isRecord(parsed) || parsed.kind !== TEMPLATE_KIND)
    return { ok: false, problem: TEMPLATE_PROBLEMS.invalid };
  if (parsed.schemaVersion !== 1)
    return { ok: false, problem: TEMPLATE_PROBLEMS.version };
  const columns = parsed.columns;
  // At most a sheet's 100 columns, each with a key a sheet can hold
  // (F7-S2), so no key reads as an object's own property name.
  if (
    !Array.isArray(columns) ||
    columns.length > 100 ||
    !columns.every(
      (column) =>
        isRecord(column) &&
        typeof column.key === "string" &&
        /^c[0-9a-z]{1,8}$/.test(column.key),
    )
  )
    return { ok: false, problem: TEMPLATE_PROBLEMS.invalid };
  if (columns.some((column) => column.type === "sheet_lookup"))
    return { ok: false, problem: TEMPLATE_PROBLEMS.sheetLookup };
  const links: TemplateLink[] = [];
  for (const column of columns) {
    if (column.type !== "link") continue;
    const link = column.link;
    if (
      typeof column.key !== "string" ||
      typeof column.name !== "string" ||
      !isRecord(link) ||
      typeof link.moduleName !== "string" ||
      typeof link.departmentName !== "string"
    )
      return { ok: false, problem: TEMPLATE_PROBLEMS.invalid };
    links.push({
      key: column.key,
      name: column.name,
      moduleName: link.moduleName,
      departmentName: link.departmentName,
    });
  }
  const groups = Array.isArray(parsed.groups) ? parsed.groups.length : 0;
  const totals = isRecord(parsed.totals)
    ? Object.keys(parsed.totals).length
    : 0;
  return {
    ok: true,
    template: parsed,
    title: typeof parsed.title === "string" ? parsed.title : "",
    summary: summaryOf(columns, groups, totals),
    links,
  };
}

export type MappableModule = {
  id: string;
  name: string;
  departmentName: string;
};

function same(left: string, right: string) {
  return left.trim().toLowerCase() === right.trim().toLowerCase();
}

/**
 * The module suggested for a link column: one the person can read with the
 * same name, in the same-named department when several share the name; or
 * none, and the column becomes text.
 */
export function suggestModule(
  link: Pick<TemplateLink, "moduleName" | "departmentName">,
  modules: readonly MappableModule[],
): string | null {
  const named = modules.filter((module) => same(module.name, link.moduleName));
  const exact = named.find((module) =>
    same(module.departmentName, link.departmentName),
  );
  return (exact ?? named[0])?.id ?? null;
}

/** The line under a mapping: why the module, or why the column becomes text. */
export function mappingLine(
  link: Pick<TemplateLink, "moduleName">,
  chosen: string | null,
  suggested: string | null,
): string {
  if (chosen === null)
    return suggested === null
      ? `No module named ${link.moduleName}. It becomes a text column.`
      : "It becomes a text column.";
  return chosen === suggested
    ? "Suggested: same module name as in the template."
    : "";
}
