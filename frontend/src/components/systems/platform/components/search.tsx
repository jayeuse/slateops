"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useSearchParams } from "next/navigation";
import type { Route } from "next";
import {
  queryOptions,
  useQueries,
  useQuery,
  type UseQueryResult,
} from "@tanstack/react-query";
import { ArrowUpRight, Search as SearchIcon } from "lucide-react";
import { SearchField } from "@/components/ui/search-field";
import { PaginationControls } from "@/components/ui/pagination-controls";
import { PersonCardPopover } from "@/components/person-card";
import { GuardedWorkspaceLink } from "@/components/workspace-navigation-guard";
import { requestSessionRecheck } from "@/lib/auth-api";
import { useWorkspaceDisplayRegion } from "@/components/use-display-region";
import { useAdmittedWorkspaceScope } from "@/components/systems/shared/runtime/workspace-identity";
import { search as searchMessages } from "@/components/systems/comms/adapters/search-api";
import type { SearchHit } from "@/components/systems/comms/contract/types";
import { formatWorkspaceDate } from "@/lib/date-time-display";
import { Action, Panel } from "../../shared/components/ui";
import {
  SEARCH_KINDS,
  platformSearchOptions,
  searchDestination,
  type PlatformSearchItem,
  type SearchKind,
} from "../adapters/platform-search-api";
import { excerptParts } from "../helpers/search-panel";
import {
  isSearchAdmissionError,
  searchFailureMessage,
} from "../helpers/search-failure";
import { ErrorReference } from "@/components/ui/error-reference";
import { apiErrorReference } from "@/lib/api-errors";
import { listTotalText } from "@/lib/list-pagination";

type SearchProps = {
  query: string;
  onQueryChange: (query: string) => void;
};
type CardKind = SearchKind | "message";
// One card per kind, in the order of the search panel (DR-4.4, DR-4.8).
const CARDS: readonly CardKind[] = [
  "record",
  "person",
  "post",
  "event",
  "message",
  "file",
];
const TITLES: Record<CardKind, string> = {
  record: "Records",
  person: "People",
  post: "Posts",
  event: "Events",
  message: "Messages",
  file: "Files",
};
const PAGE_SIZE = 10;

/** Messages come from OpenComms search, bound to the verified account and organization. */
function messageSearchOptions(
  scope: { org_id: string; user_id: string } | null,
  q: string,
  offset: number,
) {
  return queryOptions({
    queryKey: [
      "platform",
      "search",
      { kind: "message", scope, q, offset, limit: PAGE_SIZE },
    ],
    // The read waits while the account or organization is still pending.
    enabled: scope !== null && q.length > 0 && q.length <= 100,
    queryFn: ({ signal }) =>
      searchMessages(
        scope ?? { org_id: "", user_id: "" },
        {
          q,
          limit: PAGE_SIZE,
          offset,
          sort_by: "relevance",
          sort_order: "desc",
        },
        { signal },
      ),
  });
}

