"use client";

import { queryOptions, useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { apiFetch } from "@/lib/api";
import { currentOrganizationId } from "@/lib/organization-context";

// The edition in effect and the license file import (spec docs/specs/editions.md).

const featureSchema = z.enum([
  "opencomms",
  "dashboards",
  "reports",
  "automations",
  "gantt",
  "audit_viewer",
]);
const limitSchema = z.enum([
  "seats",
  "guests",
  "departments",
  "modules",
  "records",
  "sheets",
  "sheet_rows",
]);
const editionSchema = z.enum(["desk", "office", "headquarters", "development"]);
const dateSchema = z.iso.date();

export const licenseStatusSchema = z
  .object({
    edition: editionSchema,
    edition_name: z.string(),
    phase: z.enum(["none", "active", "grace", "warning", "ended"]),
    read_only: z.boolean(),
    customer: z.string().nullable(),
    starts: dateSchema.nullable(),
    ends: dateSchema.nullable(),
    grace_ends: dateSchema.nullable(),
    warning_ends: dateSchema.nullable(),
    features: z.array(featureSchema),
    limits: z.array(
      z
        .object({
          limit: limitSchema,
          allowed: z.number().int().nullable(),
          used: z.number().int().nullable(),
        })
        .strict(),
    ),
    editions: z.array(
      z
        .object({
          edition: editionSchema,
          name: z.string(),
          monthly_usd: z.number().int(),
          yearly_usd: z.number().int(),
          seats: z.number().int().nullable(),
        })
        .strict(),
    ),
    can_import: z.boolean(),
  })
  .strict();

export type LicenseStatus = z.output<typeof licenseStatusSchema>;
export type EditionFeature = z.output<typeof featureSchema>;
export type EditionLimit = z.output<typeof limitSchema>;

/** Where the upgrade button and every "Available in Office" link go. */
export const LICENSING_PAGE = "/manage?view=updates";

export const licenseKeys = {
  status: (organizationId: string | null) =>
    ["license", "status", organizationId] as const,
};

export function licenseQueryOptions() {
  const organizationId = currentOrganizationId();
  return queryOptions({
    queryKey: licenseKeys.status(organizationId),
    queryFn: ({ signal }) =>
      apiFetch("/license", licenseStatusSchema, { cache: "no-store", signal }),
  });
}

export function importLicense(text: string): Promise<LicenseStatus> {
  return apiFetch("/license", licenseStatusSchema, {
    method: "PUT",
    body: JSON.stringify({ text }),
  });
}

/** The edition in effect; undefined while loading or when it could not be read. */
export function useLicense(): LicenseStatus | undefined {
  return useQuery(licenseQueryOptions()).data;
}

/**
 * False only when the edition is known and lacks the feature. While the
 * edition is loading or unreadable the feature stays visible; the API still
 * refuses it on Desk (403 `edition_required`).
 */
export function useHasFeature(feature: EditionFeature): boolean {
  const license = useLicense();
  return license === undefined || license.features.includes(feature);
}

export { isEditionRefusal } from "@/lib/api-errors";
