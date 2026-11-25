import type { Page } from "@playwright/test";

// The edition API (spec docs/specs/editions.md) for http journeys.

const EDITIONS = [
  { edition: "desk", name: "Desk", monthly_usd: 0, yearly_usd: 0, seats: 2 },
  {
    edition: "office",
    name: "Office",
    monthly_usd: 39,
    yearly_usd: 390,
    seats: 25,
  },
  {
    edition: "headquarters",
    name: "Headquarters",
    monthly_usd: 89,
    yearly_usd: 890,
    seats: 100,
  },
];

const ALL_FEATURES = [
  "audit_viewer",
  "automations",
  "dashboards",
  "gantt",
  "opencomms",
  "reports",
];

export function deskLicense(values: Record<string, unknown> = {}) {
  return {
    edition: "desk",
    edition_name: "Desk",
    phase: "none",
    read_only: false,
    customer: null,
    starts: null,
    ends: null,
    grace_ends: null,
    warning_ends: null,
    features: [],
    limits: [
      { limit: "seats", allowed: 2, used: 2 },
      { limit: "guests", allowed: 0, used: 0 },
      { limit: "departments", allowed: 2, used: 1 },
      { limit: "modules", allowed: 3, used: 1 },
      { limit: "records", allowed: 1000, used: 12 },
      { limit: "sheets", allowed: 10, used: 0 },
      { limit: "sheet_rows", allowed: 1000, used: 0 },
    ],
    editions: EDITIONS,
    can_import: true,
    ...values,
  };
}

export function officeLicense(values: Record<string, unknown> = {}) {
  return deskLicense({
    edition: "office",
    edition_name: "Office",
    phase: "active",
    customer: "Acme Ltd",
    starts: "2026-01-01",
    ends: "2026-12-31",
    grace_ends: "2027-01-14",
    warning_ends: "2027-02-13",
    features: ALL_FEATURES,
    limits: [
      { limit: "seats", allowed: 25, used: 2 },
      { limit: "guests", allowed: 50, used: 0 },
      { limit: "departments", allowed: null, used: null },
      { limit: "modules", allowed: null, used: null },
      { limit: "records", allowed: null, used: null },
      { limit: "sheets", allowed: null, used: null },
      { limit: "sheet_rows", allowed: null, used: null },
    ],
    ...values,
  });
}

/** No license file in a development or test installation: every feature, no limits. */
export function developmentLicense() {
  return officeLicense({
    edition: "development",
    edition_name: "Development",
    phase: "none",
    customer: null,
    starts: null,
    ends: null,
    grace_ends: null,
    warning_ends: null,
    limits: [
      "seats",
      "guests",
      "departments",
      "modules",
      "records",
      "sheets",
      "sheet_rows",
    ].map((limit) => ({ limit, allowed: null, used: null })),
    can_import: false,
  });
}

/** Serve GET /api/license from `state.status`; a PUT stores `state.imported`. */
export async function mockLicense(
  page: Page,
  initial: Record<string, unknown> = deskLicense(),
) {
  const state = {
    status: initial,
    imported: officeLicense() as Record<string, unknown>,
    imports: [] as string[],
    importFailure: null as { code: string; message: string } | null,
  };
  await page.route("**/api/license", async (route) => {
    const request = route.request();
    if (request.method() === "PUT") {
      const body = request.postDataJSON() as { text: string };
      state.imports.push(body.text);
      if (state.importFailure) {
        await route.fulfill({
          status: 422,
          json: { detail: state.importFailure },
        });
        return;
      }
      state.status = state.imported;
      await route.fulfill({ json: state.status });
      return;
    }
    await route.fulfill({ json: state.status });
  });
  return state;
}
