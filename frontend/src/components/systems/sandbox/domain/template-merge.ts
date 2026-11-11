import {
  MODULE_TABLE,
  departmentSize,
  modulePosition,
  moduleTableHeight,
  type CanvasBox,
} from "@/lib/sandbox/canvas-geometry";
import {
  LAYOUT_ENTRIES,
  createLimitReason,
  departmentNameReason,
  insideCanvas,
  newDepartment,
  nextDepartmentSlot,
  type CreateAdd,
} from "./create-checks";
import { projectSandboxDocument } from "./document-bridge";
import {
  fieldTypeLabel,
  uid,
  type DepartmentSetup,
  type Design,
  type Module,
} from "./model";
import { SANDBOX_ORGANIZATION_TEMPLATES } from "./templates";
import { SANDBOX_LIMITS } from "./validation-types";

/**
 * One department from an organization template, added to the draft
 * (docs/specs/sandbox-ux-redesign.md, FAST-7, "Template department", A2).
 * The merge copies the department with its modules, their fields, and the
 * relationships between its own modules, under new ids, and never the
 * template's triggers. It only appends, so the save queue sends it as one
 * add, and the page keeps it as one Undo step.
 */

export type TemplateDepartmentField = { name: string; type: string };
export type TemplateDepartmentModule = {
  id: string;
  name: string;
  fieldCount: number;
  /** The fields the preview shows, with their type words. */
  firstFields: TemplateDepartmentField[];
};
export type TemplateDepartmentLink = { id: string; name: string };
export type TemplateDepartment = {
  /** `<template id>/<department id>`: two templates both have a Finance. */
  key: string;
  name: string;
  templateName: string;
  modules: TemplateDepartmentModule[];
  /** Relationships with both ends in this department. */
  links: TemplateDepartmentLink[];
};
export type TemplateDepartmentGroup = {
  templateId: string;
  templateName: string;
  departments: TemplateDepartment[];
};

/** Fields the preview shows per module. */
const PREVIEW_FIELDS = 3;

/** One template department as Build's model: what the merge copies. */
type TemplateSource = {
  department: TemplateDepartment;
  modules: Module[];
  relationships: Design["relationships"];
};

/** Each template as Build reads it, projected once from a fresh copy. */
function templateSources(): Map<string, TemplateSource> {
  const sources = new Map<string, TemplateSource>();
  for (const template of SANDBOX_ORGANIZATION_TEMPLATES) {
    // A fresh copy: the template constant is never changed.
    const design = projectSandboxDocument(template.createDocument());
    for (const department of design.departments) {
      const modules = design.modules.filter(
        (item) => item.department === department.id,
      );
      const own = new Set(modules.map((item) => item.id));
      const relationships = design.relationships.filter(
        (item) => own.has(item.source) && own.has(item.target),
      );
      const key = `${template.id}/${department.id}`;
      sources.set(key, {
        department: {
          key,
          name: department.name,
          templateName: template.name,
          modules: modules.map((item) => ({
            id: item.id,
            name: item.name,
            fieldCount: item.fields.length,
            firstFields: item.fields.slice(0, PREVIEW_FIELDS).map((field) => ({
              name: field.name,
              type: fieldTypeLabel(field.type),
            })),
          })),
          links: relationships.map((item) => ({
            id: item.id,
            name: item.name,
          })),
        },
        modules,
        relationships,
      });
    }
  }
  return sources;
}

/** The 23 template departments, grouped by their organization template. */
export function templateDepartmentGroups(): TemplateDepartmentGroup[] {
  const sources = [...templateSources().values()];
  return SANDBOX_ORGANIZATION_TEMPLATES.map((template) => ({
    templateId: template.id,
    templateName: template.name,
    departments: sources
      .filter((source) => source.department.key.startsWith(`${template.id}/`))
      .map((source) => source.department),
  }));
}

/**
 * The prefilled name: the template name, or the first free "Sales 2",
 * "Sales 3" when it is taken, with the line that says so. Taken compares as
 * the entry does: open departments, trimmed, in any letter case.
 */
export function templateDepartmentName(
  design: Design,
  templateName: string,
): { name: string; taken: string | null } {
  if (departmentNameReason(design, templateName) === null)
    return { name: templateName, taken: null };
  let number = 2;
  while (departmentNameReason(design, `${templateName} ${number}`) !== null)
    number += 1;
  return {
    name: `${templateName} ${number}`,
    taken: `${templateName} is taken in this design.`,
  };
}

