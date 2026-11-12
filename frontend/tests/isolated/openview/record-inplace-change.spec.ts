import { expect, test } from "@playwright/test";

import type {
  OpenViewDataSourceField,
  OpenViewRecord,
} from "../../../src/components/systems/openview/adapters/views-api";
import {
  inPlaceChangeMessage,
  inPlaceCommit,
  inPlaceFailure,
  inPlaceMode,
  inPlacePatchData,
  inPlaceReducer,
  initialInPlaceState,
  inPlaceStatus,
  seenRecord,
  type InPlaceFailure,
  type InPlaceState,
} from "../../../src/components/systems/openview/domain/record-inplace-change";
import { toFormValue } from "../../../src/components/systems/openview/domain/record-form";
import { ApiError } from "../../../src/lib/api";

// Values changed in place on the record sheet's Details tab (item 2 of
// docs/specs/ux-friction-pass.md, DR-2.2 to DR-2.13): which values change in
// place, the complete-record PATCH, the one-at-a-time rule, the revision of
// the last response, Undo, the header words, and where a refusal shows.

const recordId = "00000000-0000-4000-8000-000000000701";
const statusId = "00000000-0000-4000-8000-000000000711";
const paidId = "00000000-0000-4000-8000-000000000712";
const dueId = "00000000-0000-4000-8000-000000000713";
const metId = "00000000-0000-4000-8000-000000000714";
const nameId = "00000000-0000-4000-8000-000000000715";
const deletedFieldId = "00000000-0000-4000-8000-000000000716";

function field(
  id: string,
  name: string,
  type: string,
  extra: Partial<OpenViewDataSourceField> = {},
): OpenViewDataSourceField {
  return {
    id,
    name,
    type,
    required: false,
    position: 0,
    config: {},
    ...extra,
  } as OpenViewDataSourceField;
}

const status = field(statusId, "Status", "select", {
  config: {
    options: [
      { id: "active", label: "Active" },
      { id: "former", label: "Former" },
    ],
  },
});
const paid = field(paidId, "Paid", "boolean");
const due = field(dueId, "Due", "date");
const met = field(metId, "Met at", "datetime");
const name = field(nameId, "Name", "text", { required: true });

function record(updatedAt: string, data: Record<string, unknown>) {
  return {
    id: recordId,
    moduleId: "00000000-0000-4000-8000-000000000702",
    data,
    displayValues: {},
    createdAt: "2026-11-01T08:00:00Z",
    updatedAt,
    deletedAt: null,
    isDeleted: false,
    performedBy: null,
  } as OpenViewRecord;
}

const writer = {
  enabled: true,
  canWrite: true,
  isDeleted: false,
  editing: false,
  fieldsComplete: true,
};

test("UF-C2.4 only Choice list, Checkbox, Date and Date and time change in place", () => {
  const modes = [
    "select",
    "boolean",
    "date",
    "datetime",
    "text",
    "long_text",
    "number",
    "int",
    "decimal",
    "email",
    "url",
    "user",
    "relationship",
  ].map((type) => [
    type,
    inPlaceMode({ type } as OpenViewDataSourceField, writer),
  ]);
  expect(modes).toEqual([
    ["select", "control"],
    ["boolean", "control"],
    ["date", "control"],
    ["datetime", "control"],
    ["text", "plain"],
    ["long_text", "plain"],
    ["number", "plain"],
    ["int", "plain"],
    ["decimal", "plain"],
    ["email", "plain"],
    ["url", "plain"],
    // A user field keeps Edit: a change notifies the person (DR-2.9).
    ["user", "plain"],
    ["relationship", "plain"],
  ]);
});

test("UF-C2.5 readers, guests, deleted records, an open form and a sheet that did not opt in show plain values", () => {
  const cases: Array<[string, Partial<typeof writer>, string]> = [
    ["writer", {}, "control"],
    // A reader, a guest and a Read-only record have no write access.
    ["no write access", { canWrite: false }, "plain"],
    ["deleted record", { isDeleted: true }, "plain"],
    ["Edit form open (DR-2.11)", { editing: true }, "plain"],
    ["Boards card sheet (DR-2.12)", { enabled: false }, "plain"],
    // DR-2.13: the control waits, disabled, until every field is loaded.
    ["fields incomplete", { fieldsComplete: false }, "waiting"],
    [
      "reader with fields incomplete",
      { canWrite: false, fieldsComplete: false },
      "plain",
    ],
  ];
  expect(
    cases.map(([label, change]) => [
      label,
      inPlaceMode(status, { ...writer, ...change }),
    ]),
  ).toEqual(cases.map(([label, , mode]) => [label, mode]));
  // A Details value whose field is not in the loaded catalog stays plain.
  expect(inPlaceMode(undefined, writer)).toBe("plain");
});

