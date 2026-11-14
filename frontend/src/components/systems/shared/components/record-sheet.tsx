"use client";
import {
  formatOpenViewFieldValue,
  RecordPersonCard,
} from "@/components/systems/openview/components/live-record-cards";

import { useId, useState, type ReactNode } from "react";
import type { OpenViewGroupSelector } from "@/components/systems/openview/adapters/analytics-api";
import type {
  OpenViewDataSourceField,
  OpenViewQueryDefinition,
  OpenViewQueryFieldType,
  OpenViewRecord,
} from "@/components/systems/openview/adapters/views-api";
import type { OpenViewDataSource } from "@/components/systems/openview/adapters/views-api";
import { openViewRecordFieldValue } from "@/components/systems/openview/domain/record-display";
import { RecordDetailsControls } from "@/components/systems/openview/components/record-details-controls";
import type { RecordInPlaceStatus } from "@/components/systems/openview/domain/record-inplace-change";
import { RecordHistoryPanel } from "@/components/systems/openview/components/record-history-panel";
import { formatWorkspaceDate, type WorkspaceRegion } from "@/lib/date-time";
import { RecordFilesPanel } from "@/components/systems/openview/components/record-files-panel";
import { RecordLinksPanel } from "@/components/systems/openview/components/record-links-panel";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";

export type RecordInspectionPageSource = {
  kind: "records";
  /** The originating page size; legacy fixed-size callers fall back to 25. */
  limit?: number;
  group: {
    fieldId: string;
    fieldType: OpenViewQueryFieldType;
    selected: OpenViewGroupSelector;
    offset: number;
  } | null;
  returnToPage?: (offset: number) => void;
};

export type RecordInspectionPage = {
  rows: readonly OpenViewRecord[];
  offset: number;
  total: number;
  source: RecordInspectionPageSource;
};

export type RecordInspectionContext = RecordInspectionPage & {
  key: string;
  recordId: string;
  definition: OpenViewQueryDefinition;
};

/** What the signed-in user may do with the record, and what it needs. */
export type RecordControls = {
  moduleId: string;
  departmentId: string;
  /** Every active field of the data source, for editing and history. */
  editableFields: readonly OpenViewDataSourceField[];
  fieldsHasMore?: boolean;
  fieldsLoadingMore?: boolean;
  onLoadMoreFields?: () => void;
  dataSources: readonly OpenViewDataSource[];
  canWrite: boolean;
  /** The record is open and the sheet knows its department (S4-C5). */
  canReadHistory: boolean;
  /** An admin or a manager of the record's department: the history reads
   * through the department and keeps today's text rule (D10.1, D10.2). */
  managesHistory: boolean;
  onChanged: (message: string) => void;
  onEditingChange: (editing: boolean) => void;
  /**
   * Choice list, Checkbox, Date, and Date and time values change in place on
   * Details, and Edit on any tab opens Details (item 2). Only the OpenView
   * sheet opts in; with none, Details reads as plain values and Edit stays
   * as it was (DR-2.12). `onStatus` gives the record header its
   * status: "Saving…", the change with Undo, or a refusal (DR-2.5 to DR-2.8).
   */
  inPlace?: { onStatus: (status: RecordInPlaceStatus | null) => void };
  /**
   * Delete record deletes at once, with "Record deleted." and Undo in the
   * `inPlace` header status (SI-9.1). Only the OpenView sheet sets it; the
   * Boards card sheet keeps the delete question (SI-9.5).
   */
  deleteWithUndo?: boolean;
};

type LiveRecordInspectorProps = {
  region: WorkspaceRegion | undefined;
  /** The sheet header's place for Edit and the record menu. */
  actionsSlot: HTMLElement | null;
  /** Items the record menu always holds (Copy link). */
  menuItems: ReactNode;
  controls?: RecordControls;
  record: OpenViewRecord | null;
  recordLoading: boolean;
  recordError: string;
  inspectionLoading: boolean;
  inspectionError: string;
  fields: readonly OpenViewDataSourceField[];
  onRetryRecord: () => void;
  /**
   * A tab that comes before the record's own tabs and opens first. A board
   * card's "On this board" (BR64) is the one caller; OpenView passes none.
   */
  leadingTab?: { value: string; label: string; content: ReactNode };
};

