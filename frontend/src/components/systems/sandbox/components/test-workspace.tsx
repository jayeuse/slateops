"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Link2,
  Play,
  Search,
  Upload,
} from "lucide-react";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DisabledReason } from "@/components/ui/disabled-reason";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { DepartmentMark } from "@/components/sandbox/department-mark";
import { ApiError } from "@/lib/api";
import { apiErrorMessage } from "@/lib/api-errors";
import { useErrorText } from "@/lib/use-error-text";
import { cn } from "@/lib/utils";
import type {
  SandboxDocumentDesign,
  SandboxFieldValue,
  SandboxTrigger,
} from "../domain/document";
import { openFields, valueFits } from "../domain/example-values";
import {
  blockKeyOfRun,
  moduleReading,
  testModuleGroups,
  tryEventPlan,
  type ModuleReading,
  type ReadingBlock,
  type TryPlan,
} from "../domain/test-reading";
import {
  eventDescription,
  everyEventLimitReason,
  moduleName,
} from "../domain/test-run-summary";
import { formatSavedTime } from "../domain/version-history";
import { tryTriggerPlan } from "../domain/try-this-trigger";
import type { SandboxTestRun } from "../state/api";
import { TestEventBlock } from "./test-event-rows";
import { TestResultCard } from "./test-run-result";

// Test (docs/specs/sandbox-ux-redesign.md TEST-1 to TEST-9, E1 to E11): the
// Modules list, then the reading of the chosen module. The reading is built
// from the saved draft with no request; a run happens only on "Try it",
// "Try this trigger", "Try every event", and "Run again". This component
// owns the chosen module, the result of each block, and the run in flight;
// the rules live in `domain/test-reading.ts`, `domain/example-values.ts`,
// and `domain/try-this-trigger.ts`.

const STORE_LIMIT = 50;

type Administrator = { id: string; name: string } | null;

type Props = {
  design: SandboxDocumentDesign;
  triggers: readonly SandboxTrigger[];
  /** Stored runs, newest first. */
  runs: readonly SandboxTestRun[];
  /** Stored runs that are not cleared (`GET /sandbox/tests` total). */
  total: number;
  /** Sends the run; resolves with the stored run. No `triggerIds` runs every
   *  enabled trigger. */
  onRun: (input: {
    moduleId: string;
    values: Record<string, SandboxFieldValue>;
    event: TryPlan["event"];
    triggerIds?: string[];
  }) => Promise<SandboxTestRun>;
  onClear: () => Promise<void>;
  onPendingChange?: (pending: boolean) => void;
  /** The draft's current revision, to tell results from older drafts. */
  draftRevision: number;
  /** A result to open on, such as the one "Back to result" returns to. */
  initialRunId?: string | null;
  onShowOnCanvas: (run: SandboxTestRun) => void;
  /** The signed-in administrator: the example for a User field. */
  administrator: Administrator;
  /** Live bindings; a department with none is new (E6). Null while loading. */
  bindings: ReadonlyArray<{ kind: string; sandbox_id: string }> | null;
  /** Why a run must wait for the draft ("Saving…"), or null. */
  waitReason: string | null;
  review: { reason: string | null; disabled: boolean; open: () => void };
  onOpenBuild: () => void;
};

/** The last run of one block, or the values it waits on (E4). */
type BlockResult = {
  moduleId: string;
  blockKey: string;
  /** Null until a request is sent. */
  runId: string | null;
  /** The trigger of a "Try this trigger" run. */
  only: { id: string; name: string } | null;
  plan: TryPlan;
  values: Record<string, SandboxFieldValue>;
  /** The Triggers row of "Change values". */
  checked: string[];
  editing: boolean;
};

type RunOutcome = "ran" | "waiting" | "stopped";

function resultKey(moduleId: string, blockKey: string) {
  return `${moduleId}\u0000${blockKey}`;
}

function firstModuleId(groups: ReturnType<typeof testModuleGroups>): string {
  return groups[0]?.modules[0]?.id ?? "";
}

