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
  | "setup"
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
 * when Triggers can take it, "New trigger" (TRIG-8); a new open department
 * adds "Setup…".
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
    /** The department has no live binding, so Setup applies. */
    setup?: boolean;
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
    // Connect leaves closed modules out of its targets (publish skips their
    // relationships), so a closed module has no Connect… either.
    ...(kind === "module" && options.connect && !options.closed
      ? [entry("connect", "Connect…")]
      : []),
    // Triggers offers only open modules (`moduleChoiceGroups`), so a closed
    // module has no New trigger (TRIG-8).
    ...(kind === "module" && options.newTrigger && !options.closed
      ? [entry("newTrigger", "New trigger")]
      : []),
    // The keyboard route to a new open department's Setup (FIT-1).
    ...(kind === "department" && options.setup && !options.closed
      ? [entry("setup", "Setup…")]
      : []),
    entry("delete", `Delete ${kind}`, true),
  ];
}

export type ElementBarAction = "module" | "field" | "connect" | "setup";

/**
 * The controls of an element's bar: a department adds modules, and a new open
 * one also holds Setup (FIT-1); a module
 * adds fields and connects, except a closed one, which Connect leaves out of
 * its targets and so connects to nothing (as its item menu has no
 * "Connect…").
 */
export function elementBarActions(
  kind: "department" | "module",
  closed: boolean,
  setup = false,
): ElementBarAction[] {
  if (kind === "department")
    return setup && !closed ? ["module", "setup"] : ["module"];
  return closed ? ["field"] : ["field", "connect"];
}

/** Where a bar sits: next to its element, above it, or inside under its head. */
export type BarPlace = "beside" | "above" | "inside";
export type BarPlacement = { left: number; top: number; place: BarPlace };

/** Space between an element and its bar, in screen pixels. */
export const BAR_GAP = 6;

/**
 * A department's bar (screen pixels, the canvas pane's top edge at 0). It
 * tries three places in order and never covers the head band's name or
 * module count: in the band after the name; above the frame; then, when the
 * space above is outside the pane, 6px under the band inside the frame, its
 * right edge under the count's right edge and never left of the identity
 * mark (a frame narrower than the bar lets it hang past the right edge).
 */
export function departmentBarPlacement(measure: {
  frameTop: number;
  bandBottom: number;
  nameRight: number;
  identityLeft: number;
  countLeft: number;
  countRight: number;
  width: number;
  height: number;
}): BarPlacement {
  const left = measure.nameRight + 8;
  if (left + measure.width <= measure.countLeft - 8)
    return {
      left,
      top: (measure.frameTop + measure.bandBottom) / 2 - measure.height / 2,
      place: "beside",
    };
  const above = measure.frameTop - measure.height - BAR_GAP;
  if (above >= 0) return { left, top: above, place: "above" };
  return {
    left: Math.max(measure.identityLeft, measure.countRight - measure.width),
    top: measure.bandBottom + BAR_GAP,
    place: "inside",
  };
}

/**
 * A module's bar: under the card, where the next field appears; above the
 * header when the card bottom is out of view; and 6px under the header,
 * over the first field rows, when the space above is outside the pane too.
 * It stays aligned left.
 */
export function moduleBarPlacement(measure: {
  left: number;
  top: number;
  headerBottom: number;
  bottom: number;
  viewHeight: number;
  height: number;
}): BarPlacement {
  const under = measure.bottom + BAR_GAP;
  if (under + measure.height <= measure.viewHeight - BAR_GAP)
    return { left: measure.left, top: under, place: "beside" };
  const above = measure.top - measure.height - BAR_GAP;
  if (above >= 0) return { left: measure.left, top: above, place: "above" };
  return {
    left: measure.left,
    top: measure.headerBottom + BAR_GAP,
    place: "inside",
  };
}
