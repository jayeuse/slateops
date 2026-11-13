"use client";

import { useEffect, useRef, useState } from "react";
import {
  queryOpenViewRecords,
  type OpenViewQueryDefinition,
  type OpenViewRecord,
} from "../adapters/views-api";

/**
 * Item 6 phases. routing → sheet (the sheet of the record to open opened, or
 * no sheet opens) → checking (it closed; the match reads run) → answered.
 * unchecked: the reads cannot prove a match (search text, a grouped view).
 */
type CreatedPhase = "routing" | "sheet" | "checking" | "answered" | "unchecked";

/**
 * The server's answer for one record. pinned: it matches; hidden: the
 * filters hide it; failed: the first read failed; gone: a pinned record that
 * no longer matches or exists.
 */
type Match =
  | { kind: "pending" }
  | { kind: "pinned"; row: OpenViewRecord }
  | { kind: "hidden" }
  | { kind: "failed" }
  | { kind: "gone" };

type CreatedRecords = {
  /** In the order they were created. */
  ids: readonly string[];
  /** The record whose sheet opens first, if any. */
  sheetId: string | null;
  /** The list they were created in; another one ends them (DR-6.6). */
  key: string;
  phase: CreatedPhase;
  matches: Readonly<Record<string, Match>>;
  /** The records invalidation that the last answers belong to. */
  readAt: number;
  /** DR-6.1: the status shows until a record is opened from the list. */
  statusShown: boolean;
  /** DR-SI-3.6: how many the first reads found hidden; fixed after them. */
  hidden: number | null;
};

type ReadResult = OpenViewRecord | null | "failed";

/** The page status words (DR-6.1, DR-6.5, DR-SI-3.6). */
function createdStatus(created: CreatedRecords): string {
  const count = created.ids.length;
  if (count === 1)
    return created.matches[created.ids[0]]?.kind === "hidden"
      ? "Created, hidden by filters."
      : "Record created.";
  const hidden = created.hidden ?? 0;
  return hidden > 0
    ? `${count} records created. ${hidden} hidden by your filters.`
    : `${count} records created.`;
}

/**
 * The records this page just created (spec item 6, and candidate 3 of
 * subtle-interactions.md for several): one match read per record after the
 * sheet closes, or at once when no sheet opens; a new read after every
 * records invalidation so each pinned row is the server's current row; and
 * the meta-line status.
 */
