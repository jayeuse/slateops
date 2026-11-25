"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Lock } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import {
  LICENSING_PAGE,
  licenseQueryOptions,
  useLicense,
  type EditionFeature,
} from "../adapters/license-api";

const FEATURE_WORDS: Record<EditionFeature, { name: string; does: string }> = {
  opencomms: {
    name: "OpenComms",
    does: "Channels, direct messages and threads for your whole organization.",
  },
  dashboards: {
    name: "Dashboards",
    does: "Charts of your records on one page that stays current.",
  },
  reports: {
    name: "Reports",
    does: "Record summaries that run on a schedule and arrive by notification.",
  },
  automations: {
    name: "Automations",
    does: "Rules that change records when something happens or on a schedule.",
  },
  gantt: {
    name: "Gantt view",
    does: "Cards on a timeline by their start and due dates.",
  },
  audit_viewer: {
    name: "Audit viewer",
    does: "Search and export every change in the organization.",
  },
};

/**
 * What a Desk installation shows in place of an Office feature (spec
 * editions.md ED-11): the feature, what it does, and the way to get it.
 */
export function EditionPreview({
  feature,
  className,
}: {
  feature: EditionFeature;
  className?: string;
}) {
  const license = useLicense();
  const words = FEATURE_WORDS[feature];
  return (
    <Empty className={className}>
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <Lock aria-hidden="true" />
        </EmptyMedia>
        <EmptyTitle role="heading" aria-level={2}>
          {words.name}: available in Office
        </EmptyTitle>
        <EmptyDescription>
          {words.does} Your installation runs the{" "}
          {license?.edition_name ?? "Desk"} edition.
        </EmptyDescription>
      </EmptyHeader>
      <EmptyContent>
        {license?.can_import ? (
          <Button asChild>
            <Link href={LICENSING_PAGE}>See editions and prices</Link>
          </Button>
        ) : (
          <p className="text-muted-foreground text-sm">
            {license?.limits.some((item) => item.used !== null)
              ? "Ask the installation owner to upgrade to Office."
              : "Ask your administrator to upgrade to Office."}
          </p>
        )}
      </EmptyContent>
    </Empty>
  );
}

/**
 * Render `children` only when the edition has `feature`; otherwise the
 * preview. Nothing renders until the edition is known, so a Desk installation
 * never starts the feature's requests. An unreadable edition shows the
 * feature (the API still refuses it on Desk).
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
    return <EditionPreview feature={feature} className={className} />;
  }
  return children;
}
