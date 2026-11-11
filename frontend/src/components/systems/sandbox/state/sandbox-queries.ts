import { queryOptions } from "@tanstack/react-query";
import { listSandboxVersions, type SandboxVersionListOptions } from "./api";
import { getSandboxBindings } from "./lifecycle-api";

export const sandboxKeys = {
  versionPage: (
    options: Omit<SandboxVersionListOptions, "signal">,
    refreshKey: number,
  ) => ["sandbox", "versions", options, refreshKey] as const,
  version: (id: string, refreshKey: number) =>
    ["sandbox", "version", id, refreshKey] as const,
  /** Build's read of the latest published version (FAST-5); outside
   * History's `["sandbox", "version"]` prefix. */
  publishedVersion: (id: string) =>
    ["sandbox", "published-version", id] as const,
  bindings: ["sandbox", "bindings"] as const,
  bindingsRevision: (revision: number) =>
    ["sandbox", "bindings", revision] as const,
};

export function sandboxBindingsOptions(revision: number) {
  return queryOptions({
    queryKey: sandboxKeys.bindingsRevision(revision),
    queryFn: ({ signal }) => getSandboxBindings(signal),
    enabled: revision > 0,
  });
}

export function sandboxVersionPageOptions(
  options: Omit<SandboxVersionListOptions, "signal">,
  refreshKey: number,
) {
  return queryOptions({
    queryKey: sandboxKeys.versionPage(options, refreshKey),
    queryFn: ({ signal }) => listSandboxVersions({ ...options, signal }),
    retry: false,
  });
}
