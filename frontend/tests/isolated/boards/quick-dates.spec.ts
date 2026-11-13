import { expect, test } from "@playwright/test";

import { quickDates } from "../../../src/components/systems/boards/helpers/quick-dates";

// The quick dates under a Kanban card's date input (SI-8.3, DR-SI-8.3): they
// count from the workspace's today, the date the calendar's Today shows.
// "Next Monday" is the first Monday after today, so on a Monday it is 7 days
// later. The http journeys in tests/http/boards-card-quick-actions.spec.ts
// press them on a card.

test("SI-C8.2 on a Monday, Next Monday is 7 days later", () => {
  // 2026-11-16 is a Monday.
  expect(quickDates("2026-11-16")).toEqual([
    { label: "Today", date: "2026-11-16" },
    { label: "Tomorrow", date: "2026-11-17" },
    { label: "Next Monday", date: "2026-11-23" },
  ]);
});

test("SI-C8.2 on the other days, Next Monday is the first Monday after today, across a month and a year end", () => {
  // Each row: today, then its tomorrow and its Next Monday.
  const rows: [string, string, string][] = [
    ["2026-11-15", "2026-11-16", "2026-11-16"], // Sunday: the next day
    ["2026-11-17", "2026-11-18", "2026-11-23"], // Tuesday
    ["2026-11-21", "2026-11-22", "2026-11-23"], // Saturday
    ["2026-09-30", "2026-10-01", "2026-10-05"], // Wednesday, month end
    ["2026-12-31", "2027-01-01", "2027-01-04"], // Thursday, year end
  ];
  for (const [today, tomorrow, monday] of rows)
    expect(quickDates(today), today).toEqual([
      { label: "Today", date: today },
      { label: "Tomorrow", date: tomorrow },
      { label: "Next Monday", date: monday },
    ]);
});
