"use client";

import { useEffect, useState, type ReactNode } from "react";
import type { Route } from "next";
import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { GuardedWorkspaceLink } from "@/components/workspace-navigation-guard";
import { recordTitle } from "@/components/systems/shared/components/record-sheet";

import {
  catalogFirstPageOptions,
  fieldsFirstPageOptions,
} from "../adapters/openview-queries";
import { searchOpenViewLinkTargets } from "../adapters/records-api";

// A link cell's picker (docs/specs/sheets.md N1, SH-26): only records of the
// column's module that the person can read, found by the same record search
// as the record panel's links. The record linked now is one step away.

const SEARCHABLE = new Set(["text", "long_text", "email", "url", "select"]);
export const SEARCH_DELAY_MS = 250;

/** The text a picker searches, once typing pauses. */
export function useDelayedSearch() {
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(
      () => setSearch(typed.trim()),
      SEARCH_DELAY_MS,
    );
    return () => window.clearTimeout(timer);
  }, [typed]);
  return { typed, setTyped, search, searching: typed.trim() !== search };
}

/** The frame both pickers share: a search box over a list of choices. */
export function PickerFrame({
  title,
  description,
  searchLabel,
  typed,
  onType,
  choices,
  status,
  current,
  removeLabel,
  onRemove,
  onClose,
}: {
  title: string;
  description: string;
  searchLabel: string;
  typed: string;
  onType: (value: string) => void;
  choices: { id: string; label: string; onChoose: () => void }[];
  /** Searching…, no match, or a failed search. */
  status: ReactNode;
  /** The record linked now, as a link. */
  current?: ReactNode;
  removeLabel: string | null;
  onRemove: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="flex flex-col gap-3">
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
        {current}
        <Input
          type="search"
          aria-label={searchLabel}
          placeholder={searchLabel}
          className="min-h-11"
          value={typed}
          onChange={(event) => onType(event.target.value)}
          autoFocus
        />
        <div className="flex max-h-72 flex-col overflow-y-auto rounded-md border">
          {choices.length > 0 ? (
            <ul className="flex flex-col">
              {choices.map((choice) => (
                <li key={choice.id}>
                  <button
                    type="button"
                    className="hover:bg-tint-hover focus-visible:outline-ring min-h-11 w-full px-3 text-left text-sm outline-offset-[-2px] focus-visible:outline-2"
                    onClick={choice.onChoose}
                  >
                    {choice.label}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          {status}
        </div>
        <div className="flex justify-between gap-2">
          {removeLabel ? (
            <Button variant="ghost" className="min-h-11" onClick={onRemove}>
              {removeLabel}
            </Button>
          ) : (
            <span />
          )}
          <Button variant="outline" className="min-h-11" onClick={onClose}>
            Cancel
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** "Searching…", "No … match." or the failure, under the choices. */
export function pickerStatus(state: {
  searching: boolean;
  empty: boolean;
  failed: boolean;
  noMatch: string;
  failure: string;
}): ReactNode {
  if (state.failed)
    return (
      <p role="alert" className="text-destructive px-3 py-3 text-sm">
        {state.failure}
      </p>
    );
  if (state.searching)
    return (
      <p role="status" className="text-muted-foreground px-3 py-3 text-sm">
        Searching…
      </p>
    );
  if (state.empty)
    return (
      <p className="text-muted-foreground px-3 py-3 text-sm">{state.noMatch}</p>
    );
  return null;
}

export function SheetLinkPicker({
  columnName,
  moduleId,
  current,
  onPick,
  onClose,
}: {
  columnName: string;
  moduleId: string;
  /** The record the cell links now, if any. */
  current: { recordId: string; label: string } | null;
  onPick: (recordId: string | null, label: string) => void;
  onClose: () => void;
}) {
  const { typed, setTyped, search, searching } = useDelayedSearch();
  const catalog = useQuery(catalogFirstPageOptions());
  const source = catalog.data?.items.find((item) => item.id === moduleId);
  const fields = useQuery(fieldsFirstPageOptions(moduleId));
  const fieldList = fields.data?.items ?? [];
  const titleField =
    fieldList.find((field) => field.id === source?.titleFieldId) ??
    fieldList[0];
  const results = useQuery({
    queryKey: ["openview", "worksheets", "link-search", moduleId, search],
    enabled: fields.isSuccess,
    queryFn: () =>
      searchOpenViewLinkTargets({
        moduleId,
        definition: {
          version: 1,
          logic: "and",
          columns: titleField
            ? [{ fieldId: titleField.id, expectedType: titleField.type }]
            : [],
          filters: [],
          sort: [],
          deleted: "exclude",
          search: search || null,
          searchFields: fieldList
            .filter((field) => SEARCHABLE.has(field.type))
            .map((field) => ({ fieldId: field.id, expectedType: field.type })),
        },
      }),
  });
  const moduleName = source?.name ?? "records";
  const items = results.data?.items ?? [];
  return (
    <PickerFrame
      title={`Choose ${columnName}`}
      description={`Only records of ${moduleName} that you can read.`}
      searchLabel={`Search ${moduleName}`}
      typed={typed}
      onType={setTyped}
      current={
        current ? (
          <GuardedWorkspaceLink
            href={
              `/openview?section=views&module=${encodeURIComponent(moduleId)}&record=${encodeURIComponent(current.recordId)}` as Route
            }
            className="text-action-text inline-flex min-h-11 items-center self-start text-sm font-medium underline underline-offset-4 xl:min-h-8"
          >
            Open {current.label}&apos;s record
          </GuardedWorkspaceLink>
        ) : null
      }
      choices={items.map((record) => {
        const label = recordTitle(record, fieldList, titleField?.id ?? null);
        return {
          id: record.id,
          label,
          onChoose: () => onPick(record.id, label),
        };
      })}
      status={pickerStatus({
        searching: searching || results.isPending,
        empty: results.isSuccess && items.length === 0,
        failed: results.isError,
        noMatch: "No records match.",
        failure: "Records could not be searched.",
      })}
      removeLabel={current ? "Remove link" : null}
      onRemove={() => onPick(null, "")}
      onClose={onClose}
    />
  );
}
