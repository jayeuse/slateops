"use client";

import {
  CircleAlert,
  CircleCheck,
  CircleSlash,
  Link2,
  Play,
  Workflow,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DisabledReason } from "@/components/ui/disabled-reason";
import { useWorkspaceDisplayRegion } from "@/components/use-display-region";
import { cn } from "@/lib/utils";
import type {
  SandboxDocumentDesign,
  SandboxDocumentField,
  SandboxFieldValue,
  SandboxTrigger,
} from "../domain/document";
import {
  fieldValueText,
  summarizeTestRun,
  whatHappened,
  type HappenedLine,
} from "../domain/test-run-summary";
import type { SandboxTestRun } from "../state/api";
import { TestValues, type ValuesTriggerChoice } from "./test-values";

// A Test result card (docs/specs/sandbox-ux-redesign.md TEST-5, E2 to E4,
// E10): under the event block that ran, the values used and what happened,
// "Change values" to edit them, and "Run again".

export type TestResultCardProps = {
  design: SandboxDocumentDesign;
  triggers: readonly SandboxTrigger[];
  draftRevision: number;
  administrator: { id: string; name: string } | null;
  /** Null until the first request: the values wait for a field (E4). */
  run: SandboxTestRun | null;
  /** "Example record", or "Example record · <trigger> only". */
  title: string;
  fields: readonly SandboxDocumentField[];
  values: Readonly<Record<string, SandboxFieldValue>>;
  startValues: Readonly<Record<string, SandboxFieldValue>>;
  setFieldIds: readonly string[];
  /** The event's previous value, as a "<field> before" row. */
  before: {
    label: string;
    field: SandboxDocumentField;
    value: SandboxFieldValue;
  } | null;
  needed: readonly { fieldId: string; name: string }[];
  notes: readonly string[];
  onlyTrigger: boolean;
  triggerChoices: readonly ValuesTriggerChoice[] | null;
  checkedTriggerIds: readonly string[];
  editing: boolean;
  /** "Run 13 of 50 kept"; null for a result not kept yet. */
  runNumber: number | null;
  running: boolean;
  runDisabledReason: string | null;
  idPrefix: string;
  onEdit: () => void;
  onValue: (fieldId: string, value: SandboxFieldValue) => void;
  onCheckTrigger: (triggerId: string, checked: boolean) => void;
  onRunAgain: () => void;
  onShowOnCanvas: (run: SandboxTestRun) => void;
};

function Happened({ line }: { line: HappenedLine }) {
  if (line.kind === "ran")
    return (
      <li className="flex gap-2">
        <CircleCheck
          aria-hidden
          className="text-flow-text mt-0.5 size-4 shrink-0"
        />
        <div className="min-w-0">
          <p className="font-medium">{line.name} ran</p>
          {line.changes.length ? (
            line.changes.map((change) => (
              <p key={change.fieldId} className="text-muted-foreground">
                {change.name} {change.before} →{" "}
                <span className="text-foreground font-medium">
                  {change.after}
                </span>
              </p>
            ))
          ) : (
            <p className="text-muted-foreground">No field changed.</p>
          )}
        </div>
      </li>
    );
  if (line.kind === "attention")
    return (
      <li className="flex gap-2">
        <CircleAlert
          aria-hidden
          className="text-warn-text mt-0.5 size-4 shrink-0"
        />
        <div className="min-w-0">
          <p className="font-medium">{line.name} needs attention</p>
          {line.reasons.map((reason) => (
            <p key={reason} className="text-warn-text">
              {reason}
            </p>
          ))}
        </div>
      </li>
    );
  return (
    <li className="flex gap-2">
      <CircleSlash
        aria-hidden
        className="text-muted-foreground mt-0.5 size-4 shrink-0"
      />
      <div className="min-w-0">
        <p className="font-medium">
          {line.name} did not run
          <span className="text-muted-foreground font-normal">
            {" "}
            · {line.status}
          </span>
        </p>
        {line.reason ? (
          <p className="text-muted-foreground">{line.reason}</p>
        ) : null}
      </div>
    </li>
  );
}

