"use client";

import { Fragment, lazy, Suspense, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  Copy,
  Download,
  FileJson,
  History,
  MoreHorizontal,
  Pencil,
  Sheet as SheetIcon,
  Trash2,
  Upload,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ApiError } from "@/lib/api";

import { authMeOptions } from "../adapters/openview-queries";

import {
  exportWorksheet,
  type WorksheetDetail,
  type WorksheetExportFormat,
} from "../adapters/worksheets-api";
import { sheetActions, type SheetRole } from "../domain/sheet-share";

// The sheet header's actions (docs/specs/sheets.md Screens 3 to 5): Export
// for everyone who can see the sheet, Share for its owner, and More (Rename
// and Delete for the owner, Sheet history for everyone). An open sheet keeps
// Export and history only (L7). F7: Import for the owner and Edit (X9), Make
// a copy for readers of an open sheet and for the owner (L6, Decision 3),
// New sheet from this structure for anyone who can create (X7); guests do
// neither. The dialogs load on first use, apart from the page.

const SheetShareDialog = lazy(() => import("./sheet-share-dialog"));
const SheetHistoryPanel = lazy(() => import("./sheet-history-panel"));
const SheetRenameDialog = lazy(() =>
  import("./sheet-manage-dialogs").then((module) => ({
    default: module.SheetRenameDialog,
  })),
);
const SheetDeleteDialog = lazy(() =>
  import("./sheet-manage-dialogs").then((module) => ({
    default: module.SheetDeleteDialog,
  })),
);

const SheetImportDialog = lazy(() => import("./sheet-import-dialog"));
const SheetCopyDialog = lazy(() =>
  import("./sheet-copy-dialogs").then((module) => ({
    default: module.SheetCopyDialog,
  })),
);
const SheetFromStructureDialog = lazy(() =>
  import("./sheet-copy-dialogs").then((module) => ({
    default: module.SheetFromStructureDialog,
  })),
);

type Open =
  | "share"
  | "history"
  | "rename"
  | "delete"
  | "import"
  | "copy"
  | "structure"
  | null;

const EXPORTS: {
  format: WorksheetExportFormat;
  label: string;
  description: string;
}[] = [
  {
    format: "csv",
    label: "Download CSV",
    description: "All rows. Computed and lookup columns as values.",
  },
  {
    format: "xlsx",
    label: "Download Excel",
    description: "The same, as an .xlsx file.",
  },
  {
    format: "template",
    label: "Download template",
    description: "Columns and settings only, no rows (.json).",
  },
];

/** Why an export was refused, in the reader's words; never the server's. */
function exportFailure(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 422 && error.code === "export_limit_exceeded")
      return "This sheet is larger than an export allows (10,000 rows or 8 MiB). Nothing was exported.";
    // The recheck after the build answers a plain 403 (D9.1); a coded 403
    // is the session's own check, which rechecks the session.
    if (error.status === 403 && !error.code)
      return "You can no longer read one of the linked modules. Nothing was exported.";
    if (error.status === 503)
      return "The export is not available right now. Nothing was exported. Try again.";
  }
  return "The export could not be downloaded. Try again.";
}

function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

const actionButton = "min-h-11 xl:h-8 xl:min-h-8";