test("UF-C2.2 a commit sends every active value of the complete record with only that field changed", () => {
  const stored = {
    [nameId]: "Harbor Supplies",
    [statusId]: "active",
    [paidId]: true,
    // A field that is no longer active is not sent, as the Edit save does.
    [deletedFieldId]: "kept by the server",
  };
  expect(
    inPlacePatchData([name, status, paid, due], stored, statusId, "former"),
  ).toEqual({
    [nameId]: "Harbor Supplies",
    [statusId]: "former",
    [paidId]: true,
    [dueId]: null,
  });
});

test("UF-C2.2 a value commits only when it is complete and different", () => {
  expect(inPlaceCommit(status, "active", "former")).toEqual({
    kind: "commit",
    value: "former",
  });
  expect(inPlaceCommit(status, "active", "active")).toEqual({ kind: "none" });
  // An optional Choice list set to None, and a date removed, clear the value.
  expect(inPlaceCommit(status, "active", "")).toEqual({
    kind: "commit",
    value: null,
  });
  expect(inPlaceCommit(due, "2026-11-20", "")).toEqual({
    kind: "commit",
    value: null,
  });
  expect(inPlaceCommit({ ...status, required: true }, "active", "")).toEqual({
    kind: "revert",
  });
  expect(inPlaceCommit(paid, false, true)).toEqual({
    kind: "commit",
    value: true,
  });
  expect(inPlaceCommit(due, "2026-11-20", "2026-11-21")).toEqual({
    kind: "commit",
    value: "2026-11-21",
  });
  // An incomplete date puts back the stored value and sends nothing.
  expect(inPlaceCommit(due, "2026-11-20", "", false)).toEqual({
    kind: "revert",
  });
  // A stored instant with seconds is the same minute the input shows
  // (the input is local time, so the test reads it in the runner's zone).
  const instant = "2026-11-20T15:30:45.000Z";
  expect(inPlaceCommit(met, instant, toFormValue(met, instant))).toEqual({
    kind: "none",
  });
});

test("UF-C2.2 one commit runs at a time, and the next one sends the revision of the last response", () => {
  const shown = record("2026-11-12T09:00:00Z", { [statusId]: "active" });
  const saving = inPlaceReducer(initialInPlaceState, {
    type: "start",
    fieldId: statusId,
    value: "former",
    undo: false,
  });
  expect(saving.saving).toEqual({
    fieldId: statusId,
    value: "former",
    undo: false,
  });
  // A second commit while one saves is refused.
  expect(
    inPlaceReducer(saving, {
      type: "start",
      fieldId: paidId,
      value: true,
      undo: false,
    }),
  ).toBe(saving);
  const response = record("2026-11-12T09:05:00Z", { [statusId]: "former" });
  const saved = inPlaceReducer(saving, {
    type: "saved",
    record: response,
    message: "Status changed to Former.",
    undo: { fieldId: statusId, previous: "active" },
  });
  expect(saved.saving).toBeNull();
  // The page has not read the record again yet: the response is newer.
  expect(seenRecord(shown, saved.latest).updatedAt).toBe(
    "2026-11-12T09:05:00Z",
  );
  // The page read it again with the same revision: the response still wins.
  expect(seenRecord(record("2026-11-12T09:05:00Z", {}), saved.latest)).toBe(
    response,
  );
  // Someone changed it later, and the page shows that change.
  expect(
    seenRecord(record("2026-11-12T09:07:00Z", {}), saved.latest).updatedAt,
  ).toBe("2026-11-12T09:07:00Z");
});

