"use client";

import { Link2, Plus } from "lucide-react";
import type { MouseEvent, ReactNode } from "react";

import { DepartmentMark } from "@/components/sandbox/department-mark";
import { Button } from "@/components/ui/button";
import { DisabledReason } from "@/components/ui/disabled-reason";
import { cn } from "@/lib/utils";
import { setupAccessibleName } from "../domain/department-setup";
import type { DepartmentSetup } from "../domain/model";
import { elementBarActions } from "../helpers/element-bar";
import { SetupControlWords } from "./setup-popover";

/** What a bar control opens, while it is open. */
export type ElementBarOpen = "module" | "field" | "connect" | "setup" | null;

export type ElementBarControlsProps = {
  kind: "department" | "module";
  name: string;
  /** A closed module adds fields but connects to nothing. */
  closed?: boolean;
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
  /**
   * A new open department's Setup (FIT-1): its draft value, or absent when
   * the department offers no Setup.
   */
  setup?: { value: DepartmentSetup | undefined } | null;
  onSetup?: (anchor: HTMLElement) => void;
};

/**
 * The controls of an element bar (docs/specs/sandbox-ux-redesign.md,
 * "Element bar"): a department adds a module, and a new one holds Setup; a
 * module adds a field or connects. Visible labels are one word; accessible names name the result
 * and the parent.
 */
export function ElementBarControls({
  kind,
  name,
  closed = false,
  departmentIndex,
  pinned,
  open,
  connectReason,
  onAddModule,
  onAddField,
  onConnect,
  setup = null,
  onSetup,
}: ElementBarControlsProps) {
  const control = (
    action: Exclude<ElementBarOpen, null>,
    label: string,
    word: ReactNode,
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
        <>
          {control(
            "module",
            `Add module to ${name}`,
            "Module",
            <Plus aria-hidden="true" />,
            onAddModule,
          )}
          {setup &&
          onSetup &&
          elementBarActions(kind, closed, true).includes("setup") ? (
            <>
              <span
                aria-hidden="true"
                className="bg-border mx-0.5 h-4 w-px shrink-0"
              />
              {control(
                "setup",
                setupAccessibleName(name, setup.value),
                <SetupControlWords setup={setup.value} />,
                null,
                onSetup,
              )}
            </>
          ) : null}
        </>
      ) : (
        <>
          {control(
            "field",
            `Add field to ${name}`,
            "Field",
            <Plus aria-hidden="true" />,
            onAddField,
          )}
          {elementBarActions(kind, closed).includes("connect") ? (
            <DisabledReason stable reason={connectReason}>
              {control(
                "connect",
                `Connect ${name} to another module`,
                "Connect",
                <Link2 aria-hidden="true" />,
                onConnect,
              )}
            </DisabledReason>
          ) : null}
        </>
      )}
    </>
  );
}
