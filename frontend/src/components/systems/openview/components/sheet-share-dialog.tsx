"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, Lock, Users, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogCloseButton,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  NativeSelect,
  NativeSelectOption,
} from "@/components/ui/native-select";
import { SearchSelect } from "@/components/ui/search-select";
import { ApiError } from "@/lib/api";

import {
  worksheetKeys,
  worksheetSharesOptions,
} from "../adapters/worksheet-queries";
import {
  changeWorksheetShare,
  removeWorksheetShare,
  searchWorksheetShareCandidates,
  shareWorksheet,
  type WorksheetDetail,
  type WorksheetShare,
  type WorksheetShareTarget,
} from "../adapters/worksheets-api";
import { shareLines } from "../domain/sheet-share";
import { useSheetOrganizationName } from "./use-sheet-organization";

// Screen 4, Share (docs/specs/sheets.md V2, V5, V6, V8, V9; SH-8 to SH-12):
// the owner adds people or groups at View or Edit, changes a level, removes a
// share, and reads what sharing and leaving mean. Route 25 lists the people
// the owner can see and the owner's own groups; a guest gets View only (the
// server refuses Edit with 422 guest_view_only).

const SEARCH_DELAY_MS = 250;
type Level = "view" | "edit";
type Chosen = WorksheetShareTarget & { label: string };

