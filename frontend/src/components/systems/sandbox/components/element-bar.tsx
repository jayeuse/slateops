"use client";

import { Link2, Plus } from "lucide-react";
import type { MouseEvent, ReactNode } from "react";

import { DepartmentMark } from "@/components/sandbox/department-mark";
import { Button } from "@/components/ui/button";
import { DisabledReason } from "@/components/ui/disabled-reason";
import { cn } from "@/lib/utils";

/** What a bar control opens, while it is open. */
export type ElementBarOpen = "module" | "field" | "connect" | null;

export type ElementBarControlsProps = {
  kind: "department" | "module";
  name: string;
  departmentIndex: number;
  /** The phone bar pinned to the bottom of the canvas: name first, 44px. */
  pinned: boolean;
  /** The entry or Connect popover this bar opened, while it is open. */
  open: ElementBarOpen;
  /** Why Connect cannot act ("Add a second module first."), or null. */
  connectReason: string | null;
  onAddModule: (anchor: HTMLElement) => void;
  onAddField: (anchor: HTMLElement) => void;
  onConnect: (anchor: HTMLElement) => void;
};

/**
 * The controls of an element bar (docs/specs/sandbox-ux-redesign.md,
 * "Element bar"): a department adds a module; a module adds a field or
 * connects. Visible labels are one word; accessible names name the result
 * and the parent.
 */
export function ElementBarControls({
  kind,
  name,
  departmentIndex,
  pinned,
  open,
  connectReason,
  onAddModule,
  onAddField,
  onConnect,
}: ElementBarControlsProps) {
  const control = (
    action: Exclude<ElementBarOpen, null>,
    label: string,
    word: string,
    icon: ReactNode,
    run: (anchor: HTMLElement) => void,
  ) => (
    <Button
      type="button"
      variant="ghost"
      data-bar-action={action}
      aria-label={label}
      aria-haspopup="dialog"
      aria-expanded={open === action}
      className={cn(
        "gap-1.5 px-2.5 text-[13px] font-medium",
        pinned ? "h-11 px-3" : "h-11 xl:h-7",
        open === action &&
          "bg-[color-mix(in_oklab,var(--ink)_14%,transparent)]",
      )}
      onClick={(event: MouseEvent<HTMLButtonElement>) =>
        run(event.currentTarget)
      }
    >
      {icon}
      {word}
    </Button>
  );
  return (
    <>
      {pinned ? (
        <span className="flex min-w-0 flex-1 items-center gap-2 px-2 text-sm font-semibold">
          <DepartmentMark departmentIndex={departmentIndex} />
          <span className="truncate">{name}</span>
        </span>
      ) : null}
      {kind === "department" ? (
        control(
          "module",
          `Add module to ${name}`,
          "Module",
          <Plus aria-hidden="true" />,
          onAddModule,
        )
      ) : (
        <>
          {control(
            "field",
            `Add field to ${name}`,
            "Field",
            <Plus aria-hidden="true" />,
            onAddField,
          )}
          <DisabledReason stable reason={connectReason}>
            {control(
              "connect",
              `Connect ${name} to another module`,
              "Connect",
              <Link2 aria-hidden="true" />,
              onConnect,
            )}
          </DisabledReason>
        </>
      )}
    </>
  );
}
