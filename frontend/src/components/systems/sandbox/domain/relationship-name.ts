import type { Design } from "./model";
import { SANDBOX_LIMITS } from "./validation-types";

/**
 * Connect from a module (FAST-4, N6, docs/specs/sandbox-ux-redesign.md):
 * the grouped target list, the prefilled relationship name, and the checks
 * that refuse a clashing name in place before it reaches publish.
 */

/**
 * "self" is the source; "linked" already has a relationship from the source
 * to it, the duplicate Build refuses. A link only the other way stays
 * choosable, so a reverse relationship can still be made.
 */
export type ConnectTargetState = "self" | "linked" | "choosable";
export type ConnectTarget = {
  id: string;
  name: string;
  state: ConnectTargetState;
};
export type ConnectTargetGroup = {
  departmentId: string;
  departmentName: string;
  /** The department's position in the design, for its color mark. */
  departmentIndex: number;
  modules: ConnectTarget[];
};
/**
 * The names publish compares a new relationship name with (N6,
 * `publications/preflight.py:136-184`): the source module's open fields and
 * its other outgoing relationships to open modules. Kept apart so a refusal
 * can say which kind of name clashed.
 */
export type RelationshipNamesInUse = {
  fields: readonly string[];
  relationships: readonly string[];
};
/** `typedName` is null until the administrator types in Name. */
export type ConnectDraft = {
  targetId: string | null;
  typedName: string | null;
};
export type ConnectRequest = { targetId: string; name: string };
export type ConnectSubmission =
  { ok: true; request: ConnectRequest } | { ok: false; reason: string };

export const EMPTY_CONNECT_DRAFT: ConnectDraft = {
  targetId: null,
  typedName: null,
};

// The browser compares without case, stricter than publish (N6).
const key = (name: string) => name.trim().toLowerCase();

export function relationshipNamesInUse(
  design: Design,
  sourceId: string,
): RelationshipNamesInUse {
  const source = design.modules.find((item) => item.id === sourceId);
  const openModules = new Set(
    design.modules.filter((item) => !item.closed).map((item) => item.id),
  );
  return {
    fields: (source?.fields ?? [])
      .filter((item) => !item.closed)
      .map((item) => item.name),
    relationships: design.relationships
      .filter(
        (item) =>
          item.source === sourceId &&
          openModules.has(item.source) &&
          openModules.has(item.target),
      )
      .map((item) => item.name),
  };
}

/**
 * Open modules under their department, in design order, as Build's
 * relationship dialog groups them. Closed modules are left out: publish
 * skips a relationship to a closed module.
 */
export function connectTargetGroups(
  design: Design,
  sourceId: string,
): ConnectTargetGroup[] {
  const linked = new Set(
    design.relationships
      .filter((item) => item.source === sourceId)
      .map((item) => item.target),
  );
  return design.departments
    .map((department, index) => ({
      departmentId: department.id,
      departmentName: department.name,
      departmentIndex: index,
      modules: design.modules
        .filter((item) => item.department === department.id && !item.closed)
        .map((item) => ({
          id: item.id,
          name: item.name,
          state:
            item.id === sourceId
              ? ("self" as const)
              : linked.has(item.id)
                ? ("linked" as const)
                : ("choosable" as const),
        })),
    }))
    .filter((group) => group.modules.length);
}

function inUse(name: string, existingNames: RelationshipNamesInUse): boolean {
  const wanted = key(name);
  return [...existingNames.fields, ...existingNames.relationships].some(
    (item) => key(item) === wanted,
  );
}

/** "Orders to Customers", then " 2", " 3", … while the name is in use. */
export function prefill(
  sourceName: string,
  targetName: string,
  existingNames: RelationshipNamesInUse,
): string {
  const base = `${sourceName.trim()} to ${targetName.trim()}`;
  let name = base;
  for (let suffix = 2; inUse(name, existingNames); suffix += 1)
    name = `${base} ${suffix}`;
  return name;
}

/** The refusal for a name already in use on the source, or null. */
export function clashReason(
  name: string,
  existingNames: RelationshipNamesInUse,
  sourceName: string,
): string | null {
  const wanted = key(name);
  const field = existingNames.fields.find((item) => key(item) === wanted);
  if (field !== undefined)
    return `${sourceName} already has a field named ${field}.`;
  const relationship = existingNames.relationships.find(
    (item) => key(item) === wanted,
  );
  if (relationship !== undefined)
    return `${sourceName} already has a relationship named ${relationship}.`;
  return null;
}