export function useCreatedRecord({
  listKey,
  moduleId,
  definition,
  groupedView,
  sheetRecordId,
  invalidation,
}: {
  /** Changes with the applied conditions, sort, search, page, and view. */
  listKey: string;
  moduleId: string | undefined;
  /** The applied definition (DR-6.2). */
  definition: OpenViewQueryDefinition;
  groupedView: boolean;
  /** The record whose sheet is open, if any. */
  sheetRecordId: string | null;
  invalidation: number;
}) {
  const [created, setCreated] = useState<CreatedRecords | null>(null);
  const request = useRef(0);
  const current = created?.key === listKey ? created : null;

  useEffect(() => {
    if (!created) return;
    if (created.key !== listKey) {
      request.current += 1;
      setCreated(null);
      return;
    }
    if (created.phase === "routing") {
      if (sheetRecordId === created.sheetId)
        setCreated({ ...created, phase: "sheet" });
      return;
    }
    // The first reads wait for the sheet to close; after them, every
    // records invalidation (an in-place change, a delete, a colleague) reads
    // again.
    const first = created.phase === "sheet";
    if (first ? sheetRecordId !== null : created.phase !== "answered") return;
    if (!first && created.readAt === invalidation) return;
    // DR-6.2: the person's search text is replaced by the id search, so the
    // read cannot prove a match; a grouped view cannot prove the group.
    if (!moduleId || definition.search || groupedView) {
      setCreated({ ...created, phase: "unchecked", readAt: invalidation });
      return;
    }
    setCreated({
      ...created,
      phase: first ? "checking" : created.phase,
      readAt: invalidation,
    });
    const read = ++request.current;
    // DR-6.2: one match read per record.
    const ids = created.ids.filter(
      (id) => created.matches[id]?.kind !== "gone",
    );
    const readOne = (id: string): Promise<ReadResult> =>
      queryOpenViewRecords({
        moduleId,
        definition: { ...definition, search: id, searchFields: [] },
        limit: 1,
        offset: 0,
      })
        .then((result) => result.items.find((item) => item.id === id) ?? null)
        .catch(() => "failed" as const);
    void Promise.all(ids.map(readOne)).then((results) => {
      if (read !== request.current) return;
      setCreated((latest) => {
        if (latest?.key !== created.key || latest.ids !== created.ids)
          return latest;
        const matches = { ...latest.matches };
        ids.forEach((id, index) => {
          const result = results[index];
          const previous = matches[id];
          if (result === "failed") {
            if (first) matches[id] = { kind: "failed" };
          } else if (result) matches[id] = { kind: "pinned", row: result };
          // A pinned record that no longer matches or exists goes; one the
          // filters hid stays hidden.
          else
            matches[id] =
              previous?.kind === "pinned"
                ? { kind: "gone" }
                : { kind: "hidden" };
        });
        // When every record has gone, so has the status.
        if (latest.ids.every((id) => matches[id]?.kind === "gone")) return null;
        return {
          ...latest,
          phase: "answered",
          matches,
          hidden: first
            ? latest.ids.filter((id) => matches[id]?.kind === "hidden").length
            : latest.hidden,
        };
      });
    });
  }, [
    created,
    definition,
    groupedView,
    invalidation,
    listKey,
    moduleId,
    sheetRecordId,
  ]);

  const single = current?.ids.length === 1 ? current.ids[0] : null;
  const singleMatch = single ? current?.matches[single] : undefined;
  return {
    /** The record, when the page created one (its status opens it). */
    id: single,
    /**
     * DR-6.3: the server's current rows, pinned first with "New". DR-SI-3.6:
     * newest first, so the last record made takes the first row, as one
     * created record does.
     */
    pinned:
      current && !groupedView
        ? current.ids.toReversed().flatMap((id) => {
            const match = current.matches[id];
            return match?.kind === "pinned" ? [match.row] : [];
          })
        : [],
    /** DR-6.1, DR-6.5, DR-SI-3.6: the meta-line status. */
    status: current?.statusShown ? createdStatus(current) : "",
    /**
     * DR-6.5 and the Failure and Grouped view states: the list cannot show
     * the one record, so the status opens it. Several records have no
     * "Open record" (DR-SI-3.6).
     */
    openable: Boolean(
      current?.statusShown &&
      single &&
      (current.phase === "unchecked" ||
        singleMatch?.kind === "hidden" ||
        singleMatch?.kind === "failed"),
    ),
    /**
     * Records were created in the New record dialog. `sheetId`: the record
     * whose sheet opens now; with none, the match reads run at once.
     */
    start: (ids: readonly string[], sheetId: string | null) => {
      request.current += 1;
      setCreated(
        ids.length === 0
          ? null
          : {
              ids,
              sheetId,
              key: listKey,
              phase: sheetId ? "routing" : "sheet",
              matches: Object.fromEntries(
                ids.map((id) => [id, { kind: "pending" }]),
              ),
              readAt: invalidation,
              statusShown: true,
              hidden: null,
            },
      );
    },
    end: () => {
      request.current += 1;
      setCreated(null);
    },
    /**
     * DR-6.1: opening a record from the list clears the status. Another
     * record ends it; the new ones keep their first places and their tags.
     */
    openedFromList: (recordId: string) => {
      if (!created) return;
      if (!created.ids.includes(recordId)) {
        request.current += 1;
        setCreated(null);
      } else if (created.statusShown)
        setCreated({ ...created, statusShown: false });
    },
  };
}
