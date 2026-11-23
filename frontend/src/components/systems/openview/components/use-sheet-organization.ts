"use client";

import { useQuery } from "@tanstack/react-query";

import { useAdmittedWorkspaceScope } from "@/components/systems/shared/runtime/workspace-identity";

import { authMeOptions } from "../adapters/openview-queries";

/**
 * The organization the sheet belongs to, from the shell's identity read; never
 * a name left from another organization before a switch. The sheet's words
 * fall back to "this organization" while it is unknown.
 */
export function useSheetOrganizationName(): string {
  const admitted = useAdmittedWorkspaceScope()?.org_id ?? null;
  const identity = useQuery({ ...authMeOptions(), enabled: false });
  const current = identity.data?.currentOrganization;
  return current && (admitted === null || current.orgId === admitted)
    ? current.name
    : "this organization";
}
