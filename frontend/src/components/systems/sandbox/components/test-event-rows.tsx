"use client";

import { useId, type ReactNode } from "react";
import { CalendarClock, Flag, PenLine, Play, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DisabledReason } from "@/components/ui/disabled-reason";
import { cn } from "@/lib/utils";
import type { ReadingBlock, ReadingTrigger } from "../domain/test-reading";

// One event block of the Test reading (docs/specs/sandbox-ux-redesign.md
// TEST-1, TEST-9, E1, E7, E10): the event, each trigger that listens with
// its conditions in words and the fields it sets, a quiet "Try it" for the
// event, and "Try this trigger" on each trigger that is on. The result of a
// run shows under its block.

const eventIcons = {
  "record-created": Plus,
  "field-changed": PenLine,
  "threshold-crossed": Flag,
  schedule: CalendarClock,
} as const;

function TriggerRow({
  item,
  disabledReason,
  busy,
  running,
  onTry,
}: {
  item: ReadingTrigger;
  disabledReason: string | null;
  busy: boolean;
  running: boolean;
  onTry: () => void;
}) {
  return (
    <li className="grid min-w-0 gap-x-3 gap-y-1 py-1.5 text-sm sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center">
      <p
        className={cn(
          "min-w-0 [overflow-wrap:anywhere]",
          !item.enabled && "text-muted-foreground",
        )}
      >
        <span className="font-medium">{item.name}</span>
        <span className="text-muted-foreground">
          {" · "}
          {item.enabled ? item.conditions : "Off"}
        </span>
        {item.attention ? (
          <span className="text-warn-text block text-xs">{item.attention}</span>
        ) : null}
      </p>
      <p className="text-muted-foreground text-xs sm:text-right">
        {item.sets.length ? (
          <>
            sets{" "}
            <span className="text-foreground font-medium">
              {item.sets.join(", ")}
            </span>
          </>
        ) : null}
      </p>
      {item.enabled ? (
        <DisabledReason reason={disabledReason}>
          <Button
            variant="ghost"
            size="sm"
            className="text-primary min-h-11 justify-self-start xl:min-h-8"
            disabled={busy && !running}
            pending={running}
            pendingLabel="Running…"
            onClick={onTry}
          >
            Try this trigger
          </Button>
        </DisabledReason>
      ) : (
        <span aria-hidden className="hidden sm:block" />
      )}
    </li>
  );
}

export function TestEventBlock({
  block,
  disabledReason,
  busy,
  runningKey,
  onTry,
  onTryTrigger,
  children,
}: {
  block: ReadingBlock;
  /** Why no run can start now; null when one can. */
  disabledReason: string | null;
  /** Another run or a clear is in flight. */
  busy: boolean;
  /** "event" or a trigger id while that run is in flight. */
  runningKey: string | null;
  onTry: () => void;
  onTryTrigger: (triggerId: string) => void;
  /** The result card of the last run of this block. */
  children?: ReactNode;
}) {
  const Icon = eventIcons[block.event.kind];
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      className="border-border grid min-w-0 gap-2 border-b py-4 last:border-b-0"
    >
      <div className="flex min-w-0 items-center gap-3">
        <span className="border-border text-muted-foreground grid size-7 shrink-0 place-items-center rounded-md border">
          <Icon aria-hidden className="size-3.5" />
        </span>
        <h4
          id={headingId}
          className="min-w-0 flex-1 font-semibold [overflow-wrap:anywhere]"
        >
          {block.title}
        </h4>
        {block.triggers.length ? (
          <DisabledReason reason={disabledReason}>
            <Button
              variant="ghost"
              size="sm"
              className="min-h-11 xl:min-h-8"
              aria-label={`Try it: ${block.title}`}
              disabled={busy && runningKey !== "event"}
              pending={runningKey === "event"}
              pendingLabel="Running…"
              onClick={onTry}
            >
              <Play aria-hidden />
              Try it
            </Button>
          </DisabledReason>
        ) : null}
      </div>
      <div className="min-w-0 sm:pl-10">
        {block.triggers.length ? (
          <ul className="grid">
            {block.triggers.map((item) => (
              <TriggerRow
                key={item.id}
                item={item}
                disabledReason={disabledReason}
                busy={busy}
                running={runningKey === item.id}
                onTry={() => onTryTrigger(item.id)}
              />
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground text-sm">No trigger listens.</p>
        )}
      </div>
      {children ? <div className="min-w-0 sm:pl-10">{children}</div> : null}
    </section>
  );
}
