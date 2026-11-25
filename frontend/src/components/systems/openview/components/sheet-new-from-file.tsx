"use client";

import { isEditionRefusal } from "@/lib/api-errors";
import { useEffect, useId, useRef, useState } from "react";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, FileText, Link2 } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DialogFooter } from "@/components/ui/dialog";
import { DialogFrameFooter } from "@/components/ui/dialog-frame";
import { DisabledReason } from "@/components/ui/disabled-reason";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { useWorkspaceNavigationRequest } from "@/components/workspace-navigation-guard";
import { ApiError } from "@/lib/api";
import { apiErrorReference } from "@/lib/api-errors";
import { cn } from "@/lib/utils";

import { worksheetKeys } from "../adapters/worksheet-queries";
import { createWorksheet } from "../adapters/worksheets-api";
import { importFileKind } from "../domain/sheet-import";
import {
  mappingLine,
  readTemplate,
  suggestModule,
  TEMPLATE_MAX_BYTES,
  TEMPLATE_PROBLEMS,
  type TemplateRead,
} from "../domain/sheet-template";
import { sheetHref } from "./sheet-display";
import type { SheetAnchor } from "./sheet-lists";
import { moduleLabel, useSheetModules } from "./use-sheet-modules";

// New sheet from a template file or a data file (docs/specs/sheets.md X6,
// D9.2, D9.3; Screens 2): the file, the template's summary and the module
// each link column maps to, and the dialog's buttons. A data file goes on
// to the import preview ("Check the rows"). Loaded on first use.

/** A template refused by the server, in the reader's words. */
function templateRefusal(error: unknown, onModule: boolean): string {
  if (error instanceof ApiError) {
    const types = Array.isArray(error.details)
      ? error.details.map((item) =>
          typeof item === "object" && item !== null && "type" in item
            ? String(item.type)
            : "",
        )
      : [];
    if (types.includes("template_unsupported_version"))
      return TEMPLATE_PROBLEMS.version;
    if (types.includes("template_sheet_lookup"))
      return TEMPLATE_PROBLEMS.sheetLookup;
    if (error.status === 404)
      return "A chosen module, or this record, is no longer available. Choose again.";
    if (error.status === 409)
      return onModule
        ? "This module was closed, so it cannot hold a new sheet."
        : "This record was deleted or its module was closed, so it cannot hold a new sheet.";
    if (isEditionRefusal(error)) return error.message;
    if (error.status === 403) return "Guests cannot create sheets.";
    if (error.status === 422)
      return "This template could not be used. Nothing was created.";
  }
  return "The sheet could not be created. Try again.";
}