/** A stored run as a block result, for a result opened from the list. */
function storedResult(
  run: SandboxTestRun,
  reading: ModuleReading,
): BlockResult {
  const blockKey = blockKeyOfRun(reading, run.event) ?? "added";
  const block = reading.blocks.find((item) => item.key === blockKey);
  const listening =
    block?.triggers.filter((item) => item.enabled).map((item) => item.id) ?? [];
  return {
    moduleId: run.input.moduleId,
    blockKey,
    runId: run.id,
    only: null,
    plan: {
      moduleId: run.input.moduleId,
      values: run.input.values,
      event: run.event,
      triggerIds: run.triggerIds,
      unfillable: [],
      setFieldIds: [],
      notes: [],
    },
    values: { ...run.input.values },
    checked: run.triggerIds
      ? listening.filter((id) => run.triggerIds?.includes(id))
      : listening,
    editing: false,
  };
}

export function TestWorkspace({
  design,
  triggers,
  runs,
  total,
  onRun,
  onClear,
  onPendingChange,
  draftRevision,
  initialRunId = null,
  onShowOnCanvas,
  administrator,
  bindings,
  waitReason,
  review,
  onOpenBuild,
}: Props) {
  const groups = testModuleGroups(design, triggers, bindings);
  const initialRun = runs.find((item) => item.id === initialRunId);
  const initialReading = initialRun
    ? moduleReading(design, triggers, initialRun.input.moduleId)
    : null;
  const [moduleId, setModuleId] = useState(() =>
    initialRun &&
    groups.some((group) =>
      group.modules.some((item) => item.id === initialRun.input.moduleId),
    )
      ? initialRun.input.moduleId
      : firstModuleId(groups),
  );
  const [results, setResults] = useState<Record<string, BlockResult>>(() => {
    if (!initialRun || !initialReading) return {};
    const result = storedResult(initialRun, initialReading);
    return { [resultKey(result.moduleId, result.blockKey)]: result };
  });
  const [search, setSearch] = useState("");
  // The run in flight: its block result key and "event" or a trigger id.
  const [running, setRunning] = useState<{
    key: string;
    which: string;
  } | null>(null);
  const [every, setEvery] = useState<{ index: number; count: number } | null>(
    null,
  );
  const [clearing, setClearing] = useState(false);
  // The store refused a run (409 run_history_full) since the last clear.
  const [fullSeen, setFullSeen] = useState(false);
  const [errorFailure, setError] = useErrorText();
  const error = errorFailure?.message ?? "";
  const workspaceRef = useRef<HTMLElement>(null);
  const [phone, setPhone] = useState(false);
  const [phoneView, setPhoneView] = useState<"list" | "reading">(
    initialRun ? "reading" : "list",
  );
  // The result heading that takes focus once it renders.
  const [focusId, setFocusId] = useState<string | null>(null);
  const [recentOpen, setRecentOpen] = useState(false);

  const reading = moduleId ? moduleReading(design, triggers, moduleId) : null;
  const selectedGroup = groups.find((group) =>
    group.modules.some((item) => item.id === moduleId),
  );
  const sandboxModule = design.modules.find((item) => item.id === moduleId);
  const fields = openFields(sandboxModule);
  const count = fullSeen ? STORE_LIMIT : Math.min(total, STORE_LIMIT);
  const full = count >= STORE_LIMIT;
  const left = STORE_LIMIT - count;
  const busy = running !== null || every !== null || clearing;
  const clearDisabled = busy || (!runs.length && !count);
  const tryReason = waitReason ?? (full ? "Clear results first." : null);
  const tryBlocks =
    reading?.blocks.filter((block) => block.triggers.length) ?? [];
  const everyReason =
    waitReason ?? everyEventLimitReason(tryBlocks.length, left);

  useEffect(() => {
    const element = workspaceRef.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) =>
      setPhone(entry.contentRect.width < 640),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!focusId) return;
    const heading = document.getElementById(focusId);
    if (!heading) return;
    heading.scrollIntoView({ block: "nearest" });
    heading.focus({ preventScroll: true });
    setFocusId(null);
  }, [focusId, results, phoneView]);
  useEffect(() => onPendingChange?.(busy), [busy, onPendingChange]);
  useEffect(() => () => onPendingChange?.(false), [onPendingChange]);
  // A module closed or removed in the draft gives way to the first one.
  if (
    moduleId &&
    !groups.some((group) => group.modules.some((item) => item.id === moduleId))
  )
    setModuleId(firstModuleId(groups));

  function headingIdOf(blockKey: string) {
    const index = reading?.blocks.findIndex((block) => block.key === blockKey);
    return `sandbox-test-result-${index ?? 0}-heading`;
  }

  function putResult(result: BlockResult) {
    setResults((current) => ({
      ...current,
      [resultKey(result.moduleId, result.blockKey)]: result,
    }));
  }

  function chooseModule(id: string) {
    setModuleId(id);
    setError("");
    if (phone) setPhoneView("reading");
  }

  /** Sends one run; a stop code ends "Try every event" (N10). */
  async function send(
    result: BlockResult,
    triggerIds: string[] | null,
  ): Promise<RunOutcome> {
    const key = resultKey(result.moduleId, result.blockKey);
    setRunning({ key, which: result.only?.id ?? "event" });
    setError("");
    try {
      const stored = await onRun({
        moduleId: result.moduleId,
        values: result.values,
        event: result.plan.event,
        ...(triggerIds ? { triggerIds } : {}),
      });
      putResult({ ...result, runId: stored.id, editing: false });
      setFocusId(headingIdOf(result.blockKey));
      return "ran";
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) {
        if (reason.code === "run_history_full") {
          setFullSeen(true);
          return "stopped";
        }
        if (reason.code === "stale_revision") {
          setError("Sandbox draft changed; reload before testing.", reason);
          return "stopped";
        }
      }
      // The server's words never show (S1-C6); the shared path says it.
      setError(
        apiErrorMessage(reason, "The test could not run. Try again."),
        reason,
      );
      return "stopped";
    } finally {
      setRunning(null);
    }
  }

  function listeningIds(blockKey: string) {
    return (
      reading?.blocks
        .find((block) => block.key === blockKey)
        ?.triggers.filter((item) => item.enabled)
        .map((item) => item.id) ?? []
    );
  }

  /** Opens the values in "Change values" with no request (E4). */
  function waitForValues(result: BlockResult): RunOutcome {
    putResult({ ...result, editing: true });
    setFocusId(headingIdOf(result.blockKey));
    return "waiting";
  }

  async function tryBlock(block: ReadingBlock): Promise<RunOutcome> {
    if (!reading) return "stopped";
    const plan = tryEventPlan(design, reading.moduleId, block.event, {
      now: new Date(),
      administratorId: administrator?.id ?? null,
    });
    const result: BlockResult = {
      moduleId: reading.moduleId,
      blockKey: block.key,
      runId: null,
      only: null,
      plan,
      values: { ...plan.values },
      checked: listeningIds(block.key),
      editing: false,
    };
    if (plan.unfillable.length) return waitForValues(result);
    return send(result, null);
  }

  async function tryTrigger(block: ReadingBlock, triggerId: string) {
    const recordTrigger = triggers.find((item) => item.id === triggerId);
    if (!reading || !recordTrigger || busy || tryReason) return;
    const plan = tryTriggerPlan(design, recordTrigger, {
      now: new Date(),
      administratorId: administrator?.id ?? null,
    });
    const result: BlockResult = {
      moduleId: reading.moduleId,
      blockKey: block.key,
      runId: null,
      only: { id: recordTrigger.id, name: recordTrigger.name },
      plan,
      values: { ...plan.values },
      checked: [recordTrigger.id],
      editing: false,
    };
    if (plan.unfillable.length) {
      waitForValues(result);
      return;
    }
    await send(result, [recordTrigger.id]);
  }

  async function runAgain(result: BlockResult) {
    if (busy) return;
    const stillNeeded = result.plan.unfillable.filter((item) => {
      const field = fields.find((candidate) => candidate.id === item.fieldId);
      return (
        !field ||
        !valueFits(
          design,
          result.moduleId,
          field,
          result.values[item.fieldId] ?? null,
        )
      );
    });
    if (stillNeeded.length) {
      waitForValues(result);
      return;
    }
    const listening = listeningIds(result.blockKey);
    // Every listening trigger checked sends null (today's rule, C5).
    const triggerIds = result.only
      ? [result.only.id]
      : listening.every((id) => result.checked.includes(id))
        ? null
        : result.checked.filter((id) => listening.includes(id));
    await send({ ...result, plan: { ...result.plan, triggerIds } }, triggerIds);
  }

  async function tryEvery() {
    if (busy || everyReason || !reading) return;
    const blocks = reading.blocks.filter((block) => block.triggers.length);
    try {
      for (const [index, block] of blocks.entries()) {
        setEvery({ index: index + 1, count: blocks.length });
        // Results that finished stay when a later run stops (N10).
        if ((await tryBlock(block)) !== "ran") break;
      }
    } finally {
      setEvery(null);
    }
  }

  async function clear() {
    if (busy) return;
    setClearing(true);
    setError("");
    try {
      await onClear();
      setFullSeen(false);
      setResults({});
      setRecentOpen(false);
    } catch (reason) {
      setError(
        apiErrorMessage(
          reason,
          "Test results could not be cleared. Try again.",
        ),
        reason,
      );
    } finally {
      setClearing(false);
    }
  }

  function openStoredRun(run: SandboxTestRun) {
    const storedReading = moduleReading(design, triggers, run.input.moduleId);
    if (!storedReading) return;
    const result = storedResult(run, storedReading);
    putResult(result);
    setModuleId(run.input.moduleId);
    setRecentOpen(false);
    if (phone) setPhoneView("reading");
    const index = storedReading.blocks.findIndex(
      (block) => block.key === result.blockKey,
    );
    setFocusId(`sandbox-test-result-${Math.max(index, 0)}-heading`);
  }

  /** The event's previous value as a "<field> before" row, if it has one. */
  function beforeOf(result: BlockResult) {
    const event = result.plan.event;
    if (event.kind !== "field-changed" && event.kind !== "threshold-crossed")
      return null;
    const field = fields.find((item) => item.id === event.fieldId);
    if (!field || event.previousValue === undefined) return null;
    return {
      label: `${field.name} before`,
      field,
      value: event.previousValue,
    };
  }

  const query = search.trim().toLocaleLowerCase();
  const shownGroups = groups
    .map((group) => ({
      ...group,
      modules: group.modules.filter(
        (item) => !query || item.name.toLocaleLowerCase().includes(query),
      ),
    }))
    .filter((group) => group.modules.length);
  const moduleCount = groups.reduce(
    (sum, group) => sum + group.modules.length,
    0,
  );

  const modulesPane = (
    <section
      aria-label="Modules"
      className={cn(
        "border-border flex min-w-0 flex-col @min-[640px]/test:min-h-0 @min-[640px]/test:border-r",
        // With no module, a phone shows both panes, list then reading, so
        // "Open Build" stays in reach (E7, QA-7).
        phone && moduleCount > 0 && phoneView === "reading" && "hidden",
      )}
    >
      <div className="border-border flex min-h-14 items-center gap-2 border-b px-4 py-2">
        <h3 className="font-semibold">Modules</h3>
        <span className="text-muted-foreground text-sm">{moduleCount}</span>
      </div>
      {/* No search over an empty list (F13); the Triggers search pattern:
          placeholder and accessible name, no visible label (F7). */}
      {moduleCount ? (
        <div className="px-4 pt-3">
          <div className="relative">
            <Search
              aria-hidden="true"
              className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
            />
            <Input
              type="search"
              aria-label="Search modules"
              placeholder="Search modules"
              className="min-h-11 pl-9"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
        </div>
      ) : null}
      <div className="min-h-0 flex-1 overflow-y-auto py-2">
        {!moduleCount ? (
          <p className="text-muted-foreground px-4 py-3 text-sm">
            No modules yet
          </p>
        ) : null}
        {shownGroups.map((group) => (
          <div
            key={group.departmentId}
            role="group"
            aria-label={group.departmentName}
          >
            <p className="text-muted-foreground flex items-center gap-2 px-4 pt-3 pb-1 text-xs font-semibold">
              <DepartmentMark departmentIndex={group.departmentIndex} />
              {group.departmentName}
              {group.isNew ? <Badge variant="secondary">New</Badge> : null}
            </p>
            <ul>
              {group.modules.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    aria-current={item.id === moduleId ? "true" : undefined}
                    className={cn(
                      "hover:bg-muted focus-visible:ring-ring flex min-h-11 w-full items-center justify-between gap-3 px-6 text-left text-sm outline-none focus-visible:ring-2 xl:min-h-10",
                      item.id === moduleId && "bg-muted font-medium",
                    )}
                    onClick={() => chooseModule(item.id)}
                  >
                    <span className="min-w-0 [overflow-wrap:anywhere]">
                      {item.name}
                    </span>
                    <span className="text-muted-foreground shrink-0 text-xs font-normal">
                      {item.triggerCount
                        ? `${item.triggerCount} trigger${item.triggerCount === 1 ? "" : "s"}`
                        : "No triggers"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
        {groups.length && !shownGroups.length ? (
          <p className="text-muted-foreground px-4 py-3 text-sm">
            No module matches.
          </p>
        ) : null}
      </div>
      <div className="border-border flex min-h-12 flex-wrap items-center justify-between gap-2 border-t px-4 py-2 pb-[max(0.5rem,env(safe-area-inset-bottom))]">
        <Popover open={recentOpen} onOpenChange={setRecentOpen}>
          <PopoverTrigger
            render={
              <Button
                variant="ghost"
                size="sm"
                className={cn(
                  "min-h-11 px-2 xl:min-h-8",
                  full && "text-warn-text",
                )}
                disabled={!runs.length}
              />
            }
          >
            Results {count} of {STORE_LIMIT}
          </PopoverTrigger>
          <PopoverContent align="start" className="w-80 p-1">
            <ul
              aria-label="Recent results"
              className="max-h-72 overflow-y-auto"
            >
              {runs.map((run) => (
                <li key={run.id}>
                  <button
                    type="button"
                    className="hover:bg-muted focus-visible:ring-ring grid min-h-11 w-full gap-0.5 rounded-md px-3 py-2 text-left text-sm outline-none focus-visible:ring-2"
                    onClick={() => openStoredRun(run)}
                  >
                    <span className="font-medium">
                      {moduleName(design, run.input.moduleId)} ·{" "}
                      {eventDescription(design, run)}
                    </span>
                    <span className="text-muted-foreground text-xs">
                      {formatSavedTime(run.createdAt)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </PopoverContent>
        </Popover>
        <Button
          variant="ghost"
          size="sm"
          // Action ink only while it can act (as Try this trigger).
          className={cn(
            "min-h-11 xl:min-h-8",
            !clearDisabled && "text-primary",
          )}
          disabled={clearDisabled}
          pending={clearing}
          pendingLabel="Clearing results…"
          onClick={() => void clear()}
        >
          Clear results
        </Button>
      </div>
    </section>
  );

  const readingPane = (
    <section
      aria-label="Reading"
      className={cn(
        "@container/reading flex min-w-0 flex-col @min-[640px]/test:min-h-0",
        phone && moduleCount > 0 && phoneView === "list" && "hidden",
      )}
    >
      {!reading ? (
        <div className="grid flex-1 place-content-center justify-items-center gap-3 p-8 text-center">
          <div className="grid gap-1">
            <h3 className="font-semibold">Nothing to test yet</h3>
            <p className="text-muted-foreground text-sm">
              Add a module in Build to see what it does.
            </p>
          </div>
          <Button variant="outline" className="min-h-11" onClick={onOpenBuild}>
            Open Build
          </Button>
        </div>
      ) : (
        <>
          <div className="border-border grid gap-2 border-b px-4 py-3 @min-[40rem]/reading:grid-cols-[minmax(0,1fr)_auto] @min-[40rem]/reading:items-start">
            {phone ? (
              <Button
                variant="ghost"
                size="sm"
                className="min-h-11 justify-self-start"
                onClick={() => setPhoneView("list")}
              >
                <ArrowLeft aria-hidden />
                Modules
              </Button>
            ) : null}
            <div className="min-w-0">
              <h3 className="flex flex-wrap items-center gap-2 text-lg font-semibold [overflow-wrap:anywhere]">
                <DepartmentMark departmentIndex={reading.departmentIndex} />
                {reading.name}
                {selectedGroup?.isNew ? (
                  <Badge variant="secondary">New</Badge>
                ) : null}
              </h3>
              <p className="text-muted-foreground text-sm">{reading.facts}</p>
            </div>
            {tryBlocks.length ? (
              <DisabledReason reason={busy ? null : everyReason}>
                <Button
                  variant="outline"
                  size="sm"
                  className="min-h-11 xl:min-h-8"
                  disabled={busy && every === null}
                  pending={every !== null}
                  pendingLabel={
                    every
                      ? `Running ${every.index} of ${every.count}`
                      : "Running…"
                  }
                  onClick={() => void tryEvery()}
                >
                  <Play aria-hidden />
                  Try every event · {tryBlocks.length}{" "}
                  {tryBlocks.length === 1 ? "run" : "runs"}
                </Button>
              </DisabledReason>
            ) : null}
          </div>
          <div className="min-h-0 flex-1 px-4 @min-[640px]/test:overflow-y-auto">
            {error ? (
              <Alert
                variant="destructive"
                role="alert"
                className="mt-4"
                reference={errorFailure?.reference}
              >
                {error}
              </Alert>
            ) : null}
            {selectedGroup?.isNew ? (
              <div className="bg-muted/50 mt-4 flex flex-wrap items-center gap-3 rounded-md px-3 py-2 text-sm">
                <Upload aria-hidden className="text-muted-foreground size-4" />
                <p className="min-w-0 flex-1">
                  Review &amp; Publish lists what publishing creates.
                </p>
                <DisabledReason reason={review.disabled ? review.reason : null}>
                  <Button
                    variant="ghost"
                    size="sm"
                    className={cn(
                      "min-h-11 xl:min-h-8",
                      !review.disabled && "text-primary",
                    )}
                    disabled={review.disabled && !review.reason}
                    onClick={review.open}
                  >
                    Open review
                  </Button>
                </DisabledReason>
              </div>
            ) : null}
            {reading.blocks.map((block, index) => {
              const result = results[resultKey(reading.moduleId, block.key)];
              const run = result?.runId
                ? runs.find((item) => item.id === result.runId)
                : undefined;
              const key = resultKey(reading.moduleId, block.key);
              const runIndex = run
                ? runs.findIndex((item) => item.id === run.id)
                : -1;
              const before = result ? beforeOf(result) : null;
              return (
                <TestEventBlock
                  key={block.key}
                  block={block}
                  disabledReason={busy ? null : tryReason}
                  busy={busy}
                  runningKey={running?.key === key ? running.which : null}
                  onTry={() => {
                    if (!busy && !tryReason) void tryBlock(block);
                  }}
                  onTryTrigger={(triggerId) =>
                    void tryTrigger(block, triggerId)
                  }
                >
                  {result && (result.runId === null || run) ? (
                    <TestResultCard
                      design={design}
                      triggers={triggers}
                      draftRevision={draftRevision}
                      administrator={administrator}
                      run={run ?? null}
                      title={
                        result.only
                          ? `Example record · ${result.only.name} only`
                          : "Example record"
                      }
                      fields={fields}
                      values={result.values}
                      startValues={result.plan.values}
                      setFieldIds={result.plan.setFieldIds}
                      before={before}
                      needed={result.plan.unfillable.filter((item) => {
                        const field = fields.find(
                          (candidate) => candidate.id === item.fieldId,
                        );
                        return (
                          !field ||
                          !valueFits(
                            design,
                            result.moduleId,
                            field,
                            result.values[item.fieldId] ?? null,
                          )
                        );
                      })}
                      notes={result.plan.notes}
                      onlyTrigger={result.only !== null}
                      triggerChoices={
                        result.only
                          ? null
                          : block.triggers
                              .filter((item) => item.enabled)
                              .map((item) => ({ id: item.id, name: item.name }))
                      }
                      checkedTriggerIds={result.checked}
                      editing={result.editing}
                      runNumber={
                        runIndex >= 0 ? Math.max(count - runIndex, 1) : null
                      }
                      running={running?.key === key}
                      runDisabledReason={busy ? null : tryReason}
                      idPrefix={`sandbox-test-result-${index}`}
                      onEdit={() => putResult({ ...result, editing: true })}
                      onValue={(fieldId, value) =>
                        putResult({
                          ...result,
                          values: { ...result.values, [fieldId]: value },
                        })
                      }
                      onCheckTrigger={(triggerId, checked) =>
                        putResult({
                          ...result,
                          checked: checked
                            ? [...result.checked, triggerId]
                            : result.checked.filter((id) => id !== triggerId),
                        })
                      }
                      onRunAgain={() => {
                        if (!tryReason) void runAgain(result);
                      }}
                      onShowOnCanvas={onShowOnCanvas}
                    />
                  ) : null}
                </TestEventBlock>
              );
            })}
            <section
              aria-labelledby="sandbox-test-links"
              className="grid gap-2 py-4"
            >
              <div className="flex items-center gap-3">
                <span className="border-border text-muted-foreground grid size-7 shrink-0 place-items-center rounded-md border">
                  <Link2 aria-hidden className="size-3.5" />
                </span>
                <h4 id="sandbox-test-links" className="font-semibold">
                  Links
                </h4>
              </div>
              {reading.links.length ? (
                <ul className="grid gap-1 text-sm sm:pl-10">
                  {reading.links.map((link) => (
                    <li
                      key={link.key}
                      className="flex min-w-0 flex-wrap items-center gap-x-2"
                    >
                      {link.direction === "out" ? (
                        <ArrowRight
                          aria-label="Links to"
                          className="text-primary size-4 shrink-0"
                        />
                      ) : (
                        <ArrowLeft
                          aria-label="Linked from"
                          className="text-primary size-4 shrink-0"
                        />
                      )}
                      <span className="font-medium">{link.moduleName}</span>
                      <span className="text-muted-foreground inline-flex items-center gap-1.5">
                        <DepartmentMark
                          departmentIndex={link.departmentIndex}
                        />
                        {link.departmentName}
                      </span>
                      <span className="text-muted-foreground ml-auto text-xs">
                        {link.carries.length
                          ? `carries ${link.carries.join(", ")}`
                          : "no values"}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground text-sm sm:pl-10">
                  No links.
                </p>
              )}
            </section>
          </div>
        </>
      )}
    </section>
  );

  return (
    <section
      ref={workspaceRef}
      aria-label="Sandbox test"
      className="@container/test flex h-full min-w-0 flex-col gap-4"
    >
      <div className="bg-card border-border grid min-w-0 shrink-0 rounded-xl border @min-[640px]/test:grid-cols-[18rem_minmax(0,1fr)] @min-[900px]/test:h-[calc(100dvh-15rem)] @min-[900px]/test:overflow-clip xl:@min-[900px]/test:h-auto xl:@min-[900px]/test:min-h-0 xl:@min-[900px]/test:flex-1 xl:@min-[900px]/test:shrink">
        {modulesPane}
        {readingPane}
      </div>
    </section>
  );
}
