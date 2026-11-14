"use client";

import { Settings2, TriangleAlert } from "lucide-react";
import { useId, useState, useSyncExternalStore } from "react";

import { DepartmentMark } from "@/components/sandbox/department-mark";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent } from "@/components/ui/popover";
import { Sheet, SheetContent } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

import {
  SETUP_ITEMS,
  departmentSetup,
  setupAccessibleName,
  setupClearedCount,
} from "../domain/department-setup";
import type { DepartmentSetup } from "../domain/model";

/**
 * Setup choices (docs/specs/sandbox-ux-redesign.md, "Setup choices", B9;
 * plan section 11.3): the `Setup` control of a new department and its
 * "Created at publish" popover. Build's element bar and the review use the
 * same words, checkboxes, and lines.
 */

const PHONE_QUERY = "(max-width: 767px)";

function subscribePhone(onChange: () => void): () => void {
  const query = window.matchMedia(PHONE_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

/** Phones get a bottom sheet with 44px rows (B10). */
function usePhone(): boolean {
  return useSyncExternalStore(
    subscribePhone,
    () => window.matchMedia(PHONE_QUERY).matches,
    () => false,
  );
}

/** "Setup", or "Setup · 1 cleared" with the count in warn ink (R1.4). */
export function SetupControlWords({
  setup,
}: {
  setup: DepartmentSetup | undefined;
}) {
  const cleared = setupClearedCount(setup);
  return (
    <>
      <Settings2 aria-hidden="true" />
      Setup
      {cleared > 0 ? (
        <>
          <span aria-hidden="true">·</span>
          <span className="text-warn-text">{cleared} cleared</span>
        </>
      ) : null}
    </>
  );
}

export type SetupPopoverBodyProps = {
  /** The department's name, for the popover's accessible name. */
  name: string;
  departmentIndex: number;
  /** The department's draft value; none means every item is on. */
  setup: DepartmentSetup | undefined;
  /**
   * A save or a review holds the draft: the boxes keep focus and their
   * values but take no change until it ends.
   */
  held: boolean;
  onToggle: (item: keyof DepartmentSetup, on: boolean) => void;
  phone: boolean;
};

/** The popover's content; exported for markup tests. */
export function SetupPopoverBody({
  departmentIndex,
  setup,
  held,
  onToggle,
  phone,
}: SetupPopoverBodyProps) {
  const id = useId();
  const value = departmentSetup({ setup });
  const row = phone ? "min-h-11" : "min-h-11 xl:min-h-8";
  return (
    <div className="grid gap-1 px-3.5 pt-3 pb-3" aria-busy={held || undefined}>
      <p className="flex items-center gap-2 pb-1 text-sm font-semibold">
        <DepartmentMark departmentIndex={departmentIndex} />
        Created at publish
      </p>
      {SETUP_ITEMS.map(({ item, label, detail }) => {
        const itemId = `${id}-${item}`;
        const noteId = `${id}-${item}-note`;
        // SD14: a cleared category puts the channel in no category.
        const note =
          item === "category" && !value.category
            ? "The channel goes in no category."
            : null;
        return (
          <div key={item} className="grid">
            <div className={cn("flex items-center gap-2", row)}>
              <Checkbox
                id={itemId}
                checked={value[item]}
                readOnly={held}
                aria-describedby={note ? noteId : undefined}
                onCheckedChange={(checked) => {
                  if (!held) onToggle(item, checked === true);
                }}
              />
              <label htmlFor={itemId} className="text-sm">
                {label}
                {detail ? (
                  <span className="text-muted-foreground ml-1.5 text-xs">
                    · {detail}
                  </span>
                ) : null}
              </label>
            </div>
            {note ? (
              <p
                id={noteId}
                className="text-warn-text -mt-1 ml-6 flex items-center gap-1.5 pb-1 text-xs"
              >
                <TriangleAlert aria-hidden="true" className="size-3.5" />
                {note}
              </p>
            ) : null}
          </div>
        );
      })}
      <p
        className={cn(
          "text-muted-foreground flex items-center pl-6 text-sm",
          row,
        )}
      >
        Board · always created
      </p>
    </div>
  );
}

export type SetupPopoverProps = Omit<SetupPopoverBodyProps, "phone"> & {
  open: boolean;
  /** The control that opened the popover; focus returns to it on close. */
  anchor: HTMLElement | null;
  onRequestClose: () => void;
};

/**
 * "Created at publish": anchored to the control that opened it, a bottom
 * sheet on phones. Escape closes it and returns focus to the control.
 */
export function SetupPopover({
  open,
  anchor,
  onRequestClose,
  ...body
}: SetupPopoverProps) {
  const phone = usePhone();
  const label = `Setup for ${body.name}`;
  const finalFocus = () => anchor ?? true;
  if (phone)
    return (
      <Sheet
        open={open}
        onOpenChange={(next) => (next ? undefined : onRequestClose())}
      >
        <SheetContent
          aria-label={label}
          finalFocus={finalFocus}
          className="inset-x-0 top-auto bottom-0 max-h-[min(80dvh,40rem)] w-full gap-0 rounded-t-xl border-t border-l-0 p-0 pb-[env(safe-area-inset-bottom)] data-ending-style:translate-x-0 data-ending-style:translate-y-full data-starting-style:translate-x-0 data-starting-style:translate-y-full"
        >
          <SetupPopoverBody {...body} phone />
        </SheetContent>
      </Sheet>
    );
  return (
    <Popover
      open={open}
      onOpenChange={(next) => (next ? undefined : onRequestClose())}
    >
      <PopoverContent
        aria-label={label}
        anchor={anchor}
        align="start"
        side="bottom"
        sideOffset={6}
        collisionPadding={16}
        finalFocus={finalFocus}
        className="slim-ui w-[21rem] max-w-[calc(100vw-2rem)] gap-0 p-0"
      >
        <SetupPopoverBody {...body} phone={false} />
      </PopoverContent>
    </Popover>
  );
}

/**
 * The review's Setup control (plan 11.3): the same control and popover as in
 * Build, at the end of a new department's row. It owns its open state; the
 * row keeps its key, so the control keeps focus through a second review.
 */
export function SetupControl({
  name,
  departmentIndex,
  setup,
  held,
  onToggle,
}: Omit<SetupPopoverBodyProps, "phone">) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        type="button"
        variant="ghost"
        aria-label={setupAccessibleName(name, setup)}
        aria-haspopup="dialog"
        aria-expanded={open}
        className={cn(
          "aria-expanded:bg-tint-selected h-11 gap-1.5 px-2.5 text-[13px] font-medium sm:h-7",
        )}
        onClick={(event) => {
          setAnchor(event.currentTarget);
          setOpen(true);
        }}
      >
        <SetupControlWords setup={setup} />
      </Button>
      <SetupPopover
        open={open}
        anchor={anchor}
        onRequestClose={() => setOpen(false)}
        name={name}
        departmentIndex={departmentIndex}
        setup={setup}
        held={held}
        onToggle={onToggle}
      />
    </>
  );
}
