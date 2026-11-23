"use client";

import { useEffect, useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { recordTitle } from "@/components/systems/shared/components/record-sheet";

import {
  catalogFirstPageOptions,
  fieldsFirstPageOptions,
} from "../adapters/openview-queries";
import { searchOpenViewLinkTargets } from "../adapters/records-api";

// A link cell's picker (docs/specs/sheets.md N1, SH-26): only records of the
// column's module that the person can read, found by the same record search
// as the record panel's links.

const SEARCHABLE = new Set(["text", "long_text", "email", "url", "select"]);
const SEARCH_DELAY_MS = 250;

export function SheetLinkPicker({
  columnName,
  moduleId,
  hasLink,
  onPick,
  onClose,
}: {
  columnName: string;
  moduleId: string;
  hasLink: boolean;
  onPick: (recordId: string | null) => void;
  onClose: () => void;
}) {
  const id = useId();
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(
      () => setSearch(typed.trim()),
      SEARCH_DELAY_MS,
    );
    return () => window.clearTimeout(timer);
  }, [typed]);
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
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="flex flex-col gap-3">
        <DialogTitle>Choose {columnName}</DialogTitle>
        <DialogDescription>
          Only records of {moduleName} that you can read.
        </DialogDescription>
        <Input
          type="search"
          aria-label={`Search ${moduleName}`}
          placeholder={`Search ${moduleName}`}
          className="min-h-11"
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          autoFocus
        />
        <div
          role="listbox"
          aria-label={`${moduleName} records`}
          id={`${id}-results`}
          className="flex max-h-72 flex-col overflow-y-auto rounded-md border"
        >
          {(results.data?.items ?? []).map((record) => (
            <button
              key={record.id}
              type="button"
              role="option"
              aria-selected="false"
              className={cn(
                "hover:bg-tint-hover focus-visible:outline-ring min-h-11 px-3 text-left text-sm outline-offset-[-2px] focus-visible:outline-2",
              )}
              onClick={() => onPick(record.id)}
            >
              {recordTitle(record, fieldList, titleField?.id ?? null)}
            </button>
          ))}
          {results.isSuccess && results.data.items.length === 0 ? (
            <p className="text-muted-foreground px-3 py-3 text-sm">
              No records match.
            </p>
          ) : null}
          {results.isError ? (
            <p role="alert" className="text-destructive px-3 py-3 text-sm">
              Records could not be searched.
            </p>
          ) : null}
        </div>
        <div className="flex justify-between gap-2">
          {hasLink ? (
            <Button
              variant="ghost"
              className="min-h-11"
              onClick={() => onPick(null)}
            >
              Remove link
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