export function TestResultCard(props: TestResultCardProps) {
  const {
    design,
    triggers,
    draftRevision,
    administrator,
    run,
    title,
    fields,
    editing,
    runNumber,
    running,
    runDisabledReason,
    idPrefix,
  } = props;
  // Dates read in the workspace format (F9); inputs keep the stored text.
  const region = useWorkspaceDisplayRegion();
  const summary = run
    ? summarizeTestRun(run, design, triggers, draftRevision)
    : null;
  const happened = run
    ? whatHappened({
        run,
        design,
        triggers,
        notes: props.notes,
        onlyTrigger: props.onlyTrigger,
        listeningIds: props.triggerChoices?.map((choice) => choice.id) ?? null,
        administrator,
        region,
      })
    : null;
  // Issues about a value or a link, not about one trigger.
  const otherIssues =
    summary?.issues.filter((issue) => issue.subject?.kind !== "trigger") ?? [];
  const sandboxModule = design.modules.find(
    (item) => item.id === run?.input.moduleId,
  );
  const headingId = `${idPrefix}-heading`;
  return (
    <section
      aria-labelledby={headingId}
      data-test-result
      className="border-border bg-background/40 grid min-w-0 rounded-lg border"
    >
      <header className="border-border flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 border-b px-4 py-2.5">
        <h5
          id={headingId}
          tabIndex={-1}
          className="min-w-0 font-semibold [overflow-wrap:anywhere] outline-none"
        >
          {title}
        </h5>
        <Badge variant="outline">Test only · live data unchanged</Badge>
        {summary?.stale === "older-draft" ? (
          <Badge variant="warning">From an older draft</Badge>
        ) : null}
        {run ? (
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto min-h-11 xl:min-h-8"
            onClick={() => props.onShowOnCanvas(run)}
          >
            <Workflow aria-hidden />
            Show on canvas
          </Button>
        ) : null}
      </header>
      <div className="grid min-w-0 @min-[44rem]/reading:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <section
          aria-label="Values used"
          className="border-border grid min-w-0 content-start gap-3 border-b p-4 @min-[44rem]/reading:border-r @min-[44rem]/reading:border-b-0"
        >
          <div className="flex items-center justify-between gap-2">
            <h6 className="text-muted-foreground text-xs font-semibold">
              Values used
            </h6>
            {!editing ? (
              <Button
                variant="ghost"
                size="sm"
                // Action ink only while it can act (as Try this trigger).
                className={cn(
                  "min-h-11 xl:min-h-8",
                  !running && "text-primary",
                )}
                disabled={running}
                onClick={props.onEdit}
              >
                Change values
              </Button>
            ) : null}
          </div>
          <TestValues
            fields={fields}
            values={props.values}
            startValues={props.startValues}
            setFieldIds={props.onlyTrigger ? props.setFieldIds : []}
            before={
              props.before
                ? {
                    label: props.before.label,
                    text: fieldValueText(
                      props.before.field,
                      props.before.value,
                      administrator,
                      region,
                    ),
                  }
                : null
            }
            administrator={administrator}
            region={region}
            editing={editing}
            idPrefix={idPrefix}
            needed={new Set(props.needed.map((item) => item.fieldId))}
            triggerChoices={props.triggerChoices}
            checkedTriggerIds={props.checkedTriggerIds}
            onValue={props.onValue}
            onCheckTrigger={props.onCheckTrigger}
          />
        </section>
        <section
          aria-label="What happened"
          className="grid min-w-0 content-start gap-3 p-4 text-sm"
        >
          <h6 className="text-muted-foreground text-xs font-semibold">
            What happened
          </h6>
          {/* Before the first request (E4) the field that waits says why
              under itself, in Values used; nothing has happened yet. */}
          {run ? null : (
            <p className="text-muted-foreground">Nothing has run yet.</p>
          )}
          {run ? (
            <ul className="grid gap-3">
              {happened?.lines.map((line) => (
                <Happened key={`${line.triggerId}:${line.kind}`} line={line} />
              ))}
              {happened?.lines.length === 0 ? (
                <li className="text-muted-foreground">
                  No trigger on {sandboxModule?.name ?? "this module"} ran for
                  this event.
                </li>
              ) : null}
              {happened?.otherChanges.length ? (
                <li className="flex gap-2">
                  <CircleCheck
                    aria-hidden
                    className="text-muted-foreground mt-0.5 size-4 shrink-0"
                  />
                  <div className="min-w-0">
                    <p className="font-medium">Also changed</p>
                    {happened.otherChanges.map((change) => (
                      <p key={change.fieldId} className="text-muted-foreground">
                        {change.name} {change.before} →{" "}
                        <span className="text-foreground font-medium">
                          {change.after}
                        </span>
                      </p>
                    ))}
                  </div>
                </li>
              ) : null}
              {otherIssues.map((issue) => (
                <li key={issue.key} className="flex gap-2">
                  <CircleAlert
                    aria-hidden
                    className="text-warn-text mt-0.5 size-4 shrink-0"
                  />
                  <p className="text-warn-text">
                    {issue.subject ? `${issue.subject.name}: ` : ""}
                    {issue.message}
                    {issue.count > 1 ? ` (${issue.count} times)` : ""}
                  </p>
                </li>
              ))}
              {happened?.linked.map((route) => (
                <li
                  key={`${route.label}:${route.detail ?? ""}`}
                  className="flex gap-2"
                >
                  <Link2
                    aria-hidden
                    className="text-muted-foreground mt-0.5 size-4 shrink-0"
                  />
                  <div className="min-w-0 [overflow-wrap:anywhere]">
                    <p className="font-medium">{route.label}</p>
                    {route.detail ? (
                      <p className="text-muted-foreground">{route.detail}</p>
                    ) : null}
                  </div>
                </li>
              ))}
              {happened?.leftOut ? (
                <li className="text-muted-foreground flex gap-2">
                  <CircleSlash aria-hidden className="mt-0.5 size-4 shrink-0" />
                  <p>{happened.leftOut}</p>
                </li>
              ) : null}
            </ul>
          ) : null}
        </section>
      </div>
      <footer className="border-border flex flex-wrap items-center gap-3 border-t px-4 py-2.5">
        {runNumber !== null ? (
          <p className="text-muted-foreground text-sm">
            Run {runNumber} of 50 kept
          </p>
        ) : null}
        <DisabledReason reason={runDisabledReason}>
          <Button
            variant={editing ? "default" : "outline"}
            size="sm"
            className="ml-auto min-h-11 xl:min-h-8"
            pending={running}
            pendingLabel="Running…"
            onClick={props.onRunAgain}
          >
            <Play aria-hidden />
            Run again
          </Button>
        </DisabledReason>
      </footer>
    </section>
  );
}
