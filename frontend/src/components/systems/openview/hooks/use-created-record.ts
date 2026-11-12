"use client";

import { useEffect, useRef, useState } from "react";
import {
  queryOpenViewRecords,
  type OpenViewQueryDefinition,
  type OpenViewRecord,
} from "../adapters/views-api";

/**
 * Item 6 phases. routing → sheet (the new record's sheet opened) → checking
 * (it closed; the match read runs) → pinned, hidden, or failed. unchecked:
 * the read cannot prove a match (search text, a grouped view).
 */
type CreatedPhase =
  | "routing"
  | "sheet"
  | "checking"
  | "pinned"
  | "hidden"
  | "failed"
  | "unchecked";

type CreatedRecord = {
  id: string;
  /** The list it was created in; another one ends it (DR-6.6). */
  key: string;
  phase: CreatedPhase;
  /** The server's answer to the last match read. */
  row: OpenViewRecord | null;
  /** The records invalidation that answer belongs to. */
  readAt: number;
  /** DR-6.1: the status shows until a record is opened from the list. */
  statusShown: boolean;
};

/**
 * The record this page just created (spec item 6): the match read after its
 * sheet closes, a new read after every records invalidation so the pinned
 * row is the server's current row, and the meta-line status.
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
  const [created, setCreated] = useState<CreatedRecord | null>(null);
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
      if (sheetRecordId === created.id)
        setCreated({ ...created, phase: "sheet" });
      return;
    }
    // The first read waits for the sheet to close; after it, every records
    // invalidation (an in-place change, a delete, a colleague) reads again.
    const first = created.phase === "sheet";
    const answered =
      created.phase === "pinned" ||
      created.phase === "hidden" ||
      created.phase === "failed";
    if (first ? sheetRecordId !== null : !answered) return;
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
    const settle = (row: OpenViewRecord | null | "failed") => {
      if (read !== request.current) return;
      setCreated((latest) => {
        if (latest?.id !== created.id || latest.key !== created.key)
          return latest;
        if (row === "failed")
          return first ? { ...latest, phase: "failed", row: null } : latest;
        if (row) return { ...latest, phase: "pinned", row };
        // A pinned record that no longer matches or exists goes, with its
        // status; one the filters hid stays hidden.
        return latest.phase === "pinned"
          ? null
          : { ...latest, phase: "hidden", row: null };
      });
    };
    void queryOpenViewRecords({
      moduleId,
      definition: { ...definition, search: created.id, searchFields: [] },
      limit: 1,
      offset: 0,
    })
      .then((result) =>
        settle(result.items.find((item) => item.id === created.id) ?? null),
      )
      .catch(() => settle("failed"));
  }, [
    created,
    definition,
    groupedView,
    invalidation,
    listKey,
    moduleId,
    sheetRecordId,
  ]);

  return {
    id: current?.id ?? null,
    /** DR-6.3: the server's current row, pinned first with "New". */
    pinned: current?.phase === "pinned" && !groupedView ? current.row : null,
    /** DR-6.1, DR-6.5: the meta-line status. */
    status: current?.statusShown
      ? current.phase === "hidden"
        ? "Created, hidden by filters."
        : "Record created."
      : "",
    /**
     * DR-6.5 and the Failure and Grouped view states: the list cannot show
     * it, so the status opens it.
     */
    openable: Boolean(
      current?.statusShown &&
      (current.phase === "hidden" ||
        current.phase === "unchecked" ||
        current.phase === "failed"),
    ),
    start: (id: string) => {
      request.current += 1;
      setCreated({
        id,
        key: listKey,
        phase: "routing",
        row: null,
        readAt: invalidation,
        statusShown: true,
      });
    },
    end: () => {
      request.current += 1;
      setCreated(null);
    },
    /**
     * DR-6.1: opening a record from the list clears the status. Another
     * record ends it; the new one keeps its first place and its tag.
     */
    openedFromList: (recordId: string) => {
      if (!created) return;
      if (created.id !== recordId) {
        request.current += 1;
        setCreated(null);
      } else if (created.statusShown)
        setCreated({ ...created, statusShown: false });
    },
  };
}