export default function SheetNewFromFile({
  kind,
  anchor,
  title,
  onClose,
  onCheckRows,
}: {
  kind: "template" | "data";
  anchor: SheetAnchor;
  /** The name typed in New sheet, or null after it showed "Enter a name." */
  title: () => string | null;
  onClose: () => void;
  onCheckRows: (file: File) => void;
}) {
  const id = useId();
  const client = useQueryClient();
  const router = useRouter();
  const requestNavigation = useWorkspaceNavigationRequest();
  const catalog = useSheetModules();
  const { modules } = catalog;
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [template, setTemplate] = useState<Extract<
    TemplateRead,
    { ok: true }
  > | null>(null);
  // Each link column's module; null makes it a text column.
  const [mapping, setMapping] = useState<Record<string, string | null>>({});
  const [suggested, setSuggested] = useState<Record<string, string | null>>({});

  // Suggestions wait for the modules the person can read, once per file: a
  // later read of the catalog keeps what the person chose (N8).
  const suggestedFor = useRef<object | null>(null);
  useEffect(() => {
    if (!template || !modules.length || suggestedFor.current === template)
      return;
    suggestedFor.current = template;
    const next = Object.fromEntries(
      template.links.map((link) => [link.key, suggestModule(link, modules)]),
    );
    setSuggested(next);
    setMapping(next);
  }, [template, modules]);

  const create = useMutation({
    mutationFn: (name: string) =>
      createWorksheet({
        ...(anchor.kind === "record"
          ? { recordId: anchor.recordId }
          : { moduleId: anchor.moduleId }),
        title: name,
        source: {
          kind: "template",
          template: template?.template ?? {},
          moduleMapping: mapping,
        },
      }),
    onSuccess: (sheet) => {
      void client.invalidateQueries({ queryKey: worksheetKeys.all });
      onClose();
      const href = sheetHref(sheet.id);
      const resume = () => router.push(href as Route);
      if (requestNavigation(href, resume)) resume();
    },
  });

  const choose = async (chosen: File) => {
    setFile(chosen);
    setProblem(null);
    setTemplate(null);
    create.reset();
    if (kind === "data") {
      try {
        importFileKind(chosen);
      } catch (error) {
        setProblem(error instanceof Error ? error.message : null);
      }
      return;
    }
    if (chosen.size > TEMPLATE_MAX_BYTES) {
      setProblem(TEMPLATE_PROBLEMS.large);
      return;
    }
    const read = readTemplate(await chosen.text());
    if (read.ok) setTemplate(read);
    else setProblem(read.problem);
  };

  const pending = create.isPending;
  const blocked = !file
    ? "Choose a file first."
    : problem
      ? kind === "template"
        ? "Choose another template file."
        : "Choose another file."
      : kind === "template" && !template
        ? "Wait for the file to be read."
        : template &&
            template.links.some((link) => !Object.hasOwn(mapping, link.key))
          ? "Wait for the modules to load."
          : null;
  const submit = () => {
    if (blocked || pending) return;
    const name = title();
    if (name === null) return;
    if (kind === "data" && file) onCheckRows(file);
    else create.mutate(name);
  };

  return (
    <>
      <input
        ref={fileInput}
        type="file"
        accept={
          kind === "template"
            ? ".json,application/json"
            : ".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        }
        aria-label="Choose a file"
        tabIndex={-1}
        className="sr-only"
        onChange={(event) => {
          const chosen = event.target.files?.[0];
          event.target.value = "";
          if (chosen) void choose(chosen);
        }}
      />
      <div
        className={cn(
          "flex flex-wrap items-center gap-3 rounded-md border p-3",
          problem && "border-danger-rule bg-danger-tint",
        )}
      >
        {problem ? (
          <AlertCircle
            aria-hidden="true"
            className="text-danger-text size-4 shrink-0"
          />
        ) : (
          <FileText
            aria-hidden="true"
            className="text-muted-foreground size-4 shrink-0"
          />
        )}
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-sm font-medium">
            {file?.name ?? "No file chosen"}
          </span>
          {problem ? (
            <span role="alert" className="text-danger-text text-xs">
              {problem}
            </span>
          ) : (
            <span className="text-muted-foreground text-xs">
              {template
                ? template.summary
                : file && kind === "data"
                  ? file.name.toLowerCase().endsWith(".xlsx")
                    ? "Excel · you choose the tab next"
                    : "CSV · you check the rows next"
                  : kind === "template"
                    ? "A .json file that Download template made."
                    : "A CSV or Excel (.xlsx) file."}
            </span>
          )}
        </div>
        <Button
          type="button"
          variant="outline"
          className="min-h-11 xl:h-8 xl:min-h-8"
          disabled={pending}
          onClick={() => fileInput.current?.click()}
        >
          {file ? "Choose another file" : "Choose a file"}
        </Button>
      </div>
      {template && template.links.length > 0 ? (
        <div
          role="group"
          aria-label="Link columns"
          className="grid grid-cols-1 items-center gap-x-3 gap-y-1.5 sm:grid-cols-[minmax(0,1fr)_auto_minmax(0,1.6fr)]"
        >
          <span className="text-muted-foreground hidden text-xs font-medium sm:block">
            Link column in the file
          </span>
          <span className="hidden sm:block" />
          <span className="text-muted-foreground hidden text-xs font-medium sm:block">
            Links to, in this organization
          </span>
          {template.links.map((link) => {
            const chosen = mapping[link.key] ?? null;
            const line = mappingLine(link, chosen, suggested[link.key] ?? null);
            return (
              <div key={link.key} className="contents">
                <span className="flex min-w-0 items-center gap-1.5 text-sm font-medium max-sm:pt-2">
                  <Link2
                    aria-hidden="true"
                    className="text-muted-foreground size-3.5 shrink-0"
                  />
                  <span className="truncate">{link.name}</span>
                </span>
                <ArrowRight
                  aria-hidden="true"
                  className="text-muted-foreground hidden size-4 sm:block"
                />
                <NativeSelect
                  aria-label={`${link.name} links to`}
                  aria-describedby={line ? `${id}-${link.key}` : undefined}
                  className="w-full [&_select]:h-11 xl:[&_select]:h-8"
                  value={chosen ?? ""}
                  disabled={pending}
                  onChange={(event) =>
                    setMapping((current) => ({
                      ...current,
                      [link.key]: event.target.value || null,
                    }))
                  }
                >
                  <NativeSelectOption value="">Text column</NativeSelectOption>
                  {modules.map((module) => (
                    <NativeSelectOption key={module.id} value={module.id}>
                      {moduleLabel(module)}
                    </NativeSelectOption>
                  ))}
                </NativeSelect>
                {line ? (
                  <span
                    id={`${id}-${link.key}`}
                    className="text-muted-foreground text-xs sm:col-start-3"
                  >
                    {line}
                  </span>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}
      {template && template.links.length > 0 && catalog.failed ? (
        <Alert
          variant="destructive"
          className="flex flex-wrap items-center gap-x-4 gap-y-2"
        >
          <p className="min-w-0 flex-1">The modules could not be listed.</p>
          <Button
            type="button"
            variant="outline"
            className="min-h-11 xl:h-8 xl:min-h-8"
            onClick={catalog.retry}
          >
            Retry
          </Button>
        </Alert>
      ) : null}
      {create.isError ? (
        <Alert
          variant="destructive"
          reference={apiErrorReference(create.error)}
        >
          <p>{templateRefusal(create.error, anchor.kind === "module")}</p>
        </Alert>
      ) : null}
      <DialogFrameFooter>
        <p className="text-muted-foreground text-sm">
          Only you can see it until you share it.
        </p>
        <DialogFooter className="mt-0">
          <Button
            type="button"
            variant="ghost"
            className="min-h-11"
            disabled={pending}
            onClick={onClose}
          >
            Cancel
          </Button>
          <DisabledReason stable reason={pending ? null : blocked}>
            <Button
              type="button"
              className="min-h-11"
              pending={pending}
              pendingLabel="Creating…"
              onClick={submit}
            >
              {kind === "data" ? "Check the rows" : "Create sheet"}
            </Button>
          </DisabledReason>
        </DialogFooter>
      </DialogFrameFooter>
    </>
  );
}
