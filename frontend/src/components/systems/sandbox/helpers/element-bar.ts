import type { Design } from "../domain/model";
import { canvasFieldId } from "./bridge";

/**
 * Rules of the element bar and the canvas item menu
 * (docs/specs/sandbox-ux-redesign.md, "Build: find and create"). The bar of
 * the selected element shows without pointer action; any other element's bar
 * shows after the pointer rests on it, and stays a moment after it leaves so
 * the pointer can reach it.
 */

/** The pointer rests this long on an element before its bar shows. */
export const BAR_REST_MS = 120;
/** A pointed bar stays this long after the pointer leaves its element. */
export const BAR_LINGER_MS = 300;

export type PointerRest = {
  /** The element under the pointer whose rest has not finished yet. */
  candidate: string | null;
  since: number;
  /** The pointed element whose bar shows. */
  shown: string | null;
  /** When the shown bar hides, unless the pointer comes back first. */
  hideAt: number | null;
  /** The pointer is on the shown bar itself. */
  onBar: boolean;
};

export type PointerRestEvent =
  | { type: "enter"; id: string; at: number }
  | { type: "leave"; id: string; at: number }
  | { type: "barEnter" }
  | { type: "barLeave"; at: number }
  | { type: "tick"; at: number }
  /** A pan, zoom, or drag: no pointed bar until the pointer rests again. */
  | { type: "cancel" };

export const idlePointerRest: PointerRest = {
  candidate: null,
  since: 0,
  shown: null,
  hideAt: null,
  onBar: false,
};

export function reducePointerRest(
  state: PointerRest,
  event: PointerRestEvent,
): PointerRest {
  switch (event.type) {
    case "enter":
      return state.shown === event.id
        ? { ...state, candidate: null, hideAt: null }
        : { ...state, candidate: event.id, since: event.at };
    case "leave":
      return {
        ...state,
        candidate: state.candidate === event.id ? null : state.candidate,
        hideAt:
          state.shown === event.id ? event.at + BAR_LINGER_MS : state.hideAt,
      };
    case "barEnter":
      return { ...state, onBar: true, hideAt: null };
    case "barLeave":
      return {
        ...state,
        onBar: false,
        hideAt: state.shown === null ? null : event.at + BAR_LINGER_MS,
      };
    case "tick": {
      let next = state;
      if (next.hideAt !== null && event.at >= next.hideAt && !next.onBar)
        next = { ...next, shown: null, hideAt: null };
      if (next.candidate !== null && event.at - next.since >= BAR_REST_MS)
        next = {
          ...next,
          shown: next.candidate,
          candidate: null,
          hideAt: null,
        };
      return next;
    }
    case "cancel":
      return idlePointerRest;
  }
}

/** When the next tick changes something, so a timer can wake for it. */
export function pointerRestWake(state: PointerRest): number | null {
  const times = [
    state.candidate === null ? null : state.since + BAR_REST_MS,
    state.onBar ? null : state.hideAt,
  ].filter((time): time is number => time !== null);
  return times.length ? Math.min(...times) : null;
}

/**
 * The element whose bar a selection or a pointed element shows: a field
 * shows its module's bar; a relationship has none.
 */
export function elementBarOwner(
  state: {
    departments: readonly { id: string }[];
    modules: readonly { id: string }[];
    fields: readonly { id: string; moduleId: string }[];
  },
  id: string | null,
): string | null {
  if (!id) return null;
  if (state.departments.some((item) => item.id === id)) return id;
  if (state.modules.some((item) => item.id === id)) return id;
  return state.fields.find((item) => item.id === id)?.moduleId ?? null;
}

/**
 * The bars on the canvas, once each: a held bar (focus is inside it, or an
 * entry it opened is open) always; the selected element's, the focused
 * Structure row's, and the pointed element's unless the canvas is busy.
 */
export function elementBarOwners({
  held,
  selected,
  focused,
  pointed,
  busy,
}: {
  held: string | null;
  selected: string | null;
  focused: string | null;
  pointed: string | null;
  busy: boolean;
}): string[] {
  const owners = busy ? [held] : [held, selected, focused, pointed];
  return [
    ...new Set(owners.filter((id): id is string => typeof id === "string")),
  ];
}

/**
 * The canvas and Structure ids of queued adds that the design still has. An
 * Undo of a queued add can leave its id in the queue; it marks nothing.
 */
export function savingMarkIds(
  design: Design,
  ids: readonly string[],
): Set<string> {
  const queued = new Set(ids);
  const marked = new Set<string>();
  if (queued.size === 0) return marked;
  for (const item of design.departments)
    if (queued.has(item.id)) marked.add(item.id);
  for (const item of design.modules) {
    if (queued.has(item.id)) marked.add(item.id);
    for (const field of item.fields)
      if (queued.has(field.id)) marked.add(canvasFieldId(item.id, field.id));
  }
  for (const item of design.relationships)
    if (queued.has(item.id)) marked.add(item.id);
  return marked;
}

export type ItemMenuKind = "department" | "module" | "field";
export type ItemMenuAction =
  | "rename"
  | "lifecycle"
  | "purge"
  | "duplicate"
  | "connect"
  | "newTrigger"
  | "delete";
export type ItemMenuEntry = {
  action: ItemMenuAction;
  label: string;
  /** The last group, after a separator. */
  destructive: boolean;
};

/**
 * The item menu of a department, module, or field: the same in the
 * Structure tree and on the canvas (FIND-6). A module adds "Connect…" and,
 * when Triggers can take it, "New trigger" (TRIG-8).
 */
export function itemMenuEntries(
  kind: ItemMenuKind,
  options: {
    closed: boolean;
    canPurge: boolean;
    /** Close and Reopen are offered. */
    lifecycle: boolean;
    duplicate: boolean;
    connect: boolean;
    newTrigger: boolean;
  },
): ItemMenuEntry[] {
  const entry = (
    action: ItemMenuAction,
    label: string,
    destructive = false,
  ): ItemMenuEntry => ({ action, label, destructive });
  return [
    entry("rename", `Rename ${kind}`),
    ...(options.lifecycle
      ? [entry("lifecycle", `${options.closed ? "Reopen" : "Close"} ${kind}`)]
      : []),
    ...(options.canPurge ? [entry("purge", `Delete ${kind} forever`)] : []),
    ...(options.duplicate ? [entry("duplicate", `Duplicate ${kind}`)] : []),
    ...(kind === "module" && options.connect
      ? [entry("connect", "Connect…")]
      : []),
    ...(kind === "module" && options.newTrigger
      ? [entry("newTrigger", "New trigger")]
      : []),
    entry("delete", `Delete ${kind}`, true),
  ];
}
