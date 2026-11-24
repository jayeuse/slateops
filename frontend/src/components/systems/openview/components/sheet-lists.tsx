"use client";

import { lazy, Suspense, useId, useState, type ReactNode } from "react";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Plus, Sheet as SheetIcon, Upload } from "lucide-react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DialogFrameFooter,
  DialogFrameHeader,
  dialogFrameContentClass,
} from "@/components/ui/dialog-frame";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { LoadingRegion } from "@/components/ui/loading-region";
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkspaceDisplayRegion } from "@/components/use-display-region";
import {
  GuardedWorkspaceLink,
  useWorkspaceNavigationRequest,
} from "@/components/workspace-navigation-guard";
import { ApiError } from "@/lib/api";
import { apiErrorReference } from "@/lib/api-errors";
import { cn } from "@/lib/utils";

import { useOpenViewAccessDenied } from "../adapters/openview-access";
import {
  moduleWorksheetsOptions,
  recordWorksheetsOptions,
  worksheetKeys,
} from "../adapters/worksheet-queries";
import {
  createWorksheet,
  type WorksheetSummary,
} from "../adapters/worksheets-api";
import {
  SheetAccess,
  SheetTableRow,
  SheetsTable,
  sheetDetails,
  sheetHref,
} from "./sheet-display";

// The sheets of one record (its Sheets tab) or one module (its Sheets view),
// with New sheet: docs/specs/sheets.md P2, C1, C3 and Screens 1 and 2. A
// template file or a data file loads its part on first use (F7).

const SheetNewFromFile = lazy(() => import("./sheet-new-from-file"));
const SheetImportDialog = lazy(() => import("./sheet-import-dialog"));

type Start = "blank" | "template" | "data";

const STARTS: {
  value: Start;
  title: string;
  line: string;
  Icon: typeof SheetIcon;
}[] = [
  {
    value: "blank",
    title: "Blank sheet",
    line: "You add the columns.",
    Icon: SheetIcon,
  },
  {
    value: "template",
    title: "Template file",
    line: "A .json file with columns and settings, from another sheet.",
    Icon: FileText,
  },
  {
    value: "data",
    title: "Data file",
    line: "A CSV or Excel file with rows. You check the rows before anything is added.",
    Icon: Upload,
  },
];

export type SheetAnchor =
  | {
      kind: "record";
      recordId: string;
      recordTitle: string;
      moduleName: string;
    }
  | { kind: "module"; moduleId: string; moduleName: string };

const TITLE_MAX = 200;

function createRefusal(error: unknown, anchor: SheetAnchor): string {
  const onModule = anchor.kind === "module";
  if (error instanceof ApiError) {
    if (error.status === 409)
      return onModule
        ? "This module was closed, so it cannot hold a new sheet."
        : "This record was deleted or its module was closed, so it cannot hold a new sheet.";
    if (error.status === 404)
      return onModule
        ? "This module is no longer available."
        : "This record is no longer available.";
    if (error.status === 403) return "Guests cannot create sheets.";
    if (error.status === 422) return "Check the name and try again.";
  }
  return "The sheet could not be created. Try again.";
}

