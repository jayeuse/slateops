"use client";

import { useQueries, useQuery } from "@tanstack/react-query";

import { PersonAvatar } from "@/components/person-avatar";
import { personCardOptions } from "@/components/profile/adapters/profile-queries";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

import { authMeOptions } from "../adapters/openview-queries";
import { presenceColor, type PresencePeer } from "../domain/sheet-presence";

// The sheet header's "who is here" (docs/specs/sheets.md PR1): an avatar for
// each other person with the sheet open now, ringed in their colour, the
// name on hover or focus. More than four collapse into "+N". Names and
// photos come from the person cards the viewer can already read.

const SHOWN = 4;

const trigger =
  "focus-visible:outline-ring rounded-full outline-offset-2 focus-visible:outline-2 max-sm:min-h-11 max-sm:min-w-8 max-sm:inline-flex max-sm:items-center";

export function SheetPresenceAvatars({ peers }: { peers: PresencePeer[] }) {
  const identity = useQuery(authMeOptions());
  const viewer = identity.data
    ? { id: identity.data.id, role: identity.data.role ?? "guest" }
    : null;
  const cards = useQueries({
    queries: peers.map((peer) => ({
      ...personCardOptions(viewer ?? { id: "", role: "member" }, peer.userId),
      enabled: Boolean(viewer),
    })),
  });
  if (peers.length === 0) return null;
  // A name not read yet, or refused, reads as a person, never as an id.
  const names = cards.map(
    (card) => card.data?.data.display_name ?? "Someone on this sheet",
  );
  const rest = names.slice(SHOWN);
  return (
    <div
      role="group"
      aria-label="On this sheet now"
      className="flex items-center gap-1.5"
    >
      {peers.slice(0, SHOWN).map((peer, index) => (
        <Tooltip key={peer.userId}>
          <TooltipTrigger
            render={
              <button
                type="button"
                aria-label={names[index]}
                className={trigger}
              />
            }
          >
            {/* The page's own colour between the avatars, then theirs. */}
            <span
              className="inline-flex rounded-full"
              style={{
                boxShadow: `0 0 0 2px var(--background), 0 0 0 4px ${presenceColor(peer.userId)}`,
              }}
            >
              <PersonAvatar
                name={names[index]}
                avatarUrl={cards[index].data?.data.avatar_url ?? null}
                size="sm"
              />
            </span>
          </TooltipTrigger>
          <TooltipContent>{names[index]}</TooltipContent>
        </Tooltip>
      ))}
      {rest.length > 0 ? (
        <Tooltip>
          <TooltipTrigger
            render={
              <button
                type="button"
                aria-label={`${rest.length} more: ${rest.join(", ")}`}
                className={trigger}
              />
            }
          >
            <span
              aria-hidden="true"
              className="bg-muted text-muted-foreground ring-background relative flex size-6 items-center justify-center rounded-full text-xs font-medium tabular-nums ring-2"
            >
              +{rest.length}
            </span>
          </TooltipTrigger>
          <TooltipContent>{rest.join(", ")}</TooltipContent>
        </Tooltip>
      ) : null}
    </div>
  );
}
