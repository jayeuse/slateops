"use client";

import { Check, ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type { ChangeOption } from "../domain/record-batch-change";

/** The "Change <Field> to" group: offered to writers on live records only. */
export type ChoiceCellChange = {
  options: readonly ChangeOption[];
  /** The stored value; its option is checked (DR-SI-1.5). */
  current: unknown;
  onPick: (value: ChangeOption["value"]) => void;
};

/**
 * A Choice list value in a table row (candidate 1, DR-SI-1.1 to DR-SI-1.6):
 * the value with a chevron opens "Show only <value>" and, for a writer,
 * "Change <Field> to". A cell is sized to its text; on a phone the chip is a
 * 44 px target at the row's end. It sits above the row's open button, so
 * the rest of the row still opens the record. With no item to offer it is
 * plain text: a menu with no item does not open.
 */
export function ChoiceCellMenu({
  fieldName,
  label,
  variant,
  busy,
  disabled,
  onShowOnly,
  change,
}: {
  fieldName: string;
  /** The value shown: the stored one, or the new one while it saves. */
  label: string;
  variant: "cell" | "chip";
  busy: boolean;
  disabled: boolean;
  onShowOnly: (() => void) | null;
  change: ChoiceCellChange | null;
}) {
  if (!onShowOnly && !change)
    return variant === "chip" ? null : (
      <span className="block truncate">{label}</span>
    );
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={disabled || busy}
        aria-busy={busy || undefined}
        aria-label={`${fieldName}: ${label}, options`}
        className={cn(
          "focus-visible:outline-ring relative z-10 inline-flex max-w-full min-w-0 items-center gap-1 rounded-sm text-left focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-default aria-busy:opacity-70",
          variant === "chip"
            ? "border-border bg-card min-h-11 shrink-0 rounded-full border px-3 text-xs font-medium"
            : "min-h-11 hover:underline hover:underline-offset-4 xl:min-h-8",
        )}
      >
        <span className="truncate">{label}</span>
        <ChevronDown
          aria-hidden="true"
          className="text-muted-foreground size-3.5 shrink-0"
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent className="slim-ui min-w-48">
        {onShowOnly ? (
          <DropdownMenuItem
            className="min-h-11 xl:min-h-8"
            onClick={onShowOnly}
          >
            Show only {label}
          </DropdownMenuItem>
        ) : null}
        {change ? (
          <>
            {onShowOnly ? <DropdownMenuSeparator /> : null}
            <DropdownMenuGroup>
              <DropdownMenuLabel className="text-muted-foreground px-2 pt-1.5 pb-0.5 text-xs font-medium">
                Change {fieldName} to
              </DropdownMenuLabel>
              {/* Plain items marked as radios, as the Layout menu does: the
                  menu's radio parts would join the shared menu code. */}
              {change.options.map((option) => {
                const checked = option.value === (change.current ?? null);
                return (
                  <DropdownMenuItem
                    key={String(option.value)}
                    role="menuitemradio"
                    aria-checked={checked}
                    className="min-h-11 xl:min-h-8"
                    onClick={() => {
                      // A pick of the checked value only closes the menu.
                      if (!checked) change.onPick(option.value);
                    }}
                  >
                    {option.label}
                    {checked ? (
                      <Check aria-hidden="true" className="ml-auto" />
                    ) : null}
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuGroup>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
