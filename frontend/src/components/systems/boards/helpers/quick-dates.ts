import { addDays, weekday } from "../domain/calendar-dates";

export type QuickDate = {
  label: "Today" | "Tomorrow" | "Next Monday";
  date: string;
};

/**
 * The quick dates under a Kanban card's date input (DR-SI-8.3), counted from
 * the workspace's today: the date the calendar's Today shows. "Next Monday"
 * is the first Monday after today, so on a Monday it is 7 days later.
 */
export function quickDates(today: string): QuickDate[] {
  const toMonday = (8 - weekday(today)) % 7 || 7;
  return [
    { label: "Today", date: today },
    { label: "Tomorrow", date: addDays(today, 1) },
    { label: "Next Monday", date: addDays(today, toMonday) },
  ];
}
