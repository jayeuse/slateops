import { ApiError, getApiFieldErrors } from "@/lib/api";
import { apiErrorReference } from "@/lib/api-errors";
import type {
  OpenViewDataSourceField,
  OpenViewRecord,
} from "../adapters/views-api";
import {
  encodeFormValue,
  selectOptions,
  serverFieldMessage,
  toFormValue,
  type RecordFormValue,
} from "./record-form";

// A value changed in place on the record sheet's Details tab (item 2,
// docs/specs/ux-friction-pass.md, DR-2.2 to DR-2.13). Four field types change
// in place; the rest keep Edit. A PATCH replaces every active value, so each
// commit sends the complete stored record with one value changed, and its
// `If-Match` is the revision behind the value on screen.

/** The four field types that change in place (DR-2.2). */
export const IN_PLACE_FIELD_TYPES: ReadonlySet<
  OpenViewDataSourceField["type"]
> = new Set(["select", "boolean", "date", "datetime"]);

export const IN_PLACE_WORDS = {
  saving: "Saving…",
  conflict: "Someone changed this record. It shows their value now.",
  undoConflict: "Not undone. Someone changed this record after you.",
  notSaved: "Not saved. Try again.",
} as const;

/**
 * How one Details value shows: plain text, an in-place control, or the
 * control disabled until every field is loaded (DR-2.10, DR-2.11, DR-2.13).
 */
export type InPlaceMode = "plain" | "control" | "waiting";

export function inPlaceMode(
  field: Pick<OpenViewDataSourceField, "type"> | undefined,
  record: {
    canWrite: boolean;
    isDeleted: boolean;
    editing: boolean;
    fieldsComplete: boolean;
  },
): InPlaceMode {
  if (
    !field ||
    !record.canWrite ||
    record.isDeleted ||
    record.editing ||
    !IN_PLACE_FIELD_TYPES.has(field.type)
  )
    return "plain";
  return record.fieldsComplete ? "control" : "waiting";
}

export type InPlaceCommit =
  { kind: "none" } | { kind: "revert" } | { kind: "commit"; value: unknown };

/**
 * What a committed control value does (DR-2.3): an incomplete date or an
 * unchanged value sends nothing, a value that cannot be saved puts back the
 * stored value, and any other value is sent.
 */
export function inPlaceCommit(
  field: OpenViewDataSourceField,
  stored: unknown,
  input: RecordFormValue,
  complete = true,
): InPlaceCommit {
  if (!complete) return { kind: "revert" };
  // Compare form values, so a stored instant with seconds is not "changed".
  if (toFormValue(field, stored) === input) return { kind: "none" };
  const encoded = encodeFormValue(field, input);
  if ("error" in encoded) return { kind: "revert" };
  return { kind: "commit", value: encoded.value };
}

/**
 * The `data` of one in-place PATCH (DR-2.4): every active field of the
 * complete catalog with its stored value, as the Edit save sends unchanged
 * fields, and the one changed value.
 */
export function inPlacePatchData(
  fields: readonly Pick<OpenViewDataSourceField, "id">[],
  stored: Record<string, unknown>,
  fieldId: string,
  value: unknown,
): Record<string, unknown> {
  return Object.fromEntries(
    fields.map((field) => [
      field.id,
      field.id === fieldId ? value : (stored[field.id] ?? null),
    ]),
  );
}

/** Whether `left` changed at the same time as or after `right`. */
function notOlder(left: string, right: string): boolean {
  const leftTime = Date.parse(left);
  const rightTime = Date.parse(right);
  if (Number.isNaN(leftTime) || Number.isNaN(rightTime)) return left === right;
  return leftTime >= rightTime;
}

/**
 * The record whose values show and whose revision the next PATCH sends
 * (DR-2.13): the last response, unless the sheet's record is newer.
 */
export function seenRecord(
  shown: OpenViewRecord,
  latest: OpenViewRecord | null,
): OpenViewRecord {
  return latest &&
    latest.id === shown.id &&
    notOlder(latest.updatedAt, shown.updatedAt)
    ? latest
    : shown;
}

/** The words of a value change for the record header (DR-2.5, DR-2.6). */
export function inPlaceChangeMessage(
  field: OpenViewDataSourceField,
  value: unknown,
  formatted: string,
  undone = false,
): string {
  if (field.type === "boolean")
    return `${field.name} turned ${value === true ? "on" : "off"}.`;
  if (value === null || value === undefined || value === "")
    return `${field.name} cleared.`;
  const label =
    field.type === "select"
      ? (selectOptions(field).find((option) => option.id === value)?.label ??
        formatted)
      : formatted;
  return undone
    ? `${field.name} changed back to ${label}.`
    : `${field.name} changed to ${label}.`;
}

/** Where a refused in-place save shows (DR-2.7, DR-2.8). */
export type InPlaceFailure =
  | { kind: "conflict" }
  | { kind: "field"; message: string }
  | { kind: "other-field"; message: string }
  | { kind: "failed"; reference: string | undefined };

export function inPlaceFailure(
  error: unknown,
  fieldId: string,
): InPlaceFailure {
  if (error instanceof ApiError && error.status === 412)
    return { kind: "conflict" };
  if (error instanceof ApiError && error.status === 422) {
    const fieldMessages = getApiFieldErrors(error);
    const own = fieldMessages[fieldId]?.[0];
    if (own !== undefined)
      return { kind: "field", message: serverFieldMessage(own) };
    const other = Object.values(fieldMessages).find(
      (messages) => messages.length > 0,
    )?.[0];
    if (other !== undefined)
      return { kind: "other-field", message: serverFieldMessage(other) };
  }
  return { kind: "failed", reference: apiErrorReference(error) };
}

