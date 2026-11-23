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
} from "../adapters/worksheets-api";

// Add column and Column settings: the popover and its form.
import ColumnForm from "./sheet-column-form";

type Column = WorksheetColumnInput;

export function SheetColumnPopover({
  sheet,
  column,
  trigger,
  children,
}: {
  sheet: WorksheetDetail;
  /** The column to change; none adds a column. */
  column: Column | null;
  trigger: ReactElement;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger render={trigger}>{children}</PopoverTrigger>
      <PopoverContent align="start" className="w-80">
        {open ? (
          <ColumnForm
            sheet={sheet}
            column={column}
            onDone={() => setOpen(false)}
          />
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
