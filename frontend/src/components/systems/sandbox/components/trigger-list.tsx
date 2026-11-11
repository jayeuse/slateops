"use client";

import { useState, type Ref } from "react";
import { Plus, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";
import type { SandboxTrigger } from "../domain/document";
import {
  TriggerEventIcon,
  triggerEventLabel,
  triggerStatusWord,
} from "./trigger-flow";

// The list pane of Triggers (docs/specs/sandbox-relayout.md S6, S7): the
// count and New trigger in the head, a search and the All, On, and Off quick
// filters, then one 40px row per trigger: a dot and a word for its state,
// the name on one line, and the event as a mark and a word.

export type TriggerStatusFilter = "all" | "on" | "off";

const statusFilters: { value: TriggerStatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "on", label: "On" },
  { value: "off", label: "Off" },
];

/** The name a trigger shows; a trigger with no name is "Untitled trigger". */
export function triggerDisplayName(recordTrigger: SandboxTrigger): string {
  return recordTrigger.name || "Untitled trigger";
}

/** The quick-filter counts: totals of the whole list, not of the search. */
export function triggerStatusCounts(
  triggers: readonly SandboxTrigger[],
): Record<TriggerStatusFilter, number> {
  const on = triggers.filter((item) => item.enabled).length;
  return { all: triggers.length, on, off: triggers.length - on };
}

/** The rows to show: the state filter, then the name or event word. */
export function filterTriggers(
  triggers: readonly SandboxTrigger[],
  { query, status }: { query: string; status: TriggerStatusFilter },
): SandboxTrigger[] {
  const needle = query.trim().toLowerCase();
  return triggers.filter(
    (item) =>
      (status === "all" || item.enabled === (status === "on")) &&
      (!needle ||
        triggerDisplayName(item).toLowerCase().includes(needle) ||
        triggerEventLabel(item).toLowerCase().includes(needle)),
  );
}

/** The state as a dot and a word: a filled flow dot for On, a ring for Off. */
function TriggerStatusMark({ enabled }: { enabled: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 w-[2.75rem] items-center gap-1.5 text-sm whitespace-nowrap",
        enabled ? "text-flow-text" : "text-muted-foreground",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "inline-block size-2 shrink-0 rounded-full",
          enabled
            ? "bg-[var(--flow)]"
            : "shadow-[inset_0_0_0_1.5px_var(--ink-muted)]",
        )}
      />
      {triggerStatusWord(enabled)}
    </span>
  );
}