type CardRow = {
  id: string;
  title: ReactNode;
  context: string;
  href: Route | null;
  /** A person row keeps its person card and its own Open link. */
  person?: PlatformSearchItem;
};
export default function Search({ query, onQueryChange }: SearchProps) {
  const search = query.trim();
  // "Show all results" opens this page with the panel's words in `q`; they
  // fill the field once per address, so later typing is never replaced.
  const addressQuery = useSearchParams().get("q");
  const seeded = useRef<string | null>(null);
  useEffect(() => {
    if (addressQuery === null || seeded.current === addressQuery) return;
    seeded.current = addressQuery;
    onQueryChange(addressQuery.slice(0, 100));
  }, [addressQuery, onQueryChange]);
  const [settled, setSettled] = useState(search);
  const [pages, setPages] = useState<{
    search: string;
    offsets: Partial<Record<CardKind, number>>;
  }>({ search, offsets: {} });
  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(search), 250);
    return () => window.clearTimeout(timer);
  }, [search]);
  const offsets = pages.search === search ? pages.offsets : {};
  const settledOffset = (kind: CardKind) =>
    pages.search === settled ? (pages.offsets[kind] ?? 0) : 0;
  const reads = useQueries({
    queries: SEARCH_KINDS.map((kind) =>
      platformSearchOptions(settled, kind, settledOffset(kind)),
    ),
  });
  // Messages are bound to the admitted account and organization; with no
  // organization there is no Messages card, as in the panel.
  const scope = useAdmittedWorkspaceScope();
  const messageRead = useQuery(
    messageSearchOptions(scope, settled, settledOffset("message")),
  );
  const region = useWorkspaceDisplayRegion();
  const formatDate = (value: string) =>
    region
      ? formatWorkspaceDate(value, region, { month: "short", day: "numeric" })
      : new Intl.DateTimeFormat(undefined, {
          month: "short",
          day: "numeric",
        }).format(new Date(value));
  const cards = CARDS.filter(
    (kind) => kind !== "message" || scope !== null,
  ).map((kind) => {
    if (kind === "message") {
      const data = messageRead.data;
      return {
        kind,
        read: messageRead as UseQueryResult<unknown>,
        page: data && {
          rows: data.items.map((hit) => messageRow(hit, formatDate)),
          pagination: data.pagination,
        },
      };
    }
    const read = reads[SEARCH_KINDS.indexOf(kind)];
    const data = read.data;
    return {
      kind,
      read: read as UseQueryResult<unknown>,
      page: data && {
        rows: data.items.map((item): CardRow => ({
          id: item.id,
          title: item.title,
          context: item.context_label,
          href: searchDestination(item),
          person: item.kind === "person" ? item : undefined,
        })),
        pagination: data.pagination,
      },
    };
  });
  const admissionDenied = cards.some((card) =>
    isSearchAdmissionError(card.read.error),
  );
  useEffect(() => {
    if (admissionDenied) requestSessionRecheck();
  }, [admissionDenied]);
  return (
    <section className="space-y-6">
      <div className="max-w-2xl">
        <SearchField
          label="Search workspace"
          value={query}
          onValueChange={onQueryChange}
          maxLength={100}
          placeholder="Search records, people, posts, events, messages, and files…"
        />
      </div>
      <div className="grid items-start gap-5 md:grid-cols-2">
        {cards.map(({ kind, read, page }) => {
          const waiting = settled !== search;
          const data =
            !waiting && !read.isError && !admissionDenied ? page : undefined;
          const offset = offsets[kind] ?? 0;
          return (
            <section key={kind} aria-label={`${TITLES[kind]} search results`}>
              <Panel title={TITLES[kind]}>
                {!search ? (
                  <p className="text-muted-foreground text-sm">
                    Enter a search to find {TITLES[kind].toLowerCase()}.
                  </p>
                ) : waiting || read.isPending ? (
                  <p role="status" className="text-muted-foreground text-sm">
                    Searching {TITLES[kind].toLowerCase()}…
                  </p>
                ) : read.isError || admissionDenied ? (
                  <div className="space-y-3">
                    <p role="alert" className="text-destructive text-sm">
                      {searchFailureMessage(read.error, admissionDenied)}
                    </p>
                    <Action
                      onClick={() => void read.refetch()}
                      disabled={read.isFetching}
                    >
                      Retry
                    </Action>
                    <ErrorReference
                      id={
                        admissionDenied
                          ? undefined
                          : apiErrorReference(read.error)
                      }
                    />
                  </div>
                ) : data && !data.rows.length ? (
                  <p className="text-muted-foreground text-sm">
                    No matching {TITLES[kind].toLowerCase()}.
                  </p>
                ) : null}
                {data ? (
                  <>
                    <ul className="divide-y">
                      {data.rows.map((row) => {
                        const href = row.href;
                        const content = (
                          <>
                            <span className="min-w-0">
                              <span className="line-clamp-2">{row.title}</span>
                              <span className="text-muted-foreground mt-1 block text-xs">
                                {row.context}
                              </span>
                            </span>
                            {href ? (
                              <ArrowUpRight
                                aria-hidden="true"
                                className="size-4 shrink-0"
                              />
                            ) : null}
                          </>
                        );
                        return (
                          <li key={row.id}>
                            {row.person ? (
                              <div className="flex min-h-11 items-center justify-between gap-3 py-3 text-sm">
                                <div className="min-w-0">
                                  <PersonCardPopover
                                    personId={row.person.id}
                                    label={row.person.title}
                                  />
                                  <p className="text-muted-foreground text-xs">
                                    {row.context}
                                  </p>
                                </div>
                                {href ? (
                                  <GuardedWorkspaceLink
                                    href={href}
                                    aria-label={`Open ${row.person.title}`}
                                    className="text-primary focus-visible:outline-ring inline-flex min-h-11 shrink-0 items-center gap-1 rounded-sm px-2 underline underline-offset-4 focus-visible:outline-2"
                                  >
                                    Open{" "}
                                    <ArrowUpRight
                                      aria-hidden="true"
                                      className="size-4"
                                    />
                                  </GuardedWorkspaceLink>
                                ) : null}
                              </div>
                            ) : href ? (
                              <GuardedWorkspaceLink
                                href={href}
                                className="flex min-h-11 items-center justify-between gap-3 py-3 text-sm hover:underline"
                              >
                                {content}
                              </GuardedWorkspaceLink>
                            ) : (
                              <div className="flex min-h-11 items-center gap-3 py-3 text-sm">
                                {content}
                              </div>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                    <p className="text-muted-foreground text-xs">
                      {listTotalText(
                        data.pagination.total,
                        data.pagination.total_is_capped,
                      )}{" "}
                      results · showing {data.rows.length}
                    </p>
                    {data.pagination.total > PAGE_SIZE ? (
                      <PaginationControls
                        ariaLabel={`${TITLES[kind]} result pages`}
                        pageCount={Math.ceil(data.pagination.total / PAGE_SIZE)}
                        pageIndex={offset / PAGE_SIZE}
                        hasMore={data.pagination.has_more}
                        pageCountIsLowerBound={data.pagination.total_is_capped}
                        onPageIndexChange={(page) =>
                          setPages({
                            search,
                            offsets: { ...offsets, [kind]: page * PAGE_SIZE },
                          })
                        }
                      />
                    ) : null}
                  </>
                ) : null}
              </Panel>
            </section>
          );
        })}
      </div>
      <p className="text-muted-foreground flex items-center gap-2 text-xs">
        <SearchIcon aria-hidden="true" className="size-4" />
        Results include workspace content you can read.
      </p>
    </section>
  );
}

/** A message opens at itself in OpenComms, with its matched words marked. */
function messageRow(
  hit: SearchHit,
  formatDate: (value: string) => string,
): CardRow {
  return {
    id: hit.message_id,
    title: excerptParts(hit.excerpt, hit.matches).map((part, index) =>
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
    ),
    context: `${hit.conversation_name} · ${hit.author_name} · ${formatDate(hit.created_at)}`,
    href: `/comms?conversation=${encodeURIComponent(hit.conversation_id)}&message=${encodeURIComponent(hit.message_id)}` as Route,
  };
}
