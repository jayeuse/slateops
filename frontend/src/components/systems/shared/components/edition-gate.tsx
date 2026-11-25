"use client";

import { lazy, Suspense, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  licenseQueryOptions,
  type EditionFeature,
} from "../adapters/license-api";

// The preview loads only on Desk, so a cold load of an Office feature ships none of it.
const EditionPreview = lazy(() =>
  import("./edition-preview").then((module) => ({
    default: module.EditionPreview,
  })),
);

/**
 * Render `children` only when the edition has `feature`; otherwise the
 * "Available in Office" preview (spec editions.md ED-11). Nothing renders until
 * the edition is known, so a Desk installation never starts the feature's
 * requests. An unreadable edition shows the feature (the API still refuses it
 * on Desk).
 */
export function EditionGate({
  feature,
  children,
  className,
}: {
  feature: EditionFeature;
  children: ReactNode;
  className?: string;
}) {
  const license = useQuery(licenseQueryOptions());
  if (license.isPending) return null;
  if (license.data && !license.data.features.includes(feature)) {
    return (
      <Suspense fallback={null}>
        <EditionPreview feature={feature} className={className} />
      </Suspense>
    );
  }
  return children;
}
