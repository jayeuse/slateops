"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { DisabledReason } from "@/components/ui/disabled-reason";
import { ErrorReference } from "@/components/ui/error-reference";
import { LoadingRegion } from "@/components/ui/loading-region";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { SearchSelect } from "@/components/ui/search-select";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";
import { apiErrorReference } from "@/lib/api-errors";
import { cn } from "@/lib/utils";

import { accessKeys, afterAccessGroupChange } from "../adapters/access-queries";
import {
  AddAccessPlanChanged,
  AddAccessStepError,
  alreadyHas,
  fitsOnlyWithOtherGrants,
  levelLines,
  levelsFor,
  planAddAccess,
  planGroupName,
  readEveryGroup,
  runAddAccess,
} from "../helpers/add-access";
import { groupErrorMessage, isAccessLevel } from "../helpers/groups";
import { isUnansweredRequest, levelLabels } from "../helpers/people";
import {
  catalogDepartments,
  useAccessCatalog,
} from "../hooks/use-access-catalog";
import {
  createAccessGroup,
  getAccessGroup,
  listAccessGroups,
  replaceAccessGroupAccess,
  replaceAccessGroupMembers,
  type AccessLevel,
  type AccessUser,
  type AccessUserAccess,
} from "../state/api";
import {
  useAccessDraftRegistration,
  useAccessVerifying,
  verifyingReason,
} from "../state/draft-navigation";
import { ActionError } from "./editor-conflicts";
import { detailRowClassName } from "./people-fields";

/** Every group, for the result line; a group change marks it stale. */
const everyGroupKey = [...accessKeys.groups, "every"] as const;

const listEveryGroupPage = (offset: number, signal?: AbortSignal) =>
  listAccessGroups({
    limit: 100,
    offset,
    sort_by: "name",
    deleted: "exclude",
    signal,
  });

/** The label-left row of the sheet, for the search field's own label. */
const searchRowClassName = cn(
  detailRowClassName,
  "md:space-y-0 md:[&>*]:contents md:[&_[data-slot=field-label]]:text-muted-foreground md:[&_[role=alert]]:col-start-2",
);

const unanswered =
  "The change got no answer, so it may have completed. Try again to finish it.";

type Failure = {
  /** A group exists without this person: the result line says so. */
  partial: boolean;
  message: string;
  /** The server's reason, when it refused a step (G6). */
  detail: string | null;
  reference: string | undefined;
};

const keepNothing = () => true;

function failureFor(caught: unknown): Failure {
  const failed = caught instanceof AddAccessStepError ? caught : null;
  const cause = failed ? failed.failure : caught;
  const reference = apiErrorReference(cause);
  if (failed?.made)
    return {
      partial: true,
      message: `${failed.made} was made, but this person was not added. Try again.`,
      detail:
        cause instanceof ApiError
          ? groupErrorMessage(cause, "The server refused the change.")
          : null,
      reference,
    };
  if (
    failed?.step === "create" &&
    cause instanceof ApiError &&
    cause.status === 403
  )
    return {
      partial: false,
      message: "Only an administrator can make groups.",
      detail: null,
      reference,
    };
  if (isUnansweredRequest(cause))
    return { partial: true, message: unanswered, detail: null, reference };
  const fallback =
    failed?.step === "read"
      ? "The groups could not be read. Try again."
      : failed?.step === "create"
        ? "The group could not be made. Try again."
        : "This person could not be added. Try again.";
  return {
    partial: false,
    message: groupErrorMessage(cause, fallback),
    detail: null,
    reference,
  };
}

/**
 * The inline Add access form of a person's Access tab (DR-10.2 to DR-10.8):
 * a department, a level, one line that says what will happen, and the
 * action. The person joins a group that gives exactly this, or a group with
 * exactly this access is made for them. The server decides each step.
 */
