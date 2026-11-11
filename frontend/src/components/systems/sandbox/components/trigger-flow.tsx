// The words and marks of a trigger: the event word and its icon, and the
// operator and weekday choices. The list pane, the rail, and the
// whole-trigger sentence read them from here.

import { CalendarClock, Flag, PencilLine, Plus } from "lucide-react";
import type { SandboxTrigger } from "../domain/document";

/** The words of each comparison, as the pickers and the sentence say it. */
export const operatorWords = {
  "=": "is",
  "!=": "is not",
  ">": "is more than",
  ">=": "is at least",
  "<": "is less than",
  "<=": "is at most",
} as const;
const weekdays = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];
/** The weekday choices for a weekly schedule; stored values are 1 to 7. */
export const weekdayOptions = weekdays.map((name, index) => ({
  value: String(index + 1),
  label: name,
}));

/** A trigger's state, the same word in its list row and its Status row. */
export function triggerStatusWord(enabled: boolean): "On" | "Off" {
  return enabled ? "On" : "Off";
}
export function triggerEventLabel(recordTrigger: SandboxTrigger): string {
  return {
    "record-created": "Item added",
    "field-changed": "Field changed",
    "threshold-crossed": "Threshold crossed",
    schedule: "Schedule",
  }[recordTrigger.trigger.kind];
}
/** The mark of a trigger's event, beside its word in the list and the rail. */
export function TriggerEventIcon({
  kind,
  className,
}: {
  kind: SandboxTrigger["trigger"]["kind"];
  className?: string;
}) {
  const Icon = {
    "record-created": Plus,
    "field-changed": PencilLine,
    "threshold-crossed": Flag,
    schedule: CalendarClock,
  }[kind];
  return <Icon aria-hidden="true" className={className} />;
}
