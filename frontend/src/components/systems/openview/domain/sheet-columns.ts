import { ApiError } from "@/lib/api";
import type { WorksheetStructure } from "../adapters/worksheets-api";

// The column list as route 6 takes it back (docs/specs/sheets.md K8, D1.7):
// a column group is a named band over adjacent columns, its keys in column
// order, groups never overlapping. Groups are found by their place in the
// list: the server does not require their names to differ.

type Structure = Pick<WorksheetStructure, "columns" | "groups" | "totals">;
type Column = WorksheetStructure["columns"][number];
type Group = WorksheetStructure["groups"][number];

/** Where a column goes: no group, an existing group by place, or a new one. */
export type GroupChoice = { group: number | null } | { newGroup: string };

/** Each group's keys in column order, empty groups dropped. */
function inColumnOrder(columns: readonly Column[], groups: Group[]): Group[] {
  const position = new Map(columns.map((column, index) => [column.key, index]));
  return groups
    .map((group) => ({
      ...group,
      keys: group.keys
        .filter((key) => position.has(key))
        .sort((a, b) => (position.get(a) ?? 0) - (position.get(b) ?? 0)),
    }))
    .filter((group) => group.keys.length > 0);
}

/**
 * The structure with one column placed in its group: a column that joins a
 * group moves after the group's last column; one that leaves a group moves
 * out after it; otherwise it keeps its place (a new column goes last). The
 * column is given by key, or as a new column.
 */
export function placeColumn(
  structure: Structure,
  column: string | Column,
  choice: GroupChoice,
): Structure {
  const key = typeof column === "string" ? column : column.key;
  const moving =
    typeof column === "string"
      ? structure.columns.find((item) => item.key === key)
      : column;
  if (!moving) return structure;
  const index = structure.columns.findIndex((item) => item.key === key);
  const columns = structure.columns.filter((item) => item.key !== key);
  const fromIndex = structure.groups.findIndex((group) =>
    group.keys.includes(key),
  );
  let groups = structure.groups.map((group) => ({
    ...group,
    keys: group.keys.filter((item) => item !== key),
  }));
  const target = "newGroup" in choice ? null : choice.group;
  const after = (group: Group | undefined) => {
    const last = group?.keys.at(-1);
    const at = columns.findIndex((item) => item.key === last);
    return at < 0 ? columns.length : at + 1;
  };
  let at: number;
  if (target !== null && target === fromIndex && groups[target]) {
    // It stays in its group: same place.
    at = index;
    groups[target] = { ...groups[target], keys: [...groups[target].keys, key] };
  } else if (target !== null && groups[target]) {
    at = after(groups[target]);
    groups[target] = { ...groups[target], keys: [...groups[target].keys, key] };
  } else if (fromIndex >= 0 && fromIndex !== target) {
    at = after(groups[fromIndex]);
  } else at = index < 0 ? columns.length : index;
  columns.splice(at, 0, moving);
  if ("newGroup" in choice)
    groups = [...groups, { name: choice.newGroup, keys: [key] }];
  return { ...structure, columns, groups: inColumnOrder(columns, groups) };
}

export function renameGroup(
  groups: readonly Group[],
  index: number,
  name: string,
): Group[] {
  return groups.map((group, place) =>
    place === index ? { ...group, name } : group,
  );
}

/** Removes a group; its columns stay where they are, without a group. */
export function removeGroup(groups: readonly Group[], index: number): Group[] {
  return groups.filter((_group, place) => place !== index);
}

/** The structure without one column, its group place and its total. */
export function withoutColumn(structure: Structure, key: string): Structure {
  const columns = structure.columns.filter((column) => column.key !== key);
  const totals = { ...structure.totals };
  delete totals[key];
  return {
    columns,
    groups: inColumnOrder(columns, [...structure.groups]),
    totals,
  };
}

const refusalSchema = (details: unknown) =>
  typeof details === "object" && details !== null
    ? (details as { code?: unknown; key?: unknown; reason?: unknown })
    : {};

function sentence(text: string): string {
  const trimmed = text.trim();
  if (!trimmed) return trimmed;
  const first = trimmed[0].toUpperCase() + trimmed.slice(1);
  return /[.!?]$/.test(first) ? first : `${first}.`;
}

/**
 * A refused column save in plain words. The server's message starts with
 * the column's name; for the column being edited the name is dropped. A
 * computed column that reads a deleted column is named, because the
 * server's words then show the deleted column's key.
 */
export function columnRefusal(
  error: unknown,
  context: {
    editedKey: string;
    names: Record<string, string>;
    /** The name of the column being deleted. */
    removedName?: string;
  },
): string {
  if (!(error instanceof ApiError))
    return "The column could not be saved. Try again.";
  if (error.status === 412)
    return "Someone changed this sheet's columns. Close this and try again.";
  if (error.status !== 409 && error.status !== 422)
    return "The column could not be saved. Try again.";
  const details = refusalSchema(error.details);
  const key = typeof details.key === "string" ? details.key : null;
  const other = key && key !== context.editedKey ? context.names[key] : null;
  if (
    other &&
    details.reason === "unknown_column" &&
    context.removedName !== undefined
  )
    return `${other} uses ${context.removedName}. Change ${other} first.`;
  const message = error.message;
  const prefix = key ? context.names[key] : undefined;
  if (prefix && key === context.editedKey && message.startsWith(`${prefix}: `))
    return sentence(message.slice(prefix.length + 2));
  const colon = message.indexOf(": ");
  if (key === context.editedKey && colon > 0)
    return sentence(message.slice(colon + 2));
  return sentence(message);
}