/** The record header's in-place status, which the page renders (DR-2.5). */
export type RecordInPlaceStatus =
  | { kind: "saving"; message: string }
  | {
      kind: "saved";
      message: string;
      /** Writes the previous value back; null once undone (DR-2.6). */
      undo: (() => void) | null;
    }
  | { kind: "failed"; message: string; reference: string | undefined };

/** The value an Undo writes back, and the change it undoes. */
export type InPlaceUndo = { fieldId: string; previous: unknown };

/** The message and reference shown under one field (DR-2.7, DR-2.8). */
export type InPlaceFieldError = {
  fieldId: string;
  message: string;
  reference: string | undefined;
};

/** The meta-line message of the last settled commit (DR-2.5 to DR-2.8). */
export type InPlaceNotice =
  | { kind: "saved"; message: string }
  | { kind: "failed"; message: string; reference: string | undefined };

/**
 * One record's in-place session. One commit runs at a time (DR-2.13); the
 * last response is the complete record and the revision for the next one.
 */
export type InPlaceState = {
  saving: { fieldId: string; value: unknown; undo: boolean } | null;
  latest: OpenViewRecord | null;
  undo: InPlaceUndo | null;
  fieldError: InPlaceFieldError | null;
  notice: InPlaceNotice | null;
};

export const initialInPlaceState: InPlaceState = {
  saving: null,
  latest: null,
  undo: null,
  fieldError: null,
  notice: null,
};

export type InPlaceAction =
  | { type: "start"; fieldId: string; value: unknown; undo: boolean }
  | {
      type: "saved";
      record: OpenViewRecord;
      /** The header words of the change (`inPlaceChangeMessage`). */
      message: string;
      /** The value before the change; null after an Undo. */
      undo: InPlaceUndo | null;
    }
  | {
      type: "refused";
      failure: InPlaceFailure;
      /** The record read again after a conflict, when the read succeeded. */
      record: OpenViewRecord | null;
    }
  /** Edit, a tab change: the Undo offer ends and its words go (DR-2.6). */
  | { type: "clear-status" };

/** Whether a new commit may start: never beside one that is saving. */
export function canStartInPlace(state: InPlaceState): boolean {
  return state.saving === null;
}

/** Where a refusal shows: under the field, in the meta line, or both kept. */
function refusal(
  saving: NonNullable<InPlaceState["saving"]>,
  failure: InPlaceFailure,
  notice: InPlaceNotice | null,
): Pick<InPlaceState, "fieldError" | "notice"> {
  const under = (message: string, reference?: string) => ({
    fieldError: { fieldId: saving.fieldId, message, reference },
    // A failed Undo keeps the change's words and its Undo (DR-2.8).
    notice: saving.undo ? notice : null,
  });
  switch (failure.kind) {
    case "conflict":
      return saving.undo
        ? {
            fieldError: null,
            notice: {
              kind: "failed",
              message: IN_PLACE_WORDS.undoConflict,
              reference: undefined,
            },
          }
        : under(IN_PLACE_WORDS.conflict);
    case "field":
      return under(failure.message);
    case "other-field":
      // That field has no control on screen.
      return {
        fieldError: null,
        notice: {
          kind: "failed",
          message: failure.message,
          reference: undefined,
        },
      };
    case "failed":
      return under(IN_PLACE_WORDS.notSaved, failure.reference);
  }
}

export function inPlaceReducer(
  state: InPlaceState,
  action: InPlaceAction,
): InPlaceState {
  switch (action.type) {
    case "start":
      if (!canStartInPlace(state)) return state;
      return {
        ...state,
        saving: {
          fieldId: action.fieldId,
          value: action.value,
          undo: action.undo,
        },
        fieldError: null,
        // A new change ends the offer to undo the last one, and its words
        // (DR-2.6); an Undo keeps them until it settles.
        undo: action.undo ? state.undo : null,
        notice: action.undo ? state.notice : null,
      };
    case "saved":
      return {
        saving: null,
        latest: action.record,
        undo: action.undo,
        fieldError: null,
        notice: { kind: "saved", message: action.message },
      };
    case "refused": {
      if (!state.saving) return state;
      return {
        ...state,
        saving: null,
        latest: action.record ?? state.latest,
        // A failed Undo stays offered, unless someone changed the record.
        undo: action.failure.kind === "conflict" ? null : state.undo,
        ...refusal(state.saving, action.failure, state.notice),
      };
    }
    case "clear-status":
      // The words go with the Undo; a failure message stays only until here.
      return state.undo || state.notice
        ? { ...state, undo: null, notice: null }
        : state;
  }
}

/** The header status as data; `canUndo` asks the page to show Undo. */
export type InPlaceStatusData =
  | { kind: "saving"; message: string }
  | { kind: "saved"; message: string; canUndo: boolean }
  | { kind: "failed"; message: string; reference: string | undefined };

/**
 * The record header's status (DR-2.4 to DR-2.8): "Saving…" while a commit
 * runs, else the last notice. Undo shows only while it is offered and a
 * commit may start (the fields are complete, DR-2.13).
 */
export function inPlaceStatus(
  state: InPlaceState,
  commitsOpen: boolean,
): InPlaceStatusData | null {
  if (state.saving) return { kind: "saving", message: IN_PLACE_WORDS.saving };
  const notice = state.notice;
  if (!notice) return null;
  if (notice.kind === "failed") return notice;
  return {
    kind: "saved",
    message: notice.message,
    canUndo: state.undo !== null && commitsOpen,
  };
}