test("UF-C2.3 UF-C2.6 the header status: Saving, the change with Undo, a failed Undo that keeps it, and refusals", () => {
  const statusOf = (state: InPlaceState, commitsOpen = true) =>
    inPlaceStatus(state, commitsOpen);
  const start = (
    state: InPlaceState,
    fieldId: string,
    value: unknown,
    undo: boolean,
  ) => inPlaceReducer(state, { type: "start", fieldId, value, undo });
  const refused = (state: InPlaceState, failure: InPlaceFailure) =>
    inPlaceReducer(state, { type: "refused", failure, record: null });

  const saving = start(initialInPlaceState, statusId, "former", false);
  expect(statusOf(saving)).toEqual({ kind: "saving", message: "Saving…" });
  const changed = inPlaceReducer(saving, {
    type: "saved",
    record: record("2026-11-12T09:05:00Z", { [statusId]: "former" }),
    message: "Status changed to Former.",
    undo: { fieldId: statusId, previous: "active" },
  });
  expect(statusOf(changed)).toEqual({
    kind: "saved",
    message: "Status changed to Former.",
    canUndo: true,
  });
  // Undo waits while fields are incomplete: a PATCH would drop values.
  expect(statusOf(changed, false)).toMatchObject({ canUndo: false });
  // Undo writes the previous value back; it starts from the saved offer.
  const undoing = start(changed, statusId, "active", true);
  expect(statusOf(undoing)).toEqual({ kind: "saving", message: "Saving…" });
  // A failed Undo keeps the words and the offer, and says why under the field.
  const undoFailed = refused(undoing, { kind: "failed", reference: "ref-1" });
  expect(statusOf(undoFailed)).toEqual({
    kind: "saved",
    message: "Status changed to Former.",
    canUndo: true,
  });
  expect(undoFailed.fieldError).toEqual({
    fieldId: statusId,
    message: "Not saved. Try again.",
    reference: "ref-1",
  });
  // An Undo that meets a 412 ends the offer and says so in the meta line.
  const undoConflict = refused(undoing, { kind: "conflict" });
  expect(statusOf(undoConflict)).toEqual({
    kind: "failed",
    message: "Not undone. Someone changed this record after you.",
    reference: undefined,
  });
  expect(undoConflict.fieldError).toBeNull();
  // A successful Undo has no Undo.
  const undone = inPlaceReducer(undoing, {
    type: "saved",
    record: record("2026-11-12T09:06:00Z", { [statusId]: "active" }),
    message: "Status changed back to Active.",
    undo: null,
  });
  expect(statusOf(undone)).toEqual({
    kind: "saved",
    message: "Status changed back to Active.",
    canUndo: false,
  });
  // A tab change, Edit, or Previous and Next end the offer; the words stay.
  expect(statusOf(inPlaceReducer(changed, { type: "clear-undo" }))).toEqual({
    kind: "saved",
    message: "Status changed to Former.",
    canUndo: false,
  });
  // A new change ends the offer and the words; its refusal shows under it.
  const next = start(changed, paidId, true, false);
  const conflict = refused(next, { kind: "conflict" });
  expect(statusOf(conflict)).toBeNull();
  expect(conflict.undo).toBeNull();
  expect(conflict.fieldError).toEqual({
    fieldId: paidId,
    message: "Someone changed this record. It shows their value now.",
    reference: undefined,
  });
  expect(
    refused(next, { kind: "field", message: "Is required." }).fieldError,
  ).toEqual({
    fieldId: paidId,
    message: "Is required.",
    reference: undefined,
  });
  // A 422 on a field with no control on screen shows in the meta line.
  const other = refused(next, {
    kind: "other-field",
    message: "Enter a value.",
  });
  expect(statusOf(other)).toEqual({
    kind: "failed",
    message: "Enter a value.",
    reference: undefined,
  });
  expect(other.fieldError).toBeNull();
});

test("UF-C2.2 UF-C2.3 the header words name each change", () => {
  expect([
    inPlaceChangeMessage(status, "former", "former"),
    inPlaceChangeMessage(status, "active", "active", true),
    inPlaceChangeMessage(status, null, "—"),
    inPlaceChangeMessage(paid, true, "Yes"),
    inPlaceChangeMessage(paid, false, "No"),
    inPlaceChangeMessage(due, "2026-11-21", "Nov 21, 2026"),
    inPlaceChangeMessage(due, null, "—"),
  ]).toEqual([
    "Status changed to Former.",
    "Status changed back to Active.",
    "Status cleared.",
    "Paid turned on.",
    "Paid turned off.",
    "Due changed to Nov 21, 2026.",
    "Due cleared.",
  ]);
});

test("UF-C2.6 a 412 is a conflict; a 422 shows under its field or in the meta line; other failures keep the reference", () => {
  const requestId = "00000000-0000-4000-8000-0000000007ff";
  const invalid = (fieldId: string) =>
    new ApiError(422, "Invalid record", {
      code: "invalid_record",
      errors: [
        { field_id: fieldId, message: `Field ${fieldId} is not an option` },
      ],
    });
  expect([
    inPlaceFailure(new ApiError(412, "Record changed"), statusId),
    inPlaceFailure(invalid(statusId), statusId),
    inPlaceFailure(invalid(nameId), statusId),
    inPlaceFailure(
      new ApiError(
        503,
        "Unavailable",
        undefined,
        undefined,
        undefined,
        requestId,
      ),
      statusId,
    ),
  ]).toEqual([
    { kind: "conflict" },
    { kind: "field", message: "Is not an option." },
    { kind: "other-field", message: "Is not an option." },
    { kind: "failed", reference: requestId },
  ]);
});
