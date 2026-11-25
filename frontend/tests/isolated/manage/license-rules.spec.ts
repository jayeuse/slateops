import { expect, test } from "@playwright/test";

import type { LicenseStatus } from "../../../src/components/systems/shared/adapters/license-api";
import {
  editionPriceWords,
  licenseStateWords,
  limitRows,
  nearestLimit,
} from "../../../src/components/systems/manage/domain/license-rules";
import { deskLicense, officeLicense } from "../../http/helpers/license";

// The words of the Edition and license section and the banner's limit
// (spec docs/specs/editions.md ED-10, ED-12).

const desk = (values: Record<string, unknown> = {}) =>
  deskLicense(values) as LicenseStatus;

test("each limit shows its use, its allowance or no limit, and whether it is full", () => {
  const rows = limitRows(officeLicense() as LicenseStatus);
  expect(rows.slice(0, 3)).toEqual([
    {
      limit: "seats",
      label: "People (administrators and members)",
      used: "2",
      allowed: "25",
      full: false,
    },
    { limit: "guests", label: "Guests", used: "0", allowed: "50", full: false },
    {
      limit: "departments",
      label: "Published departments",
      used: "—",
      allowed: "No limit",
      full: false,
    },
  ]);
  expect(limitRows(desk())[0]!.full).toBe(true); // 2 of 2 people
});

test("the license state names the next date for each phase", () => {
  const dates = {
    ends: "2026-12-31",
    grace_ends: "2027-01-14",
    warning_ends: "2027-02-13",
  };
  expect(licenseStateWords(desk())).toBe("No license file · Desk is free");
  expect(
    licenseStateWords(
      desk({ edition: "development", edition_name: "Development" }),
    ),
  ).toBe("No license file · development installation, no limits");
  expect(licenseStateWords(desk({ ...dates, phase: "active" }))).toBe(
    "Active until Dec 31, 2026",
  );
  expect(licenseStateWords(desk({ ...dates, phase: "grace" }))).toBe(
    "Ended Dec 31, 2026 · renew by Jan 14, 2027",
  );
  expect(licenseStateWords(desk({ ...dates, phase: "warning" }))).toBe(
    "Ended Dec 31, 2026 · becomes Desk on Feb 13, 2027",
  );
  expect(
    licenseStateWords(desk({ ...dates, phase: "ended", read_only: true })),
  ).toBe("Ended Dec 31, 2026 · read-only until you import a new license file");
});

test("prices show free or both periods with the people of each edition", () => {
  const [free, office] = desk().editions;
  expect(editionPriceWords(free!)).toBe("Free · 2 people");
  expect(editionPriceWords(office!)).toBe(
    "$39 a month or $390 a year · 25 people",
  );
});

test("the banner names the fullest limit at 80% or more, and nothing below", () => {
  expect(nearestLimit(desk())?.label).toBe(
    "People (administrators and members)",
  );
  const quiet = desk({
    limits: [
      { limit: "seats", allowed: 2, used: 1 },
      { limit: "records", allowed: 1000, used: 799 },
    ],
  });
  expect(nearestLimit(quiet)).toBeNull();
  const records = desk({
    limits: [
      { limit: "seats", allowed: 2, used: 1 },
      { limit: "records", allowed: 1000, used: 800 },
    ],
  });
  expect(nearestLimit(records)?.label).toBe("Records in a module");
});
