"use client";

// The header search panel (docs/specs/ux-friction-pass.md item 4). The shell
// loads this module on the first open, so no page's cold load carries it.

import { useEffect, useId, useRef, useState, type RefObject } from "react";
import { useRouter } from "next/navigation";
import {
  keepPreviousData,
  queryOptions,
  useQueries,
  useQuery,
  type UseQueryResult,
} from "@tanstack/react-query";
import {
  ArrowRight,
  CalendarDays,
  FileText,
  Megaphone,
  MessageSquare,
  Search as SearchIcon,
  Table,
  UserRound,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorReference } from "@/components/ui/error-reference";
import { useSkeletonVisible } from "@/components/ui/loading-region";
import {
  GuardedWorkspaceLink,
  useWorkspaceNavigationRequest,
} from "@/components/workspace-navigation-guard";
import { useWorkspaceDisplayRegion } from "@/components/use-display-region";
import { search as searchMessages } from "@/components/systems/comms/adapters/search-api";
import { requestSessionRecheck } from "@/lib/auth-api";
import { apiErrorReference } from "@/lib/api-errors";
import { formatWorkspaceDate } from "@/lib/date-time-display";
import { cn } from "@/lib/utils";
import { platformSearchOptions } from "../adapters/platform-search-api";
import { isSearchAdmissionError } from "../helpers/search-failure";
import {
  PANEL_GROUPS,
  PANEL_LIMIT,
  PANEL_SCOPE,
  activeOrder,
  addressWordsScope,
  groupHeading,
  messageRows,
  moveActive,
  platformRows,
  rememberAddressWords,
  showAllHref,
  type PanelGroupKind,
  type PanelRow,
} from "../helpers/search-panel";

const GROUP_CLASS = "border-border py-1.5 not-first:border-t";

const ICONS: Record<PanelGroupKind, LucideIcon> = {
  record: Table,
  person: UserRound,
  post: Megaphone,
  event: CalendarDays,
  message: MessageSquare,
  file: FileText,
};

const PLATFORM_KINDS = ["record", "person", "post", "event", "file"] as const;

type GroupPage = {
  rows: PanelRow[];
  total: number;
  capped: boolean;
};

/** Messages come from OpenComms search, bound to the verified account and organization. */
function messageSearchOptions(
  userId: string | null,
  organizationId: string | null,
  q: string,
) {
  return queryOptions({
    queryKey: [
      "platform",
      "search-panel",
      "messages",
      { organizationId, userId, q, limit: PANEL_LIMIT },
    ],
    enabled: q.length > 0 && q.length <= 100 && !!userId && !!organizationId,
    queryFn: ({ signal }) =>
      searchMessages(
        { org_id: organizationId ?? "", user_id: userId ?? "" },
        {
          q,
          limit: PANEL_LIMIT,
          sort_by: "relevance",
          sort_order: "desc",
        },
        { signal },
      ),
  });
}

export function SearchPanel({
  open,
  onOpenChange,
  returnFocus,
  userId,
  organizationId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The header Search button; focus goes back to it on close. */
  returnFocus: RefObject<HTMLButtonElement | null>;
  userId: string | null;
  organizationId: string | null;
}) {
  const field = useRef<HTMLInputElement | null>(null);
  // A picked result leaves the page, so focus does not go back to Search.
  const picked = useRef(false);
  useEffect(() => {
    if (open) picked.current = false;
  }, [open]);
  return (
    <Dialog open={open} onOpenChange={(next) => onOpenChange(next)}>
      <DialogContent
        initialFocus={field}
        finalFocus={() => (picked.current ? false : returnFocus.current)}
        className={cn(
          "fixed inset-0 flex h-dvh max-h-none w-full max-w-none flex-col overflow-hidden rounded-none border-0 p-0",
          "md:inset-auto md:top-24 md:left-1/2 md:h-auto md:max-h-[calc(100dvh-160px)] md:w-160 md:-translate-x-1/2 md:rounded-[var(--radius)] md:border",
        )}
      >
        <DialogTitle className="sr-only">Search workspace</DialogTitle>
        <PanelBody
          field={field}
          userId={userId}
          organizationId={organizationId}
          onPick={() => {
            picked.current = true;
            onOpenChange(false);
          }}
        />
      </DialogContent>
    </Dialog>
  );
}

