"use client";

import type { Route } from "next";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { departmentNavigationOptions } from "@/components/department-navigation";
import {
  departmentNavigation,
  isRefusal,
  moduleLocation,
} from "@/components/department-navigation-model";
import { GuardedWorkspaceLink } from "@/components/workspace-navigation-guard";
import { cn } from "@/lib/utils";

import { catalogFirstPageOptions } from "../adapters/openview-queries";
import { worksheetPlaceOptions } from "../adapters/worksheet-queries";

// Department › module › record › sheet (docs/specs/sheets.md Screens 3); a
// module sheet has no record crumb. The names come from the caches that the
// sidebar and the sheet page fill, so the header adds no read. The shell
// loads this only on a sheet's address. Below 768px only the way back stays:
// the record crumb, or the module's for a module sheet.

const crumbTarget = "inline-flex min-h-6 items-center";

export default function SheetCrumbs({ sheetId }: { sheetId: string }) {
  const place = useQuery({
    ...worksheetPlaceOptions(sheetId, undefined),
    enabled: false,
  }).data;
  const departments = useQuery({
    ...departmentNavigationOptions(),
    enabled: false,
  });
  const modules = useQuery({ ...catalogFirstPageOptions(), enabled: false });
  const readable =
    departments.data &&
    modules.data &&
    !isRefusal(departments.error) &&
    !isRefusal(modules.error)
      ? departmentNavigation(departments.data.items, modules.data.items)
      : null;
  const department =
    place && readable
      ? moduleLocation(readable, place.moduleId)?.department
      : undefined;
  const moduleHref = place
    ? `/openview?section=views&module=${encodeURIComponent(place.moduleId)}`
    : null;
  return (
    <Breadcrumb className="min-w-0">
      <BreadcrumbList className="flex-nowrap">
        {department ? (
          <>
            <BreadcrumbItem className="shrink-0 max-sm:hidden">
              {department.name}
            </BreadcrumbItem>
            <BreadcrumbSeparator className="max-sm:hidden" />
          </>
        ) : null}
        {place && moduleHref ? (
          <>
            <BreadcrumbItem
              className={
                place.recordId ? "shrink-0 max-md:hidden" : "min-w-0 shrink"
              }
            >
              <BreadcrumbLink
                className={`${crumbTarget} gap-1 truncate`}
                render={<GuardedWorkspaceLink href={moduleHref as Route} />}
              >
                {place.recordId ? null : (
                  <ArrowLeft aria-hidden="true" className="size-4 md:hidden" />
                )}
                {place.moduleName}
              </BreadcrumbLink>
            </BreadcrumbItem>
            <BreadcrumbSeparator className="max-md:hidden" />
            {place.recordId && place.recordTitle ? (
              <>
                <BreadcrumbItem className="min-w-0 shrink">
                  <BreadcrumbLink
                    className={`${crumbTarget} gap-1 truncate`}
                    render={
                      <GuardedWorkspaceLink
                        href={
                          `${moduleHref}&record=${encodeURIComponent(place.recordId)}` as Route
                        }
                      />
                    }
                  >
                    <ArrowLeft
                      aria-hidden="true"
                      className="size-4 md:hidden"
                    />
                    {place.recordTitle}
                  </BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator className="max-md:hidden" />
              </>
            ) : null}
          </>
        ) : null}
        <BreadcrumbItem className={cn("min-w-0", place && "max-md:hidden")}>
          <BreadcrumbPage className="block min-h-6 truncate leading-6">
            {place?.sheetTitle ?? "Sheet"}
          </BreadcrumbPage>
        </BreadcrumbItem>
      </BreadcrumbList>
    </Breadcrumb>
  );
}
