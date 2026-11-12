import type {
  AccessGroup,
  AccessGroupAccessEntry,
  AccessLevel,
  AccessPage,
  AccessUser,
  AccessUserAccess,
  AccessUserRole,
  AccessVersioned,
} from "../state/api-contracts";
import { accessSummary, moduleCount } from "./groups";
import { levelLabels } from "./people";

// Rules of "Add access" in a person's Access tab and of the group lines in
// Invite (docs/specs/ux-friction-pass.md, item 10). Access stays group-based:
// the person joins a group that gives exactly the chosen access, or one is
// made with that access. The server decides every step and may refuse it.

const levelRank: Record<AccessLevel, number> = { read: 1, write: 2, manage: 3 };

/** The short line under each level choice (Words, item 10). */
export const levelLines: Record<AccessLevel, string> = {
  read: "See records.",
  write: "Add and change records.",
  manage: "Also manage its views, dashboard, and group members.",
};

/**
 * Add access shows only to an administrator viewing a person who is not an
 * administrator (DR-10.2, DR-10.9). The server refuses group and access
 * changes from anyone else; this only hides a control it would refuse.
 */
export function canAddAccess(
  viewer: { role: AccessUserRole | null } | null | undefined,
  person: Pick<AccessUser, "role" | "is_deleted">,
): boolean {
  return (
    viewer?.role === "admin" && person.role !== "admin" && !person.is_deleted
  );
}

/** A guest is capped at Read, so only Read is offered (DR-10.3). */
export function levelsFor(role: AccessUserRole): AccessLevel[] {
  return role === "guest" ? ["read"] : ["read", "write", "manage"];
}

const byName = (left: AccessGroup, right: AccessGroup) =>
  left.name.localeCompare(right.name, undefined, { sensitivity: "base" }) ||
  left.id.localeCompare(right.id);

/** One access row: that department, no module, that level (DR-10.4). */
export function givesExactly(
  group: AccessGroup,
  departmentId: string,
  level: AccessLevel,
): boolean {
  const [only] = group.access;
  return (
    !group.is_deleted &&
    group.access.length === 1 &&
    only.department_id === departmentId &&
    only.module_id === null &&
    only.level === level
  );
}

/** Of the groups that give exactly this, the earliest name. */
export function exactFit(
  groups: readonly AccessGroup[],
  departmentId: string,
  level: AccessLevel,
): AccessGroup | null {
  return (
    groups
      .filter((group) => givesExactly(group, departmentId, level))
      .sort(byName)[0] ?? null
  );
}

/**
 * "<Department> read access", then " 2", " 3" (DR-10.5). Sandbox derived
 * group names end in "managers", "members" or "viewers", so this name never
 * equals one.
 */
export function madeGroupName(
  departmentName: string,
  level: AccessLevel,
  position = 1,
): string {
  const base = `${departmentName.trim()} ${levelLabels[level].toLowerCase()} access`;
  return position > 1 ? `${base} ${position}` : base;
}

/** The access the person already has in the whole department, if it is enough. */
export function alreadyHas(
  access: AccessUserAccess,
  departmentId: string,
  level: AccessLevel,
): { level: AccessLevel; groupName: string | null } | null {
  const entry = access.entries.find(
    (item) => item.department_id === departmentId && item.module_id === null,
  );
  if (!entry || levelRank[entry.level] < levelRank[level]) return null;
  // The group that gives the most names the source; a name breaks a tie.
  const [source] = [...entry.groups].sort(
    (left, right) =>
      levelRank[right.level] - levelRank[left.level] ||
      left.name.localeCompare(right.name, undefined, { sensitivity: "base" }),
  );
  return { level: entry.level, groupName: source?.name ?? null };
}

export type AddAccessPlan =
  | { kind: "join"; group: AccessGroup }
  | { kind: "reuse"; group: AccessGroup }
  | { kind: "make"; name: string };

const sameName = (left: string, right: string) =>
  left.trim().toLocaleLowerCase() === right.trim().toLocaleLowerCase();

/**
 * What Add access does with the groups read now. A group that gives exactly
 * this is joined. Otherwise the made name is used: a same-name group with no
 * access rows and no members is the one an earlier try made, so it is used
 * again and no second group is made (DR-10.8). A same-name group with other
 * access or with members is never reused: the name takes " 2", then " 3".
 * The plan reads only the groups, so a retry needs no memory of an earlier
 * try.
 */
export function planAddAccess({
  groups,
  departmentId,
  departmentName,
  level,
}: {
  groups: readonly AccessGroup[];
  departmentId: string;
  departmentName: string;
  level: AccessLevel;
}): AddAccessPlan {
  const fit = exactFit(groups, departmentId, level);
  if (fit) return { kind: "join", group: fit };
  const active = groups.filter((group) => !group.is_deleted);
  for (let position = 1; position <= active.length + 1; position += 1) {
    const name = madeGroupName(departmentName, level, position);
    const named = active.filter((group) => sameName(group.name, name));
    if (!named.length) return { kind: "make", name };
    const empty = named
      .filter((group) => !group.access.length && !group.member_ids.length)
      .sort(byName)[0];
    if (empty) return { kind: "reuse", group: empty };
  }
  // Unreachable: each position past the first needs one more active group.
  return {
    kind: "make",
    name: madeGroupName(departmentName, level, active.length + 2),
  };
}

/** The group the plan uses, or will make. */
export function planGroupName(plan: AddAccessPlan): string {
  return plan.kind === "make" ? plan.name : plan.group.name;
}

/** Every page of the groups, in name order (DR-10.4). */
export async function readEveryGroup(
  readPage: (offset: number) => Promise<AccessPage<AccessGroup>>,
): Promise<AccessGroup[]> {
  const groups: AccessGroup[] = [];
  for (let offset = 0; ;) {
    const page = await readPage(offset);
    groups.push(...page.items);
    if (!page.pagination.has_more || page.pagination.count === 0) return groups;
    offset += page.pagination.count;
  }
}

