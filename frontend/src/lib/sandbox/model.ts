/**
 * Sandbox domain model (frontend-only mock state).
 *
 * Pure data + pure lookups. No backend, no API calls, no canvas imports.
 */

export type SandboxCanvasLayout = Record<
  string,
  { x: number; y: number; width: number; height: number }
>;

export type SandboxFieldType =
  | "text"
  | "long-text"
  | "int"
  | "decimal"
  | "boolean"
  | "date"
  | "datetime"
  | "select"
  | "email"
  | "url";

export interface SandboxDepartment {
  id: string;
  name: string;
  moduleIds: string[];
  closed?: boolean;
}

export interface SandboxModule {
  id: string;
  departmentId: string;
  name: string;
  fieldIds: string[];
  closed?: boolean;
}

export interface SandboxField {
  id: string;
  moduleId: string;
  name: string;
  type: SandboxFieldType;
  required: boolean;
  description: string;
  closed?: boolean;
}

export interface SandboxLink {
  id: string;
  sourceModuleId: string;
  targetModuleId: string;
  label: string;
  relationshipType?: string;
  direction: "directed";
}

export interface SandboxState {
  departments: SandboxDepartment[];
  modules: SandboxModule[];
  fields: SandboxField[];
  links: SandboxLink[];
  selectedCellId: string | null;
}

export interface SandboxFieldTypeMeta {
  label: string;
  /** Lucide icon component name (resolved by the UI layer). */
  icon: string;
}

export const FIELD_TYPE_META: Record<SandboxFieldType, SandboxFieldTypeMeta> = {
  text: { label: "Text", icon: "Type" },
  "long-text": { label: "Long text", icon: "AlignLeft" },
  int: { label: "Whole number", icon: "Hash" },
  decimal: { label: "Number", icon: "Calculator" },
  boolean: { label: "Checkbox", icon: "ToggleLeft" },
  date: { label: "Date", icon: "Calendar" },
  datetime: { label: "Date and time", icon: "CalendarClock" },
  select: { label: "Choice list", icon: "List" },
  email: { label: "Email", icon: "Mail" },
  url: { label: "Web link", icon: "Link" },
};

type SandboxFieldSource = readonly SandboxField[] | Map<string, SandboxField>;

/**
 * Resolve the fields declared by a module without changing their saved order.
 * The canvas passes its indexed map while list views can pass the state array.
 */
export function fieldsForModule(
  moduleId: string,
  fieldIds: readonly string[],
  fields: SandboxFieldSource,
): SandboxField[] {
  const findField = (fieldId: string): SandboxField | undefined => {
    if (fields instanceof Map) return fields.get(fieldId);
    return fields.find((field) => field.id === fieldId);
  };

  return fieldIds.flatMap((fieldId) => {
    const field = findField(fieldId);
    return field !== undefined && field.moduleId === moduleId ? [field] : [];
  });
}

export interface SandboxStructureDepartmentSearch {
  departmentMatches: boolean;
  matches: boolean;
  modules: SandboxModule[];
  fieldsByModule: ReadonlyMap<string, SandboxField[]>;
}

export interface SandboxStructureSearch {
  query: string;
  hasMatches: boolean;
  departments: ReadonlyMap<string, SandboxStructureDepartmentSearch>;
}

/**
 * Select the visible hierarchy rows for the Inspector. Keeping this predicate
 * in one place ensures its empty state and rendered rows cannot drift apart.
 */
export function searchSandboxStructure(
  state: Pick<SandboxState, "departments" | "modules" | "fields">,
  query: string,
): SandboxStructureSearch {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const fieldsById = new Map(state.fields.map((field) => [field.id, field]));
  const departments = new Map<string, SandboxStructureDepartmentSearch>();

  for (const department of state.departments) {
    const departmentMatches = department.name
      .toLocaleLowerCase()
      .includes(normalizedQuery);
    const allDepartmentModules = department.moduleIds.flatMap(
      (moduleId) =>
        state.modules.find((sandboxModule) => sandboxModule.id === moduleId) ??
        [],
    );
    const modules = allDepartmentModules.filter((sandboxModule) => {
      if (!normalizedQuery || departmentMatches) return true;
      if (sandboxModule.name.toLocaleLowerCase().includes(normalizedQuery))
        return true;
      return fieldsForModule(
        sandboxModule.id,
        sandboxModule.fieldIds,
        fieldsById,
      ).some((field) =>
        field.name.toLocaleLowerCase().includes(normalizedQuery),
      );
    });
    const fieldsByModule = new Map<string, SandboxField[]>();

    for (const sandboxModule of modules) {
      const moduleFields = fieldsForModule(
        sandboxModule.id,
        sandboxModule.fieldIds,
        fieldsById,
      );
      const moduleMatches = sandboxModule.name
        .toLocaleLowerCase()
        .includes(normalizedQuery);
      fieldsByModule.set(
        sandboxModule.id,
        !normalizedQuery || departmentMatches || moduleMatches
          ? moduleFields
          : moduleFields.filter((field) =>
              field.name.toLocaleLowerCase().includes(normalizedQuery),
            ),
      );
    }

    departments.set(department.id, {
      departmentMatches,
      matches: !normalizedQuery || departmentMatches || modules.length > 0,
      modules,
      fieldsByModule,
    });
  }

  return {
    query: normalizedQuery,
    hasMatches: [...departments.values()].some(
      (department) => department.matches,
    ),
    departments,
  };
}

export type UpdateSandboxFieldPatch = Partial<
  Pick<SandboxField, "name" | "type" | "required" | "description">
>;
