import type { Design } from "../domain/model";
import type { SandboxDocumentV4 } from "../domain/document";
import type { SandboxDocumentResponse } from "./api";
import { SandboxCommandError } from "./commands";
import {
  openSandboxDocumentSession,
  proposedSandboxDocument,
  synchronizeSandboxHistoryRules,
  type SandboxDocumentSession,
} from "./document-session";

/**
 * The Build save queue (N1, A1). Only Build adds, and Undo or Redo, are
 * accepted while a `PUT /api/sandbox/document` is in flight; they change the
 * local design at once and leave together in the next request. One request
 * is in flight at a time. The page owns the session and the requests; this
 * module holds only the queue's state and the pure rules around it.
 */
export type SandboxSaveQueue = {
  /** A request is in flight. */
  readonly inFlight: boolean;
  /** Local changes accepted so far. */
  readonly accepted: number;
  /** Accepted changes that a request already carries. */
  readonly sent: number;
  /** Added element ids the request in flight carries. */
  readonly sending: readonly string[];
  /** Added element ids accepted after it, waiting for the next request. */
  readonly queued: readonly string[];
};

export type SandboxSaveQueueEvent =
  | { type: "accept"; ids: readonly string[] }
  | { type: "send" }
  | { type: "confirm" }
  | { type: "fail" };

export const idleSaveQueue: SandboxSaveQueue = {
  inFlight: false,
  accepted: 0,
  sent: 0,
  sending: [],
  queued: [],
};

export function reduceSaveQueue(
  queue: SandboxSaveQueue,
  event: SandboxSaveQueueEvent,
): SandboxSaveQueue {
  switch (event.type) {
    case "accept":
      return {
        ...queue,
        accepted: queue.accepted + 1,
        queued: [
          ...queue.queued,
          ...event.ids.filter((id) => !queue.queued.includes(id)),
        ],
      };
    case "send":
      if (!saveQueueNeedsSend(queue)) return queue;
      return {
        ...queue,
        inFlight: true,
        sent: queue.accepted,
        sending: queue.queued,
        queued: [],
      };
    case "confirm":
      return { ...queue, inFlight: false, sending: [] };
    case "fail":
      // The conflict record keeps every accepted change; nothing more is sent.
      return idleSaveQueue;
  }
}

/** Accepted changes that no request carries yet. */
export function saveQueueHasQueued(queue: SandboxSaveQueue): boolean {
  return queue.accepted > queue.sent;
}

/** Nothing is in flight and accepted changes wait to be sent. */
export function saveQueueNeedsSend(queue: SandboxSaveQueue): boolean {
  return !queue.inFlight && saveQueueHasQueued(queue);
}

/** A non-empty queue: every action that reads the saved draft waits. */
export function saveQueueActive(queue: SandboxSaveQueue): boolean {
  return queue.inFlight || saveQueueHasQueued(queue);
}

/** Added elements that are not confirmed yet (the saving mark). */
export function savingElementIds(queue: SandboxSaveQueue): string[] {
  return [
    ...queue.sending,
    ...queue.queued.filter((id) => !queue.sending.includes(id)),
  ];
}

export type DesignChange =
  { kind: "none" } | { kind: "edit" } | { kind: "add"; ids: string[] };

function same(left: unknown, right: unknown): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

/**
 * The items of `next` without the ones whose id `previous` lacks, and those
 * new ids. An add keeps every earlier item exactly as it was.
 */
function splitNew<T extends { id: string }>(
  previous: readonly T[],
  next: readonly T[],
): { kept: T[]; added: string[] } {
  const known = new Set(previous.map((item) => item.id));
  return {
    kept: next.filter((item) => known.has(item.id)),
    added: next.filter((item) => !known.has(item.id)).map((item) => item.id),
  };
}

function sameLayout(
  previous: Design["layout"],
  next: Design["layout"],
  added: ReadonlySet<string>,
): boolean {
  const before = previous ?? {};
  const after = Object.fromEntries(
    Object.entries(next ?? {}).filter(([id]) => !added.has(id)),
  );
  const keys = Object.keys(before);
  return (
    keys.length === Object.keys(after).length &&
    keys.every((id) => same(before[id], after[id]))
  );
}

/**
 * Tells a Build add from any other edit: an add only appends departments,
 * modules, fields, or relationships with new ids (and their layout slots)
 * and leaves every other part of the design as it was.
 */