/** New sheet (Screens 2): a blank sheet with a name, on one record or module. */
export function NewSheetDialog({
  anchor,
  onClose,
}: {
  anchor: SheetAnchor;
  onClose: () => void;
}) {
  const id = useId();
  const client = useQueryClient();
  const router = useRouter();
  const requestNavigation = useWorkspaceNavigationRequest();
  const [name, setName] = useState("");
  const [missing, setMissing] = useState(false);
  const [start, setStart] = useState<Start>("blank");
  const [importing, setImporting] = useState<File | null>(null);
  const create = useMutation({
    mutationFn: (title: string) =>
      createWorksheet(
        anchor.kind === "record"
          ? { recordId: anchor.recordId, title }
          : { moduleId: anchor.moduleId, title },
      ),
    onSuccess: (sheet) => {
      void client.invalidateQueries({ queryKey: worksheetKeys.all });
      // Close first: a held navigation must not leave Create to run twice.
      onClose();
      const href = sheetHref(sheet.id);
      const resume = () => router.push(href as Route);
      if (requestNavigation(href, resume)) resume();
    },
  });
  const pending = create.isPending;
  const submit = () => {
    if (pending) return;
    const title = name.trim();
    if (!title) {
      setMissing(true);
      return;
    }
    setMissing(false);
    create.mutate(title);
  };
  const close = () => {
    if (!pending) onClose();
  };
  const errorId = `${id}-name-error`;
  /** The typed name, or null after showing "Enter a name." */
  const checkedTitle = () => {
    const title = name.trim();
    setMissing(!title);
    return title || null;
  };
  if (importing)
    return (
      <Suspense fallback={null}>
        <SheetImportDialog
          target={{ kind: "new", title: name.trim(), anchor }}
          initialFile={importing}
          onClose={onClose}
        />
      </Suspense>
    );
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) close();
      }}
    >
      <DialogContent className={cn(dialogFrameContentClass, "sm:max-w-lg")}>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (start === "blank") submit();
          }}
        >
          <DialogFrameHeader
            title={<DialogTitle>New sheet</DialogTitle>}
            description={
              <DialogDescription>
                {anchor.kind === "record"
                  ? `On ${anchor.recordTitle} · ${anchor.moduleName}`
                  : `On ${anchor.moduleName}`}
              </DialogDescription>
            }
            closeLabel="Close New sheet"
            closeDisabled={pending}
            onClose={close}
          />
          <Field>
            <FieldLabel htmlFor={`${id}-name`}>Name</FieldLabel>
            <Input
              id={`${id}-name`}
              className="min-h-11 xl:h-8 xl:min-h-8"
              maxLength={TITLE_MAX}
              autoComplete="off"
              value={name}
              aria-invalid={missing || undefined}
              aria-describedby={missing ? errorId : undefined}
              onChange={(event) => {
                setName(event.target.value);
                if (missing && event.target.value.trim()) setMissing(false);
              }}
            />
            {missing ? (
              <p id={errorId} className="text-destructive text-sm">
                Enter a name.
              </p>
            ) : null}
          </Field>
          <div
            role="radiogroup"
            aria-labelledby={`${id}-start`}
            className="flex flex-col gap-2"
          >
            <span id={`${id}-start`} className="text-sm font-medium">
              Start with
            </span>
            {STARTS.map(({ value, title, line, Icon }) => (
              <label
                key={value}
                className={cn(
                  "has-focus-visible:outline-ring flex min-h-11 cursor-pointer items-start gap-3 rounded-md border p-3 has-focus-visible:outline-2",
                  start === value && "border-action-text bg-tint-hover",
                )}
              >
                <input
                  type="radio"
                  name={`${id}-start`}
                  value={value}
                  checked={start === value}
                  disabled={pending}
                  onChange={() => setStart(value)}
                  className="mt-0.5 size-4 shrink-0 accent-[var(--action)]"
                />
                <Icon
                  aria-hidden="true"
                  className="text-muted-foreground mt-0.5 size-4 shrink-0"
                />
                <span className="flex min-w-0 flex-col">
                  <span className="text-sm font-medium">{title}</span>
                  <span className="text-muted-foreground text-xs">{line}</span>
                </span>
              </label>
            ))}
          </div>
          {start !== "blank" ? (
            <Suspense fallback={null}>
              <SheetNewFromFile
                key={start}
                kind={start}
                anchor={anchor}
                title={checkedTitle}
                onClose={onClose}
                onCheckRows={setImporting}
              />
            </Suspense>
          ) : null}
          {start === "blank" && create.isError ? (
            <Alert
              variant="destructive"
              reference={apiErrorReference(create.error)}
            >
              <p>{createRefusal(create.error, anchor)}</p>
            </Alert>
          ) : null}
          {start !== "blank" ? null : (
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
                  onClick={close}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  className="min-h-11"
                  pending={pending}
                  pendingLabel="Creating…"
                >
                  Create sheet
                </Button>
              </DialogFooter>
            </DialogFrameFooter>
          )}
        </form>
      </DialogContent>
    </Dialog>
  );
}

