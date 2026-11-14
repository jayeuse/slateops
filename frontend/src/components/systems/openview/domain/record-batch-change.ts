import { ApiError } from "@/lib/api";
import { apiErrorReference } from "@/lib/api-errors";
import {
  RECORD_BATCH_LIMIT,
  type RecordBatchItem,
  type RecordBatchResult,
} from "../adapters/record-batch-api";
import type {
  OpenViewDataSourceField,
  OpenViewQueryDefinition,
  OpenViewRecord,
} from "../adapters/views-api";
import { selectOptions, serverFieldMessage } from "./record-form";
import { IN_PLACE_WORDS, inPlaceChangeMessage } from "./record-inplace-change";
import { isFilterApplied } from "./server-view-draft";

// List actions of the OpenView table (candidates 1 and 5 of
// docs/specs/subtle-interactions.md): "Show only" from a Choice value, one
// field changed on one or several rows through `batch-update`, the page
// status words, and the Undo that writes back only what a change did.

type Filter = OpenViewQueryDefinition["filters"][number];
type Field = OpenViewDataSourceField;

/** Field types that change from the list (SI-1.6, DR-SI-5.5). */
export function changesFromList(field: Pick<Field, "type">): boolean {
  return field.type === "select" || field.type === "boolean";
}

/** The stored value, with every "no value" read as null. */
function storedValue(value: unknown): unknown {
  return value === undefined || value === "" ? null : value;
}

/** Whether the record already holds this value: then nothing is sent. */
export function holdsValue(
  record: Pick<OpenViewRecord, "data">,
  fieldId: string,
  value: unknown,
): boolean {
  return storedValue(record.data[fieldId]) === storedValue(value);
}

// ---------------------------------------------------------------- Show only

/**
 * DR-SI-1.4 and SI-0.1: "Show only" is offered for a value when the applied
 * conditions use "All conditions" (or there is none), and that condition is
 * not already the only applied one on its field.
 */
export function showOnlyOffered(
  definition: Pick<OpenViewQueryDefinition, "logic" | "filters">,
  fieldId: string,
  value: unknown,
): boolean {
  if (typeof value !== "string" || value === "") return false;
  const applied = definition.filters.filter(isFilterApplied);
  if (definition.logic === "or" && applied.length > 0) return false;
  const onField = applied.filter((filter) => filter.fieldId === fieldId);
  return !(
    onField.length === 1 &&
    onField[0].operator === "eq" &&
    onField[0].value === value
  );
}

/**
 * N-4: "Show only" replaces every applied condition on its field; an
 * unfinished row and the other fields' conditions stay.
 */
export function replacedByShowOnly(filter: Filter, fieldId: string): boolean {
  return filter.fieldId === fieldId && isFilterApplied(filter);
}

/** The condition "<Field> is <value>". */
export function showOnlyCondition(fieldId: string, value: string): Filter {
  return { fieldId, expectedType: "select", operator: "eq", value };
}

// ---------------------------------------------------------------- options

export type ChangeOption = { value: string | boolean | null; label: string };

/**
 * The values a field changes to (DR-SI-1.5, DR-SI-5.6): a Choice list's
 * options, with "None" last only when the field is optional; a Checkbox's
 * "On" and "Off".
 */
export function changeOptions(
  field: Pick<Field, "type" | "required" | "config">,
): ChangeOption[] {
  if (field.type === "boolean")
    return [
      { value: true, label: "On" },
      { value: false, label: "Off" },
    ];
  const options: ChangeOption[] = selectOptions(field).map((option) => ({
    value: option.id,
    label: option.label,
  }));
  return field.required
    ? options
    : [...options, { value: null, label: "None" }];
}

// ---------------------------------------------------------------- selection

export type RowSelection = {
  ids: readonly string[];
  /** The last row toggled one at a time: Shift-click ranges from it. */
  anchor: string | null;
};

export const emptySelection: RowSelection = { ids: [], anchor: null };

/**
 * DR-SI-5.3: a click toggles one row; Shift-click selects every row from the
 * anchor to this one. Only rows on the page are ever selected.
 */
export function toggleRow(
  selection: RowSelection,
  pageIds: readonly string[],
  id: string,
  range: boolean,
): RowSelection {
  const selected = new Set(
    selection.ids.filter((key) => pageIds.includes(key)),
  );
  const from =
    selection.anchor === null ? -1 : pageIds.indexOf(selection.anchor);
  const to = pageIds.indexOf(id);
  if (to < 0) return selection;
  if (range && from >= 0) {
    const [start, end] = from < to ? [from, to] : [to, from];
    for (const key of pageIds.slice(start, end + 1)) selected.add(key);
  } else if (selected.has(id)) selected.delete(id);
  else selected.add(id);
  return {
    ids: pageIds.filter((key) => selected.has(key)),
    anchor: id,
  };
}