function findTarget(
  targets: readonly ConnectTargetGroup[],
  targetId: string | null,
): ConnectTarget | undefined {
  return targets
    .flatMap((group) => group.modules)
    .find((item) => item.id === targetId);
}

/** Chooses a target; a row that is not choosable changes nothing. */
export function chooseTarget(
  draft: ConnectDraft,
  targets: readonly ConnectTargetGroup[],
  targetId: string,
): ConnectDraft {
  return findTarget(targets, targetId)?.state === "choosable"
    ? { ...draft, targetId }
    : draft;
}

/** Typing in Name stops the name from following the target. */
export function typeName(draft: ConnectDraft, value: string): ConnectDraft {
  return { ...draft, typedName: value };
}

/** The Name value: what was typed, else the prefill for the target. */
export function draftName(
  draft: ConnectDraft,
  sourceName: string,
  targets: readonly ConnectTargetGroup[],
  existingNames: RelationshipNamesInUse,
): string {
  if (draft.typedName !== null) return draft.typedName;
  const target = findTarget(targets, draft.targetId);
  return target ? prefill(sourceName, target.name, existingNames) : "";
}

/** The refusal for a Name value, or null; an empty name is the caller's. */
export function nameProblem(
  name: string,
  existingNames: RelationshipNamesInUse,
  sourceName: string,
): string | null {
  if (name.trim().length > SANDBOX_LIMITS.nameCharacters)
    return `Use ${SANDBOX_LIMITS.nameCharacters} characters or fewer.`;
  return clashReason(name, existingNames, sourceName);
}

/**
 * Why Connect waits while no target is chosen: choose one, or, when every
 * row is dim, there is nothing left to connect to.
 */
export function noTargetReason(
  targets: readonly ConnectTargetGroup[],
  sourceName: string,
): string {
  return choosableIds(targets).length
    ? "Choose a module to connect to."
    : `${sourceName} has no module left to connect to.`;
}

export function connectSubmission(
  draft: ConnectDraft,
  sourceName: string,
  targets: readonly ConnectTargetGroup[],
  existingNames: RelationshipNamesInUse,
): ConnectSubmission {
  const target = findTarget(targets, draft.targetId);
  if (!target || target.state !== "choosable")
    return { ok: false, reason: noTargetReason(targets, sourceName) };
  const name = draftName(draft, sourceName, targets, existingNames).trim();
  if (!name) return { ok: false, reason: "Enter a name." };
  const problem = nameProblem(name, existingNames, sourceName);
  if (problem) return { ok: false, reason: problem };
  return { ok: true, request: { targetId: target.id, name } };
}

function choosableIds(targets: readonly ConnectTargetGroup[]): string[] {
  return targets
    .flatMap((group) => group.modules)
    .filter((item) => item.state === "choosable")
    .map((item) => item.id);
}

/** The next or previous choosable target; the ends do not wrap. */
export function nextChoosable(
  targets: readonly ConnectTargetGroup[],
  activeId: string | null,
  step: 1 | -1,
): string | null {
  const ids = choosableIds(targets);
  const at = activeId === null ? -1 : ids.indexOf(activeId);
  if (at < 0) return ids[0] ?? null;
  return ids[Math.min(Math.max(at + step, 0), ids.length - 1)] ?? null;
}

/**
 * Type-ahead: the first choosable target whose name starts with the typed
 * letters. One repeated letter moves on from the active target.
 */
export function typeAheadMatch(
  targets: readonly ConnectTargetGroup[],
  query: string,
  activeId: string | null,
): string | null {
  const wanted = query.toLowerCase();
  if (!wanted) return null;
  const choosable = targets
    .flatMap((group) => group.modules)
    .filter((item) => item.state === "choosable");
  const at = choosable.findIndex((item) => item.id === activeId);
  const start = wanted.length === 1 && at >= 0 ? at + 1 : 0;
  const ordered = [...choosable.slice(start), ...choosable.slice(0, start)];
  return (
    ordered.find((item) => item.name.toLowerCase().startsWith(wanted))?.id ??
    null
  );
}
