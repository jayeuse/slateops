import type { Department, DepartmentSetup, Design } from "./model";

/**
 * Setup choices (docs/specs/sandbox-ux-redesign.md, "Setup choices"; setup
 * spec SD13, SD14, BE-SD5): what the first publish of a new department
 * creates. The Board is always created and is not a choice.
 */

/** Every item on: the default until setup slice 5 (FIT-4). */
export const DEFAULT_DEPARTMENT_SETUP: DepartmentSetup = {
  groups: true,
  dashboard: true,
  category: true,
  channel: true,
};

/** The four choices in popover order, with their visible words. */
export const SETUP_ITEMS: ReadonlyArray<{
  item: keyof DepartmentSetup;
  label: string;
  /** Muted words after the label. */
  detail?: string;
}> = [
  { item: "groups", label: "Groups", detail: "managers, members, viewers" },
  { item: "dashboard", label: "Dashboard" },
  { item: "category", label: "Category" },
  { item: "channel", label: "Channel" },
];

/** A department's setup: its own value, else every item on. */
export function departmentSetup(
  department: Pick<Department, "setup">,
): DepartmentSetup {
  return department.setup ?? DEFAULT_DEPARTMENT_SETUP;
}

/** How many of the four choices are cleared; Groups counts as one. */
export function setupClearedCount(setup: DepartmentSetup | undefined): number {
  if (!setup) return 0;
  return SETUP_ITEMS.filter(({ item }) => !setup[item]).length;
}

/** "Setup for Sales", or "Setup for Sales: 1 item cleared" (FIND-3 words). */
export function setupAccessibleName(
  name: string,
  setup: DepartmentSetup | undefined,
): string {
  const cleared = setupClearedCount(setup);
  if (cleared === 0) return `Setup for ${name}`;
  return `Setup for ${name}: ${cleared} ${cleared === 1 ? "item" : "items"} cleared`;
}

/**
 * Setup applies to a department with no live binding (FIT-1) that is open:
 * a publish creates the setup only for a new open department (BE-SD5).
 */
export function setupOffered(
  department: Pick<Department, "closed">,
  bound: boolean,
): boolean {
  return !bound && !department.closed;
}

/**
 * One toggle: the department's whole setup value with one item changed.
 * Other departments keep their objects as they are.
 */
export function withSetupItem(
  design: Design,
  departmentId: string,
  item: keyof DepartmentSetup,
  on: boolean,
): Design {
  return {
    ...design,
    departments: design.departments.map((department) =>
      department.id === departmentId
        ? {
            ...department,
            setup: { ...departmentSetup(department), [item]: on },
          }
        : department,
    ),
  };
}