function SheetRow({ sheet }: { sheet: WorksheetSummary }) {
  const region = useWorkspaceDisplayRegion();
  return (
    <li className="hover:bg-tint-hover has-[a:focus-visible]:bg-tint-hover relative grid min-h-14 grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-2.5 gap-y-0.5 px-3 py-2">
      <SheetIcon
        aria-hidden="true"
        className="text-muted-foreground row-span-2 size-4 shrink-0"
      />
      <GuardedWorkspaceLink
        href={sheetHref(sheet.id) as Route}
        className="focus-visible:outline-ring truncate rounded-sm text-sm font-medium outline-offset-2 after:absolute after:inset-0 focus-visible:outline-2"
      >
        {sheet.title}
      </GuardedWorkspaceLink>
      <span className="row-span-2 text-sm">
        <SheetAccess sheet={sheet} short />
      </span>
      <span className="text-muted-foreground truncate text-xs tabular-nums">
        {sheetDetails(sheet, region)}
      </span>
    </li>
  );
}

function SheetListSkeleton() {
  return (
    <div className="flex flex-col gap-2 py-1">
      {[0, 1].map((row) => (
        <Skeleton key={row} className="h-12 w-full" />
      ))}
    </div>
  );
}

/**
 * One list of sheets with its heading, count and New sheet. The empty state
 * keeps the same frame (P2); a sheet the person cannot see adds nothing (V7).
 */
function SheetSection({
  heading,
  headingLevel,
  read,
  canCreate,
  anchor,
  empty,
  table = false,
}: {
  heading: string;
  headingLevel: "h2" | "h3";
  /** From 768px, the same table as My sheets in a card that scrolls alone. */
  table?: boolean;
  read: ReturnType<
    typeof useQuery<{ items: WorksheetSummary[]; total: number }>
  >;
  canCreate: boolean;
  anchor: SheetAnchor;
  empty: { title: string; description: string };
}) {
  const id = useId();
  const region = useWorkspaceDisplayRegion();
  const denied = useOpenViewAccessDenied();
  const [creating, setCreating] = useState(false);
  const Heading = headingLevel;
  const count = read.data?.total;
  // A record that left (deleted with Undo, or no longer readable) answers
  // 404; the panel says so itself, so the tab adds nothing.
  const gone = read.error instanceof ApiError && read.error.status === 404;
  if (denied || gone) return null;
  let body: ReactNode;
  if (read.isError)
    body = (
      <Alert
        variant="destructive"
        reference={apiErrorReference(read.error)}
        className="flex flex-wrap items-center gap-x-4 gap-y-2"
      >
        <p className="min-w-0 flex-1">Sheets could not be loaded.</p>
        <Button
          variant="outline"
          className="min-h-11 shrink-0 xl:h-8 xl:min-h-8"
          aria-disabled={read.isFetching || undefined}
          onClick={() => {
            if (!read.isFetching) void read.refetch();
          }}
        >
          Retry
        </Button>
      </Alert>
    );
  else
    body = (
      <LoadingRegion
        loading={read.isPending}
        label="Loading sheets…"
        skeleton={<SheetListSkeleton />}
        className={table ? "access-fill" : undefined}
      >
        {read.data && read.data.items.length > 0 ? (
          <>
            {table ? (
              <div className="bg-card hidden min-h-0 flex-1 overflow-auto overscroll-contain rounded-md border md:block">
                <SheetsTable
                  label={heading}
                  columns={moduleColumns}
                  empty={null}
                >
                  {read.data.items.map((sheet) => (
                    <SheetTableRow
                      key={sheet.id}
                      sheet={sheet}
                      region={region}
                      anchor={false}
                      guarded
                    />
                  ))}
                </SheetsTable>
              </div>
            ) : null}
            <ul
              aria-labelledby={id}
              className={cn(
                "divide-border divide-y rounded-md border",
                table && "md:hidden",
              )}
            >
              {read.data.items.map((sheet) => (
                <SheetRow key={sheet.id} sheet={sheet} />
              ))}
            </ul>
          </>
        ) : (
          <ul aria-labelledby={id} className="rounded-md border border-dashed">
            <li className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-2.5 gap-y-0.5 px-3 py-3">
              <SheetIcon
                aria-hidden="true"
                className="text-muted-foreground row-span-2 size-4"
              />
              <span className="text-sm font-medium">{empty.title}</span>
              <span className="text-muted-foreground text-xs">
                {empty.description}
              </span>
            </li>
          </ul>
        )}
      </LoadingRegion>
    );
  return (
    <section
      aria-labelledby={id}
      className={cn("flex min-w-0 flex-col gap-2", table && "access-fill")}
    >
      <div className="flex min-h-11 items-center gap-2 xl:min-h-8">
        <Heading id={id} className="text-sm font-semibold">
          {heading}
        </Heading>
        {count ? (
          <span className="text-muted-foreground text-sm tabular-nums">
            {count}
          </span>
        ) : null}
        {canCreate ? (
          <Button
            variant="ghost"
            className="ml-auto min-h-11 xl:h-8 xl:min-h-8"
            onClick={() => setCreating(true)}
          >
            <Plus aria-hidden="true" />
            New sheet
          </Button>
        ) : null}
      </div>
      {body}
      {creating ? (
        <NewSheetDialog anchor={anchor} onClose={() => setCreating(false)} />
      ) : null}
    </section>
  );
}

