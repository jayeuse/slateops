"use client";

import Link from "next/link";
import type { Route } from "next";

import {
  linkTabsIndicatorClass as indicator,
  linkTabsListClass as list,
  linkTabsTriggerClass as trigger,
} from "@/components/ui/link-tabs";

/**
 * The module page's views, Records, Reports (DC1) and its module sheets
 * (docs/specs/sheets.md P2), with their counts. They are links: each view
 * has its own address. On a phone they sit under the title (DC12).
 */
export function ModulePageSwitch({
  moduleName,
  view,
  recordsHref,
  reportsHref,
  sheetsHref,
  recordCount,
  reportCount,
  sheetCount,
}: {
  moduleName: string;
  view: "records" | "reports" | "sheets";
  recordsHref: string;
  reportsHref: string;
  sheetsHref: string;
  recordCount: number | null;
  reportCount: number | null;
  sheetCount: number | null;
}) {
  const count = (value: number | null) =>
    value === null ? null : (
      <span className="text-muted-foreground font-normal tabular-nums">
        {value}
      </span>
    );
  const tab = (
    label: string,
    href: string,
    value: number | null,
    current: boolean,
  ) => (
    <Link
      href={href as Route}
      scroll={false}
      aria-current={current ? "page" : undefined}
      data-slot="tabs-trigger"
      data-active={current ? "" : undefined}
      className={trigger}
    >
      {current ? (
        <span
          aria-hidden="true"
          data-slot="tabs-indicator"
          className={indicator}
        />
      ) : null}
      {label} {count(value)}
    </Link>
  );
  return (
    <nav
      aria-label={`${moduleName} page`}
      data-slot="tabs-list"
      className={list}
    >
      {tab("Records", recordsHref, recordCount, view === "records")}
      {tab("Reports", reportsHref, reportCount, view === "reports")}
      {/* A sheet count of 0 shows no number, as the record's Sheets tab. */}
      {tab("Sheets", sheetsHref, sheetCount || null, view === "sheets")}
    </nav>
  );
}