function PanelBody({
  field,
  userId,
  organizationId,
  onPick,
}: {
  field: RefObject<HTMLInputElement | null>;
  userId: string | null;
  organizationId: string | null;
  /** Closes the panel before a picked result navigates. */
  onPick: () => void;
}) {
  const id = useId();
  const router = useRouter();
  const requestNavigation = useWorkspaceNavigationRequest();
  const region = useWorkspaceDisplayRegion();
  const [query, setQuery] = useState("");
  const text = query.trim();
  // The reads wait until typing settles (DR-4.5).
  const [settled, setSettled] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(text), 250);
    return () => window.clearTimeout(timer);
  }, [text]);
  // A new query replaces the previous query's reads; TanStack aborts the
  // reads that lose their observer, because each read passes its signal.
  const platformReads = useQueries({
    queries: PLATFORM_KINDS.map((kind) => ({
      ...platformSearchOptions(settled, kind, 0, PANEL_LIMIT),
      placeholderData: keepPreviousData,
    })),
  });
  const messagesEnabled = !!userId && !!organizationId;
  const messageRead = useQuery({
    ...messageSearchOptions(userId, organizationId, settled),
    placeholderData: keepPreviousData,
  });
  const formatDate = (value: string) =>
    region
      ? formatWorkspaceDate(value, region, { month: "short", day: "numeric" })
      : new Intl.DateTimeFormat(undefined, {
          month: "short",
          day: "numeric",
        }).format(new Date(value));
  const groups = PANEL_GROUPS.map((group) => {
    if (group.kind === "message")
      return {
        ...group,
        read: messageRead as UseQueryResult<unknown>,
        enabled: messagesEnabled && settled.length > 0,
        page: messageRead.data
          ? {
              rows: messageRows(messageRead.data.items, formatDate),
              total: messageRead.data.pagination.total,
              capped: messageRead.data.pagination.total_is_capped,
            }
          : undefined,
      };
    const read = platformReads[PLATFORM_KINDS.indexOf(group.kind)];
    return {
      ...group,
      read: read as UseQueryResult<unknown>,
      enabled: settled.length > 0,
      page: read.data
        ? {
            rows: platformRows(read.data.items),
            total: read.data.pagination.total,
            capped: read.data.pagination.total_is_capped,
          }
        : undefined,
    };
  });
  const admissionDenied = groups.some((group) =>
    isSearchAdmissionError(group.read.error),
  );
  useEffect(() => {
    if (admissionDenied) requestSessionRecheck();
  }, [admissionDenied]);
  const shown = (group: (typeof groups)[number]) =>
    group.enabled && !group.read.isError && group.page?.rows.length
      ? group.page.rows
      : [];
  // Rows of the previous words stay on screen while new words settle and
  // load, but no row is active, so Enter never opens an old answer.
  const current =
    text === settled &&
    !groups.some(
      (group) => shown(group).length > 0 && group.read.isPlaceholderData,
    );
  const order = current ? activeOrder(groups.map(shown)) : [];
  const [chosen, setChosen] = useState<string | null>(null);
  const active =
    chosen !== null && order.includes(chosen) ? chosen : (order[0] ?? null);
  useEffect(() => {
    if (active)
      document.getElementById(active)?.scrollIntoView({ block: "nearest" });
  }, [active]);
  const nothingMatches =
    settled.length > 0 &&
    settled === text &&
    groups.every(
      (group) =>
        !group.enabled ||
        (group.read.isSuccess &&
          !group.read.isPlaceholderData &&
          group.page?.rows.length === 0),
    );
  const rows = new Map(
    groups.flatMap((group) => shown(group).map((row) => [row.id, row])),
  );
  // The words this person sends to the Search page or Files belong to this
  // account and organization (FX-SR-8).
  const wordsScope = addressWordsScope(userId, organizationId);
  function open(row: PanelRow) {
    const href = row.href;
    if (!href) return;
    const fileSearch = new URL(href, window.location.origin).searchParams;
    if (fileSearch.get("section") === "files" && fileSearch.get("search"))
      rememberAddressWords(
        "search",
        wordsScope,
        row.title.trim().slice(0, 100),
      );
    onPick();
    const go = () => router.push(href);
    if (requestNavigation(href, go)) go();
  }
  const listIds = PANEL_GROUPS.map((group) => `${id}-${group.kind}`);
  const shownLists = listIds.filter((_, index) =>
    shown(groups[index]).some((row) => row.href !== null),
  );
  return (
    <>
      {/* The field's focus shows as a 2 px line along the bottom of the row,
          inside the panel, so the panel edge never cuts it (DR-4.2). */}
      <div className="has-[input:focus]:after:bg-ring relative flex h-14 shrink-0 items-center gap-2.5 border-b pr-1.5 pl-4 after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 md:h-13">
        <SearchIcon
          aria-hidden="true"
          className="text-muted-foreground size-4 shrink-0"
        />
        <input
          ref={field}
          role="combobox"
          aria-label="Search workspace"
          aria-autocomplete="list"
          aria-expanded={shownLists.length > 0}
          aria-controls={shownLists.join(" ") || undefined}
          aria-activedescendant={active ?? undefined}
          placeholder="Search workspace"
          maxLength={100}
          autoComplete="off"
          spellCheck={false}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              setChosen(
                moveActive(order, active, event.key === "ArrowDown" ? 1 : -1),
              );
            } else if (event.key === "Enter" && active) {
              event.preventDefault();
              const row = rows.get(active);
              if (row) open(row);
            }
          }}
          className="placeholder:text-muted-foreground h-full min-w-0 flex-1 bg-transparent text-base outline-none"
        />
        <DialogClose
          render={
            <Button
              variant="ghost"
              size="icon"
              className="size-11 shrink-0 xl:size-8"
              aria-label="Close"
            />
          }
        >
          <X aria-hidden="true" className="size-4" />
        </DialogClose>
      </div>
      <p className="text-muted-foreground shrink-0 border-b px-4 py-2 text-xs">
        {PANEL_SCOPE}
      </p>
      {nothingMatches ? (
        <div className="px-4 pt-4.5 pb-5.5 text-sm">
          <p>Nothing matches &ldquo;{settled}&rdquo;.</p>
          <p className="text-muted-foreground mt-1">
            Check the spelling, or try fewer words.
          </p>
        </div>
      ) : settled ? (
        <div className="min-h-0 flex-1 overflow-y-auto py-1.5">
          {groups.map((group, index) => (
            <PanelGroup
              key={group.kind}
              listId={listIds[index]}
              title={group.title}
              icon={ICONS[group.kind]}
              enabled={group.enabled}
              read={group.read}
              page={group.page}
              active={active}
              onOpen={open}
              onActivate={setChosen}
            />
          ))}
        </div>
      ) : null}
      {text && !nothingMatches ? (
        <div className="flex shrink-0 items-center border-t px-2 py-1.5">
          <GuardedWorkspaceLink
            href={showAllHref(text)}
            // As a picked row: the panel closes, then the guard runs.
            onClick={() => {
              rememberAddressWords("q", wordsScope, text);
              onPick();
            }}
            className="text-primary focus-visible:outline-ring inline-flex min-h-11 w-full items-center justify-center gap-1.5 rounded-md px-2 text-sm font-medium hover:underline focus-visible:outline-2 md:w-auto md:justify-start xl:min-h-8"
          >
            Show all results for &ldquo;{text}&rdquo;
            <ArrowRight aria-hidden="true" className="size-4" />
          </GuardedWorkspaceLink>
        </div>
      ) : null}
    </>
  );
}