export function TriggerList({
  listRef,
  status,
  onStatusChange,
  triggers,
  selectedId,
  unsaved,
  incomplete,
  phone,
  canCreate,
  onOpen,
  onCreate,
}: {
  listRef: Ref<HTMLElement>;
  /** The quick filter; the studio owns it, so a link can set it back. */
  status: TriggerStatusFilter;
  onStatusChange: (status: TriggerStatusFilter) => void;
  triggers: readonly SandboxTrigger[];
  selectedId: string;
  /** Ids of triggers that Save will write (new or changed). */
  unsaved: ReadonlySet<string>;
  /** After Save refused: ids of changed triggers with an empty part (B1). */
  incomplete?: ReadonlySet<string> | undefined;
  phone: boolean;
  canCreate: boolean;
  onOpen: (id: string) => void;
  onCreate: () => void;
}) {
  const [query, setQuery] = useState("");
  const counts = triggerStatusCounts(triggers);
  const rows = filterTriggers(triggers, { query, status });
  return (
    <aside
      ref={listRef}
      aria-label="Trigger list"
      className="bg-card border-border flex min-w-0 flex-col overflow-clip rounded-xl border @min-[900px]/studio:h-full"
    >
      <div className="border-border flex min-h-14 items-center gap-2.5 border-b px-4 py-2">
        <h2
          data-slot="section-title"
          id="trigger-studio-title"
          className="font-semibold"
        >
          Triggers
        </h2>
        <span className="text-muted-foreground text-sm tabular-nums">
          {triggers.length}
        </span>
        <Button
          variant="ghost"
          className="ml-auto min-h-11"
          onClick={() => {
            // A new trigger is On and unnamed, so it shows whatever the
            // search and filter were.
            setQuery("");
            onStatusChange("all");
            onCreate();
          }}
          disabled={!canCreate}
        >
          <Plus aria-hidden="true" />
          New trigger
        </Button>
      </div>
      {/* Nothing to search or filter until a trigger exists (S27). */}
      {triggers.length ? (
        <div className="border-border flex flex-wrap items-center gap-2 border-b p-3">
          <div className="relative min-w-40 flex-1">
            <Search
              aria-hidden="true"
              className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
            />
            <Input
              type="search"
              aria-label="Search triggers"
              placeholder="Search triggers"
              className="min-h-11 pl-9"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <ToggleGroup
            aria-label="Status"
            variant="segmented"
            multiple={false}
            value={[status]}
            className="w-fit flex-nowrap [&>*]:shrink-0"
            onValueChange={(selection) => {
              const next = statusFilters.find(
                (filter) => filter.value === selection[0],
              );
              if (next) onStatusChange(next.value);
            }}
          >
            {statusFilters.map((filter) => (
              <ToggleGroupItem
                key={filter.value}
                value={filter.value}
                className="flex-none gap-1.5 px-2 text-sm whitespace-nowrap"
              >
                {filter.label}{" "}
                <span className="text-muted-foreground font-normal tabular-nums">
                  {counts[filter.value]}
                </span>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
      ) : null}
      <nav
        aria-label="Trigger list"
        className={cn(
          "min-h-0 @min-[900px]/studio:flex-1 @min-[900px]/studio:overflow-y-auto",
          !phone && "max-h-64 overflow-y-auto @min-[900px]/studio:max-h-none",
        )}
      >
        {rows.map((recordTrigger) => {
          const name = triggerDisplayName(recordTrigger);
          const event = triggerEventLabel(recordTrigger);
          // One badge per row (Incomplete is always also unsaved).
          const badge = incomplete?.has(recordTrigger.id)
            ? "Incomplete"
            : unsaved.has(recordTrigger.id)
              ? "Unsaved"
              : null;
          return (
            <Button
              key={recordTrigger.id}
              variant="ghost"
              data-trigger-row
              aria-current={
                recordTrigger.id === selectedId ? "true" : undefined
              }
              aria-label={[
                triggerStatusWord(recordTrigger.enabled),
                name,
                event,
                ...(badge ? [badge] : []),
              ].join(", ")}
              className={cn(
                // The row rule (Product Designer, PR1 gate R5): status
                // 2.75rem, the name the only part that clips (8rem floor),
                // the badge on a second line under the name, the event as
                // its icon. 40px rows from 1280px, 64px with a badge (DESIGN
                // "Access rows"); the bottom padding gives 1px to the bottom
                // border, so the border sits inside those heights. Hover and open tints come from the look's
                // ink, so both read in every look, light and dark; the open
                // row is the tint only (the One Selection Rule, S26).
                "border-border grid h-auto min-h-11 w-full min-w-0 grid-cols-[2.75rem_minmax(8rem,1fr)_auto] items-start justify-normal gap-2.5 rounded-none border-b px-3 py-3 pb-[calc(0.75rem-1px)] text-left font-normal whitespace-nowrap max-sm:min-h-13 max-sm:py-4 max-sm:pb-[calc(1rem-1px)] xl:min-h-10 xl:py-2.5 xl:pb-[calc(0.625rem-1px)]",
                "hover:bg-[color-mix(in_oklab,var(--ink)_6%,transparent)] aria-[current=true]:bg-[color-mix(in_oklab,var(--ink)_14%,transparent)]",
              )}
              onClick={() => onOpen(recordTrigger.id)}
            >
              <TriggerStatusMark enabled={recordTrigger.enabled} />
              <span className="flex min-w-0 flex-col gap-1">
                <span className="truncate font-medium" title={name}>
                  {name}
                </span>
                {/* Which triggers Save will write (the Build field-row
                    pattern), under the name at its full width. */}
                {badge ? (
                  <Badge variant="warning" className="self-start">
                    {badge}
                  </Badge>
                ) : null}
              </span>
              {/* The event is its icon at every width; the word is its
                  tooltip, the search match, and the accessible name. */}
              <span
                title={event}
                className="text-muted-foreground inline-flex h-5 items-center"
              >
                <TriggerEventIcon
                  kind={recordTrigger.trigger.kind}
                  className="shrink-0"
                />
                <span className="sr-only">{event}</span>
              </span>
            </Button>
          );
        })}
        {!triggers.length ? (
          <p className="text-muted-foreground p-4 text-sm">No triggers yet.</p>
        ) : !rows.length ? (
          <p className="text-muted-foreground p-4 text-sm">
            No triggers match.
          </p>
        ) : null}
      </nav>
    </aside>
  );
}