/** The header box: every row on the page, or none. */
export function toggleAllRows(
  selection: RowSelection,
  pageIds: readonly string[],
): RowSelection {
  const all =
    pageIds.length > 0 && pageIds.every((id) => selection.ids.includes(id));
  return { ids: all ? [] : [...pageIds], anchor: null };
}

/** DR-SI-5.10: a re-read keeps only the selected rows still on the page. */
export function selectedOnPage(
  selection: RowSelection,
  pageIds: readonly string[],
): string[] {
  return pageIds.filter((id) => selection.ids.includes(id));
}

/** A row's box name: "Select <title>", or "Select record" (DR-SI-5.1). */
export function selectionLabel(title: string | undefined): string {
  return title && title.trim() && title !== "—"
    ? `Select ${title}`
    : "Select record";
}

export function headerSelectionState(
  selectedCount: number,
  pageCount: number,
): "all" | "none" | "some" {
  if (selectedCount === 0 || pageCount === 0) return "none";
  return selectedCount >= pageCount ? "all" : "some";
}

// ---------------------------------------------------------------- the change

/** The `batch-update` items: only the rows that do not hold the value. */
export function changeItems(
  rows: readonly Pick<OpenViewRecord, "id" | "data" | "updatedAt">[],
  fieldId: string,
  value: unknown,
): RecordBatchItem[] {
  return rows
    .filter((row) => !holdsValue(row, fieldId, value))
    .map((row) => ({
      recordId: row.id,
      revision: row.updatedAt,
      fieldId,
      value: storedValue(value),
    }));
}

function records(count: number): string {
  return count === 1 ? "1 record" : `${count} records`;
}

/**
 * DR-SI-5.6, DR-SI-5.7: the popover's final button. The label always names
 * the action; a blocked button says why in `reason` (TASK-0061 rules 2, 6).
 */
export function finalChangeLabel({
  selected,
  picked,
  changing,
}: {
  selected: number;
  picked: boolean;
  /** k: the selected rows that do not hold the picked value. */
  changing: number;
}): { label: string; reason: string | null } {
  if (selected > RECORD_BATCH_LIMIT)
    return {
      label: "Change records",
      reason: `Select at most ${RECORD_BATCH_LIMIT} records.`,
    };
  if (!picked)
    return { label: "Change records", reason: "Choose a value first." };
  if (changing === 0)
    return {
      label: "Change records",
      reason: `All ${selected} already have this value.`,
    };
  return { label: `Change ${records(changing)}`, reason: null };
}

/** One record a change sent, kept for its words and its Undo. */
export type SentRecord = {
  recordId: string;
  title: string;
  /** The value before this change, from the row the person saw. */
  previous: unknown;
};

export type NotChangedRecord = {
  recordId: string;
  title: string;
  reason: string;
};

/** What Undo writes back: each record's own previous value (SI-0.2). */
export type ListUndo = {
  field: Field;
  /** One cell (candidate 1) or a selection (candidate 5): their words differ. */
  scope: "cell" | "selection";
  items: RecordBatchItem[];
  titles: Readonly<Record<string, string>>;
};

/** The page status after a list change (G7, DR-SI-1.7 to DR-SI-5.9). */
export type ListChangeNotice = {
  message: string;
  /** "2 not changed": the link button that lists the records (DR-SI-5.8). */
  notChangedLabel: string | null;
  notChanged: readonly NotChangedRecord[];
  reference: string | undefined;
  undo: ListUndo | null;
};

/** The settled change: its notice and what the page does next. */
export type ListChangeOutcome = {
  notice: ListChangeNotice;
  /** The server's records, for the rows on the page (DR-SI-1.7). */
  updated: OpenViewRecord[];
  /** A refusal or an unknown result: the list reads the stored values. */
  readAgain: boolean;
  /** A failed request of an Undo keeps the change's Undo offered. */
  keepUndo: boolean;
};

const UNCONFIRMED = "The result could not be confirmed.";

/** N-1: the server could not confirm whether the batch was saved. */
export function isUnconfirmedBatch(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.status === 503 &&
    error.message === "Batch outcome could not be confirmed"
  );
}

/** N-8: the field the server names, which may be another than the one changed. */
function invalidReason(
  result: Extract<RecordBatchResult, { status: "invalid" }>,
  fields: readonly Pick<Field, "id" | "name">[],
): string {
  const error = result.errors[0];
  if (!error) return "This value cannot be saved.";
  const message = serverFieldMessage(error.message);
  const named = fields.find((field) => field.id === error.fieldId);
  return named ? `${named.name}: ${message}` : message;
}

function reasonFor(
  result: RecordBatchResult | undefined,
  fields: readonly Pick<Field, "id" | "name">[],
): string {
  if (result?.status === "stale") return "Someone changed it";
  if (result?.status === "invalid")
    return `Not valid: ${invalidReason(result, fields)}`;
  return "You cannot change it";
}