/** The record panel's Sheets tab label: its count is what the tab lists. */
export function RecordSheetsTabLabel({ recordId }: { recordId: string }) {
  const read = useQuery(recordWorksheetsOptions(recordId));
  const denied = useOpenViewAccessDenied();
  const count = denied ? undefined : read.data?.total;
  return (
    <>
      Sheets
      {count ? (
        <>
          {/* The space names the tab "Sheets 3"; the trigger is a flex
              row, so the margin draws it. */}{" "}
          <span className="text-muted-foreground ml-1.5 font-normal tabular-nums">
            {count}
          </span>
        </>
      ) : null}
    </>
  );
}

/** The record panel's Sheets tab (Screens 1); Appears in follows in F8. */
export function RecordSheetsPanel({
  anchor,
  canCreate,
}: {
  anchor: Extract<SheetAnchor, { kind: "record" }>;
  canCreate: boolean;
}) {
  const read = useQuery(recordWorksheetsOptions(anchor.recordId));
  return (
    <SheetSection
      heading="On this record"
      headingLevel="h3"
      read={read}
      canCreate={canCreate}
      anchor={anchor}
      empty={{
        title: "No sheets on this record yet",
        description: "A new sheet is visible only to you until you share it.",
      }}
    />
  );
}

const moduleColumns = [
  ["Sheet", "w-[34%]"],
  ["Owner", "w-[22%]"],
  ["Your access", "w-[18%]"],
  ["Rows", "w-[10%]"],
  ["Last change", "w-[16%]"],
] as const;

/** The module page's Sheets view (P2, SH-67). */
export function ModuleSheets({
  anchor,
  canCreate,
}: {
  anchor: Extract<SheetAnchor, { kind: "module" }>;
  canCreate: boolean;
}) {
  const read = useQuery(moduleWorksheetsOptions(anchor.moduleId));
  return (
    // On the module page's fill chain (OD6): from 1280px the table card
    // takes the height that is left and scrolls alone.
    <div className="access-fill flex min-h-0 min-w-0 flex-col max-md:max-w-3xl">
      <SheetSection
        heading="Module sheets"
        headingLevel="h2"
        read={read}
        canCreate={canCreate}
        anchor={anchor}
        table
        empty={{
          title: "No module sheets yet",
          description: "A new sheet is visible only to you until you share it.",
        }}
      />
    </div>
  );
}
