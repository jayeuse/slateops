import type {
  EditionLimit,
  LicenseStatus,
} from "../../shared/adapters/license-api";

// The words of the Edition and license section (spec editions.md ED-10).

const LIMIT_LABELS: Record<EditionLimit, string> = {
  seats: "People (administrators and members)",
  guests: "Guests",
  departments: "Published departments",
  modules: "Modules in a department",
  records: "Records in a module",
  sheets: "Sheets",
  sheet_rows: "Rows in a sheet",
};

const NUMBER = new Intl.NumberFormat("en-US");

export type LimitRow = {
  limit: EditionLimit;
  label: string;
  used: string;
  allowed: string;
  /** At or above the limit. */
  full: boolean;
};

export function limitRows(status: LicenseStatus): LimitRow[] {
  return status.limits.map((item) => ({
    limit: item.limit,
    label: LIMIT_LABELS[item.limit],
    used: item.used === null ? "—" : NUMBER.format(item.used),
    allowed: item.allowed === null ? "No limit" : NUMBER.format(item.allowed),
    full:
      item.allowed !== null && item.used !== null && item.used >= item.allowed,
  }));
}

function day(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));
}

export function licenseStateWords(status: LicenseStatus): string {
  switch (status.phase) {
    case "none":
      return status.edition === "development"
        ? "No license file · development installation, no limits"
        : "No license file · Desk is free";
    case "active":
      return status.ends ? `Active until ${day(status.ends)}` : "Active";
    case "grace":
      return `Ended ${day(status.ends!)} · renew by ${day(status.grace_ends!)}`;
    case "warning":
      return `Ended ${day(status.ends!)} · becomes Desk on ${day(status.warning_ends!)}`;
    case "ended":
      return status.read_only
        ? `Ended ${day(status.ends!)} · read-only until you import a new license file`
        : `Ended ${day(status.ends!)} · running as Desk`;
  }
}

export function editionPriceWords(
  edition: LicenseStatus["editions"][number],
): string {
  const seats = edition.seats === null ? "" : ` · ${edition.seats} people`;
  if (edition.monthly_usd === 0) return `Free${seats}`;
  return `$${edition.monthly_usd} a month or $${edition.yearly_usd} a year${seats}`;
}

/** The fullest limit at or above `share` of its allowance, for the banner. */
export function nearestLimit(
  status: LicenseStatus,
  share = 0.8,
): LimitRow | null {
  const rows = limitRows(status);
  let found: { row: LimitRow; ratio: number } | null = null;
  status.limits.forEach((item, index) => {
    if (item.allowed === null || item.used === null || item.allowed === 0)
      return;
    const ratio = item.used / item.allowed;
    if (ratio >= share && (!found || ratio > found.ratio))
      found = { row: rows[index]!, ratio };
  });
  return (found as { row: LimitRow } | null)?.row ?? null;
}