function choiceLabel(field: Field, value: unknown): string {
  if (field.type === "select")
    return (
      selectOptions(field).find((option) => option.id === value)?.label ?? ""
    );
  return "";
}

function emptyNotice(message: string): ListChangeNotice {
  return {
    message,
    notChangedLabel: null,
    notChanged: [],
    reference: undefined,
    undo: null,
  };
}

/**
 * A change of one field on records the person saw, or the Undo of one:
 * one `batch-update`, then the page status words and the Undo items.
 * Undo items carry the `updated_at` that the change's response returned.
 */
export async function runListChange({
  field,
  fields,
  sent,
  items,
  scope,
  undo,
  send,
}: {
  field: Field;
  /** The module's fields, to name the field of an `invalid` reason. */
  fields: readonly Pick<Field, "id" | "name">[];
  sent: readonly SentRecord[];
  items: readonly RecordBatchItem[];
  scope: "cell" | "selection";
  /** True when this change is an Undo: its words differ and it offers none. */
  undo: boolean;
  send: (items: readonly RecordBatchItem[]) => Promise<RecordBatchResult[]>;
}): Promise<ListChangeOutcome> {
  let results: RecordBatchResult[];
  try {
    results = await send(items);
  } catch (error) {
    if (isUnconfirmedBatch(error))
      return {
        notice: emptyNotice(UNCONFIRMED),
        updated: [],
        readAgain: true,
        keepUndo: false,
      };
    const message = undo
      ? "Not undone. Try again."
      : scope === "cell"
        ? `${field.name} not changed. Try again.`
        : "No records changed. Try again.";
    return {
      notice: { ...emptyNotice(message), reference: apiErrorReference(error) },
      updated: [],
      readAgain: false,
      keepUndo: undo,
    };
  }
  const byId = new Map(results.map((result) => [result.recordId, result]));
  const titles = Object.fromEntries(
    sent.map((record) => [record.recordId, record.title]),
  );
  const updated: OpenViewRecord[] = [];
  const undoItems: RecordBatchItem[] = [];
  const notChanged: NotChangedRecord[] = [];
  for (const record of sent) {
    const result = byId.get(record.recordId);
    if (result?.status === "updated") {
      updated.push(result.record);
      undoItems.push({
        recordId: record.recordId,
        revision: result.record.updatedAt,
        fieldId: field.id,
        value: storedValue(record.previous),
      });
    } else
      notChanged.push({
        recordId: record.recordId,
        title: record.title,
        reason: reasonFor(result, fields),
      });
  }
  const readAgain = notChanged.length > 0;
  const offerUndo = !undo && undoItems.length > 0;
  const nextUndo: ListUndo | null = offerUndo
    ? { field, scope, items: undoItems, titles }
    : null;

  if (scope === "cell") {
    const result = byId.get(sent[0]?.recordId ?? "");
    let message: string;
    if (result?.status === "updated") {
      const value = items[0]?.value;
      message = inPlaceChangeMessage(
        field,
        value,
        choiceLabel(field, value),
        undo,
      );
    } else if (undo)
      message =
        result?.status === "stale"
          ? IN_PLACE_WORDS.undoConflict
          : result?.status === "invalid"
            ? `Not undone. ${invalidReason(result, fields)}`
            : "Not undone. You cannot change this record.";
    else if (result?.status === "stale")
      message = `${field.name} not changed. Someone changed this record; it shows their value now.`;
    else if (result?.status === "invalid")
      message = `${field.name} not changed. ${invalidReason(result, fields)}`;
    else message = `${field.name} not changed. You cannot change this record.`;
    return {
      notice: { ...emptyNotice(message), undo: nextUndo },
      updated,
      readAgain,
      keepUndo: false,
    };
  }

  const changed = updated.length;
  const failed = notChanged.length;
  let message: string;
  let notChangedLabel: string | null = null;
  if (undo) {
    message =
      failed === 0
        ? `${field.name} changed back on ${records(changed)}.`
        : changed === 0
          ? "No records changed back."
          : `${changed} changed back.`;
    if (failed > 0) notChangedLabel = `${failed} not changed back`;
  } else {
    message =
      changed === 0
        ? "No records changed."
        : `${field.name} changed on ${records(changed)}.`;
    if (failed > 0) notChangedLabel = `${failed} not changed`;
  }
  return {
    notice: {
      message,
      notChangedLabel,
      notChanged,
      reference: undefined,
      undo: nextUndo,
    },
    updated,
    readAgain,
    keepUndo: false,
  };
}

/** The records a list Undo sends, with the titles its words use. */
export function undoSent(undo: ListUndo): SentRecord[] {
  return undo.items.map((item) => ({
    recordId: item.recordId,
    title: undo.titles[item.recordId] ?? "",
    // An Undo of an Undo is never offered, so its previous value is unused.
    previous: null,
  }));
}