const plural = (count: number, one: string, many: string) =>
  `${count.toLocaleString("en-US")} ${count === 1 ? one : many}`;

/** The footer line: "Adds 4 modules and 3 links, without triggers." */
export function templateDepartmentSummary(department: TemplateDepartment) {
  const modules = plural(department.modules.length, "module", "modules");
  const links = department.links.length
    ? ` and ${plural(department.links.length, "link", "links")}`
    : "";
  return `Adds ${modules}${links}, without triggers.`;
}

/** Why the merge would pass a document limit (N2), or null. */
export function templateDepartmentLimitReason(
  design: Design,
  department: TemplateDepartment,
): string | null {
  const departmentLimit = createLimitReason(design, "department");
  if (departmentLimit) return departmentLimit;
  const fields = department.modules.reduce(
    (total, item) => total + item.fieldCount,
    0,
  );
  const checks: Array<[number, number, number, string, string]> = [
    [
      department.modules.length,
      design.modules.length,
      SANDBOX_LIMITS.modules,
      "module",
      "modules",
    ],
    [
      fields,
      design.modules.reduce((total, item) => total + item.fields.length, 0),
      SANDBOX_LIMITS.fields,
      "field",
      "fields",
    ],
    [
      department.links.length,
      design.relationships.length,
      SANDBOX_LIMITS.relationships,
      "link",
      "links",
    ],
    [
      department.modules.length + 1,
      Object.keys(design.layout ?? {}).length,
      LAYOUT_ENTRIES,
      "department and module",
      "departments and modules",
    ],
  ];
  for (const [adds, current, limit, one, many] of checks) {
    const room = Math.max(limit - current, 0);
    if (adds > room)
      return `Adds ${plural(adds, one, many)}; this design has room for ${room.toLocaleString("en-US")}.`;
  }
  return null;
}

/**
 * Why Add department cannot add now: a document limit, or a name that is
 * blank, too long, or taken (N2). Null when the merge can be added.
 */
export function templateDepartmentRefusal(
  design: Design,
  department: TemplateDepartment,
  name: string,
): string | null {
  return (
    templateDepartmentLimitReason(design, department) ??
    departmentNameReason(design, name)
  );
}

/**
 * The draft with the template department added under `name`, or why it
 * cannot be added. New ids for the department, its modules, and its
 * relationships (A2); field ids stay, since a field is known by its module
 * and its own id, so each title field and field mapping stays valid. The
 * frame takes the next free slot right of the existing frames, and its
 * modules take the canvas's own module slots inside it.
 */
export function mergeTemplateDepartment(
  design: Design,
  key: string,
  name: string,
  newId: () => string = uid,
  setup?: DepartmentSetup,
): CreateAdd {
  const source = templateSources().get(key);
  if (!source)
    return { ok: false, reason: "This template department is not available." };
  const refusal = templateDepartmentRefusal(design, source.department, name);
  if (refusal) return { ok: false, reason: refusal };

  const departmentId = newId();
  const moduleIds = new Map(source.modules.map((item) => [item.id, newId()]));
  const heights = source.modules.map((item) =>
    moduleTableHeight(item.fields.length),
  );
  const frame: CanvasBox = {
    ...nextDepartmentSlot(design),
    ...departmentSize(heights),
  };
  const boxes = source.modules.map((_, index): CanvasBox => ({
    ...modulePosition(frame, index, heights),
    width: MODULE_TABLE.width,
    height: heights[index]!,
  }));
  if (![frame, ...boxes].every(insideCanvas))
    return {
      ok: false,
      reason: "The canvas has no room for another department.",
    };

  const modules: Module[] = source.modules.map((item, index) => ({
    ...structuredClone(item),
    id: moduleIds.get(item.id)!,
    department: departmentId,
    x: boxes[index]!.x,
    y: boxes[index]!.y,
  }));
  const relationships = source.relationships.map((item) => ({
    ...structuredClone(item),
    id: newId(),
    source: moduleIds.get(item.source)!,
    target: moduleIds.get(item.target)!,
  }));
  return {
    ok: true,
    design: {
      ...design,
      departments: [
        ...design.departments,
        newDepartment(departmentId, name, setup),
      ],
      modules: [...design.modules, ...modules],
      relationships: [...design.relationships, ...relationships],
      layout: {
        ...design.layout,
        [departmentId]: frame,
        ...Object.fromEntries(
          modules.map((item, index) => [item.id, boxes[index]!]),
        ),
      },
    },
  };
}
