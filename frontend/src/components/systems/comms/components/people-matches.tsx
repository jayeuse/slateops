"use client";
import { useEffect, useId, useRef, useState } from "react";
import { User } from "lucide-react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useSkeletonVisible } from "@/components/ui/loading-region";
import type { ApiErrorText } from "@/lib/api-errors";
import { peopleToOffer, PEOPLE_LIMIT } from "../domain/people-matches";
import { useCommsClient } from "../state/client-context";
import {
  commsErrorText,
  useCommsCommands,
  useCommsRead,
} from "../state/runtime";
import type { SidebarRow } from "../state/use-comms-sidebar";

/** DR-5.1: the read waits this long after the last key. */
const READ_DELAY_MS = 250;
/** A new direct's composer mounts after the follow-up refresh. */
const COMPOSER_WAIT_MS = 5000;

/** The one composer wait in progress: a new start ends the older one. */
let pendingFocus: (() => void) | null = null;

/**
 * Focus the opened conversation's composer once it exists, unless the person
 * moved focus somewhere else in the meantime. Returns the loop's cancel.
 */
export function focusComposerWhenReady(
  id: string,
  frame: (step: () => void) => number = requestAnimationFrame,
  cancelFrame: (handle: number) => void = cancelAnimationFrame,
): () => void {
  pendingFocus?.();
  let handle = 0;
  const start = document.activeElement;
  const deadline = performance.now() + COMPOSER_WAIT_MS;
  const step = () => {
    const composer = document.getElementById(`composer-${id}`);
    if (
      composer instanceof HTMLTextAreaElement &&
      !composer.disabled &&
      composer.getClientRects().length
    ) {
      composer.focus();
      if (document.activeElement === composer) return;
    }
    const active = document.activeElement;
    if (active && active !== document.body && active !== start) return;
    if (performance.now() < deadline) handle = frame(step);
  };
  handle = frame(step);
  const cancel = () => {
    cancelFrame(handle);
    if (pendingFocus === cancel) pendingFocus = null;
  };
  pendingFocus = cancel;
  return cancel;
}

type Candidate = { user_id: string; display_name: string };

/**
 * The People part of "Find a conversation…" and the switcher (item 5). Rendered
 * only for someone who may start a direct message (never a guest), and only
 * with text typed, so the candidate read never runs on a cold load.
 * `show` picks the part to render: the People rows, the empty text, or both.
 * `placement` follows the surface: the sidebar list or the switcher dialog.
 */
export function PeopleMatches({
  search,
  matches,
  show,
  placement,
  onOpen,
  onStarted,
}: {
  search: string;
  /** The conversation matches on screen for this text. */
  matches: readonly SidebarRow[];
  show: "people" | "empty" | "both";
  placement: "list" | "switcher";
  onOpen?: (id: string) => void;
  /** Runs after a successful start, before the composer takes focus. */
  onStarted?: () => void;
}) {
  const { live } = useCommsClient();
  const q = search.trim();
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(q), READ_DELAY_MS);
    return () => clearTimeout(timer);
  }, [q]);
  const read = useCommsRead(
    `people-matches:${debounced}`,
    async (_client, signal) => {
      if (!live) throw new Error("Live candidate search is unavailable");
      return (
        await live.client.listDirectCandidates(
          { q: debounced, limit: PEOPLE_LIMIT },
          { signal },
        )
      ).items;
    },
    !!debounced,
  );
  const current = debounced === q;
  // DR-5.5: a refused or failed read hides People, with no message.
  const failed =
    current &&
    read.status !== "loading" &&
    (read.status === "error" || !read.data);
  const settled = current && read.status === "ready" && !!read.data;
  // While a newer read runs, the rows keep the last result.
  const [last, setLast] = useState<readonly Candidate[]>([]);
  if (read.data && read.data !== last) setLast(read.data);
  const offered = failed ? [] : peopleToOffer(read.data ?? last, matches);
  // The skeleton belongs to the read itself, not to the typing delay.
  const skeleton = useSkeletonVisible(
    current && !!debounced && read.status === "loading" && !offered.length,
  );
  const { run, isPending } = useCommsCommands();
  const [starting, setStarting] = useState("");
  const [failure, setFailure] = useState<ApiErrorText | null>(null);
  // The list owns its composer wait and ends it when it unmounts. The
  // switcher closes itself on success, so its wait outlives that close.
  const wait = useRef<(() => void) | null>(null);
  useEffect(() => {
    const owned = wait;
    return () => owned.current?.();
  }, []);
  const headingId = useId();
  async function start(person: Candidate) {
    if (isPending("people:start")) return;
    setStarting(person.user_id);
    setFailure(null);
    try {
      const result = await run("people:start", (client, signal) =>
        client.findOrCreateDirect({ recipient_id: person.user_id }, { signal }),
      );
      onOpen?.(result.data.id);
      onStarted?.();
      const cancel = focusComposerWhenReady(result.data.id);
      if (placement === "list") wait.current = cancel;
    } catch (error) {
      setFailure(
        commsErrorText(error, "The conversation did not start. Try again."),
      );
    } finally {
      setStarting("");
    }
  }
  const list = placement === "list";
  const Heading = list ? "h2" : "h3";
  const people = show !== "empty" &&
    (offered.length > 0 || skeleton || failure) && (
      <section aria-labelledby={headingId} className={list ? "mt-5" : "mt-2"}>
        <Heading
          id={headingId}
          className={
            list
              ? "text-muted-foreground px-2 py-2 text-xs font-semibold"
              : "text-muted-foreground px-4 py-2 text-xs font-semibold"
          }
        >
          People
        </Heading>
        {failure && (
          <Alert
            role="alert"
            variant="destructive"
            reference={failure.reference}
            className={list ? "mx-2 mb-2" : "mb-2"}
          >
            {failure.message}
          </Alert>
        )}
        {offered.map((person) => (
          <Button
            key={person.user_id}
            type="button"
            variant="ghost"
            disabled={starting === person.user_id}
            onClick={() => void start(person)}
            className={
              list
                ? "text-muted-foreground h-auto min-h-11 w-full justify-start gap-2 py-2 pr-3 pl-3 text-left font-medium"
                : "min-h-11 w-full justify-start"
            }
          >
            <User
              aria-hidden="true"
              className="text-muted-foreground size-4 shrink-0"
            />
            <span className="truncate">{person.display_name}</span>
            {starting === person.user_id && (
              <span className="ml-auto shrink-0 text-xs">Starting…</span>
            )}
          </Button>
        ))}
        {!offered.length && skeleton && (
          <div
            role="status"
            aria-label="Loading people…"
            className="flex min-h-11 items-center gap-2 px-3"
          >
            <Skeleton className="size-4 shrink-0 rounded-full" />
            <Skeleton className="h-3 w-32" />
          </div>
        )}
      </section>
    );
  const empty = show !== "people" &&
    !matches.length &&
    (settled || failed) &&
    !offered.length &&
    !skeleton && (
      <p
        className={
          list
            ? "text-muted-foreground px-2 py-3 text-sm"
            : "text-muted-foreground py-4 text-sm"
        }
      >
        {failed
          ? "No conversations match."
          : "No conversations or people match."}
      </p>
    );
  return (
    <>
      {empty}
      {people}
    </>
  );
}
