"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Action, Panel } from "../../shared/components/ui";
import { Alert } from "@/components/ui/alert";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  notificationCountOptions,
  notificationKeys,
  notificationPageOptions,
  notificationRefusalOptions,
  refreshNotificationReads,
} from "../adapters/platform-queries";
import { useWorkspaceInteractionSuspended } from "../../shared/runtime/workspace-identity";
import {
  NotificationItems,
  useNotificationCommands,
} from "./notification-items";
import { apiErrorReference } from "@/lib/api-errors";
import {
  listCountText,
  listNumberText,
  listTotalText,
} from "@/lib/list-pagination";

const PAGE_LIMIT = 25;

export default function ConnectedReportNotifications() {
  const client = useQueryClient();
  const suspended = useWorkspaceInteractionSuspended();
  const [status, setStatus] = useState<"all" | "unread">("all");
  const [later, setLater] = useState<{
    offset: number;
    readAt: number;
    status: string;
  } | null>(null);
  const first = useQuery({
    ...notificationPageOptions(status, PAGE_LIMIT),
    enabled: !suspended,
  });
  const count = useQuery({
    ...notificationCountOptions(),
    enabled: !suspended,
  });
  const refused = useQuery(notificationRefusalOptions()).data;
  const offset =
    later?.status === status && later.readAt === first.dataUpdatedAt
      ? later.offset
      : 0;
  const next = useQuery({
    ...notificationPageOptions(status, PAGE_LIMIT, offset),
    enabled: offset > 0 && !suspended,
  });
  const query = offset === 0 ? first : next;
  const page = refused ? undefined : query.data;
  const commands = useNotificationCommands();
  const loading = query.isFetching;
  const pagination = page?.pagination;
  const error = refused
    ? "Notifications are unavailable. Sign in or ask for access, then try again."
    : query.isError
      ? page
        ? "Couldn’t refresh notifications. Showing the last loaded page."
        : "Couldn’t load notifications."
      : null;
  function changePage(nextOffset: number) {
    setLater({ offset: nextOffset, readAt: first.dataUpdatedAt, status });
  }
  return (
    <section aria-label="Notifications" aria-busy={loading}>
      <Panel title="Notifications">
        <p className="text-muted-foreground text-sm">
          Each notification shows a title and a time. Open one to see the item
          if you still have access.
        </p>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <ToggleGroup
            variant="segmented"
            className="w-fit"
            aria-label="Notification filter"
            value={[status]}
            onValueChange={(values) => {
              const next = values[0];
              if (next === "all" || next === "unread") setStatus(next);
            }}
          >
            <ToggleGroupItem value="all">All</ToggleGroupItem>
            <ToggleGroupItem value="unread">Unread</ToggleGroupItem>
          </ToggleGroup>
          <div className="flex flex-wrap gap-2">
            <Action
              type="button"
              size="sm"
              disabled={Boolean(commands.pending) || refused || !count.data}
              onClick={() => void commands.markAll()}
            >
              {commands.pending === "all"
                ? "Marking all as read…"
                : "Mark all as read"}
            </Action>
            <Action
              type="button"
              size="sm"
              disabled={loading || Boolean(commands.pending)}
              onClick={() => {
                void query.refetch();
                void refreshNotificationReads(client, notificationKeys.count);
                void refreshNotificationReads(client, notificationKeys.titles);
              }}
            >
              Refresh
            </Action>
          </div>
        </div>
        <p className="text-muted-foreground text-sm">
          {pagination
            ? listCountText(
                pagination.total,
                pagination.totalIsCapped,
                "notification",
                "notifications",
              )
            : "Current account"}
        </p>
        {loading && (
          <p role="status" className="text-muted-foreground text-sm">
            {page ? "Refreshing notifications…" : "Loading notifications…"}
          </p>
        )}
        {error && (
          <Alert
            role="alert"
            variant="destructive"
            className="flex w-full flex-wrap items-center justify-between gap-3"
            reference={refused ? undefined : apiErrorReference(query.error)}
          >
            <p className="min-w-0">{error}</p>
            <Action
              type="button"
              size="sm"
              onClick={() => void first.refetch()}
            >
              Try again
            </Action>
          </Alert>
        )}
        {page?.items.length === 0 && (
          <p className="text-muted-foreground py-6 text-center text-sm">
            No notifications on this page.
          </p>
        )}
        {page && <NotificationItems items={page.items} commands={commands} />}
        {pagination && pagination.total > PAGE_LIMIT && (
          <nav
            aria-label="Notification pages"
            className="flex items-center justify-between gap-2"
          >
            <Action
              type="button"
              size="sm"
              disabled={
                loading || Boolean(commands.pending) || pagination.offset === 0
              }
              onClick={() =>
                changePage(Math.max(0, pagination.offset - PAGE_LIMIT))
              }
            >
              Previous
            </Action>
            <span className="text-muted-foreground text-sm">
              {listNumberText(pagination.offset + 1)}–
              {listNumberText(pagination.offset + pagination.count)} of{" "}
              {listTotalText(pagination.total, pagination.totalIsCapped)}
            </span>
            <Action
              type="button"
              size="sm"
              disabled={
                loading || Boolean(commands.pending) || !pagination.hasMore
              }
              onClick={() => changePage(pagination.offset + PAGE_LIMIT)}
            >
              Next
            </Action>
          </nav>
        )}
      </Panel>
    </section>
  );
}