export function SheetHeaderActions({
  sheet,
  role,
  onFailure,
  onGone,
  onRowsChanged,
}: {
  sheet: WorksheetDetail;
  role: SheetRole;
  /** A refused action's words, shown over the grid. */
  onFailure: (message: string | null) => void;
  /** The sheet is hidden or gone (404). */
  onGone: () => void;
  /** Rows were imported: the page reads its rows again. */
  onRowsChanged: () => void;
}) {
  const actions = sheetActions(role);
  // Guests create no sheets (C3) and copy none (Decision 3); unknown until
  // the identity is read, so the actions wait for it.
  const identity = useQuery(authMeOptions());
  const canCreate = identity.data ? identity.data.role !== "guest" : false;
  // A guest never imports, even into a sheet they still own (F7-S4).
  const canImport = (role === "owner" || role === "edit") && canCreate;
  const copyFirst = role === "open" && canCreate;
  const copyInMore = role === "owner" && canCreate;
  const [open, setOpen] = useState<Open>(null);
  const [exporting, setExporting] = useState(false);
  const exportLock = useRef(false);
  const more = useRef<HTMLButtonElement | null>(null);

  const runExport = async (format: WorksheetExportFormat) => {
    if (exportLock.current) return;
    exportLock.current = true;
    setExporting(true);
    onFailure(null);
    try {
      const file = await exportWorksheet(sheet.id, format);
      download(file.blob, file.filename);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) onGone();
      else onFailure(exportFailure(error));
    } finally {
      exportLock.current = false;
      setExporting(false);
    }
  };

  const close = () => setOpen(null);
  return (
    <div className="flex w-full min-w-0 items-center gap-2 sm:w-auto">
      {canImport ? (
        <Button
          variant="ghost"
          className={actionButton}
          onClick={() => setOpen("import")}
        >
          <Upload aria-hidden="true" />
          Import
        </Button>
      ) : null}
      {actions.export ? (
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                variant="ghost"
                aria-busy={exporting || undefined}
                className={actionButton}
              />
            }
          >
            <Download aria-hidden="true" />
            Export
            <ChevronDown aria-hidden="true" className="size-3.5" />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-72">
            {EXPORTS.map((item, index) => (
              <Fragment key={item.format}>
                {index === 2 ? <DropdownMenuSeparator /> : null}
                <DropdownMenuItem
                  className="items-start py-2"
                  onClick={() => void runExport(item.format)}
                >
                  {item.format === "template" ? (
                    <FileJson aria-hidden="true" className="mt-0.5" />
                  ) : (
                    <Download aria-hidden="true" className="mt-0.5" />
                  )}
                  <span className="flex min-w-0 flex-col">
                    <span>{item.label}</span>
                    <span className="text-muted-foreground text-xs">
                      {item.description}
                    </span>
                  </span>
                </DropdownMenuItem>
              </Fragment>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
      {copyFirst ? (
        <Button
          className={`${actionButton} max-sm:flex-1`}
          onClick={() => setOpen("copy")}
        >
          <Copy aria-hidden="true" />
          Make a copy
        </Button>
      ) : null}
      {actions.share ? (
        <Button
          className={`${actionButton} max-sm:flex-1`}
          onClick={() => setOpen("share")}
        >
          <Users aria-hidden="true" />
          Share
        </Button>
      ) : null}
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              ref={more}
              variant="ghost"
              size="icon"
              aria-label="More sheet actions"
              className="size-11 shrink-0 xl:size-8"
            />
          }
        >
          <MoreHorizontal aria-hidden="true" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          {actions.rename ? (
            <DropdownMenuItem onClick={() => setOpen("rename")}>
              <Pencil aria-hidden="true" />
              Rename
            </DropdownMenuItem>
          ) : null}
          {copyInMore ? (
            <DropdownMenuItem onClick={() => setOpen("copy")}>
              <Copy aria-hidden="true" />
              Make a copy
            </DropdownMenuItem>
          ) : null}
          {actions.history ? (
            <DropdownMenuItem onClick={() => setOpen("history")}>
              <History aria-hidden="true" />
              Sheet history
            </DropdownMenuItem>
          ) : null}
          {canCreate ? (
            <DropdownMenuItem
              className="items-start py-2"
              onClick={() => setOpen("structure")}
            >
              <SheetIcon aria-hidden="true" className="mt-0.5" />
              <span className="flex min-w-0 flex-col">
                <span>New sheet from this structure</span>
                <span className="text-muted-foreground text-xs">
                  Same columns, on a record you choose. No rows.
                </span>
              </span>
            </DropdownMenuItem>
          ) : null}
          {actions.remove ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                variant="destructive"
                onClick={() => setOpen("delete")}
              >
                <Trash2 aria-hidden="true" />
                Delete sheet
              </DropdownMenuItem>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>
      <Suspense fallback={null}>
        {open === "share" ? (
          <SheetShareDialog sheet={sheet} onClose={close} onGone={onGone} />
        ) : null}
        {open === "history" ? (
          <SheetHistoryPanel
            sheet={sheet}
            onClose={() => {
              close();
              more.current?.focus();
            }}
            onGone={onGone}
          />
        ) : null}
        {open === "rename" ? (
          <SheetRenameDialog sheet={sheet} onClose={close} onGone={onGone} />
        ) : null}
        {open === "delete" ? (
          <SheetDeleteDialog sheet={sheet} onClose={close} onGone={onGone} />
        ) : null}
        {open === "import" ? (
          <SheetImportDialog
            target={{ kind: "existing", sheet }}
            initialFile={null}
            onClose={close}
            onImported={onRowsChanged}
          />
        ) : null}
        {open === "copy" ? (
          <SheetCopyDialog sheet={sheet} onClose={close} />
        ) : null}
        {open === "structure" ? (
          <SheetFromStructureDialog sheet={sheet} onClose={close} />
        ) : null}
      </Suspense>
    </div>
  );
}