export function classifyDesignChange(
  previous: Design,
  next: Design,
): DesignChange {
  if (next === previous || same(next, previous)) return { kind: "none" };
  if (!same(next.rules, previous.rules)) return { kind: "edit" };
  const departments = splitNew(previous.departments, next.departments);
  const modules = splitNew(previous.modules, next.modules);
  const relationships = splitNew(previous.relationships, next.relationships);
  const fieldIds: string[] = [];
  const keptModules = modules.kept.map((item) => {
    const before = previous.modules.find((entry) => entry.id === item.id);
    const fields = splitNew(before?.fields ?? [], item.fields);
    fieldIds.push(...fields.added);
    return { ...item, fields: fields.kept };
  });
  const ids = [
    ...departments.added,
    ...modules.added,
    ...fieldIds,
    ...relationships.added,
  ];
  if (
    ids.length === 0 ||
    !same(departments.kept, previous.departments) ||
    !same(keptModules, previous.modules) ||
    !same(relationships.kept, previous.relationships) ||
    !sameLayout(previous.layout, next.layout, new Set(ids))
  )
    return { kind: "edit" };
  return { kind: "add", ids };
}

/** Element ids in `next` that `previous` lacks: what an Undo or Redo brings back. */
export function addedElementIds(previous: Design, next: Design): string[] {
  const known = new Set([
    ...previous.departments.map((item) => item.id),
    ...previous.modules.flatMap((item) => [
      item.id,
      ...item.fields.map((field) => field.id),
    ]),
    ...previous.relationships.map((item) => item.id),
  ]);
  return [
    ...next.departments.map((item) => item.id),
    ...next.modules.flatMap((item) => [
      item.id,
      ...item.fields.map((field) => field.id),
    ]),
    ...next.relationships.map((item) => item.id),
  ].filter((id) => !known.has(id));
}

/**
 * The next request: the local design merged onto the last confirmed
 * document, at the last confirmed revision.
 */
export function saveQueueRequest(session: SandboxDocumentSession): {
  expectedRevision: number;
  document: SandboxDocumentV4;
} {
  return {
    expectedRevision: session.revision,
    document: proposedSandboxDocument(session),
  };
}

/**
 * The session after a confirmed save. With nothing queued, the confirmed
 * design replaces the local one, as before the queue. With queued changes,
 * the local design and Undo history stay; the confirmed document, revision,
 * and trigger rules become the base of the next request.
 */
export function confirmQueuedSave(
  local: SandboxDocumentSession,
  response: SandboxDocumentResponse,
  queued: boolean,
): SandboxDocumentSession {
  const confirmed = openSandboxDocumentSession(response);
  if (!queued)
    return {
      ...confirmed,
      history: synchronizeSandboxHistoryRules(
        local.history,
        confirmed.projected,
      ),
    };
  // Without the confirmed rules, the next merge would read a rule edit and
  // rebuild the stored trigger from the local projection.
  return {
    ...confirmed,
    history: synchronizeSandboxHistoryRules(local.history, {
      ...local.history.present,
      rules: confirmed.projected.rules,
    }),
  };
}

/**
 * What the conflict record keeps after a refused save: the local design at
 * that moment, queued changes included. With nothing queued, the request
 * body is that design.
 */
export function saveQueueConflictDocument(
  local: SandboxDocumentSession,
  requestDocument: SandboxDocumentV4,
  queued: boolean,
): SandboxDocumentV4 {
  return queued ? proposedSandboxDocument(local) : requestDocument;
}

/**
 * The words for a design update that threw before it changed the draft. A
 * design rule the update checks refuses it with its own reason, also under a
 * hold; any other failure under a hold reads as a save in flight, and
 * without a hold it is thrown again.
 */
export function refusedDesignUpdate(
  error: unknown,
  holdReason: string | null,
): string {
  if (error instanceof SandboxCommandError) return error.message;
  if (holdReason) return "A Sandbox change is already being saved.";
  throw error;
}

/**
 * Why an add cannot be accepted now (rule 6): a publish, a lifecycle action,
 * a conflict, or another Sandbox command holds the draft.
 */
export function designAddHoldReason(holds: {
  command: boolean;
  publication: boolean;
  /** A lifecycle action not yet counted in `command` (the page's lock). */
  lifecycle?: boolean;
  conflict: boolean;
}): string | null {
  return holds.command || holds.publication || holds.lifecycle || holds.conflict
    ? "Wait for the current Sandbox action to finish."
    : null;
}