function shareName(share: WorksheetShare) {
  return share.subject === "user"
    ? (share.person?.displayName ?? "Unknown person")
    : share.group.name || "Unnamed group";
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

/** A refused share change in the owner's words; never the server's. */
function refusal(error: unknown, name: string): string {
  if (error instanceof ApiError) {
    if (error.code === "guest_view_only")
      return `${name} is a guest and can only get View. Share again to give View.`;
    if (error.code === "share_exists") return `${name} already has access.`;
    if (error.code === "share_target_not_found")
      return "This person or group is no longer available. Choose someone else.";
    if (error.code === "worksheet_open")
      return "This sheet is open now, so nobody can share it.";
    if (error.status === 403) return "Only the owner can share this sheet.";
  }
  return "The change could not be saved. Try again.";
}

function Avatar({ group, name }: { group: boolean; name: string }) {
  return (
    <span
      aria-hidden="true"
      className="bg-muted text-muted-foreground inline-flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold"
    >
      {group ? <Users className="size-4" /> : initials(name)}
    </span>
  );
}

export default function SheetShareDialog({
  sheet,
  onClose,
  onGone,
}: {
  sheet: WorksheetDetail;
  onClose: () => void;
  onGone: () => void;
}) {
  const client = useQueryClient();
  const organization = useSheetOrganizationName();
  const shares = useQuery(worksheetSharesOptions(sheet.id));
  const [typed, setTyped] = useState("");
  const [search, setSearch] = useState("");
  const [chosen, setChosen] = useState<Chosen | null>(null);
  const [level, setLevel] = useState<Level>("view");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const timer = window.setTimeout(
      () => setSearch(typed.trim()),
      SEARCH_DELAY_MS,
    );
    return () => window.clearTimeout(timer);
  }, [typed]);
  const candidates = useQuery({
    queryKey: [...worksheetKeys.shares(sheet.id), "candidates", search],
    queryFn: ({ signal }) =>
      searchWorksheetShareCandidates(sheet.id, search, signal),
  });
  const list = shares.data ?? [];
  const taken = new Set(
    list.map((share) =>
      share.subject === "user"
        ? `user:${share.person?.id ?? share.id}`
        : `group:${share.group.id}`,
    ),
  );
  const options = [
    ...(candidates.data?.people ?? [])
      .filter((person) => person.id !== sheet.owner.id)
      .map((person) => ({
        value: `user:${person.id}`,
        label: person.displayName,
        group: "People",
      })),
    ...(candidates.data?.groups ?? []).map((group) => ({
      value: `group:${group.id}`,
      label: group.name,
      description: "Group",
      group: "Groups",
    })),
  ].filter((option) => !taken.has(option.value));

  const changed = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: worksheetKeys.shares(sheet.id) }),
      client.invalidateQueries({ queryKey: worksheetKeys.detail(sheet.id) }),
      client.invalidateQueries({
        queryKey: ["openview", "worksheets", "mine"],
      }),
    ]);
  };

  /** Runs one share change; a hidden sheet leaves the page (404). */
  const run = async (name: string, change: () => Promise<unknown>) => {
    if (pending) return false;
    setPending(true);
    setError(null);
    try {
      await change();
      await changed();
      return true;
    } catch (failure) {
      if (
        failure instanceof ApiError &&
        failure.status === 404 &&
        failure.code !== "share_target_not_found" &&
        failure.code !== "share_not_found"
      ) {
        onGone();
        return false;
      }
      setError(refusal(failure, name));
      if (failure instanceof ApiError && failure.code === "guest_view_only")
        setLevel("view");
      void changed();
      return false;
    } finally {
      setPending(false);
    }
  };

  const share = async () => {
    if (!chosen) return;
    const done = await run(chosen.label, () =>
      shareWorksheet(sheet.id, chosen, level),
    );
    if (done) {
      setChosen(null);
      setTyped("");
      setLevel("view");
    }
  };

  const [peopleLine, leaveLine] = shareLines(sheet, organization);
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="flex max-w-xl flex-col gap-4">
        <DialogHeader className="pr-10">
          <DialogTitle>Share {sheet.title}</DialogTitle>
          <DialogDescription>
            View reads and exports. Edit also changes rows and columns.
          </DialogDescription>
        </DialogHeader>
        <DialogCloseButton />
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <div className="min-w-0 flex-1">
            <SearchSelect
              label="Add people or groups"
              hideLabel
              value={chosen ? `${chosen.subject}:${chosen.id}` : ""}
              selectedOption={
                chosen
                  ? {
                      value: `${chosen.subject}:${chosen.id}`,
                      label: chosen.label,
                    }
                  : undefined
              }
              options={options}
              placeholder="Add people or groups"
              searchPlaceholder="Search people and groups"
              emptyMessage="No people or groups match."
              search={typed}
              onSearchChange={setTyped}
              loading={candidates.isPending}
              error={
                candidates.isError
                  ? "People and groups could not be listed."
                  : undefined
              }
              onRetry={() => void candidates.refetch()}
              onValueChange={(value) => {
                const option = options.find((item) => item.value === value);
                const [subject, id] = value.split(":");
                if (
                  !option ||
                  !id ||
                  (subject !== "user" && subject !== "group")
                )
                  return;
                setError(null);
                setChosen({ subject, id, label: option.label });
              }}
              popupClassName="slim-ui"
            />
          </div>
          <div className="flex gap-2">
            <NativeSelect
              aria-label="Level"
              value={level}
              onChange={(event) => setLevel(event.target.value as Level)}
              className="min-w-24 flex-1 [&_select]:h-11"
            >
              <NativeSelectOption value="view">View</NativeSelectOption>
              <NativeSelectOption value="edit">Edit</NativeSelectOption>
            </NativeSelect>
            <Button
              variant="outline"
              className="min-h-11"
              aria-disabled={!chosen || pending || undefined}
              onClick={() => void share()}
            >
              Share
            </Button>
          </div>
        </div>
        {error ? (
          <p role="alert" className="text-danger-text text-sm">
            {error}
          </p>
        ) : null}
        <ul
          aria-label="People and groups with access"
          className="divide-border flex flex-col divide-y rounded-md border"
        >
          <li className="flex min-h-14 items-center gap-3 px-3 py-2">
            <Avatar group={false} name={sheet.owner.displayName} />
            <span className="min-w-0 flex-1 truncate text-sm font-medium">
              {sheet.owner.displayName} (you)
            </span>
            <span className="text-muted-foreground pr-2 text-sm">Owner</span>
          </li>
          {list.map((item) => {
            const name = shareName(item);
            return (
              <li
                key={item.id}
                className="flex min-h-14 items-center gap-3 px-3 py-2"
              >
                <Avatar group={item.subject === "group"} name={name} />
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-sm font-medium">{name}</span>
                  {item.subject === "group" ? (
                    <span className="text-muted-foreground text-xs">Group</span>
                  ) : null}
                </span>
                <NativeSelect
                  aria-label={`Level for ${name}`}
                  value={item.level}
                  disabled={pending}
                  onChange={(event) =>
                    void run(name, () =>
                      changeWorksheetShare(
                        sheet.id,
                        item.id,
                        event.target.value as Level,
                      ),
                    )
                  }
                  className="w-24 [&_select]:h-11 xl:[&_select]:h-8"
                >
                  <NativeSelectOption value="view">View</NativeSelectOption>
                  <NativeSelectOption value="edit">Edit</NativeSelectOption>
                </NativeSelect>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove ${name}`}
                  className="size-11 shrink-0 xl:size-8"
                  onClick={() =>
                    void run(name, () =>
                      removeWorksheetShare(sheet.id, item.id),
                    )
                  }
                >
                  <X aria-hidden="true" />
                </Button>
              </li>
            );
          })}
        </ul>
        {shares.isError ? (
          <div
            role="alert"
            className="text-danger-text flex flex-wrap items-center gap-x-3 gap-y-1 text-sm"
          >
            The people with access could not be listed.
            <Button
              variant="outline"
              className="min-h-11 xl:h-8 xl:min-h-8"
              onClick={() => void shares.refetch()}
            >
              Retry
            </Button>
          </div>
        ) : null}
        <div className="flex flex-col gap-2">
          <p className="bg-muted flex items-start gap-2.5 rounded-md p-3 text-sm">
            <Lock aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <span>{peopleLine}</span>
          </p>
          <p className="bg-muted flex items-start gap-2.5 rounded-md p-3 text-sm">
            <Eye aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            <span>{leaveLine}</span>
          </p>
        </div>
        <DialogFooter>
          <Button className="min-h-11 xl:h-8 xl:min-h-8" onClick={onClose}>
            Done
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