export function AddAccessForm({
  person,
  access,
  onAdded,
  onCancel,
}: {
  person: AccessUser;
  access: AccessUserAccess;
  /** The words of the tab's status line after a success. */
  onAdded: (status: string) => void;
  onCancel: () => void;
}) {
  const id = useId();
  const client = useQueryClient();
  const verifying = useAccessVerifying();
  const levels = levelsFor(person.role);
  const [department, setDepartment] = useState<{
    id: string;
    name: string;
  } | null>(null);
  const [chosen, setChosen] = useState<AccessLevel>("read");
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  // The last click stopped because the groups changed (P3F3-9).
  const [changed, setChanged] = useState(false);
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  // A step in flight holds the Access page guards until it ends.
  useAccessDraftRegistration("person-add-access", {
    dirty: false,
    discard: keepNothing,
    pending,
  });
  // A guest is capped at Read on the server; only Read is offered.
  const level = levels.includes(chosen) ? chosen : "read";
  const departments = useAccessCatalog({
    kind: "departments",
    selectedIds: department ? [department.id] : [],
  });
  const groups = useQuery({
    queryKey: everyGroupKey,
    queryFn: ({ signal }) =>
      readEveryGroup((offset) => listEveryGroupPage(offset, signal)),
  });
  const has = department ? alreadyHas(access, department.id, level) : null;
  const plan =
    department && groups.data
      ? planAddAccess({
          groups: groups.data,
          departmentId: department.id,
          departmentName: department.name,
          level,
        })
      : null;
  const resultId = `${id}-result`;
  // The "Already has" line is the visible reason only when it is the line shown.
  const hasShown = Boolean(
    has && !failure?.partial && !groups.isError && !groups.isPending,
  );
  const options = catalogDepartments(departments.combined).map((item) => ({
    value: item.id,
    label: item.department_name,
  }));

  function choose(
    next: { id: string; name: string } | null,
    nextLevel = level,
  ) {
    setDepartment(next);
    setChosen(nextLevel);
    setFailure(null);
    setChanged(false);
  }

  async function add() {
    if (!department || !plan || has || pending || verifying) return;
    setPending(true);
    setFailure(null);
    setChanged(false);
    // Try again follows the retry rule; any other click runs only the
    // plan its button named.
    const shown = failure?.partial ? undefined : plan;
    try {
      const result = await runAddAccess(
        {
          departmentId: department.id,
          departmentName: department.name,
          level,
          personId: person.id,
        },
        {
          listGroups: (offset) => listEveryGroupPage(offset),
          createGroup: (name) => createAccessGroup({ name }),
          getGroup: (groupId) => getAccessGroup(groupId),
          setAccess: (groupId, rows, etag) =>
            replaceAccessGroupAccess(groupId, { access: rows, etag }),
          putMembers: (groupId, memberIds, etag) =>
            replaceAccessGroupMembers(groupId, { member_ids: memberIds, etag }),
        },
        shown,
      );
      await afterAccessGroupChange(client);
      if (!mounted.current) return;
      onAdded(
        `Added ${department.name} · ${levelLabels[level]}, from ${result.groupName}.`,
      );
    } catch (caught) {
      if (caught instanceof AddAccessPlanChanged) {
        // No member write was sent: show the fresh plan; the next click runs
        // it. A stopped member step reads the groups again, because a group
        // may have been made before it.
        if (caught.groups) client.setQueryData(everyGroupKey, caught.groups);
        else void afterAccessGroupChange(client);
        if (mounted.current) setChanged(true);
        return;
      }
      // A step may have made a group: every group read is stale now.
      void afterAccessGroupChange(client);
      if (mounted.current) setFailure(failureFor(caught));
    } finally {
      if (mounted.current) setPending(false);
    }
  }

  const action = !plan
    ? "Add"
    : failure?.partial
      ? "Try again"
      : plan.kind === "join"
        ? `Add to ${plan.group.name}`
        : `Make group "${planGroupName(plan)}" and add`;
  const reason = verifying
    ? verifyingReason
    : !department
      ? "Choose a department first."
      : groups.isError
        ? "The groups could not be read."
        : !plan
          ? "Reading the groups…"
          : has
            ? "This person already has this access."
            : null;

  return (
    <form
      aria-labelledby={`${id}-title`}
      data-slim-well="surface"
      className="bg-card grid gap-4 rounded-lg border p-4"
      onSubmit={(event) => {
        event.preventDefault();
        void add();
      }}
    >
      <h3 id={`${id}-title`} className="text-sm font-semibold">
        Add access
      </h3>
      <div className={searchRowClassName}>
        <SearchSelect
          id={`${id}-department`}
          popupClassName="slim-ui"
          label="Department"
          value={department?.id ?? ""}
          options={options}
          selectedOption={
            department
              ? { value: department.id, label: department.name }
              : undefined
          }
          onValueChange={(value) => {
            const found = options.find((option) => option.value === value);
            if (found) choose({ id: found.value, name: found.label });
          }}
          search={departments.search}
          onSearchChange={departments.onSearchChange}
          loading={departments.loading}
          error={departments.error}
          reference={departments.reference}
          onRetry={() => void departments.retry()}
          hasMore={departments.hasMore}
          onLoadMore={() => void departments.loadMore()}
          loadingMore={departments.loadingMore}
          disabled={pending}
          placeholder="Choose a department"
          searchPlaceholder="Search departments"
          emptyMessage={
            departments.search
              ? "No departments match."
              : "There are no departments yet."
          }
        />
      </div>
      <div className={cn(detailRowClassName, "md:items-start")}>
        <p
          id={`${id}-level`}
          className="md:text-muted-foreground text-sm font-medium md:pt-2 md:font-normal"
        >
          Level
        </p>
        <RadioGroup
          aria-labelledby={`${id}-level`}
          value={level}
          onValueChange={(value) => {
            if (typeof value === "string" && isAccessLevel(value))
              choose(department, value);
          }}
          disabled={pending}
          className="gap-1"
        >
          {levels.map((value) => (
            <label
              key={value}
              className="hover:bg-muted flex min-h-11 cursor-pointer items-start gap-3 rounded-md px-2 py-2 xl:min-h-8 xl:py-1.5"
            >
              <RadioGroupItem
                value={value}
                className="mt-0.5"
                aria-labelledby={`${id}-${value}`}
                aria-describedby={`${id}-${value}-line`}
              />
              <span className="min-w-0">
                <span
                  id={`${id}-${value}`}
                  className="block text-sm font-medium"
                >
                  {levelLabels[value]}
                </span>
                <span
                  id={`${id}-${value}-line`}
                  className="text-muted-foreground block text-xs"
                >
                  {levelLines[value]}
                </span>
              </span>
            </label>
          ))}
        </RadioGroup>
      </div>
      <div className="grid gap-3 border-t pt-3">
        <div aria-live="polite" className="text-sm">
          {changed ? (
            <p role="status" className="mb-1 font-medium">
              The groups changed. Check the new line, then add.
            </p>
          ) : null}
          {failure?.partial ? (
            <div role="alert" className="space-y-1">
              <p id={resultId} className="text-danger-text">
                {failure.message}
              </p>
              {failure.detail ? <p>{failure.detail}</p> : null}
              <ErrorReference id={failure.reference} className="mt-0" />
            </div>
          ) : groups.isError ? (
            <div role="alert" className="space-y-2">
              <p id={resultId}>The groups could not be read.</p>
              <Button
                type="button"
                variant="outline"
                className="min-h-11"
                onClick={() => void groups.refetch()}
              >
                Try again
              </Button>
              <ErrorReference
                id={apiErrorReference(groups.error)}
                className="mt-0"
              />
            </div>
          ) : groups.isPending ? (
            // Nothing for 300 ms, then one skeleton line (DR-10.7).
            <LoadingRegion
              loading
              label="Reading the groups…"
              skeleton={<Skeleton className="h-5 w-56 max-w-full" />}
            />
          ) : !department ? null : has ? (
            <p id={resultId}>
              Already has {levelLabels[has.level]} in {department.name}
              {has.groupName ? `, from ${has.groupName}` : ""}.
            </p>
          ) : !plan ? null : plan.kind === "join" ? (
            <p id={resultId}>{plan.group.name} gives exactly this.</p>
          ) : fitsOnlyWithOtherGrants(groups.data, department.id, level) ? (
            <p id={resultId}>No group gives only this.</p>
          ) : (
            <p id={resultId}>No group gives exactly this.</p>
          )}
        </div>
        {failure && !failure.partial ? (
          <ActionError
            message={failure.message}
            title={null}
            reference={failure.reference}
          />
        ) : null}
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          <DisabledReason
            reason={reason}
            reasonId={hasShown ? resultId : undefined}
            stable
          >
            <Button
              type="submit"
              className="min-h-11"
              pending={pending}
              pendingLabel="Adding…"
            >
              {action}
            </Button>
          </DisabledReason>
          <Button
            type="button"
            variant="outline"
            className="min-h-11"
            disabled={pending}
            onClick={onCancel}
          >
            Cancel
          </Button>
        </div>
      </div>
    </form>
  );
}
