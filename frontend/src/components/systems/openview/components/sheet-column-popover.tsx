"use client";

import { useState, type ReactElement, type ReactNode } from "react";

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

import type {
  WorksheetColumnInput,
  WorksheetDetail,
  WorksheetHiddenSourceColumn,
} from "../adapters/worksheets-api";

// Add column and Column settings: the popover and its form.
import ColumnForm from "./sheet-column-form";
import type { SheetPreviewRow } from "./sheet-computed-field";

export function SheetColumnPopover({
  sheet,
  column,
  locale,
  preview,
  onDeleted,
  trigger,
  children,
}: {
  sheet: WorksheetDetail;
  /** The column to change; none adds a column. */
  column: WorksheetColumnInput | WorksheetHiddenSourceColumn | null;
  locale: string;
  /** Row 1, for a computed column's preview. */
  preview: () => SheetPreviewRow | null;
  onDeleted: (key: string) => void;
  trigger: ReactElement;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger render={trigger}>{children}</PopoverTrigger>
      <PopoverContent
        align="start"
        className="max-h-[var(--available-height)] w-[22rem] max-w-[calc(100vw-1rem)] overflow-y-auto"
      >
        {open ? (
          <ColumnForm
            sheet={sheet}
            column={column}
            locale={locale}
            preview={preview()}
            onDone={() => setOpen(false)}
            onDeleted={onDeleted}
          />
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
