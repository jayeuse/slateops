"use client";

import { EditionGate } from "../../shared/components/edition-gate";
import { lazy, Suspense } from "react";
import Link from "next/link";
import { Alert } from "@/components/ui/alert";
import { usePathname, useSearchParams } from "next/navigation";
import { usePageFileDropGuard } from "@/lib/file-drop";
import { parseOpenViewUrl } from "../domain/model";
import { OpenViewQuerySync } from "./openview-query-sync";
import { OpenViewLoading } from "./openview-skeletons";
import ServerBackedDashboards from "./server-backed-dashboards";
import { MySheets } from "./my-sheets";
import { ReportLinkRedirect } from "./report-link-redirect";
import ServerBackedViewsWorkspace, {
  OpenViewHeader,
} from "./server-backed-views-workspace";

const SheetPage = lazy(() => import("./sheet-page"));

function OpenViewRouteContent() {
  const pathname = usePathname();
  const query = useSearchParams();
  const urlState = parseOpenViewUrl(`${pathname}?${query.toString()}`);
  const isLegacySampleRecordLink = Boolean(
    urlState.section === "views" && urlState.record?.startsWith("sample-"),
  );
  // A sheet's own address (P6): its page is its own chunk.
  const sheetAddress = query.get("sheet") !== null;
  const section =
    isLegacySampleRecordLink || sheetAddress ? null : urlState.section;
  // On the module page a file dropped beside the record Files tab opens
  // nothing (DR-SI-7.4).
  usePageFileDropGuard(section === "views");
  let content;
  if (sheetAddress)
    content = (
      <Suspense fallback={<OpenViewLoading />}>
        <SheetPage sheetId={query.get("sheet") ?? ""} />
      </Suspense>
    );
  else if (section === "views")
    content = (
      <ServerBackedViewsWorkspace invalidUrl={Boolean(urlState.invalid)} />
    );
  // The Charts page is gone (BD10): its links open a department dashboard
  // with the builder's saved-chart list.
  else if (section === "dashboards" || section === "charts")
    content = (
      <EditionGate feature="dashboards">
        <ServerBackedDashboards />
      </EditionGate>
    );
  // My sheets reads its own list, with no records.read and no stream (P4).
  else if (section === "sheets") content = <MySheets />;
  // The Reports page is gone (DC8, DC9): its links open a module page's
  // Reports view.
  else if (section === "reports")
    content = (
      <ReportLinkRedirect reportId={urlState.report} runId={urlState.run} />
    );
  else
    content = (
      <div className="flex min-w-0 flex-col gap-5">
        <OpenViewHeader />
        <Alert className="flex flex-wrap items-center justify-between gap-3">
          <p>This example record is not in OpenView</p>
          <Link
            href="/openview?section=views"
            className="text-action-text inline-flex min-h-11 items-center font-medium underline underline-offset-4"
          >
            Views
          </Link>
        </Alert>
      </div>
    );
  // The sync keeps its place ahead of the section, so it stays mounted while
  // the section changes. It holds the shared stream only for the sections
  // that read through the cache; Dashboards, the old Reports link and
  // example notices open none.
  return (
    <>
      <OpenViewQuerySync active={section === "views"} />
      {content}
    </>
  );
}

export default function OpenViewRoute() {
  return (
    <Suspense fallback={<OpenViewLoading />}>
      <OpenViewRouteContent />
    </Suspense>
  );
}