export type AddAccessCalls = {
  /** One page of the groups from `offset`, in name order. */
  listGroups: (offset: number) => Promise<AccessPage<AccessGroup>>;
  /** `POST /api/access/groups` with the name only: no members. */
  createGroup: (name: string) => Promise<AccessVersioned<AccessGroup>>;
  getGroup: (groupId: string) => Promise<AccessVersioned<AccessGroup>>;
  /** `PUT /api/access/groups/{id}/access` with the group's ETag. */
  setAccess: (
    groupId: string,
    access: AccessGroupAccessEntry[],
    etag: string,
  ) => Promise<AccessVersioned<AccessGroup>>;
  /** Adds the person through the member merge (`changeGroupMembership`). */
  addMember: (groupId: string) => Promise<unknown>;
};

export type AddAccessStep = "read" | "create" | "access" | "member";

/**
 * A failed step. `made` names a group that exists without this person in it
 * (DR-10.8); a retry plans again from the groups and uses it.
 */
export class AddAccessStepError extends Error {
  constructor(
    readonly step: AddAccessStep,
    readonly made: string | null,
    readonly failure: unknown,
  ) {
    super(`Add access failed at ${step}`);
    this.name = "AddAccessStepError";
  }
}

async function step<Value>(
  name: AddAccessStep,
  made: string | null,
  run: () => Promise<Value>,
): Promise<Value> {
  try {
    return await run();
  } catch (caught) {
    throw new AddAccessStepError(name, made, caught);
  }
}

/** Whether two plans do the same thing: the same group, or the same new name. */
export function samePlan(left: AddAccessPlan, right: AddAccessPlan): boolean {
  if (left.kind !== right.kind) return false;
  if (left.kind === "make" || right.kind === "make")
    return planGroupName(left) === planGroupName(right);
  return left.group.id === right.group.id;
}

/**
 * The groups changed between the shown line and the run, so the action no
 * longer names what would happen. Nothing was written; `groups` is the
 * fresh read for the new line.
 */
export class AddAccessPlanChanged extends Error {
  constructor(readonly groups: AccessGroup[]) {
    super("The groups changed after the plan was shown.");
    this.name = "AddAccessPlanChanged";
  }
}

/**
 * Runs Add access in order: read every page of the groups; then join the
 * group that gives exactly this, or create the group with no members, set
 * its one access row, and add the person (DR-10.7). A reused group is read
 * first for its ETag and must still have no access rows and no members.
 * When `shown` is given and the fresh plan differs, nothing is written.
 */
export async function runAddAccess(
  target: { departmentId: string; departmentName: string; level: AccessLevel },
  calls: AddAccessCalls,
  /** The plan the action named; a different fresh plan stops the run. */
  shown?: AddAccessPlan,
): Promise<{ groupName: string; plan: AddAccessPlan["kind"] }> {
  const groups = await step("read", null, () =>
    readEveryGroup(calls.listGroups),
  );
  const plan = planAddAccess({ groups, ...target });
  if (shown && !samePlan(shown, plan)) throw new AddAccessPlanChanged(groups);
  const access: AccessGroupAccessEntry[] = [
    {
      department_id: target.departmentId,
      module_id: null,
      level: target.level,
    },
  ];
  if (plan.kind === "join") {
    await step("member", null, () => calls.addMember(plan.group.id));
    return { groupName: plan.group.name, plan: plan.kind };
  }
  let group: AccessVersioned<AccessGroup>;
  if (plan.kind === "reuse") {
    const name = plan.group.name;
    group = await step("access", name, () => calls.getGroup(plan.group.id));
    if (group.data.access.length || group.data.member_ids.length)
      throw new AddAccessStepError(
        "access",
        name,
        new Error("The group changed after it was read."),
      );
  } else {
    group = await step("create", null, () => calls.createGroup(plan.name));
  }
  const made = group.data.name;
  const withAccess = await step("access", made, () =>
    calls.setAccess(group.data.id, access, group.etag),
  );
  await step("member", made, () => calls.addMember(withAccess.data.id));
  return { groupName: made, plan: plan.kind };
}

/**
 * The second line of a group in Invite (DR-10.1): what the group gives,
 * "Sales · Write"; "Sales · Write (2 modules differ)"; two departments, then
 * "+2 more"; "Gives no access yet" with no access rows. For a guest each
 * level above Read reads "Read (guest limit)".
 */
export function groupAccessLine(
  access: readonly (AccessGroupAccessEntry & {
    department_name?: string;
    module_name?: string | null;
  })[],
  role: AccessUserRole,
): string {
  if (!access.length) return "Gives no access yet";
  const guest = role === "guest";
  const capped = (level: AccessLevel): AccessLevel => (guest ? "read" : level);
  const labels = accessSummary(access).map((department) => {
    const levels = [
      department.level,
      ...department.modules.map((module) => module.level),
    ];
    const limited =
      guest && levels.some((level) => level !== null && level !== "read");
    const limit = limited ? " (guest limit)" : "";
    if (!department.level)
      return `${department.name} · ${moduleCount(department.modules.length)}${limit}`;
    const level = capped(department.level);
    const differing = department.modules.filter(
      (module) => capped(module.level) !== level,
    ).length;
    const modules = differing
      ? ` (${moduleCount(differing)} ${differing === 1 ? "differs" : "differ"})`
      : "";
    return `${department.name} · ${levelLabels[level]}${limit}${modules}`;
  });
  const shown = labels.slice(0, 2).join(", ");
  return labels.length > 2 ? `${shown} +${labels.length - 2} more` : shown;
}