function readableValue(value: unknown): string {
  if (typeof value === "string") return value.trim() ? value : "—";
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return "—";
}

/** When a record last changed, for the sheet's meta line. */
export function recordUpdatedDate(
  value: string,
  region: WorkspaceRegion | undefined,
): string {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Date unavailable";
  return region ? formatWorkspaceDate(value, region) : "Date unavailable";
}

/** A record's name: its primary field, else the view's first field. */
export function recordTitle(
  record: OpenViewRecord,
  fields: readonly OpenViewDataSourceField[],
  primaryFieldId: string | null,
): string {
  const primaryField =
    fields.find((field) => field.id === primaryFieldId) ?? fields[0];
  return primaryField
    ? readableValue(openViewRecordFieldValue(record, primaryField))
    : `Record ${record.id.slice(0, 8)}`;
}

/**
 * The record sheet's body (OD7), shared by OpenView and Boards (BR83): the
 * Details, Linked records, Files, and History tabs, with only the open tab
 * scrolling. The sheet header, which
 * the workspace owns, holds the name, Previous and Next, and Close; Edit and
 * the record menu render into it through `actionsSlot`.
 */
export function LiveRecordInspector({
  region,
  actionsSlot,
  menuItems,
  record,
  recordLoading,
  recordError,
  inspectionLoading,
  inspectionError,
  fields,
  onRetryRecord,
  controls,
  leadingTab,
}: LiveRecordInspectorProps) {
  const rowPrefix = useId();
  const firstTab = leadingTab?.value ?? "details";
  const [tab, setTab] = useState<string>(firstTab);
  // The tabs show only with a record; when they come back they start on the
  // first tab, as they did when they mounted again.
  const tabsShown = Boolean(record && controls);
  const [hadTabs, setHadTabs] = useState(tabsShown);
  if (hadTabs !== tabsShown) {
    setHadTabs(tabsShown);
    if (!tabsShown) setTab(firstTab);
  }
  // A History tab that went away shows Details instead.
  const shownTab =
    tab === "history" && !controls?.canReadHistory ? "details" : tab;
  // `valueFor` gives a row its in-place control, or null for a plain value.
  const detailsRows = (
    valueFor?: (field: OpenViewDataSourceField, labelId: string) => ReactNode,
  ) =>
    record ? (
      fields.length > 0 ? (
        <dl className="divide-y">
          {fields.map((field) => {
            const labelId = `${rowPrefix}-${field.id}-label`;
            const control = valueFor?.(field, labelId);
            return (
              <div
                key={field.id}
                className="grid min-w-0 gap-1 py-2.5 sm:grid-cols-[9rem_minmax(0,1fr)] sm:items-center sm:gap-4"
              >
                <dt id={labelId} className="text-muted-foreground text-sm">
                  {field.name}
                </dt>
                <dd className="min-w-0 text-sm wrap-anywhere">
                  {control ?? (
                    // One date format and people in ink, as in the table (OD6).
                    <RecordPersonCard row={record} field={field} inline>
                      {formatOpenViewFieldValue(
                        openViewRecordFieldValue(record, field),
                        field.type,
                        region,
                      )}
                    </RecordPersonCard>
                  )}
                </dd>
              </div>
            );
          })}
        </dl>
      ) : (
        <Empty className="py-6">
          <EmptyHeader>
            <EmptyTitle>No readable fields in this view</EmptyTitle>
            <EmptyDescription>
              This view does not include any active fields to show for this
              record.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      )
    ) : null;
  const details = detailsRows();

  const status = (
    <>
      {inspectionLoading ? (
        <p role="status" className="text-muted-foreground px-5 pt-3 text-sm">
          Loading adjacent records…
        </p>
      ) : null}
      {inspectionError ? (
        <p role="alert" className="text-destructive px-5 pt-3 text-sm">
          {inspectionError}
        </p>
      ) : null}
    </>
  );
  const panelClassName = "min-h-0 flex-1 overflow-y-auto px-5 py-3";
  return (
    <section
      aria-label="Record details content"
      className="flex min-h-0 min-w-0 flex-1 flex-col"
    >
      {status}
      {record ? (
        controls ? (
          <Tabs
            value={shownTab}
            onValueChange={(value) => setTab(String(value))}
            className="min-h-0 flex-1 gap-0"
          >
            <div className="shrink-0 border-b px-5 py-3">
              <TabsList
                aria-label="Record sections"
                className="max-w-full flex-nowrap justify-start overflow-x-auto overflow-y-hidden"
              >
                {leadingTab ? (
                  <TabsTrigger value={leadingTab.value} className="shrink-0">
                    {leadingTab.label}
                  </TabsTrigger>
                ) : null}
                <TabsTrigger value="details" className="shrink-0">
                  Details
                </TabsTrigger>
                <TabsTrigger value="links" className="shrink-0">
                  Linked records
                </TabsTrigger>
                <TabsTrigger value="files" className="shrink-0">
                  Files
                </TabsTrigger>
                {controls.canReadHistory ? (
                  <TabsTrigger value="history" className="shrink-0">
                    History
                  </TabsTrigger>
                ) : null}
              </TabsList>
            </div>
            {leadingTab ? (
              <TabsContent value={leadingTab.value} className={panelClassName}>
                {leadingTab.content}
              </TabsContent>
            ) : null}
            <TabsContent value="details" className={panelClassName} keepMounted>
              <RecordDetailsControls
                key={record.id}
                record={record}
                moduleId={controls.moduleId}
                fields={controls.editableFields}
                fieldsHasMore={controls.fieldsHasMore}
                fieldsLoadingMore={controls.fieldsLoadingMore}
                onLoadMoreFields={controls.onLoadMoreFields}
                canWrite={controls.canWrite}
                onChanged={controls.onChanged}
                onEditingChange={controls.onEditingChange}
                actionsSlot={actionsSlot}
                menuItems={menuItems}
                // DR-2.12: only the OpenView sheet, which opts in, moves an
                // Edit to Details; the Boards card sheet keeps its own form.
                onShowDetails={
                  controls.inPlace ? () => setTab("details") : undefined
                }
                inPlace={
                  controls.inPlace
                    ? {
                        region,
                        detailsActive: shownTab === "details",
                        tab: shownTab,
                        onStatus: controls.inPlace.onStatus,
                        renderDetails: detailsRows,
                      }
                    : undefined
                }
                deleteWithUndo={controls.deleteWithUndo}
              >
                {details}
              </RecordDetailsControls>
            </TabsContent>
            <TabsContent value="links" className={panelClassName}>
              <RecordLinksPanel
                key={record.id}
                record={record}
                dataSources={controls.dataSources}
                canWrite={controls.canWrite}
                onChanged={controls.onChanged}
              />
            </TabsContent>
            <TabsContent value="files" className={panelClassName}>
              <RecordFilesPanel
                key={record.id}
                record={record}
                canWrite={controls.canWrite}
                region={region}
              />
            </TabsContent>
            {controls.canReadHistory ? (
              <TabsContent value="history" className={panelClassName}>
                <RecordHistoryPanel
                  region={region}
                  recordId={record.id}
                  moduleId={controls.moduleId}
                  departmentId={controls.departmentId}
                  fields={controls.editableFields}
                  fieldsComplete={!controls.fieldsHasMore}
                  manages={controls.managesHistory}
                  version={`${record.updatedAt}:${String(record.isDeleted)}`}
                />
              </TabsContent>
            ) : null}
          </Tabs>
        ) : (
          <div className={panelClassName}>{details}</div>
        )
      ) : recordError ? (
        <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
          <p role="alert" className="text-destructive text-sm">
            {recordError}
          </p>
          <Button
            type="button"
            variant="outline"
            className="min-h-11"
            onClick={onRetryRecord}
          >
            Retry linked record
          </Button>
        </div>
      ) : recordLoading ? (
        <p role="status" className="text-muted-foreground px-5 py-6 text-sm">
          Loading linked record…
        </p>
      ) : (
        <Empty className="px-5 py-6">
          <EmptyHeader>
            <EmptyTitle>This record is unavailable</EmptyTitle>
            <EmptyDescription>
              The record may have been removed or may not be visible to you.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}
    </section>
  );
}
