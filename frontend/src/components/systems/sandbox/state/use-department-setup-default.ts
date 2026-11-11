"use client";

import { useQuery } from "@tanstack/react-query";

import { workspaceLifecycleQueryOptions } from "../../manage/adapters/workspace-api";
import type { DepartmentSetup } from "../domain/model";

/**
 * The saved Manage default for a new department's setup (BE-SD6, FIT-4,
 * SD-C20). It reads the workspace query that the Sandbox page already
 * observes (`workspaceLifecycleQueryOptions`), from the cache: this observer
 * never refetches on mount, so the entry, the template dialog, and Duplicate
 * add no request. Undefined while that read is loading, failed, or carries
 * no default; the department then gets no `setup` (missing means all on).
 */
export function useDepartmentSetupDefault(): DepartmentSetup | undefined {
  const { data } = useQuery({
    ...workspaceLifecycleQueryOptions(),
    refetchOnMount: false,
    select: (workspace) => workspace.department_setup_defaults,
  });
  return data;
}