function PanelGroup({
  listId,
  title,
  icon: Icon,
  enabled,
  read,
  page,
  active,
  onOpen,
  onActivate,
}: {
  listId: string;
  title: string;
  icon: LucideIcon;
  enabled: boolean;
  read: UseQueryResult<unknown>;
  page: GroupPage | undefined;
  active: string | null;
  onOpen: (row: PanelRow) => void;
  onActivate: (id: string) => void;
}) {
  const headingId = `${listId}-heading`;
  const waiting = enabled && !page && !read.isError;
  // A cold group shows skeleton rows only after 300 ms (G2).
  const skeleton = useSkeletonVisible(waiting);
  if (!enabled) return null;
  const heading = (text: string) => (
    <h3
      id={headingId}
      className="text-muted-foreground px-4 pt-1.5 pb-1 text-xs font-semibold"
    >
      {text}
    </h3>
  );
  if (read.isError)
    return (
      <section aria-labelledby={headingId} className={GROUP_CLASS}>
        {heading(title)}
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 px-4 pb-2 text-sm">
          <span className="text-destructive">
            {title} could not be searched.
          </span>
          <button
            type="button"
            className="text-primary focus-visible:outline-ring inline-flex min-h-11 items-center rounded-sm font-medium underline-offset-4 hover:underline focus-visible:outline-2 disabled:opacity-50 xl:min-h-8"
            disabled={read.isFetching}
            onClick={() => void read.refetch()}
          >
            Try again
          </button>
          <ErrorReference
            id={
              isSearchAdmissionError(read.error)
                ? undefined
                : apiErrorReference(read.error)
            }
          />
        </div>
      </section>
    );
  if (!page)
    return skeleton ? (
      <section aria-labelledby={headingId} className={GROUP_CLASS}>
        {heading(title)}
        <p role="status" className="sr-only">
          Searching {title.toLowerCase()}…
        </p>
        {[0, 1].map((row) => (
          <div
            key={row}
            className="flex min-h-11 items-start gap-2.5 px-4 py-2"
          >
            <Skeleton className="mt-0.5 size-4 shrink-0" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-3 w-1/3" />
            </div>
          </div>
        ))}
      </section>
    ) : null;
  if (!page.rows.length) return null;
  // A row that cannot open is not an option, so the arrows skip it (DR-4.6).
  const options = page.rows.filter((row) => row.href !== null);
  const plain = page.rows.filter((row) => row.href === null);
  const text = (row: PanelRow) => (
    <>
      <Icon
        aria-hidden="true"
        className="text-muted-foreground mt-0.5 size-4 shrink-0"
      />
      <div className="min-w-0 flex-1">
        <div className={cn("truncate", row.href && "font-medium")} dir="auto">
          {row.excerpt
            ? row.excerpt.map((part, index) =>
                part.marked ? (
                  <mark
                    key={index}
                    className="bg-action-tint rounded-sm px-px text-inherit"
                  >
                    {part.text}
                  </mark>
                ) : (
                  <span key={index}>{part.text}</span>
                ),
              )
            : row.title}
        </div>
        <div className="text-muted-foreground truncate text-xs">
          {row.context}
        </div>
      </div>
    </>
  );
  return (
    <section aria-labelledby={headingId} className={GROUP_CLASS}>
      {heading(groupHeading(title, page.total, page.capped))}
      {options.length ? (
        <div role="listbox" id={listId} aria-labelledby={headingId}>
          {options.map((row) => (
            <div
              key={row.id}
              id={row.id}
              role="option"
              aria-selected={row.id === active}
              onClick={() => onOpen(row)}
              // The pointer moves the active row: one highlighted row.
              onPointerMove={() => {
                if (row.id !== active) onActivate(row.id);
              }}
              className={cn(
                "flex min-h-11 cursor-pointer items-start gap-2.5 px-4 py-2 text-sm",
                row.id === active && "bg-accent",
              )}
            >
              {text(row)}
            </div>
          ))}
        </div>
      ) : null}
      {plain.length ? (
        <ul>
          {plain.map((row) => (
            <li
              key={row.id}
              className="text-muted-foreground flex min-h-11 items-start gap-2.5 px-4 py-2 text-sm"
            >
              {text(row)}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
