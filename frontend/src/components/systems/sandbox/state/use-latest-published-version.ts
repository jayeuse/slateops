"use client";

import { queryOptions, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import type { SandboxDocumentV4 } from "../domain/document";
import type { FieldTypeName } from "../domain/model";
import { getSandboxVersion } from "./api";
import { sandboxKeys } from "./sandbox-queries";

/** The published type of the field with this (module id, field id) pair. */
export type PublishedFieldType = (
  moduleId: string,
  fieldId: string,
) => FieldTypeName | null;

/**
 * A field's published identity is the pair (module id, field id)
 * (`publications/rules.py`, `_field_key`), never the field id alone.
 */
export function publishedFieldTypes(
  document: SandboxDocumentV4,
): PublishedFieldType {
  const modules = new Map(
    document.design.modules.map((item) => [
      item.id,
      new Map(item.fields.map((field) => [field.id, field.type])),
    ]),
  );
  return (moduleId, fieldId) => modules.get(moduleId)?.get(fieldId) ?? null;
}

/**
 * The latest published version, read with `getSandboxVersion` (which records
 * its outcome in History's access tracker, as every version read does).
 */
export function latestPublishedVersionOptions(versionId: string) {
  return queryOptions({
    queryKey: sandboxKeys.publishedVersion(versionId),
    queryFn: ({ signal }) => getSandboxVersion(versionId, { signal }),
    // A published version never changes: read it once per id (a newer
    // version is a new key). Build remounts on every selection, so the 30 s
    // default would read it again. Collection stays the client's default, so
    // an older version that nothing shows leaves memory.
    staleTime: Infinity,
  });
}

/**
 * Field types of the latest published version, or null while there is none,
 * while it loads, or when its read failed (the publish blocker decides).
 */
export function useLatestPublishedVersion(
  versionId: string | null,
): PublishedFieldType | null {
  const query = useQuery({
    ...latestPublishedVersionOptions(versionId ?? ""),
    enabled: versionId !== null,
  });
  const document = versionId === null ? undefined : query.data?.document;
  // One lookup per read document, not per render (query-cache-patterns 7).
  return useMemo(
    () => (document ? publishedFieldTypes(document) : null),
    [document],
  );
}
